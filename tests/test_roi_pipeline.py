"""Tests of the ROI OCR inside the pipeline (fixture d).

The two frames of the fixture differ in a single line at the bottom of the
dialogue box: this is the case the ROI OCR has to handle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.capture import frame_from_image
from src.config import load_config
from src.ocr import OCREngine
from src.pipeline import Pipeline
from src.roi import ROI_CROP, ROI_FULL, ROI_SKIP


@pytest.fixture()
def roi_pipeline():
    """A pipeline with the ROI enabled and the debounce disabled."""
    config = load_config()
    config.debounce_ms = 0
    config.roi_enabled = True
    pipeline = Pipeline(config, ocr_engine=OCREngine())
    return pipeline


def test_the_first_frame_reads_the_whole_screen(roi_pipeline, roi_base_image) -> None:
    """The first frame has no previous frame: the whole screen is read."""
    result = roi_pipeline.process_frame(frame_from_image(roi_base_image))
    assert result.roi_action == ROI_FULL
    assert result.blocks


def test_the_unchanged_frame_skips_the_ocr(roi_pipeline, roi_base_image) -> None:
    """The same frame twice: the second one is not read at all."""
    frame = frame_from_image(roi_base_image)
    roi_pipeline.process_frame(frame)
    result = roi_pipeline.process_frame(frame)
    assert result.frame_changed is False
    assert result.timings.ocr == 0.0


def test_a_dialogue_only_change_uses_the_roi(roi_pipeline, roi_base_image, roi_changed_image) -> None:
    """Only the changed line is read, so the OCR is much faster."""
    roi_pipeline.process_frame(frame_from_image(roi_base_image))
    result = roi_pipeline.process_frame(frame_from_image(roi_changed_image))

    assert result.roi_action == ROI_CROP
    assert result.roi_rect is not None
    x1, y1, x2, y2 = result.roi_rect
    # The ROI is in the lower part of the screen, where the last line is.
    assert y1 > 700
    assert (x2 - x1) < 1920


def test_the_roi_reads_the_changed_line(roi_pipeline, roi_base_image, roi_changed_image) -> None:
    """The changed line is found inside the ROI."""
    roi_pipeline.process_frame(frame_from_image(roi_base_image))
    result = roi_pipeline.process_frame(frame_from_image(roi_changed_image))
    texts = [b.block.text for b in result.blocks]
    assert any("completely different" in text for text in texts), texts


def test_the_roi_coordinates_are_the_screen_coordinates(
    roi_pipeline, roi_base_image, roi_changed_image
) -> None:
    """The bboxes of the ROI are the full-screen coordinates.

    A wrong offset would shift every overlay, so the y of the changed line
    has to be the real position on the screen (around 880 px).
    """
    roi_pipeline.process_frame(frame_from_image(roi_base_image))
    result = roi_pipeline.process_frame(frame_from_image(roi_changed_image))
    changed = [
        b for b in result.blocks if "completely different" in b.block.text
    ]
    assert changed, "the changed line was not found"
    bbox = changed[0].block.bbox
    # The last line of the dialogue box is around y = 880 on a 1080p screen.
    assert 820 < bbox[1] < 940, bbox


def test_the_unchanged_blocks_stay_on_the_screen(
    roi_pipeline, roi_base_image, roi_changed_image
) -> None:
    """The text that did not change keeps its translation."""
    roi_pipeline.process_frame(frame_from_image(roi_base_image))
    result = roi_pipeline.process_frame(frame_from_image(roi_changed_image))
    texts = " ".join(b.block.text for b in result.blocks)
    assert "Tacet Field" in texts, texts


def test_the_roi_can_be_disabled(roi_pipeline, roi_base_image) -> None:
    """With the ROI disabled the whole frame is always read."""
    roi_pipeline.config.roi_enabled = False
    result = roi_pipeline.process_frame(frame_from_image(roi_base_image))
    assert result.roi_action == ROI_FULL
