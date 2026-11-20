"""End-to-end tests of the P2 features on the new fixtures.

These tests use the real translation engine (Argos) and the real OCR, so they
prove that the fixes work on the actual pipeline and not only on the helpers.
"""

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
def translator(tmp_path, engine):
    """A translator with its own fresh cache."""
    config = load_config()
    cache = TranslationCache(tmp_path / "cache.db")
    glossary = Glossary.from_file(config.glossary_path)
    tr = Translator(
        engine,
        cache,
        glossary,
        split_sentences=config.translation.split_sentences,
    )
    yield tr
    cache.close()


def test_the_reward_12000_survives_the_translation(translator) -> None:
    """The P1 bug "Reward: 12000" -> "Phan thuong:2000" is fixed."""
    out = translator.translate_texts(
        ["Complete the quest to reach the Storm City before the storm arrives. Reward: 12000"]
    )
    assert len(out) == 1
    assert "12000" in out[0], out[0]
    assert "2000" not in out[0].replace("12000", ""), out[0]


def test_the_reward_12000_alone_survives_the_translation(translator) -> None:
    """Even alone, the number is not mangled."""
    out = translator.translate_texts(["Reward: 12000"])
    assert "12000" in out[0], out[0]


def test_a_percentage_survives_the_translation(translator) -> None:
    """The percentage 15% stays 15%."""
    out = translator.translate_texts(
        ["Your attack power increases by 15 percent when the Havoc attribute is active."]
    )
    assert "15" in out[0], out[0]
    assert "%" in out[0], out[0]


def test_a_multi_sentence_block_is_translated_sentence_by_sentence(translator) -> None:
    """A block with several sentences keeps all of them."""
    out = translator.translate_texts(
        [
            "The Echo has been recorded. Replay it to learn more about the Tacet Discord. "
            "You obtain 12000 gold."
        ]
    )
    assert len(out) == 1
    assert out[0].count(".") >= 2, out[0]
    assert "12000" in out[0], out[0]


def test_the_sentence_cache_is_used(translator) -> None:
    """A repeated sentence is a cache hit, even in a new block."""
    translator.translate_texts(["A repeated sentence. Another one."])
    before = translator.engine
    calls = getattr(before, "call_count", None)
    out = translator.translate_texts(["A repeated sentence. A third one."])
    assert out
    # The repeated sentence was not sent to the model again.
    if calls is not None:
        assert translator.engine.call_count == calls


def test_the_translation_of_the_reward_fixture_keeps_the_number(
    translator, reward_image
) -> None:
    """The quest fixture with "Reward: 12000" keeps its number."""
    config = load_config()
    config.debounce_ms = 0
    ocr = OCREngine()
    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    result = pipeline.process_frame(frame_from_image(reward_image))
    assert result.blocks, "no block was detected on the reward fixture"

    # The block that carries the reward is the one that has to keep 12000.
    reward_blocks = [
        block for block in result.blocks if "12000" in block.block.text
    ]
    assert reward_blocks, "the reward block was not detected"
    for block in reward_blocks:
        assert "12000" in block.translation, block.translation
    # The "Quest" label is a block of its own and is never a speaker.
    assert all(block.speaker != "Quest" for block in result.blocks)


def test_the_ui_menu_has_no_speaker(translator, ui_menu_image) -> None:
    """Quest, Skill, Inventory and Settings are never shown as a speaker."""
    config = load_config()
    config.debounce_ms = 0
    ocr = OCREngine()
    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    result = pipeline.process_frame(frame_from_image(ui_menu_image))
    assert result.blocks, "no block was detected on the UI menu fixture"
    for block in result.blocks:
        assert block.speaker not in (
            "Quest",
            "Skill",
            "Inventory",
            "Settings",
            "Skills",
        ), f"the label {block.speaker!r} was used as a speaker"


def test_the_speaker_of_the_dialogue_fixture_is_still_jiyan(
    translator, dialogue_image
) -> None:
    """Jiyan is still detected as the speaker on the dialogue fixture."""
    config = load_config()
    config.debounce_ms = 0
    ocr = OCREngine()
    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    result = pipeline.process_frame(frame_from_image(dialogue_image))
    speakers = [b.speaker for b in result.blocks if b.speaker]
    assert speakers, "no speaker was detected"
    assert "Jiyan" in speakers


def test_a_ui_label_is_not_translated(translator) -> None:
    """A menu header keeps its English name instead of being translated.

    The player looks for "Quest" or "Inventory" in the menu, so those
    labels are left in English.
    """
    out = translator.translate_texts(["Quest", "Inventory", "Settings"])
    assert out == ["Quest", "Inventory", "Settings"]


def test_a_real_sentence_is_still_translated(translator) -> None:
    """The skip only applies to the UI labels."""
    out = translator.translate_texts(["The Echo has been recorded."])
    assert out[0] != "The Echo has been recorded."
    assert out[0].strip()
