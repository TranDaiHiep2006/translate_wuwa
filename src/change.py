"""Frame differencing: decide whether a new frame contains new content.

A frame is "changed" when the fraction of pixels whose intensity differs by
more than the pixel tolerance exceeds the configured threshold. Unchanged
frames are skipped, so no OCR runs on them.

P3 (item B): the differencing runs on a **downscaled** copy of the frame
(1/4 of the size by default), because the full resolution differencing of a
1920x1080 frame cost 38-43 ms and it was the second slowest stage of the
in-game path.

Two details make the downscaled diff both **fast** and **sensitive**:

* the grayscale conversion uses OpenCV (a SIMD implementation), not a NumPy
  expression on an int16 array - that alone was the difference between
  44 ms and 6 ms;
* the mask is downscaled with a **maximum** pooling, so a change of one
  pixel is not diluted below the detection threshold (with an average, a
  changed glyph was missed entirely).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class DiffResult:
    """Result of comparing two frames.

    ``diff_mask`` is the mask of the changed pixels. When the differencing
    ran on a downscaled frame, the mask has the size of the downscaled frame
    and ``scale_factor`` tells how many full resolution pixels one mask pixel
    covers. ``full_mask`` holds the full resolution mask when it was computed
    (it is only used to refine the edges of the regions).
    """

    changed: bool
    ratio: float
    diff_mask: Optional[np.ndarray] = None
    scale_factor: int = 1
    full_mask: Optional[np.ndarray] = None


def to_gray(image: np.ndarray) -> np.ndarray:
    """Return the luminance of a BGR frame as a uint8 array.

    OpenCV is used because its implementation is vectorised: the NumPy
    version (a weighted sum of the three channels in int16) cost 20 ms per
    frame, which was more than the whole downscaled diff stage.
    """
    try:
        import cv2

        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        arr = image.astype(np.int16)
        return ((arr[:, :, 0] * 2 + arr[:, :, 1] * 5 + arr[:, :, 2]) // 8).astype(
            np.uint8
        )


def downscale_gray(gray: np.ndarray, factor: int) -> np.ndarray:
    """Downscale a grayscale frame by an integer factor.

    The **maximum** of every ``factor x factor`` block is used, so a small
    change is not lost: with an average, a changed glyph that covers only a
    few pixels of a block is diluted below the detection threshold and the
    change is missed. With a maximum, one changed pixel is enough to mark
    the whole block as changed.

    The result keeps the full resolution height when the height is not a
    multiple of the factor.
    """
    factor = max(1, int(factor))
    if factor == 1:
        return gray
    height, width = gray.shape[:2]
    small_h = max(1, height // factor)
    small_w = max(1, width // factor)
    # Crop to a multiple of the factor so the blocks are regular.
    cropped = gray[: small_h * factor, : small_w * factor]
    blocks = cropped.reshape(small_h, factor, small_w, factor)
    return blocks.max(axis=(1, 3)).astype(gray.dtype)


def downscale_mask(mask: np.ndarray, factor: int) -> np.ndarray:
    """Downscale a **binary** mask by an integer factor.

    The result marks a block as changed when **at least one** of its pixels
    was changed. That is the maximum pooling of the mask: it never loses a
    small change.

    The mask is scaled to 0..255 before the resize, because the area
    interpolation of a 0/1 mask would divide the value by the number of
    pixels of the block and round it to zero: a single changed pixel would
    be lost. With the 0..255 mask, one changed pixel of the block gives an
    average of ``255 / (factor * factor)``, which is not zero, so the block
    is kept.
    """
    factor = max(1, int(factor))
    if factor == 1:
        return mask
    try:
        import cv2

        height, width = mask.shape[:2]
        small_h = max(1, height // factor)
        small_w = max(1, width // factor)
        small = cv2.resize(
            mask.astype(np.uint8) * 255,
            (small_w, small_h),
            interpolation=cv2.INTER_AREA,
        )
        return small > 0
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        return downscale_gray(mask.astype(np.int16), factor) > 0


def downscale_difference(
    difference: np.ndarray, factor: int, pixel_tolerance: int = 12
) -> np.ndarray:
    """Downscale a difference image and return the binary changed mask.

    The difference is scaled with an **area** interpolation, so the value of
    the result is the average of the block. The mask is then built from that
    average with a **scaled** tolerance: a block where only one pixel of
    four changed has an average of ``tolerance / 4``, so the tolerance has
    to be divided by the number of pixels of the block as well.

    That is what keeps the downscaled diff both **fast** (one resize instead
    of one resize plus one comparison over the full resolution) and
    **sensitive** (a change of one pixel is not lost).
    """
    factor = max(1, int(factor))
    if factor == 1:
        return difference > int(pixel_tolerance)

    try:
        import cv2

        height, width = difference.shape[:2]
        small_h = max(1, height // factor)
        small_w = max(1, width // factor)
        small = cv2.resize(
            difference,
            (small_w, small_h),
            interpolation=cv2.INTER_AREA,
        )
        # One changed pixel of the block gives an average of
        # ``tolerance / (factor * factor)``: the tolerance is scaled too.
        scaled_tolerance = max(1.0, float(pixel_tolerance) / float(factor * factor))
        return small > scaled_tolerance
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        return downscale_mask(difference > int(pixel_tolerance), factor)


def frame_diff(
    current: np.ndarray,
    previous: Optional[np.ndarray],
    threshold: float = 0.002,
    pixel_tolerance: int = 12,
    downscale: int = 1,
) -> DiffResult:
    """Compare ``current`` with ``previous``.

    ``threshold`` is the fraction of changed pixels above which the frame is
    considered changed. ``downscale`` is the factor of the downscaled frame
    the differencing runs on (1 = full resolution). Returns a
    :class:`DiffResult`.
    """
    if previous is None:
        height, width = current.shape[:2]
        return DiffResult(changed=True, ratio=1.0, diff_mask=None)

    if previous.shape != current.shape:
        # Resolution changed -> everything is "new".
        return DiffResult(changed=True, ratio=1.0, diff_mask=None)

    factor = max(1, int(downscale))

    try:
        import cv2

        gray_cur = to_gray(current)
        gray_prev = to_gray(previous)
        difference = cv2.absdiff(gray_cur, gray_prev)
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        gray_cur = to_gray(current).astype(np.int16)
        gray_prev = to_gray(previous).astype(np.int16)
        difference = np.abs(gray_cur - gray_prev)

    if factor > 1:
        mask = downscale_mask(difference > int(pixel_tolerance), factor)
    else:
        mask = difference > int(pixel_tolerance)

    ratio = float(np.count_nonzero(mask)) / float(mask.size)

    return DiffResult(
        changed=ratio > threshold,
        ratio=ratio,
        diff_mask=mask,
        scale_factor=factor,
        full_mask=None,
    )


def refine_mask(
    current: np.ndarray,
    previous: np.ndarray,
    box: Tuple[int, int, int, int],
    scale_factor: int,
    pixel_tolerance: int = 12,
) -> np.ndarray:
    """Compute the full resolution diff mask inside a region.

    The region ``box`` is given in full resolution coordinates. The returned
    mask has the size of the region, so it can be used to refine the edges of
    the region that the downscaled mask found.
    """
    x1, y1, x2, y2 = box
    try:
        import cv2

        cur = to_gray(current[y1:y2, x1:x2])
        prev = to_gray(previous[y1:y2, x1:x2])
        return cv2.absdiff(cur, prev) > int(pixel_tolerance)
    except Exception:  # pragma: no cover - cv2 is a hard dependency
        cur = to_gray(current[y1:y2, x1:x2]).astype(np.int16)
        prev = to_gray(previous[y1:y2, x1:x2]).astype(np.int16)
        return np.abs(cur - prev) > int(pixel_tolerance)


def scale_box(
    box: Tuple[int, int, int, int], factor: int, width: int, height: int
) -> Tuple[int, int, int, int]:
    """Scale a box from the downscaled space to the full resolution space.

    The box is clipped to the screen, so the result is always a valid
    rectangle.
    """
    factor = max(1, int(factor))
    x1, y1, x2, y2 = box
    x1 = max(0, int(x1) * factor)
    y1 = max(0, int(y1) * factor)
    x2 = min(int(width), int(x2) * factor)
    y2 = min(int(height), int(y2) * factor)
    if x2 <= x1:
        x2 = min(int(width), x1 + 1)
    if y2 <= y1:
        y2 = min(int(height), y1 + 1)
    return (x1, y1, x2, y2)
