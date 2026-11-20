"""Create a real session history file in ``data/sessions/`` from the fixtures.

It runs the pipeline on the three sample images, exactly like the tool does
while the game is running, and writes the result in the production session
format. It is used to inspect the output format and to fill the P1 report.

Usage::

    python scripts\make_session_demo.py
"""

from __future__ import annotations

import sys
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
from src.speakers import SpeakerVocabulary
from src.translator import create_engine


def main() -> int:
    """Run the pipeline on the fixtures and write a session file."""
    import cv2

    config = load_config()
    config.debounce_ms = 0

    # A dedicated cache, so the demo always shows the real translations
    # instead of the cache hits of the previous runs.
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
    ocr = OCREngine(device=config.translation.device)
    pipeline = Pipeline(
        config, ocr_engine=ocr, translator=translator, vocabulary=vocabulary
    )

    session_log = SessionLog(config.sessions_dir)
    path = session_log.start()
    print(f"session file: {path}")

    fixtures = [
        "sample_a_dialogue.png",
        "sample_b_quest.png",
        "sample_c_menu.png",
        "sample_f_reward.png",
        "sample_g_ui_menu.png",
    ]
    for name in fixtures:
        image = cv2.imread(str(PROJECT_ROOT / "tests" / "fixtures" / name))
        if image is None:
            continue
        frame = frame_from_image(image)
        result = pipeline.process_frame(frame)
        for block in result.newly_translated:
            session_log.append(
                source=block.block.text,
                translation=block.translation,
                speaker=block.speaker,
            )
            print(f"  [{name}] {block.display_text[:110]}")

    session_log.close()
    cache.close()
    print(f"\n--- {path.name} ---")
    print(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
