"""Render the overlay on top of a sample image and save a PNG.

It proves that the overlay is drawn at the right position, over the original
text, with the Vietnamese translation, the text wrapped inside the original
box and an opaque background.

The real pipeline is used (real OCR + real translation) and the very same
painting function as the live overlay, so the image is a true proof.

Usage::

    python scripts\render_overlay_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from src.cache import TranslationCache
from src.capture import frame_from_image
from src.config import load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.overlay import OverlayItem, OverlayState, paint_overlay
from src.pipeline import Pipeline, Translator
from src.speakers import SpeakerVocabulary
from src.translator import create_engine


def main() -> int:
    """Render the overlay over the dialogue fixture."""
    import cv2

    config = load_config()
    config.debounce_ms = 0
    app = QApplication.instance() or QApplication(sys.argv[:1])

    image_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_a_dialogue.png"
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        print("fixture missing - run scripts/make_fixtures.py first")
        return 1
    height, width = bgr.shape[:2]

    # -- run the real pipeline so the demo shows a real translation --------
    cache = TranslationCache(PROJECT_ROOT / "data" / "demo_cache.db")
    glossary = Glossary.from_file(config.glossary_path)
    engine = create_engine(config.translation.engine, device=config.translation.device)
    engine.load()
    vocabulary = SpeakerVocabulary.from_files(
        config.speaker.ui_labels_path, config.speaker.roster_path
    )
    translator = Translator(
        engine,
        cache,
        glossary,
        split_sentences=config.translation.split_sentences,
        vocabulary=vocabulary,
        skip_ui_labels=config.translation.skip_ui_labels,
    )
    pipeline = Pipeline(
        config, ocr_engine=OCREngine(), translator=translator, vocabulary=vocabulary
    )
    result = pipeline.process_frame(frame_from_image(bgr))
    cache.close()

    items = [
        OverlayItem(
            key=block.block.key,
            bbox=block.block.bbox,
            text=block.translation,
            speaker=block.speaker,
        )
        for block in result.blocks
        if block.translation.strip()
    ]
    if not items:
        print("no block was translated - cannot render the demo")
        return 1

    state = OverlayState(
        items=items,
        screen_width=width,
        screen_height=height,
        active=True,
    )

    qimage = QImage(
        bgr.data, width, height, bgr.strides[0], QImage.Format.Format_RGB888
    ).rgbSwapped()

    painter = QPainter(qimage)
    paint_overlay(painter, state, config.overlay)
    painter.end()

    out = PROJECT_ROOT / "data" / "overlay_demo.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    qimage.save(str(out))
    print(f"saved {out}")
    for item in items:
        print(f"  {item.bbox}  {item.display_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
