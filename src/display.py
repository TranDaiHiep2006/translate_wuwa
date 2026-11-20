"""Per-monitor DPI and hot-plug support (item F of P3).

When the game is moved to another monitor, or the resolution of the current
monitor changes, the capture backend has to be recreated: ``dxcam`` binds its
DXGI output to one device at creation and two Desktop Duplication sessions
cannot run at the same time, so the backend cannot simply be "re-pointed".

This module therefore implements a **restart** strategy:

* :class:`DisplayWatcher` polls the size of the captured area on every frame
  (a cheap size check, no DPI query in the hot path);
* when the size changes, the watcher calls :meth:`DisplayWatcher.restart_capture`,
  which closes the old backend and creates a new one;
* the overlay is resized and the scaling factor is recomputed, so the
  translations land exactly on the text again.

The DPI of the monitor is read with the Win32 API
(``GetDpiForMonitor``). On the other platforms a default of 96 DPI is used.

Nothing here is hardcoded for a specific resolution: the size is always read
from the capture backend at runtime.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .capture import CaptureBackend, create_backend
from .config import Config

logger = logging.getLogger(__name__)

DEFAULT_DPI = 96

# The Windows API constants used below.
_MDT_EFFECTIVE_DPI = 0
_MONITORINFOF_PRIMARY = 0x00000001


@dataclass
class DisplayState:
    """The state of the display the tool is capturing.

    ``width``/``height`` are the size of the captured area, ``dpi`` the
    effective DPI of the monitor (96 on a 100% display) and ``left``/``top``
    the position of the monitor in the virtual desktop.
    """

    index: int = 0
    width: int = 1920
    height: int = 1080
    dpi: int = DEFAULT_DPI
    left: int = 0
    top: int = 0

    @property
    def size(self) -> Tuple[int, int]:
        """The size of the captured area."""
        return (int(self.width), int(self.height))

    @property
    def scale(self) -> float:
        """The scaling factor relative to the 1080p reference height."""
        if int(self.height) <= 0:
            return 1.0
        return int(self.height) / 1080.0

    def describe(self) -> str:
        """A one line description of the display."""
        return (
            f"monitor {self.index}: {self.width}x{self.height} @ {self.dpi} dpi "
            f"(scale {self.scale:.3f})"
        )


# --------------------------------------------------------------------------
# Win32 helpers
# --------------------------------------------------------------------------


def _enum_monitors() -> List[Tuple[int, int, int, int, int]]:
    """Return the bounds and the DPI of every monitor.

    The list is ``(left, top, width, height, dpi)`` and it is ordered like
    the enumeration of the Win32 API, so the index of a monitor is the same
    as the index of the capture backend.
    """
    if sys.platform != "win32":
        return []

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        results: List[Tuple[int, int, int, int, int]] = []

        def _callback(hmonitor, _hdc, _lprc, _lparam):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            try:
                user32.GetMonitorInfoW(wintypes.HMONITOR(hmonitor), ctypes.byref(info))
            except Exception:  # pragma: no cover - defensive
                return True
            rect = info.rcMonitor
            dpi = DEFAULT_DPI
            try:
                dpi_x = ctypes.c_uint(0)
                dpi_y = ctypes.c_uint(0)
                # MDT_EFFECTIVE_DPI
                if shcore.GetDpiForMonitor(
                    wintypes.HMONITOR(hmonitor),
                    _MDT_EFFECTIVE_DPI,
                    ctypes.byref(dpi_x),
                    ctypes.byref(dpi_y),
                ) == 0:
                    dpi = int(dpi_x.value) or DEFAULT_DPI
            except Exception:  # pragma: no cover - defensive
                dpi = DEFAULT_DPI
            results.append(
                (
                    int(rect.left),
                    int(rect.top),
                    int(rect.right - rect.left),
                    int(rect.bottom - rect.top),
                    int(dpi),
                )
            )
            return True

        monitor_enum_proc = ctypes.WINFUNCTYPE(
            ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
        )
        proc = monitor_enum_proc(_callback)
        user32.EnumDisplayMonitors(None, None, proc, 0)
        return results
    except Exception:  # pragma: no cover - defensive
        return []


def list_displays() -> List[DisplayState]:
    """Return the state of every monitor of the virtual desktop."""
    displays: List[DisplayState] = []
    for index, (left, top, width, height, dpi) in enumerate(_enum_monitors()):
        displays.append(
            DisplayState(
                index=index,
                width=width,
                height=height,
                dpi=dpi,
                left=left,
                top=top,
            )
        )
    return displays


def read_dpi(monitor_index: int = 0) -> int:
    """Return the effective DPI of a monitor (96 when it cannot be read)."""
    displays = list_displays()
    if not displays:
        return DEFAULT_DPI
    if monitor_index < 0 or monitor_index >= len(displays):
        return DEFAULT_DPI
    return int(displays[monitor_index].dpi)


# --------------------------------------------------------------------------
# The watcher
# --------------------------------------------------------------------------


class DisplayWatcher:
    """Detects a change of the captured area and restarts the capture.

    The watcher is polled once per frame with :meth:`observe`. The call is
    cheap: it only compares the size of the last frame with the size of the
    previous observation. The DPI is only queried when the size changed (or
    when :meth:`describe` is called).
    """

    def __init__(
        self,
        config: Config,
        backend: Optional[CaptureBackend] = None,
        backend_factory: Optional[Callable[[], CaptureBackend]] = None,
        monitor_index: Optional[int] = None,
    ) -> None:
        self.config = config
        self.backend = backend
        self.monitor_index = (
            int(monitor_index)
            if monitor_index is not None
            else int(config.capture.monitor)
        )
        self._backend_factory = backend_factory or (
            lambda: create_backend(config.capture.backend, self.monitor_index)
        )
        self.state: Optional[DisplayState] = None
        # The number of times a change of the captured area was detected.
        self.detections = 0
        # The number of times the capture backend was recreated.
        self.restarts = 0
        self._callbacks: List[Callable[[DisplayState], None]] = []

    # -- observation --------------------------------------------------------
    def observe(self, size: Optional[Tuple[int, int]] = None) -> bool:
        """Poll the captured area and return True when it changed.

        The first call is the baseline and always returns False. The size can
        be given (that is what the worker does, it already knows the size of
        the frame it just captured); when it is not given, the size is read
        from the capture backend.
        """
        if size is None:
            size = self._read_size()

        if size is None:
            return False

        if self.state is None:
            # The baseline: the first observation is not a change.
            self.state = DisplayState(
                index=self.monitor_index,
                width=int(size[0]),
                height=int(size[1]),
                dpi=read_dpi(self.monitor_index),
            )
            return False

        if (int(size[0]), int(size[1])) == self.state.size:
            return False

        # The captured area changed: the DPI is read again (the monitor may
        # have been changed too) and the capture is restarted.
        self.detections += 1
        self.state = DisplayState(
            index=self.monitor_index,
            width=int(size[0]),
            height=int(size[1]),
            dpi=read_dpi(self.monitor_index),
        )
        logger.info(
            "the captured area changed to %sx%s: restarting the capture",
            self.state.width,
            self.state.height,
        )
        self.restart_capture()
        for callback in list(self._callbacks):
            try:
                callback(self.state)
            except Exception:  # pragma: no cover - defensive
                logger.exception("the display change callback failed")
        return True

    def _read_size(self) -> Optional[Tuple[int, int]]:
        """Return the size of the captured area, or None when it is unknown."""
        if self.backend is None:
            return None
        try:
            frame = self.backend.grab()
        except Exception:  # pragma: no cover - depends on the machine
            logger.exception("could not read the size of the captured area")
            return None
        return (int(frame.width), int(frame.height))

    # -- callbacks ----------------------------------------------------------
    def on_changed(self, callback: Callable[[DisplayState], None]) -> Callable[[DisplayState], None]:
        """Register a callback that is called when the display changes.

        The callback receives the new :class:`DisplayState`. The number of
        restarts is counted by :attr:`restarts` (the watcher restarts the
        capture itself, before the callbacks are called).
        """
        self._callbacks.append(callback)
        return callback

    # -- capture restart ----------------------------------------------------
    def restart_capture(self) -> Optional[CaptureBackend]:
        """Close the old capture backend and create a new one.

        The old backend is closed **before** the new one is created: DXGI
        Desktop Duplication does not allow two capture sessions on the same
        output at the same time, so creating the new one first would fail.
        """
        old = self.backend
        if old is not None:
            try:
                old.close()
            except Exception:  # pragma: no cover - defensive
                logger.exception("could not close the old capture backend")
        self.backend = None

        try:
            new_backend = self._backend_factory()
        except Exception:
            logger.exception("could not create the new capture backend")
            self.backend = old
            return None

        self.backend = new_backend
        self.restarts += 1
        logger.info("capture backend restarted: %s", getattr(new_backend, "name", "?"))
        return new_backend

    # -- queries ------------------------------------------------------------
    def scale(self) -> float:
        """Return the scaling factor of the current display (height / 1080)."""
        if self.state is None:
            return 1.0
        return self.state.scale

    def describe(self) -> str:
        """Return a one line description of the watcher.

        The description holds the size of the captured area, the DPI, the
        number of detected changes and the number of capture restarts.
        """
        if self.state is None:
            size = "unknown"
            dpi = DEFAULT_DPI
            scale = 1.0
        else:
            size = f"{self.state.width}x{self.state.height}"
            dpi = self.state.dpi
            scale = self.state.scale
        return (
            f"monitor {self.monitor_index}: {size} @ {dpi} dpi "
            f"(scale {scale:.3f}) - detections {self.detections}, "
            f"restarts {self.restarts}"
        )
