"""Frame differencing: decide whether a new frame contains new content.

A frame is "changed" when the fraction of pixels whose intensity differs by
more than the pixel tolerance exceeds the configured threshold. Unchanged
frames are skipped, so no OCR runs on them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class DiffResult:
    """Result of comparing two frames."""

    changed: bool
    ratio: float
    diff_mask: Optional[np.ndarray] = None


def frame_diff(
    current: np.ndarray,
    previous: Optional[np.ndarray],
    threshold: float = 0.002,
    pixel_tolerance: int = 12,
) -> DiffResult:
    """Compare ``current`` with ``previous``.

    ``threshold`` is the fraction of changed pixels above which the frame is
    considered changed. Returns a :class:`DiffResult`.
    """
    if previous is None:
        height, width = current.shape[:2]
        return DiffResult(changed=True, ratio=1.0, diff_mask=None)

    if previous.shape != current.shape:
        # Resolution changed -> everything is "new".
        return DiffResult(changed=True, ratio=1.0, diff_mask=None)

    cur = current.astype(np.int16)
    prev = previous.astype(np.int16)
    gray_cur = (cur[:, :, 0] * 2 + cur[:, :, 1] * 5 + cur[:, :, 2]) // 8
    gray_prev = (prev[:, :, 0] * 2 + prev[:, :, 1] * 5 + prev[:, :, 2]) // 8
    mask = np.abs(gray_cur - gray_prev) > pixel_tolerance
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    return DiffResult(changed=ratio > threshold, ratio=ratio, diff_mask=mask)
