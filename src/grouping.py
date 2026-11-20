"""Grouping stage: merge OCR lines into text blocks and detect speaker names.

Rules implemented here:

* OCR lines that are vertically close (gap below a configurable threshold) are
  merged into a single paragraph block, because translating isolated lines
  breaks sentences.
* A speaker name is either
  - the part before a colon inside the same line (``Name: dialogue``), or
  - a short, capitalised line (1-3 words, no sentence-ending period) sitting
    directly above the dialogue block.
* A speaker name is **never** a blacklisted UI label (Quest, Skill, ...) and
  it is only accepted when it is in the character roster or when it ends with
  a colon (see :mod:`src.speakers`).

The speaker name is never translated and is never invented.

P3 (item D): the two vertical gaps are not fixed pixel values any more. They
are derived from the **measured font height** of the current frame (the
median height of the OCR bboxes, which is robust against the outliers), so
the grouping also works when the game uses a font that is smaller than the
one of the fixtures. The reference 1080p values stay as the fallback when no
text was detected yet.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .ocr import OCRLine
from .speakers import DEFAULT_VOCABULARY, SpeakerVocabulary, looks_like_name

_NAME_COLON_RE = re.compile(
    r"^\s*([A-Z][A-Za-z'\-]*(?:\s+[A-Z][A-Za-z'\-]*){0,2})\s*:\s*(.+)$"
)
_SENTENCE_END = ".!?…"
_CAP_WORD_RE = re.compile(r"^[A-Z][A-Za-z'\-]*$")
_COLON = ":"


@dataclass
class TextBlock:
    """A block of text to translate, with its merged bounding box."""

    lines: List[OCRLine] = field(default_factory=list)
    speaker: Optional[str] = None

    @property
    def text(self) -> str:
        """The dialogue text of the block (without the speaker name)."""
        parts = []
        for line in self.lines:
            text = line.text.strip()
            match = _NAME_COLON_RE.match(text)
            if self.speaker and match and match.group(1).strip() == self.speaker:
                text = match.group(2).strip()
            parts.append(text)
        return " ".join(p for p in parts if p)

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Merged bounding box of every line of the block."""
        if not self.lines:
            return (0, 0, 0, 0)
        x1 = min(ln.left for ln in self.lines)
        y1 = min(ln.top for ln in self.lines)
        x2 = max(ln.right for ln in self.lines)
        y2 = max(ln.bottom for ln in self.lines)
        return (x1, y1, x2, y2)

    @property
    def key(self) -> str:
        """Stable identity of the block (used to detect stale overlays)."""
        x1, y1, x2, y2 = self.bbox
        return f"{x1},{y1},{x2},{y2}"


def measure_font_height(lines: Sequence[OCRLine]) -> Optional[int]:
    """Estimate the font height of a frame from the OCR bboxes.

    The **median** height of the detected lines is used, because it is robust
    against the outliers (a HUD icon, a damage number or a wrongly detected
    box would not move the median). Returns None when there is no line at
    all.
    """
    heights = [line.height for line in lines if line.height > 0]
    if not heights:
        return None
    return int(round(statistics.median(heights)))


def adaptive_gaps(
    lines: Sequence[OCRLine],
    reference_group_gap: int,
    reference_speaker_gap: int,
    group_ratio: float = 0.55,
    speaker_ratio: float = 1.6,
    scale: float = 1.0,
    min_lines: int = 2,
) -> Tuple[int, int]:
    """Return the grouping gaps to use for the current frame.

    When the font height could be measured, the gaps are a fraction of it
    (``font_height * group_ratio``), so a smaller font produces smaller gaps
    and the same grouping. Otherwise the reference 1080p values are used
    (scaled to the real resolution).
    """
    height = measure_font_height(lines)
    if height is None or len(lines) < int(min_lines):
        return (
            max(1, int(round(reference_group_gap * scale))),
            max(1, int(round(reference_speaker_gap * scale))),
        )
    group_gap = max(1, int(round(height * float(group_ratio))))
    speaker_gap = max(1, int(round(height * float(speaker_ratio))))
    return group_gap, speaker_gap


