"""Region of interest (ROI) computation for the OCR stage.

Only the part of the screen that actually changed has to be read by the OCR.
This module computes the bounding rectangle of the changed pixels, expands it
by a configurable padding and decides whether the OCR should run on that crop
or on the whole frame.

P3 adds two things on top of the P2 single rectangle:

* **Per-region ROI** (:func:`compute_regions`) - the changed area is split
  into several *disjoint* rectangles (connected components of the diff mask),
  so a change in two distant corners does not produce a crop that covers the
  whole screen. A region that is too small is merged into its nearest
  neighbour instead of being read on its own. The regions are read in a small
  thread pool and merged back with correct full-screen coordinates.
* **Tiled refresh** (:func:`compute_tiles`) - the scheduled refresh reads the
  frame as a grid of tiles and only the changed tiles are read.

Nothing here is hardcoded for a specific resolution: the padding is a
reference value at 1080p height and is scaled at runtime by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .ocr import OCRLine

# What the pipeline should do with the current frame.
ROI_SKIP = "skip"  # the change is too small to contain any text -> no OCR
ROI_CROP = "roi"  # read only the changed rectangle(s)
ROI_FULL = "full"  # read the whole frame
ROI_TILES = "tiles"  # read only the changed tiles of the grid

BBox = Tuple[int, int, int, int]


@dataclass
class ROIResult:
    """The decision taken for one frame.

    ``action`` is one of :data:`ROI_SKIP`, :data:`ROI_CROP` or
    :data:`ROI_FULL`. ``roi`` is the union rectangle in full-screen
    coordinates (only set for :data:`ROI_CROP`). ``regions`` holds the
    disjoint rectangles that the OCR actually has to read.
    """

    action: str
    roi: Optional[BBox] = None
    changed_area: int = 0
    screen_area: int = 0
    reason: str = ""
    regions: List[BBox] = field(default_factory=list)

    @property
    def changed_ratio(self) -> float:
        """Fraction of the screen that changed (0..1)."""
        if self.screen_area <= 0:
            return 0.0
        return self.changed_area / float(self.screen_area)

    @property
    def read_rects(self) -> List[BBox]:
        """The rectangles the OCR has to read for this frame."""
        if self.action == ROI_CROP:
            return list(self.regions) if self.regions else ([self.roi] if self.roi else [])
        return []


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


def bbox_center(box: BBox) -> Tuple[float, float]:
    """Return the center of a bounding box."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def bbox_union(boxes: Sequence[BBox]) -> BBox:
    """Return the smallest box that contains every box of the sequence."""
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


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
        regions=[padded],
        changed_area=area,
        screen_area=screen_area,
        reason=f"changed area {ratio:.2%}",
    )


# --------------------------------------------------------------------------
# Per-region ROI (item A of P3)
# --------------------------------------------------------------------------


