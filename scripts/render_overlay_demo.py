"""Render the overlay on top of a sample image and save a PNG.

It proves that the overlay is drawn at the right position, over the original
text, with the Vietnamese translation.

Usage::

    python scripts\render_overlay_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from src.config import load_config
from src.overlay import OverlayItem, OverlayState


def main() -> int:
    """Render the overlay over the dialogue fixture."""
    import cv2

    config = load_config()
    app = QApplication.instance() or QApplication(sys.argv[:1])

    image_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_a_dialogue.png"
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        print("fixture missing - run scripts/make_fixtures.py first")
        return 1
    height, width = bgr.shape[:2]

    qimage = QImage(
        bgr.data, width, height, bgr.strides[0], QImage.Format.Format_RGB888
    ).rgbSwapped()

    state = OverlayState(
        items=[
            OverlayItem(
                key="demo",
                bbox=(235, 810, 943, 933),
                text=(
                    "Tacet Field dang lan rong khap cac vung dong bang phia bac. "
                    "Resonator phai dat Storm City truoc khi dem xuong. "
                    "Ban co mot Waveplate moi cho Rover cua ban."
                ),
                speaker="Jiyan",
            )
        ],
        screen_width=width,
        screen_height=height,
        active=True,
    )

    painter = QPainter(qimage)
    font = QFont(config.overlay.font_family)
    font.setPixelSize(max(8, int(config.overlay.font_size * height / 1080.0)))
    painter.setFont(font)

    bg = QColor(config.overlay.background_color)
    bg.setAlpha(int(config.overlay.background_alpha))
    padding = int(config.overlay.padding * height / 1080.0)
    align = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    for item in state.items:
        x1, y1, x2, y2 = item.bbox
        rect = QRect(
            x1 - padding,
            y1 - padding,
            x2 - x1 + 2 * padding,
            y2 - y1 + 2 * padding,
        )
        painter.fillRect(rect, bg)
        painter.setPen(QColor(config.overlay.text_color))
        painter.drawText(rect, align, item.display_text)

    margin = int(config.overlay.margin * height / 1080.0)
    status_font = QFont(config.overlay.font_family)
    status_font.setPixelSize(
        max(8, int(config.overlay.status_font_size * height / 1080.0))
    )
    painter.setFont(status_font)
    painter.setPen(QColor("#00FF88"))
    painter.drawText(QRect(margin, margin, 400, 40), align, "TRANSLATING")
    painter.end()

    out = PROJECT_ROOT / "data" / "overlay_demo.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    qimage.save(str(out))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