def group_lines(
    lines: List[OCRLine], gap_px: int = 28, scale: float = 1.0
) -> List[List[OCRLine]]:
    """Group vertically adjacent OCR lines into blocks.

    ``gap_px`` is the maximum vertical gap (in screen pixels) between two
    lines that still belong to the same block. ``scale`` multiplies the gap so
    it follows the screen resolution.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=lambda ln: (ln.top, ln.left))
    max_gap = max(1.0, gap_px * scale)
    groups: List[List[OCRLine]] = [[ordered[0]]]
    for line in ordered[1:]:
        prev = groups[-1][-1]
        gap = line.top - prev.bottom
        if gap <= max_gap:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def is_speaker_line(
    line: OCRLine,
    max_words: int = 3,
    vocabulary: Optional[SpeakerVocabulary] = None,
) -> bool:
    """Return True when the line can be the name of a speaker.

    The line must be short, capitalised and must not be a blacklisted UI
    label. When a vocabulary is given, the name must also be in the roster or
    carry a trailing colon.
    """
    text = line.text.strip()
    if not text or len(text) > 40:
        return False
    if text.endswith(tuple(_SENTENCE_END)):
        return False
    words = text.split()
    if not 1 <= len(words) <= max_words:
        return False
    if not all(_CAP_WORD_RE.match(w) for w in words):
        return False
    if vocabulary is None:
        return True
    return looks_like_name(text, vocabulary, max_words=max_words)


def detect_speaker(
    block_lines: List[OCRLine],
    previous_line: Optional[OCRLine],
    speaker_gap_px: int = 60,
    scale: float = 1.0,
    max_words: int = 3,
    vocabulary: Optional[SpeakerVocabulary] = None,
) -> Optional[str]:
    """Detect the speaker name of a block.

    First the ``Name: dialogue`` form inside the block is checked, then a short
    capitalised line directly above the block. A blacklisted UI label is never
    returned.
    """
    vocabulary = vocabulary or DEFAULT_VOCABULARY

    for line in block_lines:
        match = _NAME_COLON_RE.match(line.text.strip())
        if match and len(match.group(1).split()) <= max_words + 1:
            name = match.group(1).strip()
            if vocabulary.is_ui_label(name):
                continue
            return name

    if previous_line is not None and is_speaker_line(
        previous_line, max_words, vocabulary
    ):
        max_gap = max(1.0, speaker_gap_px * scale)
        gap = block_lines[0].top - previous_line.bottom
        if 0 <= gap <= max_gap:
            return previous_line.text.strip()
    return None


def build_blocks(
    lines: List[OCRLine],
    gap_px: int = 18,
    speaker_gap_px: int = 120,
    scale: float = 1.0,
    max_words: int = 3,
    vocabulary: Optional[SpeakerVocabulary] = None,
) -> List[TextBlock]:
    """Group the OCR lines and attach the detected speaker name to each block.

    A line that turned out to be a speaker name is not translated on its own:
    it is removed from the dialogue text of the block below it.
    """
    vocabulary = vocabulary or DEFAULT_VOCABULARY
    ordered = sorted(lines, key=lambda ln: (ln.top, ln.left))
    groups = group_lines(ordered, gap_px=gap_px, scale=scale)

    speakers: List[Optional[str]] = []
    for index, group in enumerate(groups):
        previous_line = groups[index - 1][-1] if index > 0 else None
        speakers.append(
            detect_speaker(
                group,
                previous_line,
                speaker_gap_px=speaker_gap_px,
                scale=scale,
                max_words=max_words,
                vocabulary=vocabulary,
            )
        )

    # A group that only contains the name of the speaker of the *next* group
    # is a speaker label, not a dialogue block.
    speaker_only: set[int] = set()
    for index in range(len(groups) - 1):
        group = groups[index]
        next_speaker = speakers[index + 1]
        if (
            next_speaker
            and len(group) == 1
            and group[0].text.strip() == next_speaker
        ):
            speaker_only.add(index)

    blocks: List[TextBlock] = []
    for index, group in enumerate(groups):
        if index in speaker_only:
            continue
        speaker = speakers[index]
        block_lines = list(group)
        if (
            speaker
            and index > 0
            and len(groups[index - 1]) == 1
            and groups[index - 1][0].text.strip() == speaker
        ):
            block_lines = [
                ln for ln in block_lines if ln.text.strip() != speaker
            ]
        if not block_lines:
            continue
        blocks.append(TextBlock(lines=block_lines, speaker=speaker))
    return blocks
