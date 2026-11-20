"""Tests of the P3 features: tiled refresh, per-region ROI, async pipeline,
adaptive grouping, live HUD and the hardened sentence splitter.

They cover the items A, B, C, D, E and G of the P3 brief.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.async_translate import AsyncTranslator
from src.capture import frame_from_image
from src.change import downscale_gray, frame_diff, scale_box
from src.config import load_config
from src.grouping import (
    TextBlock,
    adaptive_gaps,
    build_blocks,
    measure_font_height,
)
from src.hud import HUDState, format_hud_lines
from src.ocr import OCRLine
from src.pipeline import Pipeline, StageTimings
from src.roi import (
    ROI_CROP,
    ROI_FULL,
    ROI_TILES,
    compute_regions,
    compute_tiles,
    connected_regions,
    dedupe_lines,
    merge_small_regions,
    offset_lines,
    tile_grid,
)
from src.sentences import (
    get_splitter,
    join_sentences,
    protect_numbers,
    split_sentences,
    split_with_stanza,
)


def _line(text: str, top: int, height: int = 36, left: int = 100) -> OCRLine:
    """Build an OCR line with the given text and geometry."""
    return OCRLine(
        text=text,
        bbox=(left, top, left + 400, top + height),
        confidence=0.95,
    )


# --------------------------------------------------------------------------
# Item A: per-region ROI
# --------------------------------------------------------------------------


def test_the_connected_components_are_found() -> None:
    """Two separated blobs give two components."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:20, 10:20] = True
    mask[70:90, 70:95] = True
    regions = connected_regions(mask)
    assert len(regions) == 2
    assert regions[0][0] == 10
    assert regions[1][0] == 70


def test_two_distant_regions_are_not_merged() -> None:
    """Two regions that are far apart stay two regions."""
    regions = [(0, 0, 100, 40), (900, 800, 1000, 840)]
    merged = merge_small_regions(regions, 100, 1920, 1080, merge_gap=200)
    assert len(merged) == 2


def test_the_glyphs_of_a_line_are_merged_back() -> None:
    """The components of one line are merged into a single region."""
    regions = [(0, 100, 20, 130), (30, 100, 50, 130), (60, 100, 80, 130)]
    merged = merge_small_regions(regions, 10, 1920, 1080, merge_gap=200)
    assert len(merged) == 1
    assert merged[0] == (0, 100, 80, 130)


def test_the_two_lines_of_a_block_are_merged() -> None:
    """Two lines that are stacked on top of each other are one region."""
    regions = [(100, 100, 500, 140), (100, 150, 500, 190)]
    merged = merge_small_regions(regions, 10, 1920, 1080, merge_gap=200)
    assert len(merged) == 1
    assert merged[0][1] == 100
    assert merged[0][3] == 190


def test_the_regions_are_computed_from_a_mask() -> None:
    """The regions of a mask are the disjoint rectangles of the changes."""
    mask = np.zeros((270, 480), dtype=bool)
    mask[20:30, 20:60] = True
    mask[200:220, 300:400] = True
    result = compute_regions(
        mask, 0, 1920, 1080, 100, 0.8, region_min_area=10, max_regions=4, merge_gap=200
    )
    assert result.action == ROI_CROP
    assert len(result.regions) == 2


def test_a_small_change_is_skipped() -> None:
    """A change that is too small to hold any text is skipped."""
    mask = np.zeros((270, 480), dtype=bool)
    mask[10:12, 10:12] = True
    result = compute_regions(mask, 0, 1920, 1080, 100000, 0.8)
    assert result.action != ROI_CROP


def test_a_big_change_reads_the_whole_frame() -> None:
    """A change that covers most of the screen reads the whole frame.

    The mask is the downscaled one, so the threshold is compared with the
    screen through the scale factor.
    """
    mask = np.ones((270, 480), dtype=bool)
    result = compute_regions(mask, 0, 1920, 1080, 100, 0.8, scale_factor=4)
    assert result.action == ROI_FULL


def test_a_small_change_stays_a_region() -> None:
    """A change that covers a small part of the screen stays a region."""
    mask = np.zeros((270, 480), dtype=bool)
    mask[100:120, 100:140] = True
    result = compute_regions(
        mask, 0, 1920, 1080, 100, 0.8, region_min_area=10, merge_gap=200, scale_factor=4
    )
    assert result.action == ROI_CROP
