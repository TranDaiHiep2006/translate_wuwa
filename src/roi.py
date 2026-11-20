"""Region of interest (ROI) computation for the OCR stage.

Only the part of the screen that actually changed has to be read by the OCR.
This module computes the bounding rectangle of the changed pixels, expands it
by a configurable padding and decides whether the OCR should run on that crop
or on the whole frame.

Nothing here is hardcoded for a specific resolution: the padding is a
reference value at 1080p height and is scaled at runtime by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .ocr import OCRLine

# What the pipeline should do with the current frame.
ROI_SKIP = "skip"  # the change is too small to contain any text -> no OCR
ROI_CROP = "roi"  # read only the changed rectangle
ROI_FULL = "full"  # read the whole frame

BBox = Tuple[int, int, int, int]


@dataclass
class ROIResult:
    """The decision taken for one frame.

    ``action`` is one of :data:`ROI_SKIP`, :data:`ROI_CROP` or
    :data:`ROI_FULL`. ``roi`` is the crop rectangle in full-screen
    coordinates (only set for :data:`ROI_CROP`).
    """

    action: str
    roi: Optional[BBox] = None
    changed_area: int = 0
    screen_area: int = 0
    reason: str = ""

    @property
    def changed_ratio(self) -> float:
        """Fraction of the screen that changed (0..1)."""
        if self.screen_area <= 0:
            return 0.0
        return self.changed_area / float(self.screen_area)


def changed_bbox(mask: np.ndarray) -> Optional[BBox]:
    """Return the bounding box of the changed pixels of ``mask``.

    The box is ``(x1, y1, x2, y2)`` in pixels, ``x2``/``y2`` exclusive.
    Returns None when nothing changed.
    """
    if mask is None or mask.size == 0:
        return None
    try:
        import cv2

        binary = mask.astype(np.uint8)
        x, y, w, h = cv2.boundingRect(binary)
        if w <= 0 or h <= 0:
            return None
        return (int(x), int(y), int(x + w), int(y + h))
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None
        return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def changed_area(mask: np.ndarray) -> int:
    """Return the number of changed pixels of ``mask``."""
    if mask is None or mask.size == 0:
        return 0
    try:
        import cv2

        return int(cv2.countNonZero(mask.astype(np.uint8)))
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        return int(np.count_nonzero(mask))


def expand_roi(roi: BBox, padding: int, width: int, height: int) -> BBox:
    """Expand ``roi`` by ``padding`` pixels and clip it to the screen."""
    x1, y1, x2, y2 = roi
    x1 = max(0, int(x1) - int(padding))
    y1 = max(0, int(y1) - int(padding))
    x2 = min(int(width), int(x2) + int(padding))
    y2 = min(int(height), int(y2) + int(padding))
    if x2 <= x1:
        x2 = min(int(width), x1 + 1)
    if y2 <= y1:
        y2 = min(int(height), y1 + 1)
    return (x1, y1, x2, y2)


def bbox_area(roi: BBox) -> int:
    """Return the area of a bounding box in pixels."""
    x1, y1, x2, y2 = roi
    return max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))


def bbox_intersects(a: BBox, b: BBox) -> bool:
    """Return True when the two boxes overlap."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2


def compute_roi(
    mask: Optional[np.ndarray],
    padding: int,
    width: int,
    height: int,
    min_area: int,
    full_frame_threshold: float,
) -> ROIResult:
    """Decide what the OCR should read for the current frame.

    * no change at all -> :data:`ROI_SKIP` (no OCR run)
    * a changed rectangle that is bigger than ``full_frame_threshold`` of the
      screen -> :data:`ROI_FULL` (reading a huge ROI is slower than reading
      the whole frame anyway)
    * a changed rectangle that is smaller than ``min_area`` -> :data:`ROI_SKIP`
      (the change cannot contain any readable text)
    * otherwise -> :data:`ROI_CROP` with the expanded rectangle
    """
    screen_area = int(width) * int(height)
    if mask is None:
        return ROIResult(
            action=ROI_FULL,
            changed_area=screen_area,
            screen_area=screen_area,
            reason="no diff mask (first frame or resolution change)",
        )

    area = changed_area(mask)
    ratio = area / float(screen_area) if screen_area else 0.0
    if area <= 0:
        return ROIResult(
            action=ROI_SKIP,
            changed_area=0,
            screen_area=screen_area,
            reason="no changed pixels",
        )

    if ratio > float(full_frame_threshold):
        return ROIResult(
            action=ROI_FULL,
            changed_area=area,
            screen_area=screen_area,
            reason=f"changed area {ratio:.1%} > {float(full_frame_threshold):.0%}",
        )

    box = changed_bbox(mask)
    if box is None:  # pragma: no cover - defensive
        return ROIResult(
            action=ROI_FULL,
            changed_area=area,
            screen_area=screen_area,
            reason="no bounding box",
        )

    padded = expand_roi(box, padding, width, height)
    if bbox_area(padded) < int(min_area):
        return ROIResult(
            action=ROI_SKIP,
            changed_area=area,
            screen_area=screen_area,
            reason=f"changed area {bbox_area(padded)} px < {int(min_area)} px",
        )

    return ROIResult(
        action=ROI_CROP,
        roi=padded,
        changed_area=area,
        screen_area=screen_area,
        reason=f"changed area {ratio:.2%}",
    )


def offset_lines(lines: Sequence[OCRLine], dx: int, dy: int) -> List[OCRLine]:
    """Move OCR lines from crop coordinates back to full-screen coordinates.

    This is the step that makes the overlay land exactly on the original
    text: every bbox found inside the crop has to be shifted by the crop
    origin.
    """
    moved: List[OCRLine] = []
    for line in lines:
        x1, y1, x2, y2 = line.bbox
        moved.append(
            OCRLine(
                text=line.text,
                bbox=(
                    int(x1) + int(dx),
                    int(y1) + int(dy),
                    int(x2) + int(dx),
                    int(y2) + int(dy),
                ),
                confidence=line.confidence,
            )
        )
    return moved
