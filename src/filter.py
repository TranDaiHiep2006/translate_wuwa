"""Filtering stage: drop OCR lines that are not translatable text.

Removes damage numbers, HP bars, timers, pure symbols and low confidence
results. The number of dropped lines is reported so it can be logged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from .ocr import OCRLine

# A line that only consists of digits, punctuation and symbols is noise
# (e.g. "1,250", "+8%", "---").
_NOISE_RE = re.compile(r"^[\W\d_]+$", re.UNICODE)
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ỹ]")
# Level indicators look like text but carry no translatable word.
_LEVEL_RE = re.compile(r"^(lv\.?|level)\s*\d+$", re.IGNORECASE)


@dataclass
class FilterReport:
    """Statistics about the filtering stage."""

    kept: int = 0
    dropped_numbers: int = 0
    dropped_confidence: int = 0
    dropped_short: int = 0
    dropped_no_alpha: int = 0

    @property
    def dropped(self) -> int:
        return (
            self.dropped_numbers
            + self.dropped_confidence
            + self.dropped_short
            + self.dropped_no_alpha
        )

    def describe(self) -> str:
        return (
            f"kept={self.kept} dropped={self.dropped} "
            f"(numbers={self.dropped_numbers}, conf={self.dropped_confidence}, "
            f"short={self.dropped_short}, no_alpha={self.dropped_no_alpha})"
        )


def is_noise_text(text: str) -> bool:
    """Return True when the text carries no translatable words."""
    stripped = text.strip()
    if not stripped:
        return True
    if _NOISE_RE.match(stripped):
        return True
    if _LEVEL_RE.match(stripped):
        return True
    return not _ALPHA_RE.search(stripped)


def filter_lines(
    lines: List[OCRLine],
    conf_min: float = 0.5,
    min_chars: int = 2,
) -> Tuple[List[OCRLine], FilterReport]:
    """Filter OCR lines by confidence, length and content.

    Returns the surviving lines (in reading order) and a :class:`FilterReport`.
    """
    report = FilterReport()
    kept: List[OCRLine] = []
    for line in lines:
        text = line.text.strip()
        if line.confidence < conf_min:
            report.dropped_confidence += 1
            continue
        if len(text) < min_chars:
            report.dropped_short += 1
            continue
        if is_noise_text(text):
            report.dropped_numbers += 1
            continue
        kept.append(line)
    kept.sort(key=lambda ln: (ln.top, ln.left))
    report.kept = len(kept)
    return kept, report
