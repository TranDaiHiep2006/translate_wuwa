"""Tests for the grouping stage and the speaker name detection."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.grouping import build_blocks, group_lines, is_speaker_line
from src.ocr import OCRLine

# A typical dialogue line: 35px tall, the next one 10px below it.
LINE_HEIGHT = 35


def line(text: str, top: int, bottom: int, left: int = 100, right: int = 500) -> OCRLine:
    """Build a fake OCR line with an explicit bounding box."""
    return OCRLine(text=text, bbox=(left, top, right, bottom), confidence=0.95)


def dialogue_lines():
    """Three dialogue lines plus a speaker name above them."""
    return [
        line("Jiyan", 700, 700 + LINE_HEIGHT),
        line("The Tacet Field is spreading across the plains.", 800, 800 + LINE_HEIGHT),
        line("Resonators must reach the Storm City.", 845, 845 + LINE_HEIGHT),
        line("You obtained a new Waveplate for your Rover.", 890, 890 + LINE_HEIGHT),
    ]


def test_close_lines_are_grouped_into_one_block() -> None:
    """Lines with a small vertical gap end up in the same paragraph."""
    lines = [
        line("First sentence of the dialogue.", 800, 830),
        line("Second sentence of the dialogue.", 840, 870),
        line("Third sentence of the dialogue.", 880, 910),
    ]
    groups = group_lines(lines, gap_px=28)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_far_lines_are_separate_blocks() -> None:
    """Lines with a large vertical gap become separate blocks."""
    lines = [
        line("Quest", 300, 330),
        line("Complete the quest to reach the Storm City", 500, 530),
    ]
    groups = group_lines(lines, gap_px=28)
    assert len(groups) == 2


def test_grouping_scales_with_the_resolution() -> None:
    """The gap threshold is scaled with the screen, so 2560x1600 still groups."""
    lines = [
        line("First sentence of the dialogue.", 1180, 1180 + LINE_HEIGHT),
        line("Second sentence of the dialogue.", 1230, 1230 + LINE_HEIGHT),
    ]
    groups_1080 = group_lines(lines, gap_px=28, scale=1.0)
    groups_1600 = group_lines(lines, gap_px=28, scale=1600 / 1080.0)
    assert len(groups_1080) == 1
    assert len(groups_1600) == 1


def test_speaker_name_above_the_dialogue_is_detected() -> None:
    """A short capitalised line above the dialogue is the speaker name."""
    blocks = build_blocks(dialogue_lines())
    dialogue_blocks = [b for b in blocks if b.speaker]
    assert len(dialogue_blocks) == 1
    block = dialogue_blocks[0]
    assert block.speaker == "Jiyan"
    assert "Jiyan" not in block.text
    assert block.text.startswith("The Tacet Field")
    assert len(block.lines) == 3


def test_speaker_name_with_a_colon_is_detected() -> None:
    """The part before the colon in the same line is the speaker name."""
    lines = [line("Jiyan: The Tacet Field is spreading.", 800, 840)]
    blocks = build_blocks(lines)
    assert blocks[0].speaker == "Jiyan"
    assert blocks[0].text == "The Tacet Field is spreading."


def test_no_speaker_name_is_invented() -> None:
    """Without a name the block has no speaker and the text is unchanged."""
    lines = [line("The Tacet Field is spreading across the northern plains.", 800, 840)]
    blocks = build_blocks(lines)
    assert blocks[0].speaker is None
    assert blocks[0].text == "The Tacet Field is spreading across the northern plains."


def test_a_name_too_far_above_is_not_a_speaker() -> None:
    """A name that is far above the dialogue is not treated as a speaker."""
    lines = [
        line("Jiyan", 300, 335),
        line("The Tacet Field is spreading across the plains.", 800, 835),
    ]
    blocks = build_blocks(lines, speaker_gap_px=120)
    assert all(b.speaker is None for b in blocks)


def test_is_speaker_line_rules() -> None:
    """Only short capitalised lines without a full stop can be a name."""
    assert is_speaker_line(line("Jiyan", 0, 20))
    assert is_speaker_line(line("Calcharo", 0, 20))
    assert not is_speaker_line(line("This is a full sentence.", 0, 20))
    assert not is_speaker_line(line("one two three four", 0, 20))


def test_block_bbox_covers_every_line() -> None:
    """The merged bbox of a block spans all its lines."""
    lines = [
        line("First line of the block.", 800, 830, left=100, right=400),
        line("Second line of the block.", 840, 870, left=120, right=460),
    ]
    blocks = build_blocks(lines)
    assert len(blocks) == 1
    x1, y1, x2, y2 = blocks[0].bbox
    assert (x1, y1, x2, y2) == (100, 800, 460, 870)