def connected_regions(mask: np.ndarray) -> List[BBox]:
    """Split the changed pixels of ``mask`` into disjoint rectangles.

    The connected components of the mask are found and each of them becomes a
    rectangle. The rectangles are returned in reading order (top to bottom,
    left to right).
    """
    if mask is None or mask.size == 0:
        return []
    try:
        import cv2

        binary = mask.astype(np.uint8)
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )
        boxes: List[BBox] = []
        for index in range(1, count):
            x, y, w, h = (int(v) for v in stats[index][:4])
            if w <= 0 or h <= 0:
                continue
            boxes.append((x, y, x + w, y + h))
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        boxes = []
        box = changed_bbox(mask)
        if box is not None:
            boxes.append(box)

    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def merge_small_regions(
    regions: Sequence[BBox],
    min_area: int,
    width: int,
    height: int,
    merge_gap: int = 0,
) -> List[BBox]:
    """Merge the regions that are close together or too small.

    Two neighbouring regions are merged when the gap between them is below
    ``merge_gap`` pixels and they are on the same line. That is what keeps a
    **text line** in one piece: the diff of a changed line is made of one
    component per glyph, so the glyphs have to be merged back into the line.

    A region that cannot hold any readable text (its area is below
    ``min_area``) is merged into its nearest neighbour instead of being read
    on its own.

    Regions that are far apart are **not** merged: that is the whole point
    of the per-region ROI (a change in two distant corners stays two
    regions).

    The merging is done row by row: the regions are grouped by their
    vertical overlap, then the ones of a row are sorted by ``x`` and the
    chains of neighbouring regions are merged. That keeps the cost linear in
    the number of components (a changed text line can be made of hundreds
    of glyph components).
    """
    if not regions:
        return []

    boxes = list(regions)

    # -- 1. merge the regions that are close together on the same line -----
    rows = _group_into_rows(boxes)
    merged: List[BBox] = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        current = row[0]
        for box in row[1:]:
            gap = max(0, box[0] - current[2])
            if gap <= int(merge_gap):
                current = _union_box(current, box)
            else:
                merged.append(current)
                current = box
        merged.append(current)

    # -- 2. merge the regions that are stacked on top of each other -------
    # Two text lines of the same block are one region: they are merged when
    # they are on the same column and the vertical gap is small.
    merged = _merge_stacked(merged, int(merge_gap))

    # -- 3. merge the regions that are too small ---------------------------
    kept: List[BBox] = []
    smalls: List[BBox] = []
    for box in merged:
        if bbox_area(box) < int(min_area):
            smalls.append(box)
        else:
            kept.append(box)

    if not smalls:
        kept.sort(key=lambda b: (b[1], b[0]))
        return kept

    if not kept:
        # Every region is small: keep the biggest one only.
        biggest = max(merged, key=bbox_area)
        return [biggest]

    for small in smalls:
        # The small region is only merged into a neighbour that is really
        # close. Merging it into a distant region would create a crop that
        # covers a big part of the screen for nothing.
        cx, cy = bbox_center(small)
        candidates = [
            box
            for box in kept
            if _box_gap(box, small) <= int(merge_gap)
        ]
        if not candidates:
            # Nothing is close: the region is kept on its own. The caller
            # drops it when it is really too small to hold any text.
            kept.append(small)
            continue
        target = min(
            candidates,
            key=lambda box: (
                (bbox_center(box)[0] - cx) ** 2 + (bbox_center(box)[1] - cy) ** 2
            ),
        )
        kept.remove(target)
        kept.append(_union_box(target, small))

    kept.sort(key=lambda b: (b[1], b[0]))
    return kept


def _merge_stacked(boxes: List[BBox], merge_gap: int) -> List[BBox]:
    """Merge the boxes that are stacked on top of each other.

    Two boxes are merged when they overlap horizontally and the vertical
    gap between them is at most ``merge_gap``. That is what turns the
    several lines of a text block into a single region, while a panel in
    the top-left corner and a panel in the bottom-right corner stay
    separate.
    """
    if len(boxes) < 2:
        return list(boxes)

    result = list(boxes)
    changed = True
    while changed and len(result) > 1:
        changed = False
        best_pair = None
        best_gap = None
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                a = result[i]
                b = result[j]
                horizontal_overlap = min(a[2], b[2]) - max(a[0], b[0])
                if horizontal_overlap <= 0:
                    continue
                if a[3] <= b[1]:
                    vertical_gap = b[1] - a[3]
                elif b[3] <= a[1]:
                    vertical_gap = a[1] - b[3]
                else:
                    vertical_gap = 0
                if vertical_gap > int(merge_gap):
                    continue
                if best_gap is None or vertical_gap < best_gap:
                    best_gap = vertical_gap
                    best_pair = (i, j)
        if best_pair is not None:
            i, j = best_pair
            result[i] = _union_box(result[i], result[j])
            result.pop(j)
            changed = True
    return result