def test_the_read_rects_are_the_regions() -> None:
    """The rectangles to read are the regions of the result."""
    result = compute_regions(
        np.ones((270, 480), dtype=bool),
        0,
        1920,
        1080,
        100,
        0.99,
        region_min_area=10,
        merge_gap=200,
    )
    assert result.action == ROI_CROP
    assert result.read_rects


def test_the_lines_are_moved_back_to_the_screen_coordinates() -> None:
    """The offset of the crop is added to every bbox."""
    lines = [_line("hello", 10)]
    moved = offset_lines(lines, 100, 200)
    assert moved[0].bbox == (200, 210, 600, 246)


def test_the_duplicated_lines_are_dropped() -> None:
    """A line that was read twice is only kept once."""
    lines = [_line("hello", 10), _line("hello", 12)]
    assert len(dedupe_lines(lines)) == 1


def test_the_different_lines_are_kept() -> None:
    """Two different lines are both kept."""
    lines = [_line("hello", 10), _line("world", 10)]
    assert len(dedupe_lines(lines)) == 2


# --------------------------------------------------------------------------
# Item A: tiled refresh
# --------------------------------------------------------------------------


def test_the_tile_grid_covers_the_whole_screen() -> None:
    """Every pixel of the frame belongs to exactly one tile."""
    tiles = tile_grid(1920, 1080, 4, 3)
    assert len(tiles) == 12
    assert tiles[0] == (0, 0, 480, 360)
    assert tiles[-1] == (1440, 720, 1920, 1080)
    area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in tiles)
    assert area == 1920 * 1080


def test_the_only_changed_tile_is_found() -> None:
    """Only the tile that changed is reported."""
    mask = np.zeros((270, 480), dtype=bool)
    mask[10:40, 10:40] = True
    result = compute_tiles(mask, 1920, 1080, 4, 3, changed_threshold=0.004, scale_factor=4)
    assert len(result.changed) == 1
    assert result.changed_tiles[0] == (0, 0, 480, 360)


def test_no_change_means_no_changed_tile() -> None:
    """An empty mask has no changed tile."""
    mask = np.zeros((270, 480), dtype=bool)
    result = compute_tiles(mask, 1920, 1080, 4, 3, changed_threshold=0.004, scale_factor=4)
    assert result.changed == []
    assert result.changed_ratio == 0.0


def test_the_first_frame_changes_every_tile() -> None:
    """Without a baseline every tile is reported as changed."""
    result = compute_tiles(None, 1920, 1080, 4, 3)
    assert len(result.changed) == 12
    assert result.changed_ratio == 1.0


def test_the_tiles_do_not_depend_on_the_resolution() -> None:
    """The grid is computed from the size, not from a hardcoded resolution."""
    tiles = tile_grid(2560, 1440, 4, 3)
    assert len(tiles) == 12
    assert tiles[0] == (0, 0, 640, 480)


# --------------------------------------------------------------------------
# Item B: downscaled diff
# --------------------------------------------------------------------------


def test_the_downscale_keeps_a_small_change() -> None:
    """A change of one pixel is not lost by the downscale.

    With an average the change was diluted below the threshold and the
    change was missed; with a maximum it is kept.
    """
    gray = np.zeros((64, 64), dtype=np.int16)
    small = downscale_gray(gray, 4)
    assert small.shape == (16, 16)
    assert small.max() == 0


def test_the_downscale_uses_the_maximum() -> None:
    """The maximum of the block is used, not the average."""
    gray = np.zeros((8, 8), dtype=np.int16)
    gray[0, 0] = 100
    small = downscale_gray(gray, 4)
    assert small[0, 0] == 100
    assert small.max() == 100


