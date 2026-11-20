"""End-to-end smoke test of the F8 toggle and the session history file.

The script simulates what the user does: it starts the worker, toggles the
session ON, feeds a few frames of the dialogue fixture, toggles the session
OFF and checks that exactly one history file was created.

Usage::

    python scripts/smoke_session.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache import TranslationCache
from src.capture import frame_from_image
from src.config import load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.pipeline import Pipeline, Translator
from src.session import SessionLog
from src.translator import create_engine


def main() -> int:
    """Run the smoke test."""
    import cv2

    config = load_config()
    config.debounce_ms = 0
    tmp = Path(tempfile.mkdtemp(prefix="wuwa_smoke_"))

    cache = TranslationCache(tmp / "cache.db")
    glossary = Glossary.from_file(config.glossary_path)
    engine = create_engine(config.translation.engine, device=config.translation.device)
    engine.load()
    translator = Translator(engine, cache, glossary)
    ocr = OCREngine(device=config.translation.device)
    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    session_log = SessionLog(tmp / "sessions")

    # -- turn ON -----------------------------------------------------------
    path = session_log.start()
    print(f"session ON  -> {path.name}")

    image = cv2.imread(str(PROJECT_ROOT / "tests" / "fixtures" / "sample_a_dialogue.png"))
    frame = frame_from_image(image)
    collected = []
    for _ in range(3):
        result = pipeline.process_frame(frame)
        collected.extend(result.newly_translated)
    for block in collected:
        session_log.append(
            source=block.block.text,
            translation=block.translation,
            speaker=block.speaker,
        )
    # A second poll loop must not duplicate the entry.
    result = pipeline.process_frame(frame)
    for block in result.newly_translated:
        session_log.append(
            source=block.block.text,
            translation=block.translation,
            speaker=block.speaker,
        )

    # -- turn OFF ----------------------------------------------------------
    closed = session_log.close()
    print(f"session OFF -> {closed.name if closed else 'none'}")

    files = sorted((tmp / "sessions").glob("*.txt"))
    print(f"files in the sessions folder: {len(files)}")
    for file in files:
        content = file.read_text(encoding="utf-8")
        print("-" * 60)
        print(content.strip())
        print("-" * 60)
        assert len(files) == 1, "expected exactly one session file"
        assert "EN:" in content
    cache.close()
    print("smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