def _group_into_rows(boxes: Sequence[BBox]) -> List[List[BBox]]:
    """Group the boxes that are on the same horizontal line.

    Two boxes are on the same line when they overlap vertically. The boxes
    are sorted by their top edge, so the grouping is a single pass.

    A box joins a row only when it overlaps **most** of the height of that
    row: a row that holds the two lines of a text block is taller than one
    line, and a box that is somewhere else on the screen must not be merged
    into it.
    """
    ordered = sorted(boxes, key=lambda b: (b[1], b[0]))
    rows: List[List[BBox]] = []
    for box in ordered:
        placed = False
        for row in rows:
            if _row_overlaps(row, box):
                row.append(box)
                placed = True
                break
        if not placed:
            rows.append([box])
    return rows


def _row_overlaps(row: Sequence[BBox], box: BBox) -> bool:
    """Return True when ``box`` overlaps vertically with the row.

    The box has to cover at least half of the height of the row, otherwise a
    box that is far below (or above) the row would be merged into it.
    """
    top = min(b[1] for b in row)
    bottom = max(b[3] for b in row)
    row_height = max(1, bottom - top)
    overlap = min(bottom, box[3]) - max(top, box[1])
    if overlap <= 0:
        return False
    return overlap * 2 >= row_height


def _union_box(a: BBox, b: BBox) -> BBox:
    """Return the smallest box that contains both boxes."""
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