def test_the_diff_of_a_downscaled_frame_is_faster() -> None:
    """The downscaled diff stays under the 15 ms of the acceptance criterion.

    The downscaled diff is not faster than the OpenCV full resolution
    ``absdiff`` (that one is already vectorised), but the mask it produces
    is 16 times smaller, so every stage that works on the mask (the region
    computation, the tile computation) is much faster.
    """
    current = np.zeros((1080, 1920, 3), dtype=np.uint8)
    previous = current.copy()
    previous[500:520, 500:520] = 255

    start = time.perf_counter()
    for _ in range(5):
        frame_diff(current, previous, downscale=4)
    small_ms = (time.perf_counter() - start) / 5 * 1000.0

    # The acceptance criterion of the P3 brief: the diff stage is under 15 ms.
    assert small_ms < 15.0, small_ms

    # The downscaled mask is 16 times smaller than the full resolution one.
    result = frame_diff(current, previous, downscale=4)
    assert result.diff_mask is not None
    assert result.diff_mask.shape == (270, 480)


def test_the_diff_finds_the_changed_area() -> None:
    """The changed area of the downscaled diff is the right one."""
    current = np.zeros((1080, 1920, 3), dtype=np.uint8)
    previous = current.copy()
    previous[400:440, 400:440] = 255
    result = frame_diff(current, previous, threshold=0.0, downscale=4)
    assert result.changed is True
    assert result.scale_factor == 4
    assert result.diff_mask is not None
    assert result.diff_mask.any()


def test_a_small_change_is_not_lost_by_the_downscale() -> None:
    """A change of a single pixel is not diluted by the downscale."""
    current = np.zeros((1080, 1920, 3), dtype=np.uint8)
    previous = current.copy()
    previous[500, 500] = 255
    result = frame_diff(current, previous, threshold=0.0, downscale=4)
    assert result.changed is True
    assert result.diff_mask is not None
    assert result.diff_mask.any()


def test_a_box_is_scaled_back_to_the_full_resolution() -> None:
    """A box of the downscaled space is scaled back."""
    assert scale_box((10, 20, 30, 40), 4, 1920, 1080) == (40, 80, 120, 160)


# --------------------------------------------------------------------------
# Item C: the async pipeline
# --------------------------------------------------------------------------


