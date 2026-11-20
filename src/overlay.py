"""Overlay window: a transparent, click-through, always-on-top window.

The overlay is drawn with PyQt6 and made click-through with pywin32
(``WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST``). It never takes the
focus and never blocks the game input.

The Vietnamese text is wrapped inside the width of the original bounding box
and the box grows vertically when the translation needs more room, so no text
is ever clipped. The background is fully opaque by default, so the original
English text is completely hidden.

All geometry is derived from the real screen size reported by the capture
backend, so nothing is hardcoded for a specific resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from .config import OverlayConfig
from .wrapping import WrappedText, fit_text, split_display_text


@dataclass
class OverlayItem:
    """One translated block to draw."""

    key: str
    bbox: Tuple[int, int, int, int]
    text: str
    speaker: Optional[str] = None

    @property
    def display_text(self) -> str:
        if self.speaker:
            return f"{self.speaker}: {self.text}"
        return self.text

    def rect(self) -> QRect:
        return QRect(
            self.bbox[0],
            self.bbox[1],
            self.bbox[2] - self.bbox[0],
            self.bbox[3] - self.bbox[1],
        )


@dataclass
class OverlayState:
    """Everything the overlay needs to paint itself."""

    items: List[OverlayItem] = field(default_factory=list)
    screen_width: int = 1920
    screen_height: int = 1080
    active: bool = False


class OverlayBridge(QObject):
    """Thread safe bridge between the worker thread and the UI thread."""

    state_changed = pyqtSignal(object)

    def update(self, state: OverlayState) -> None:
        """Emit a new overlay state (safe to call from any thread)."""
        self.state_changed.emit(state)

    def close(self) -> None:
        """Ask the overlay window to close."""
        self.state_changed.emit(None)


def paint_overlay(
    painter: QPainter,
    state: OverlayState,
    config: OverlayConfig,
) -> None:
    """Draw every translation block and the ON/OFF status.

    The very same function is used by the live overlay window and by
    ``scripts/render_overlay_demo.py``, so the demo image is a true proof of
    what the tool draws.
    """
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    height = state.screen_height
    font_size = int(round(config.font_size * (height / 1080.0)))
    font = QFont(config.font_family)
    font.setPixelSize(max(8, font_size))
    painter.setFont(font)
    metrics = QFontMetrics(font)

    text_color = QColor(config.text_color)
    speaker_color = QColor(config.speaker_color)
    bg_color = QColor(config.background_color)
    bg_color.setAlpha(int(config.background_alpha))
    padding = max(2, int(round(config.padding * height / 1080.0)))
    line_height = metrics.lineSpacing()

    for item in state.items:
        rect = item.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            continue

        speaker, body = split_display_text(item.speaker, item.text)
        # The text is wrapped inside the width of the original box.
        wrapped: WrappedText = fit_text(
            body,
            lambda text: metrics.horizontalAdvance(text),
            rect.width(),
            rect.height(),
            font_size,
            line_height,
            max_growth=config.max_height_growth,
        )
        if wrapped.font_size != font_size:
            font = QFont(config.font_family)
            font.setPixelSize(max(8, wrapped.font_size))
            painter.setFont(font)
            metrics = QFontMetrics(font)
            line_height = metrics.lineSpacing()

        # The background covers the original text completely.
        bg_rect = QRect(
            rect.x() - padding,
            rect.y() - padding,
            rect.width() + 2 * padding,
            max(rect.height(), wrapped.box_height) + 2 * padding,
        )
        painter.fillRect(bg_rect, bg_color)

        y = bg_rect.y() + padding
        for index, line in enumerate(wrapped.lines):
            if index == 0 and speaker:
                painter.setPen(QPen(speaker_color))
                painter.drawText(
                    QRect(bg_rect.x() + padding, y, bg_rect.width(), line_height),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    f"{speaker}: {line}",
                )
                painter.setPen(QPen(text_color))
            else:
                painter.drawText(
                    QRect(bg_rect.x() + padding, y, bg_rect.width(), line_height),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    line,
                )
            y += line_height

    if config.show_status:
        status_font = QFont(config.font_family)
        status_font.setPixelSize(
            max(8, int(round(config.status_font_size * height / 1080.0)))
        )
        painter.setFont(status_font)
        painter.setPen(
            QPen(QColor("#00FF88") if state.active else QColor("#888888"))
        )
        margin = max(4, int(round(config.margin * height / 1080.0)))
        painter.drawText(
            QRect(margin, margin, 400, 40),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            "TRANSLATING" if state.active else "OFF",
        )


class OverlayWidget(QWidget):
    """The transparent window that draws the translations."""

    def __init__(self, config: OverlayConfig) -> None:
        super().__init__()
        self.config = config
        self._state = OverlayState()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("WuWa Translator Overlay")
        self._apply_click_through()

    # -- Windows specific --------------------------------------------------
    def _apply_click_through(self) -> None:
        """Make the window click-through and always on top (Windows only)."""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000

            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)

            # Top-most, no activation.
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(
                wintypes.HWND(hwnd),
                wintypes.HWND(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:  # pragma: no cover - non-Windows / defensive
            pass

    # -- state -------------------------------------------------------------
    def set_state(self, state: OverlayState) -> None:
        """Apply a new state and repaint (called in the UI thread)."""
        self._state = state
        self.setGeometry(0, 0, state.screen_width, state.screen_height)
        self.update()

    def clear(self) -> None:
        """Remove every overlay item."""
        self._state.items = []
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Draw every translation block and the ON/OFF status."""
        painter = QPainter(self)
        paint_overlay(painter, self._state, self.config)
        painter.end()


def create_overlay(config: OverlayConfig) -> OverlayWidget:
    """Create the overlay widget (must be called in the UI thread)."""
    widget = OverlayWidget(config)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    widget.show()
    widget.setWindowOpacity(1.0)
    return widget
