"""End-to-end tests of the pipeline on the sample images."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache import TranslationCache
from src.capture import frame_from_image
from src.config import load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.pipeline import Pipeline, Translator
from src.translator import create_engine


@pytest.fixture(scope="module")
def engine():
    """The real translation engine, loaded once for the whole module."""
    config = load_config()
    eng = create_engine(config.translation.engine, device=config.translation.device)
    try:
        eng.load()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"translation engine unavailable: {exc}")
    return eng


@pytest.fixture()
def pipeline_parts(tmp_path, engine):
    """A pipeline with its own fresh cache (so the cache state is isolated)."""
    config = load_config()
    config.debounce_ms = 0
    cache = TranslationCache(tmp_path / "cache.db")
    glossary = Glossary.from_file(config.glossary_path)
    translator = Translator(engine, cache, glossary)
    ocr = OCREngine(device=config.translation.device)
    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    yield pipeline, cache
    cache.close()


def test_the_dialogue_image_returns_a_translated_block(
    pipeline_parts, dialogue_image
) -> None:
    """The pipeline on the dialogue fixture returns at least one translated block."""
    pipeline, _ = pipeline_parts
    frame = frame_from_image(dialogue_image)
    result = pipeline.process_frame(frame)
    assert len(result.blocks) >= 1
    assert all(b.translation.strip() for b in result.blocks)


def test_the_speaker_name_is_kept_and_formatted(
    pipeline_parts, dialogue_image
) -> None:
    """The speaker name stays untranslated and is shown as ``Name: translation``."""
    pipeline, _ = pipeline_parts
    frame = frame_from_image(dialogue_image)
    result = pipeline.process_frame(frame)
    speakers = [b.speaker for b in result.blocks if b.speaker]
    assert speakers, "no speaker name was detected on the dialogue fixture"
    for block in result.blocks:
        if block.speaker:
            assert block.display_text.startswith(f"{block.speaker}: ")


def test_the_numbers_are_filtered_out(pipeline_parts, menu_image) -> None:
    """The damage numbers of the menu fixture are never translated."""
    pipeline, _ = pipeline_parts
    frame = frame_from_image(menu_image)
    result = pipeline.process_frame(frame)
    for block in result.blocks:
        assert "1250" not in block.block.text
        assert "+8%" not in block.block.text
        assert "12345" not in block.block.text
    assert result.filter_report.dropped_numbers > 0


def test_the_overlay_position_follows_the_resolution(
    pipeline_parts, dialogue_image, scaled_image
) -> None:
    """The bbox scales with the resolution - nothing is hardcoded."""
    pipeline, _ = pipeline_parts
    frame_small = frame_from_image(dialogue_image)
    result_small = pipeline.process_frame(frame_small)

    pipeline.reset()
    frame_big = frame_from_image(scaled_image)
    result_big = pipeline.process_frame(frame_big)

    assert result_small.blocks and result_big.blocks
    small = result_small.blocks[0].block.bbox
    big = result_big.blocks[0].block.bbox
    # The 2560x1600 fixture is the 1920x1080 one scaled by 2560/1920 and
    # padded at the bottom, so every coordinate must scale by that factor.
    ratio = 2560 / 1920
    assert big[0] == pytest.approx(small[0] * ratio, abs=16)
    assert big[1] == pytest.approx(small[1] * ratio, abs=16)
    assert big[2] == pytest.approx(small[2] * ratio, abs=16)
    assert big[3] == pytest.approx(small[3] * ratio, abs=16)


def test_the_second_run_is_a_cache_hit(pipeline_parts, dialogue_image) -> None:
    """Running the same image twice hits the cache and is clearly faster."""
    pipeline, cache = pipeline_parts
    frame = frame_from_image(dialogue_image)

    result1 = pipeline.process_frame(frame)
    assert result1.cache_misses >= 1
    assert result1.newly_translated

    pipeline.reset()
    result2 = pipeline.process_frame(frame)
    assert result2.cache_misses == 0
    assert result2.cache_hits >= 1
    assert result2.timings.translate < result1.timings.translate
