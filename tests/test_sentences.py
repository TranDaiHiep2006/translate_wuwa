"""Tests for the sentence splitting and for the number protection."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.sentences import (
    digits_of,
    join_sentences,
    protect_numbers,
    restore_numbers,
    split_sentences,
)


def texts_of(text: str):
    """The list of the sentences of ``text``."""
    return [s.text.strip() for s in split_sentences(text)]


def test_a_multi_sentence_block_is_split() -> None:
    """A block with several sentences is split into the sentences."""
    sentences = texts_of(
        "The Echo has been recorded. Replay it to learn more about the Tacet Discord."
    )
    assert len(sentences) == 2
    assert sentences[0] == "The Echo has been recorded."
    assert sentences[1].startswith("Replay it")


def test_the_label_value_is_not_split_at_the_colon() -> None:
    """"Reward: 12000" stays a single unit."""
    sentences = texts_of("Reward: 12000")
    assert sentences == ["Reward: 12000"]


def test_a_number_is_never_split() -> None:
    """A decimal is not a sentence boundary."""
    sentences = texts_of("The value is 3.5 units.")
    assert sentences == ["The value is 3.5 units."]


def test_a_thousands_separator_is_not_split() -> None:
    """A number with a thousands separator stays in one piece."""
    sentences = texts_of("You receive 12,000 gold.")
    assert sentences == ["You receive 12,000 gold."]


def test_an_abbreviation_is_not_split() -> None:
    """A known abbreviation does not end a sentence."""
    sentences = texts_of("Bring it to Dr. Anby for the upgrade.")
    assert sentences == ["Bring it to Dr. Anby for the upgrade."]


def test_the_separators_are_kept() -> None:
    """The original separator is kept when the sentences are rejoined."""
    text = "First one. Second one! Third one?"
    joined = join_sentences(split_sentences(text))
    assert joined == text


def test_the_numbers_are_replaced_by_a_placeholder() -> None:
    """Every number becomes a token the model does not touch."""
    protected = protect_numbers("Reward: 12000")
    assert "12000" not in protected.text
    assert "XNUM0X" in protected.text
    assert protected.restore("Phần thưởng: XNUM0X") == "Phần thưởng: 12000"


def test_a_percentage_is_protected() -> None:
    """A percentage is protected as well."""
    protected = protect_numbers("It increases by 15%")
    assert "15" not in protected.text
    assert protected.restore("Tăng 15%") == "Tăng 15%"


def test_a_decimal_is_protected() -> None:
    """A decimal is protected as well."""
    protected = protect_numbers("The value is 3.5 units.")
    assert "3.5" not in protected.text
    assert protected.restore("Giá trị là 3.5 đơn vị.") == "Giá trị là 3.5 đơn vị."


def test_several_numbers_get_several_placeholders() -> None:
    """Every number of a sentence gets its own placeholder."""
    protected = protect_numbers("You gain 12000 gold and 250 items.")
    assert protected.numbers == ["12000", "250"]
    restored = protected.restore("Bạn có XNUM0X vàng và XNUM1X vật phẩm.")
    assert restored == "Bạn có 12000 vàng và 250 vật phẩm."


def test_the_digit_safety_net_repairs_a_mangled_number() -> None:
    """When the model loses a digit, the original digits are put back."""
    original = "Reward: 12000"
    protected = protect_numbers(original)
    # The model dropped the "1" and the "0".
    mangled = "Phần thưởng: 2000"
    fixed, corrected = restore_numbers(mangled, original, protected)
    assert corrected is True
    assert "12000" in fixed


def test_the_digit_safety_net_does_not_touch_a_correct_number() -> None:
    """A correct translation is not modified."""
    original = "Reward: 12000"
    protected = protect_numbers(original)
    fixed, corrected = restore_numbers("Phần thưởng: 12000", original, protected)
    assert corrected is False
    assert fixed == "Phần thưởng: 12000"


def test_the_digits_are_read_in_order() -> None:
    """The digits of a text are returned in the order they appear."""
    assert digits_of("Reward: 12000 for 3.5%") == ["12000", "3", "5"]
