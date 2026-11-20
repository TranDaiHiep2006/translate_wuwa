"""Text wrapping for the overlay.

The Vietnamese translation of a game line is often longer than the English
original, so it does not fit inside the original bounding box. The text is
therefore wrapped inside the box width and the box grows vertically until the
wrapped text fits.

The algorithm is pure: it only needs a ``measure`` callable that returns the
width of a string, so it can be tested without a Qt application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

Measure = Callable[[str], float]


@dataclass
class WrappedText:
    """The result of wrapping a text inside a box."""

    lines: List[str]
    width: int
    height: int
    font_size: int
    box_height: int
    font_size_changed: bool = False

    @property
    def text(self) -> str:
        """The wrapped text, joined with newlines."""
        return "\n".join(self.lines)


def wrap_text(text: str, measure: Measure, max_width: int) -> List[str]:
    """Wrap ``text`` so that every line is at most ``max_width`` wide.

    The text is split on the spaces; a word that is longer than the box is
    broken between its characters so that nothing is ever clipped.
    """
    if not text:
        return []
    max_width = max(1, int(max_width))

    lines: List[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if measure(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            # The word alone may still be too wide: break it.
            while measure(word) > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and measure(word[:cut]) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        if current:
            lines.append(current)
    return lines


def fit_text(
    text: str,
    measure: Measure,
    box_width: int,
    box_height: int,
    font_size: int,
    line_height: float,
    max_growth: float = 3.0,
    min_font_size: int = 8,
) -> WrappedText:
    """Wrap ``text`` inside a box and grow the box vertically when needed.

    The font size is only reduced when the wrapped text still does not fit
    after the box grew by ``max_growth`` times its original height.
    """
    box_width = max(1, int(box_width))
    box_height = max(1, int(box_height))

    lines = wrap_text(text, measure, box_width)
    needed = int(round(len(lines) * line_height))
    current_size = int(font_size)
    font_changed = False

    if needed > box_height:
        # Grow the box vertically instead of shrinking the font.
        grown = min(needed, int(round(box_height * max_growth)))
        if needed > grown:
            # Even the grown box is too small: reduce the font size.
            factor = grown / float(needed) if needed else 1.0
            new_size = max(min_font_size, int(current_size * factor))
            if new_size < current_size:
                font_changed = True
                current_size = new_size
                lines = wrap_text(text, measure, box_width)
                needed = int(round(len(lines) * line_height * (current_size / font_size)))
                grown = min(needed, int(round(box_height * max_growth)))
        box_height = grown

    return WrappedText(
        lines=lines,
        width=box_width,
        height=max(box_height, needed),
        font_size=current_size,
        box_height=box_height,
        font_size_changed=font_changed,
    )


def split_display_text(
    speaker: Optional[str], text: str
) -> Tuple[Optional[str], str]:
    """Split a ``Name: translation`` string into the name and the text.

    The overlay draws the speaker name in its own colour, so the name has to
    be separated from the text before the wrapping.
    """
    if not speaker:
        return None, text
    prefix = f"{speaker}:"
    if text.startswith(prefix):
        return speaker, text[len(prefix) :].strip()
    return speaker, text
