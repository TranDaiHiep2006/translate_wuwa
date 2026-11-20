"""Tests for the filtering stage (numbers, confidence, short lines)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.filter import filter_lines, is_noise_text
from src.ocr import OCRLine


def line(text: str, conf: float = 0.95, top: int = 0) -> OCRLine:
    """Build a fake OCR line."""
    return OCRLine(
        text=text, bbox=(10, top, 10 + len(text) * 8, top + 20), confidence=conf
    )


def test_number_only_lines_are_dropped() -> None:
    """Damage numbers, timers and pure symbols are filtered out."""
    kept, report = filter_lines(
        [
            line("Inventory"),
            line("1250"),
            line("+8%"),
            line("Lv.30"),
            line("999/999"),
            line("12345"),
            line("Settings"),
        ]
    )
    texts = [ln.text for ln in kept]
    assert "Inventory" in texts
    assert "Settings" in texts
    assert "1250" not in texts
    assert "+8%" not in texts
    assert "Lv.30" not in texts
    assert report.dropped_numbers == 5


def test_low_confidence_lines_are_dropped() -> None:
    """Lines below the confidence threshold are removed."""
    kept, report = filter_lines(
        [line("Good text", conf=0.9), line("Bad text", conf=0.2)], conf_min=0.5
    )
    assert [ln.text for ln in kept] == ["Good text"]
    assert report.dropped_confidence == 1


def test_short_lines_are_dropped() -> None:
    """Lines shorter than the minimum length are removed."""
    kept, report = filter_lines([line("Hello there"), line("a")], min_chars=2)
    assert [ln.text for ln in kept] == ["Hello there"]
    assert report.dropped_short == 1


def test_is_noise_text() -> None:
    """The noise detector recognises pure numbers and symbols."""
    assert is_noise_text("1250")
    assert is_noise_text("+8%")
    assert is_noise_text("  ")
    assert not is_noise_text("Inventory")
    assert not is_noise_text("1250 gold")


def test_filter_report_counts_are_consistent() -> None:
    """The report counts every dropped line exactly once."""
    kept, report = filter_lines(
        [line("Hello"), line("1250"), line("x", conf=0.1), line("ab")]
    )
    assert report.kept == len(kept)
    assert report.dropped == 2
    assert report.dropped_numbers == 1
    assert report.dropped_confidence == 1
