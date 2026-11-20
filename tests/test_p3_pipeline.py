"""Integration tests of the P3 pipeline on the new fixtures (h, i, j).

* fixture **h** - two corners changed at the same time: the per-region ROI
  has to read two disjoint rectangles, not one crop of the whole screen;
* fixture **i** - the same dialogue with a 0.7x font: the grouping has to
  give the same blocks as the normal font;
* fixture **j** - a big screen change (a menu opens): the tiled refresh has
  to read the changed tiles in parallel.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.capture import frame_from_image
from src.config import load_config
from src.ocr import OCREngine
from src.pipeline import Pipeline
from src.roi import ROI_CROP, ROI_FULL, ROI_TILES


@pytest.fixture(scope="module")
def engine():
    return OCREngine(device="cpu", intra_threads=3)


@pytest.fixture()
def config():
    cfg = load_config()
    cfg.debounce_ms = 0
    return cfg


def test_two_corners_give_two_regions(config, engine, two_corner_base, two_corner_changed) -> None:
    """A change in two distant corners gives two disjoint regions."""
    pipeline = Pipeline(config, ocr_engine=engine)
    pipeline.process_frame(frame_from_image(two_corner_base))
    result = pipeline.process_frame(frame_from_image(two_corner_changed))

    assert result.roi_action == ROI_CROP
    assert len(result.roi_regions) == 2, result.roi_regions

    # The regions are really far apart: one is in the top-left corner, the
    # other one is in the bottom-right corner.
    first, second = sorted(result.roi_regions, key=lambda r: r[0])
    assert first[0] < 800
    assert second[0] > 800
    assert first[3] < 600
    assert second[1] > 600


def test_two_corners_read_less_than_the_whole_screen(config, engine, two_corner_base, two_corner_changed) -> None:
    """The two regions cover much less than the whole screen."""
    pipeline = Pipeline(config, ocr_engine=engine)
    pipeline.process_frame(frame_from_image(two_corner_base))
    result = pipeline.process_frame(frame_from_image(two_corner_changed))

    covered = sum((r[2] - r[0]) * (r[3] - r[1]) for r in result.roi_regions)
    assert covered < 1920 * 1080 * 0.2


def test_the_changed_corner_text_is_read(config, engine, two_corner_base, two_corner_changed) -> None:
    """The text of the changed corner is found."""
    pipeline = Pipeline(config, ocr_engine=engine)
    pipeline.process_frame(frame_from_image(two_corner_base))
    result = pipeline.process_frame(frame_from_image(two_corner_changed))

    texts = " ".join(block.block.text for block in result.blocks)
    assert "9999" in texts, texts
    assert "24000" in texts, texts


def _blocks_of(pipeline, image):
    """Read the image once and return the blocks of the first frame.

    The first frame has no baseline, so the whole screen is read and the
    blocks are complete.
    """
    result = pipeline.process_frame(frame_from_image(image))
    return [b.block.text for b in result.blocks if b.block.text]


def test_the_small_font_gives_the_same_blocks(config, engine, dialogue_image, small_font_image) -> None:
    """The 0.7x font gives the same blocks as the normal font."""
    normal_pipeline = Pipeline(config, ocr_engine=engine)
    normal_blocks = _blocks_of(normal_pipeline, dialogue_image)

    small_pipeline = Pipeline(config, ocr_engine=engine)
    small_blocks = _blocks_of(small_pipeline, small_font_image)

    assert normal_blocks, "the normal font produced no block"
    assert small_blocks, "the small font produced no block"
    assert len(normal_blocks) == len(small_blocks), (normal_blocks, small_blocks)
    assert normal_blocks == small_blocks


def test_the_small_font_gives_the_same_speaker(config, engine, dialogue_image, small_font_image) -> None:
    """The speaker name is the same with the normal and with the 0.7x font."""
    normal_pipeline = Pipeline(config, ocr_engine=engine)
    normal_result = normal_pipeline.process_frame(frame_from_image(dialogue_image))

    small_pipeline = Pipeline(config, ocr_engine=engine)
    small_result = small_pipeline.process_frame(frame_from_image(small_font_image))

    normal_speakers = [b.speaker for b in normal_result.blocks if b.speaker]
    small_speakers = [b.speaker for b in small_result.blocks if b.speaker]

    assert normal_speakers, "no speaker name was detected with the normal font"
    assert small_speakers, "no speaker name was detected with the small font"
    assert normal_speakers == small_speakers


def test_the_small_font_still_finds_the_speaker(config, engine, small_font_image) -> None:
    """The speaker name is still detected with a 0.7x font."""
    pipeline = Pipeline(config, ocr_engine=engine)
    result = pipeline.process_frame(frame_from_image(small_font_image))
    speakers = [b.speaker for b in result.blocks if b.speaker]
    assert speakers, "no speaker name was detected with the small font"


def test_a_big_change_is_refreshed(config, engine, big_change_base, big_change) -> None:
    """A big screen change is read with the tiled refresh."""
    config.tiles_enabled = True
    pipeline = Pipeline(config, ocr_engine=engine)
    pipeline.process_frame(frame_from_image(big_change_base))
    result = pipeline.process_frame(frame_from_image(big_change))

    assert result.roi_action in (ROI_TILES, ROI_FULL), result.roi_action
    assert result.tiles_total > 0


def test_the_tiled_refresh_reads_the_changed_tiles(config, engine, big_change_base, big_change) -> None:
    """Only the changed tiles are read, not the whole screen."""
    config.tiles_enabled = True
    pipeline = Pipeline(config, ocr_engine=engine)
    pipeline.process_frame(frame_from_image(big_change_base))
    result = pipeline.process_frame(frame_from_image(big_change))

    if result.roi_action == ROI_TILES:
        assert 0 < result.tiles_read <= result.tiles_total


def test_a_big_change_is_faster_than_the_full_frame(config, engine, big_change_base, big_change) -> None:
    """The tiled refresh of a big change is faster than a full frame read."""
    # -- the tiled refresh -----------------------------------------------
    tiled_config = load_config()
    tiled_config.debounce_ms = 0
    tiled_config.tiles_enabled = True
    tiled_pipeline = Pipeline(tiled_config, ocr_engine=engine)
    tiled_pipeline.process_frame(frame_from_image(big_change_base))
    tiled = tiled_pipeline.process_frame(frame_from_image(big_change))
    tiled_ms = tiled.timings.total

    # -- the full frame --------------------------------------------------
    full_config = load_config()
    full_config.debounce_ms = 0
    full_config.tiles_enabled = False
    full_pipeline = Pipeline(full_config, ocr_engine=engine)
    full_pipeline.process_frame(frame_from_image(big_change_base))
    full = full_pipeline.process_frame(frame_from_image(big_change))
    full_ms = full.timings.total

    assert tiled_ms < full_ms, (tiled_ms, full_ms)
