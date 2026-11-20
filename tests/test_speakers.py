"""Tests for the speaker detection: the UI-label blacklist and the roster."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.grouping import build_blocks, detect_speaker, is_speaker_line
from src.ocr import OCRLine
from src.speakers import SpeakerVocabulary, looks_like_name, normalize_label

LINE_HEIGHT = 35


def line(text: str, top: int, bottom: int, left: int = 100, right: int = 500) -> OCRLine:
    """Build a fake OCR line with an explicit bounding box."""
    return OCRLine(text=text, bbox=(left, top, right, bottom), confidence=0.95)


def vocabulary() -> SpeakerVocabulary:
    """The vocabulary built from the shipped YAML files."""
    return SpeakerVocabulary.from_files(
        PROJECT_ROOT / "config" / "ui_labels.yaml",
        PROJECT_ROOT / "config" / "roster.yaml",
    )


def test_the_ui_labels_are_never_a_speaker() -> None:
    """Quest, Skill, Inventory and Settings are labels, not names."""
    vocab = vocabulary()
    for label in ("Quest", "Skill", "Inventory", "Settings"):
        assert vocab.is_ui_label(label), label
        assert not looks_like_name(label, vocab), label


def test_the_ui_label_matching_ignores_the_case_and_the_colon() -> None:
    """The blacklist ignores the case, the spaces and a trailing colon."""
    vocab = vocabulary()
    for text in ("quest", "QUEST", " Quest ", "Quest:", "Skill:", "  settings  "):
        assert vocab.is_ui_label(text), text


def test_the_roster_accepts_the_known_characters() -> None:
    """Jiyan and Rover are in the roster."""
    vocab = vocabulary()
    for name in ("Jiyan", "Rover", "Changli", "Shorekeeper"):
        assert vocab.in_roster(name), name
        assert looks_like_name(name, vocab), name


def test_a_bare_label_is_not_a_speaker() -> None:
    """A label without a colon is not a speaker."""
    vocab = vocabulary()
    assert not looks_like_name("Quest", vocab)
    assert not looks_like_name("Inventory", vocab)


def test_an_unknown_name_with_a_colon_is_a_speaker() -> None:
    """An unknown NPC that the game writes as "Name:" is a speaker."""
    vocab = vocabulary()
    assert looks_like_name("Florence:", vocab)
    assert looks_like_name("Unknown Wanderer:", vocab)


def test_an_unknown_bare_name_is_not_a_speaker() -> None:
    """A bare capitalised word that is not in the roster is not a speaker."""
    vocab = vocabulary()
    assert not looks_like_name("Florence", vocab)
    assert not looks_like_name("Total Power", vocab)


def test_the_quest_label_is_not_detected_as_a_speaker() -> None:
    """The speaker detector does not return "Quest"."""
    vocab = vocabulary()
    lines = [
        line("Quest", 300, 300 + LINE_HEIGHT),
        line("Complete the quest to reach the Storm City", 400, 400 + LINE_HEIGHT),
    ]
    blocks = build_blocks(lines, vocabulary=vocab)
    assert all(b.speaker is None for b in blocks)


def test_the_skill_label_is_not_detected_as_a_speaker() -> None:
    """The speaker detector does not return "Skill"."""
    vocab = vocabulary()
    lines = [
        line("Skill", 300, 300 + LINE_HEIGHT),
        line("Your attack power increases by 15 percent.", 400, 400 + LINE_HEIGHT),
    ]
    blocks = build_blocks(lines, vocabulary=vocab)
    assert all(b.speaker is None for b in blocks)


def test_jiyan_is_still_a_speaker() -> None:
    """Jiyan is still detected as the speaker of the dialogue."""
    vocab = vocabulary()
    lines = [
        line("Jiyan", 300, 300 + LINE_HEIGHT),
        line("The Tacet Field is spreading across the plains.", 400, 400 + LINE_HEIGHT),
    ]
    blocks = build_blocks(lines, vocabulary=vocab)
    speakers = [b.speaker for b in blocks]
    assert "Jiyan" in speakers
    block = next(b for b in blocks if b.speaker == "Jiyan")
    assert "Jiyan" not in block.text


def test_rover_is_still_a_speaker() -> None:
    """Rover is still detected as the speaker of the dialogue."""
    vocab = vocabulary()
    lines = [
        line("Rover", 300, 300 + LINE_HEIGHT),
        line("The Tacet Field is spreading across the plains.", 400, 400 + LINE_HEIGHT),
    ]
    blocks = build_blocks(lines, vocabulary=vocab)
    assert "Rover" in [b.speaker for b in blocks]


def test_the_inline_name_with_a_colon_still_works() -> None:
    """The "Name: dialogue" form inside a line still works."""
    vocab = vocabulary()
    lines = [line("Jiyan: The Tacet Field is spreading.", 400, 400 + LINE_HEIGHT)]
    blocks = build_blocks(lines, vocabulary=vocab)
    assert blocks[0].speaker == "Jiyan"
    assert blocks[0].text == "The Tacet Field is spreading."


def test_the_inline_label_with_a_colon_is_not_a_speaker() -> None:
    """"Quest: Complete the quest..." is a label, not a speaker."""
    vocab = vocabulary()
    lines = [line("Quest: Complete the quest to reach the Storm City", 400, 440)]
    blocks = build_blocks(lines, vocabulary=vocab)
    assert blocks[0].speaker is None


def test_is_speaker_line_respects_the_blacklist() -> None:
    """The blacklist is applied by ``is_speaker_line`` too."""
    vocab = vocabulary()
    assert not is_speaker_line(line("Quest", 0, 20), vocabulary=vocab)
    assert not is_speaker_line(line("Settings", 0, 20), vocabulary=vocab)
    assert is_speaker_line(line("Jiyan", 0, 20), vocabulary=vocab)


def test_the_label_normalisation() -> None:
    """The normalisation removes the spaces and the trailing colon."""
    assert normalize_label("  Quest:  ") == "quest"
    assert normalize_label("Settings") == "settings"
    assert normalize_label("") == ""