def _box_gap(a: BBox, b: BBox) -> int:
    """Return the distance between two boxes (0 when they overlap)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    horizontal = max(0, max(ax1, bx1) - min(ax2, bx2))
    vertical = max(0, max(ay1, by1) - min(ay2, by2))
    return horizontal + vertical


def compute_regions(
    mask: Optional[np.ndarray],
    padding: int,
    width: int,
    height: int,
    min_area: int,
    full_frame_threshold: float,
    region_min_area: int = 1200,
    max_regions: int = 4,
    merge_gap: int = 200,
    scale_factor: int = 1,
) -> ROIResult:
    """Decide what the OCR should read, as a list of disjoint rectangles.

    This is the per-region version of :func:`compute_roi`. The changed area
    is split into connected components; the components that are too small are
    merged into their nearest neighbour; at most ``max_regions`` rectangles
    are kept (the biggest ones).

    When the changed area is bigger than ``full_frame_threshold`` of the
    screen, the whole frame is read instead (a full frame read is faster than
    reading many regions).

    ``scale_factor`` is the factor of the downscaled frame the mask belongs
    to: the mask is compared with the screen through that factor, so the
    threshold means the same thing for a full and for a downscaled mask.
    """
    screen_area = int(width) * int(height)
    factor = max(1, int(scale_factor))
    if mask is None:
        return ROIResult(
            action=ROI_FULL,
            changed_area=screen_area,
            screen_area=screen_area,
            reason="no diff mask (first frame or resolution change)",
        )

    area = changed_area(mask)
    # The mask may be downscaled: the changed area of the screen is the
    # area of the mask multiplied by the factor squared.
    screen_area_of_mask = screen_area / float(factor * factor)
    ratio = area / float(screen_area_of_mask) if screen_area_of_mask else 0.0
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

    components = connected_regions(mask)
    if not components:
        return ROIResult(
            action=ROI_SKIP,
            changed_area=area,
            screen_area=screen_area,
            reason="no connected region",
        )

    regions = merge_small_regions(
        components, region_min_area, width, height, merge_gap=merge_gap
    )
    regions = [expand_roi(box, padding, width, height) for box in regions]
    regions = [box for box in regions if bbox_area(box) >= int(min_area)]

    if not regions:
        return ROIResult(
            action=ROI_SKIP,
            changed_area=area,
            screen_area=screen_area,
            reason=f"every region is smaller than {int(min_area)} px",
        )

    if len(regions) > int(max_regions):
        regions = sorted(regions, key=bbox_area, reverse=True)[: int(max_regions)]
        regions.sort(key=lambda b: (b[1], b[0]))

    return ROIResult(
        action=ROI_CROP,
        roi=bbox_union(regions),
        changed_area=area,
        screen_area=screen_area,
        reason=f"{len(regions)} changed region(s), {ratio:.2%} of the screen",
        regions=list(regions),
    )


# --------------------------------------------------------------------------
# Tiled refresh (item A of P3)
# --------------------------------------------------------------------------


@dataclass
class TileResult:
    """The tiles of a frame and the ones that changed.

    ``tiles`` holds the rectangles of the grid in full-screen coordinates and
    ``changed`` the indexes of the tiles whose changed-pixel fraction is above
    the threshold.
    """

    tiles: List[BBox]
    changed: List[int]
    changed_ratio: float = 0.0
    changed_area: int = 0
    screen_area: int = 0

    @property
    def changed_tiles(self) -> List[BBox]:
        """The rectangles of the changed tiles."""
        return [self.tiles[index] for index in self.changed]


def tile_grid(width: int, height: int, cols: int, rows: int) -> List[BBox]:
    """Build the rectangles of a regular grid over the frame.

    The grid is ``cols`` columns by ``rows`` rows and covers the whole frame,
    so no pixel is read twice and no pixel is skipped.
    """
    cols = max(1, int(cols))
    rows = max(1, int(rows))
    width = int(width)
    height = int(height)

    x_edges = [round(index * width / cols) for index in range(cols + 1)]
    y_edges = [round(index * height / rows) for index in range(rows + 1)]

    tiles: List[BBox] = []
    for row in range(rows):
        for col in range(cols):
            tiles.append(
                (x_edges[col], y_edges[row], x_edges[col + 1], y_edges[row + 1])
            )
    return tiles


def compute_tiles(
    mask: Optional[np.ndarray],
    width: int,
    height: int,
    cols: int,
    rows: int,
    changed_threshold: float = 0.004,
    scale_factor: int = 1,
) -> TileResult:
    """Find the tiles of a frame whose changed-pixel fraction is high enough.

    ``mask`` is the diff mask; ``scale_factor`` is the factor of the
    downscaled frame the mask belongs to (the tile rectangles are always in
    full-screen coordinates). When ``mask`` is None (first frame, resolution
    change) every tile is reported as changed.
    """
    tiles = tile_grid(width, height, cols, rows)
    screen_area = int(width) * int(height)

    if mask is None:
        return TileResult(
            tiles=tiles,
            changed=list(range(len(tiles))),
            changed_ratio=1.0,
            changed_area=screen_area,
            screen_area=screen_area,
        )

    factor = max(1, int(scale_factor))
    mask_h, mask_w = mask.shape[:2]

    changed: List[int] = []
    total_changed = 0
    for index, (x1, y1, x2, y2) in enumerate(tiles):
        mx1 = min(mask_w, max(0, x1 // factor))
        my1 = min(mask_h, max(0, y1 // factor))
        mx2 = min(mask_w, max(mx1 + 1, (x2 + factor - 1) // factor))
        my2 = min(mask_h, max(my1 + 1, (y2 + factor - 1) // factor))
        sub = mask[my1:my2, mx1:mx2]
        if sub.size == 0:
            continue
        area = int(np.count_nonzero(sub))
        total_changed += area
        if area / float(sub.size) >= float(changed_threshold):
            changed.append(index)

    ratio = len(changed) / float(len(tiles)) if tiles else 0.0
    return TileResult(
        tiles=tiles,
        changed=changed,
        changed_ratio=ratio,
        changed_area=total_changed,
        screen_area=screen_area,
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


def dedupe_lines(lines: Sequence[OCRLine], tolerance: int = 4) -> List[OCRLine]:
    """Remove the duplicated lines of a merged OCR result.

    Two regions can overlap (the padding of two neighbouring regions), so the
    same text line can be read twice. The duplicated lines are dropped, so a
    block is never translated twice.
    """
    kept: List[OCRLine] = []
    for line in lines:
        duplicate = False
        for other in kept:
            if other.text.strip() != line.text.strip():
                continue
            ax1, ay1, ax2, ay2 = other.bbox
            bx1, by1, bx2, by2 = line.bbox
            overlap_x = min(ax2, bx2) - max(ax1, bx1)
            overlap_y = min(ay2, by2) - max(ay1, by1)
            if overlap_x > -tolerance and overlap_y > -tolerance:
                duplicate = True
                break
        if not duplicate:
            kept.append(line)
    return kept
