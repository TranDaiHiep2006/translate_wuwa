"""Tests for the session history file."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.session import SessionLog

FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?\.txt$")


def test_start_and_close_create_exactly_one_file(tmp_path: Path) -> None:
    """Turning ON then OFF creates exactly one history file."""
    log = SessionLog(tmp_path)
    path = log.start()
    assert path.exists()
    log.append(source="Hello", translation="Xin chao", speaker="Jiyan")
    log.close()
    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1


def test_the_file_name_uses_the_session_start_time(tmp_path: Path) -> None:
    """The file name follows the YYYY-MM-DD_HH-MM-SS.txt format."""
    from datetime import datetime

    log = SessionLog(tmp_path)
    moment = datetime(2026, 3, 7, 14, 5, 9)
    path = log.start(now=moment)
    assert path.name == "2026-03-07_14-05-09.txt"
    assert FILENAME_RE.match(path.name)
    log.close()


def test_the_entry_format_with_a_speaker(tmp_path: Path) -> None:
    """With a speaker the entry is ``[time] Name: translation`` + the EN line."""
    log = SessionLog(tmp_path)
    path = log.start()
    log.append(
        source="The Tacet Field is spreading.",
        translation="Truong Tacet dang lan rong.",
        speaker="Jiyan",
    )
    log.close()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] Jiyan: Truong Tacet dang lan rong\.$", lines[0])
    assert lines[1] == "  EN: The Tacet Field is spreading."


def test_the_entry_format_without_a_speaker(tmp_path: Path) -> None:
    """Without a speaker the entry is just ``[time] translation`` + the EN line."""
    log = SessionLog(tmp_path)
    path = log.start()
    log.append(source="Hello there", translation="Xin chao")
    log.close()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] Xin chao$", lines[0])
    assert lines[1] == "  EN: Hello there"


def test_a_block_is_appended_exactly_once(tmp_path: Path) -> None:
    """The same block is never written twice, even over many poll loops."""
    log = SessionLog(tmp_path)
    path = log.start()
    for _ in range(10):
        log.append(source="Hello", translation="Xin chao", speaker="Jiyan")
    log.close()
    content = path.read_text(encoding="utf-8")
    assert content.count("Xin chao") == 1
    assert len(log.read_entries(path)) == 1


def test_the_entries_are_separated_by_a_blank_line(tmp_path: Path) -> None:
    """Consecutive entries are separated by exactly one blank line."""
    log = SessionLog(tmp_path)
    path = log.start()
    log.append(source="First", translation="Mot")
    log.append(source="Second", translation="Hai")
    log.close()
    content = path.read_text(encoding="utf-8")
    assert "\n\n" in content
    assert len(log.read_entries(path)) == 2


def test_the_history_does_not_label_a_ui_label_as_a_speaker(tmp_path: Path) -> None:
    """The session history never shows "Quest:" or "Skill:" as a speaker.

    This is the P1 bug: the UI labels were written in the history file as if
    they were the name of the character.
    """
    from src.capture import frame_from_image
    from src.config import load_config
    from src.ocr import OCREngine
    from src.pipeline import Pipeline

    config = load_config()
    config.debounce_ms = 0
    import cv2

    quest_image = cv2.imread(str(PROJECT_ROOT / "tests" / "fixtures" / "sample_b_quest.png"))
    pipeline = Pipeline(config, ocr_engine=OCREngine())
    result = pipeline.process_frame(frame_from_image(quest_image))

    log = SessionLog(tmp_path)
    path = log.start()
    for block in result.blocks:
        log.append(
            source=block.block.text,
            translation=block.translation,
            speaker=block.speaker,
        )
    log.close()

    content = path.read_text(encoding="utf-8")
    assert "Quest:" not in content, content
    assert "Skill:" not in content, content
