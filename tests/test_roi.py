"""Tests for the ROI computation and for the ROI offset of the OCR bboxes."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ocr import OCRLine
from src.roi import (
    ROI_CROP,
    ROI_FULL,
    ROI_SKIP,
    bbox_area,
    changed_bbox,
    compute_roi,
    expand_roi,
    offset_lines,
)


def mask_with_rect(width: int, height: int, x1: int, y1: int, x2: int, y2: int):
    """Build a diff mask with one changed rectangle."""
    mask = np.zeros((height, width), dtype=bool)
    mask[y1:y2, x1:x2] = True
    return mask


def test_the_changed_rectangle_is_found() -> None:
    """The bounding box of the changed pixels is computed exactly."""
    mask = mask_with_rect(1920, 1080, 300, 400, 700, 500)
    assert changed_bbox(mask) == (300, 400, 700, 500)


def test_an_unchanged_frame_has_no_rectangle() -> None:
    """Nothing changed -> there is no bounding box at all."""
    mask = np.zeros((1080, 1920), dtype=bool)
    assert changed_bbox(mask) is None


def test_an_unchanged_frame_skips_the_ocr() -> None:
    """No change -> no OCR run."""
    mask = np.zeros((1080, 1920), dtype=bool)
    result = compute_roi(mask, padding=16, width=1920, height=1080, min_area=400,
                         full_frame_threshold=0.8)
    assert result.action == ROI_SKIP
    assert result.roi is None


def test_a_small_change_uses_a_small_roi() -> None:
    """A small change -> a small ROI that contains the change."""
    mask = mask_with_rect(1920, 1080, 300, 400, 700, 500)
    result = compute_roi(mask, padding=16, width=1920, height=1080, min_area=400,
                         full_frame_threshold=0.8)
    assert result.action == ROI_CROP
    x1, y1, x2, y2 = result.roi
    # The ROI contains the whole changed rectangle...
    assert x1 <= 300 and y1 <= 400 and x2 >= 700 and y2 >= 500
    # ...and it is much smaller than the screen.
    assert bbox_area(result.roi) < bbox_area((0, 0, 1920, 1080)) // 4


def test_a_large_change_falls_back_to_the_full_frame() -> None:
    """A change of more than 80 % of the screen -> the whole frame is read."""
    mask = mask_with_rect(1920, 1080, 0, 0, 1920, 1000)
    result = compute_roi(mask, padding=16, width=1920, height=1080, min_area=400,
                         full_frame_threshold=0.8)
    assert result.action == ROI_FULL
    assert result.roi is None
    assert result.changed_ratio > 0.8


def test_a_tiny_change_is_skipped() -> None:
    """A change that is too small to hold text -> no OCR run."""
    mask = mask_with_rect(1920, 1080, 100, 100, 104, 104)
    result = compute_roi(mask, padding=0, width=1920, height=1080, min_area=400,
                         full_frame_threshold=0.8)
    assert result.action == ROI_SKIP


def test_the_padding_expands_the_roi() -> None:
    """The padding is added on every side and clipped to the screen."""
    assert expand_roi((100, 100, 200, 200), 10, 1920, 1080) == (90, 90, 210, 210)
    # The ROI never leaves the screen.
    assert expand_roi((0, 0, 50, 50), 20, 1920, 1080) == (0, 0, 70, 70)


def test_the_roi_offset_moves_the_bboxes_back_to_the_screen() -> None:
    """The bboxes found inside the crop are shifted by the crop origin.

    This is the step that makes the overlay land on the original text: a
    wrong offset shifts every overlay.
    """
    lines = [
        OCRLine(text="Hello", bbox=(10, 20, 100, 50), confidence=0.9),
        OCRLine(text="World", bbox=(0, 60, 90, 90), confidence=0.9),
    ]
    moved = offset_lines(lines, 190, 770)
    assert [ln.bbox for ln in moved] == [(200, 790, 290, 820), (190, 830, 280, 860)]
    # The text and the confidence are not touched.
    assert [ln.text for ln in moved] == ["Hello", "World"]
    assert [ln.confidence for ln in moved] == [0.9, 0.9]


def test_the_roi_offset_keeps_the_full_frame_coordinates() -> None:
    """A crop at the origin does not move the bboxes."""
    lines = [OCRLine(text="Hello", bbox=(10, 20, 100, 50), confidence=0.9)]
    moved = offset_lines(lines, 0, 0)
    assert moved[0].bbox == (10, 20, 100, 50)


def test_the_roi_offset_is_applied_to_the_real_pipeline(
    dialogue_image, scaled_image
) -> None:
    """The pipeline reads the ROI and reports the full-screen coordinates.

    The dialogue of the 1920x1080 fixture starts at x=238 / y=810; the
    pipeline has to report the very same coordinates, no matter whether the
    OCR ran on the whole frame or on a crop.
    """
    from src.capture import frame_from_image
    from src.config import load_config
    from src.ocr import OCREngine

    config = load_config()
    config.debounce_ms = 0
    engine = OCREngine()
    engine.read(dialogue_image)  # warm up the models

    # The full frame gives the reference coordinates.
    full_lines = engine.read(dialogue_image)
    full = {ln.text: ln.bbox for ln in full_lines}

    # The same text read from a crop has to give the same screen coordinates.
    x1, y1, x2, y2 = 190, 770, 1730, 990
    crop = dialogue_image[y1:y2, x1:x2]
    crop_lines = engine.read_roi(crop)
    moved = {ln.text: ln.bbox for ln in offset_lines(crop_lines, x1, y1)}

    assert moved, "the crop was not read"
    for text, bbox in moved.items():
        if text in full:
            # The coordinates of the crop and of the full frame agree.
            # The crop is read at its native resolution, so a couple of
            # pixels of difference are expected.
            for value, reference in zip(bbox, full[text]):
                assert value == pytest.approx(reference, abs=6)