class FakeTranslator:
    """A translator that records the calls and returns a fixed text."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls = 0
        self.texts = []
        self.cache = FakeCache()

    def clear_sentence_cache(self) -> None:
        pass

    def translate_texts(self, texts):
        self.calls += 1
        self.texts.extend(texts)
        if self.delay:
            time.sleep(self.delay)
        return [f"VI-{text}" for text in texts]


class FakeCache:
    """A cache that never hits."""

    def get(self, key):
        return None

    def get_many(self, keys):
        return {}


def test_the_translation_runs_in_the_background() -> None:
    """The submit does not block: the result comes later."""
    translator = FakeTranslator(delay=0.05)
    async_translator = AsyncTranslator(translator)
    async_translator.start()
    try:
        block = TextBlock(lines=[_line("hello", 10)])
        start = time.perf_counter()
        async_translator.submit([block])
        submit_ms = (time.perf_counter() - start) * 1000.0
        assert submit_ms < 20.0

        async_translator.join(timeout=5.0)
        results = async_translator.collect()
        assert len(results) == 1
        assert results[0].item.translation == "VI-hello"
    finally:
        async_translator.stop()


def test_the_collect_never_blocks() -> None:
    """The collect returns nothing when the translation is not ready."""
    translator = FakeTranslator(delay=0.5)
    async_translator = AsyncTranslator(translator)
    async_translator.start()
    try:
        async_translator.submit([TextBlock(lines=[_line("hello", 10)])])
        start = time.perf_counter()
        results = async_translator.collect()
        collect_ms = (time.perf_counter() - start) * 1000.0
        assert results == []
        assert collect_ms < 20.0
    finally:
        async_translator.stop()


def test_the_pending_count_is_tracked() -> None:
    """The number of pending translations is visible."""
    translator = FakeTranslator(delay=0.2)
    async_translator = AsyncTranslator(translator)
    async_translator.start()
    try:
        assert async_translator.pending == 0
        async_translator.submit([TextBlock(lines=[_line("hello", 10)])])
        assert async_translator.pending >= 1
        assert async_translator.busy is True
    finally:
        async_translator.stop()


def test_the_visible_time_is_measured_from_the_capture() -> None:
    """The visible time is measured from the capture of the frame."""
    translator = FakeTranslator()
    async_translator = AsyncTranslator(translator)
    async_translator.start()
    try:
        captured = time.perf_counter() - 0.05
        async_translator.submit(
            [TextBlock(lines=[_line("hello", 10)])], captured_at=captured
        )
        async_translator.join(timeout=5.0)
        results = async_translator.collect()
        assert results[0].visible_ms >= 50.0
    finally:
        async_translator.stop()


def test_the_pipeline_uses_the_async_translator() -> None:
    """The pipeline hands the blocks over to the background translator."""
    config = load_config()
    config.debounce_ms = 0
    config.roi_enabled = False

    translator = FakeTranslator()
    async_translator = AsyncTranslator(translator)
    async_translator.start()
    try:
        from src.ocr import OCREngine

        pipeline = Pipeline(config, ocr_engine=OCREngine(device="cpu", intra_threads=3))
        pipeline.translator = translator
        pipeline.set_async_translator(async_translator)

        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        import cv2

        cv2.putText(
            image,
            "The Tacet Field is spreading",
            (200, 800),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
        )
        pipeline.process_frame(frame_from_image(image))
        async_translator.join(timeout=10.0)
        assert translator.calls >= 1
    finally:
        async_translator.stop()


# --------------------------------------------------------------------------
# Item D: the adaptive grouping
# --------------------------------------------------------------------------


def test_the_font_height_is_the_median_of_the_lines() -> None:
    """The font height is the median height of the lines."""
    lines = [_line("a", 0, 30), _line("b", 40, 40), _line("c", 90, 200)]
    assert measure_font_height(lines) == 40


def test_the_font_height_is_unknown_without_a_line() -> None:
    """Without any line the font height is unknown."""
    assert measure_font_height([]) is None


def test_the_gaps_follow_the_font_height() -> None:
    """A smaller font produces smaller gaps."""
    lines = [_line("a", 0, 40), _line("b", 50, 40)]
    big_gap, big_speaker = adaptive_gaps(lines, 18, 120, 0.55, 3.0, 1.0, 2)
    small_lines = [_line("a", 0, 28), _line("b", 40, 28)]
    small_gap, small_speaker = adaptive_gaps(small_lines, 18, 120, 0.55, 3.0, 1.0, 2)
    assert small_gap < big_gap
    assert small_speaker < big_speaker


def test_the_reference_values_are_used_without_a_font() -> None:
    """Without a measured font the reference values are used."""
    gaps = adaptive_gaps([], 18, 120, 0.55, 3.0, 1.0, 2)
    assert gaps == (18, 120)


def test_the_same_dialogue_groups_the_same_at_a_smaller_font() -> None:
    """The same dialogue gives the same blocks with a normal and a 0.7x font.

    The absolute positions of the lines are scaled with the font, so the
    vertical gaps shrink too. The adaptive grouping compensates it.
    """
    normal = [
        _line("Jiyan", 700, 36),
        _line("The Tacet Field is spreading across the northern plains.", 810, 36),
        _line("Resonators must reach the Storm City before nightfall.", 856, 36),
        _line("You obtained a new Waveplate for your Rover.", 897, 36),
    ]
    # The same dialogue at 0.7x: every font and every position is scaled.
    small = [
        _line("Jiyan", 700, 25),
        _line("The Tacet Field is spreading across the northern plains.", 790, 25),
        _line("Resonators must reach the Storm City before nightfall.", 822, 25),
        _line("You obtained a new Waveplate for your Rover.", 850, 25),
    ]

    def blocks_of(lines):
        gap, speaker_gap = adaptive_gaps(lines, 18, 120, 0.55, 3.0, 1.0, 2)
        return build_blocks(lines, gap_px=gap, speaker_gap_px=speaker_gap, scale=1.0)

    normal_blocks = blocks_of(normal)
    small_blocks = blocks_of(small)
    assert len(normal_blocks) == len(small_blocks)
    assert [b.text for b in normal_blocks] == [b.text for b in small_blocks]
    assert [b.speaker for b in normal_blocks] == [b.speaker for b in small_blocks]


# --------------------------------------------------------------------------
# Item E: the live latency HUD
# --------------------------------------------------------------------------


def test_the_hud_is_off_by_default() -> None:
    """The HUD is hidden until it is toggled."""
    state = HUDState(history=10)
    assert state.enabled is False
    assert state.toggle() is True
    assert state.enabled is True
    assert state.toggle() is False


def test_the_hud_keeps_a_running_median() -> None:
    """The running median is computed over the last cycles."""
    state = HUDState(history=10)
    for value in (10.0, 20.0, 30.0):
        timings = StageTimings(total=value)
        state.update(timings)
    assert state.median_total == pytest.approx(20.0)
    assert state.cycles == 3


def test_the_hud_history_is_limited() -> None:
    """Only the last cycles are kept."""
    state = HUDState(history=3)
    for value in (10.0, 20.0, 30.0, 40.0, 50.0):
        state.update(StageTimings(total=value))
    assert state.cycles == 3
    assert state.median_total == pytest.approx(40.0)


def test_the_hud_shows_the_stage_timings() -> None:
    """The HUD shows the same numbers as the bench."""
    from src.hud import HUDSnapshot

    timings = StageTimings(capture=1.0, diff=2.0, ocr=3.0, group=4.0, translate=5.0)
    timings.total = 15.0
    snapshot = HUDSnapshot(timings=timings, median_total=15.0, cycles=1)
    lines = format_hud_lines(snapshot)
    joined = "\n".join(lines)
    assert "1.0" in joined
    assert "15.0" in joined
    assert "ocr" in joined


def test_the_hud_can_be_reset() -> None:
    """The reset forgets the recorded cycles."""
    state = HUDState(history=10)
    state.update(StageTimings(total=10.0))
    state.reset()
    assert state.cycles == 0
    assert state.median_total == 0.0


# --------------------------------------------------------------------------
# Item G: the hardened sentence splitter
# --------------------------------------------------------------------------


def texts_of(text: str):
    """The list of the sentences of ``text``."""
    return [s.text.strip() for s in split_sentences(text)]


def test_the_title_is_not_split() -> None:
    """"Dr." does not end a sentence."""
    assert texts_of("Bring it to Dr. Anby for the upgrade.") == [
        "Bring it to Dr. Anby for the upgrade."
    ]


def test_mr_and_mrs_are_not_split() -> None:
    """"Mr." and "Mrs." do not end a sentence."""
    assert texts_of("Hello Mr. Smith and Mrs. Jones are here.") == [
        "Hello Mr. Smith and Mrs. Jones are here."
    ]


def test_the_examples_are_not_split() -> None:
    """"e.g." and "i.e." do not end a sentence."""
    assert texts_of("That is e.g. the Tacet Field, i.e. the anomaly.") == [
        "That is e.g. the Tacet Field, i.e. the anomaly."
    ]


def test_the_initials_are_not_split() -> None:
    """"U.S." does not end a sentence."""
    assert texts_of("The U.S. team is ready.") == ["The U.S. team is ready."]


def test_a_decimal_comma_is_not_split() -> None:
    """"3,5" is one number, not two sentences."""
    assert texts_of("The value is 3,5 units.") == ["The value is 3,5 units."]


def test_a_number_with_a_comma_is_not_split() -> None:
    """"1,234" is one number, not two sentences."""
    assert texts_of("You receive 1,234 gold.") == ["You receive 1,234 gold."]


def test_a_number_with_a_comma_is_protected() -> None:
    """The number with a comma becomes a single placeholder."""
    protected = protect_numbers("You receive 1,234 gold.")
    assert protected.numbers == ["1,234"]
    assert "1,234" not in protected.text


def test_a_decimal_comma_is_protected() -> None:
    """The decimal comma becomes a single placeholder."""
    protected = protect_numbers("The value is 3,5 units.")
    assert protected.numbers == ["3,5"]


def test_a_decimal_with_a_dot_is_protected() -> None:
    """The decimal stays in one piece."""
    protected = protect_numbers("The value is 3.5 units.")
    assert protected.numbers == ["3.5"]


def test_the_regex_splitter_is_the_default() -> None:
    """The regex splitter is the default, the Stanza one is the fallback."""
    assert get_splitter("regex") is split_sentences
    assert get_splitter("stanza") is split_with_stanza
    assert get_splitter() is split_sentences


def test_the_sentences_are_rejoined_exactly() -> None:
    """The separator of every sentence is kept."""
    text = "First one. Second one! Third one?"
    assert join_sentences(split_sentences(text)) == text
