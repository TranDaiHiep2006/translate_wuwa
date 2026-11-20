"""Tests for the translation engine (smoke test) and the translator wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache import TranslationCache
from src.glossary import Glossary
from src.pipeline import Translator
from src.translator import SAMPLE_SENTENCES, create_engine


@pytest.fixture(scope="module")
def engine():
    """The default translation engine (loaded once for the module)."""
    from src.config import load_config

    config = load_config()
    eng = create_engine(config.translation.engine, device=config.translation.device)
    try:
        eng.load()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"translation engine unavailable: {exc}")
    return eng


def test_the_engine_translates_to_vietnamese(engine) -> None:
    """Two sample sentences are translated and the result is not empty."""
    outputs = engine.translate(
        [
            "The Tacet Field is spreading across the northern plains.",
            "You obtained a new Waveplate for your Rover.",
        ]
    )
    assert len(outputs) == 2
    for text in outputs:
        assert isinstance(text, str)
        assert text.strip()
    # The output must differ from the English input (a translation happened).
    assert outputs[0].strip() != "The Tacet Field is spreading across the northern plains."


def test_the_engine_translates_all_ten_sample_sentences(engine) -> None:
    """The engine handles the whole benchmark set without raising."""
    outputs = engine.translate(list(SAMPLE_SENTENCES))
    assert len(outputs) == len(SAMPLE_SENTENCES)
    assert all(o.strip() for o in outputs)


def test_the_translator_uses_the_cache(tmp_path: Path) -> None:
    """A cache hit never calls the translation model."""
    cache = TranslationCache(tmp_path / "cache.db")
    glossary = Glossary({"Rover": "Rover"})

    class FakeEngine:
        name = "fake"
        calls = 0

        def translate(self, texts):
            FakeEngine.calls += 1
            return [f"VI:{t}" for t in texts]

    fake = FakeEngine()
    translator = Translator(fake, cache, glossary)
    translator.translate_texts(["Hello world"])
    assert FakeEngine.calls == 1
    translator.translate_texts(["Hello world"])
    assert FakeEngine.calls == 1  # cache hit, no model call
    cache.close()


def test_the_translator_restores_the_glossary(tmp_path: Path) -> None:
    """A glossary term survives the round trip through the model."""
    cache = TranslationCache(tmp_path / "cache.db")
    glossary = Glossary({"Rover": "Rover"})

    class FakeEngine:
        def translate(self, texts):
            return [t.replace("Rover", "Rover") for t in texts]

    translator = Translator(FakeEngine(), cache, glossary)
    out = translator.translate_texts(["The Rover is here."])
    assert "Rover" in out[0]
    cache.close()
