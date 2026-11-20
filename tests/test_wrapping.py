"""Tests for the overlay text wrapping and for the opaque background."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.wrapping import fit_text, split_display_text, wrap_text

# A fake measurement: every character is 10 px wide.
def measure(text: str) -> float:
    """A deterministic measurement, so the tests need no font."""
    return len(text) * 10.0


LINE_HEIGHT = 30


def test_a_short_text_stays_on_one_line() -> None:
    """A text that fits is not wrapped."""
    lines = wrap_text("Hello world", measure, 500)
    assert lines == ["Hello world"]


def test_a_long_text_is_wrapped_inside_the_width() -> None:
    """Every line of a wrapped text fits inside the box width."""
    text = "Tacet Field dang lan rong khap cac vung dong bang phia bac Resonator phai dat Storm City"
    width = 300
    lines = wrap_text(text, measure, width)
    assert len(lines) > 1
    for line in lines:
        assert measure(line) <= width, line


def test_no_word_is_clipped() -> None:
    """The words of the text all survive the wrapping."""
    text = "Tacet Field dang lan rong khap cac vung dong bang phia bac"
    lines = wrap_text(text, measure, 300)
    rejoined = " ".join(lines)
    for word in text.split():
        assert word in rejoined


def test_a_word_longer_than_the_box_is_broken() -> None:
    """A word that is wider than the box is broken, never clipped."""
    lines = wrap_text("Supercalifragilisticexpialidocious", measure, 100)
    assert len(lines) > 1
    for line in lines:
        assert measure(line) <= 100
    assert "".join(lines) == "Supercalifragilisticexpialidocious"


def test_the_box_grows_vertically_when_the_text_needs_more_room() -> None:
    """The box grows instead of the font being shrunk."""
    text = "one two three four five six seven eight nine ten"
    result = fit_text(text, measure, 200, 40, font_size=20, line_height=LINE_HEIGHT)
    assert result.lines
    assert result.box_height > 40
    assert result.font_size == 20
    assert result.font_size_changed is False


def test_the_font_is_only_shrunk_when_the_box_cannot_grow_enough() -> None:
    """The font is reduced only when the vertical growth is not enough."""
    text = "one two three four five six seven eight nine ten"
    result = fit_text(
        text, measure, 200, 40, font_size=20, line_height=LINE_HEIGHT, max_growth=1.2
    )
    assert result.font_size_changed is True
    assert result.font_size < 20


def test_the_wrapped_text_fits_inside_the_bbox_width() -> None:
    """The text of the long dialogue fixture fits inside its bbox width.

    This is the P2 acceptance criterion: a long Vietnamese translation must
    not overflow the original bounding box.
    """
    # The bbox of the long dialogue fixture is about 710 px wide.
    width = 710
    text = (
        "Người giữ cửa đã ban phước cho chuyến đi tiếp theo và nó sẽ bảo vệ "
        "bạn trong chuyến đi tiếp theo vào vùng Cánh đồng Tacet."
    )
    result = fit_text(text, measure, width, 60, font_size=20, line_height=LINE_HEIGHT)
    assert len(result.lines) > 1, "the text should have been wrapped"
    for line in result.lines:
        assert measure(line) <= width
    # Nothing is lost.
    assert "".join(result.lines).replace(" ", "") == text.replace(" ", "")


def test_the_speaker_is_split_from_the_text() -> None:
    """The speaker name is separated from the translation."""
    speaker, body = split_display_text("Jiyan", "Jiyan: Xin chào")
    assert speaker == "Jiyan"
    assert body == "Xin chào"


def test_the_background_is_opaque_by_default() -> None:
    """The overlay background hides the original text completely."""
    config = load_config()
    assert config.overlay.background_alpha == 255
