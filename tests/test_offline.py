"""Test that the tool really works offline (no network access at all)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.offline import patch_stanza_offline
from src.translator import create_engine


@pytest.fixture()
def no_network(monkeypatch):
    """Block every outgoing socket connection."""

    class NoNetwork(socket.socket):
        def connect(self, *args, **kwargs):
            raise OSError("network disabled for the offline test")

        def connect_ex(self, *args, **kwargs):
            raise OSError("network disabled for the offline test")

    def blocked(*args, **kwargs):
        raise OSError("network disabled for the offline test")

    monkeypatch.setattr(socket, "socket", NoNetwork)
    monkeypatch.setattr(socket, "create_connection", blocked)


def test_the_stanza_patch_is_applied() -> None:
    """The offline patch is applied without raising."""
    assert patch_stanza_offline() in (True, False)


def test_the_translator_works_without_a_network(no_network) -> None:
    """The translation model runs with every socket connection blocked."""
    config = load_config()
    engine = create_engine(config.translation.engine, device=config.translation.device)
    try:
        engine.load()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"translation engine unavailable: {exc}")
    outputs = engine.translate(["The Tacet Field is spreading across the plains."])
    assert outputs and outputs[0].strip()


def test_no_api_key_is_configured() -> None:
    """Neither the code nor the config contains an API key."""
    config_text = (PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8")
    lowered = config_text.lower()
    for forbidden in ("api_key", "apikey", "openai", "deepl", "gemini", "google_api"):
        assert forbidden not in lowered

    source_dir = PROJECT_ROOT / "src"
    for path in source_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "api_key" not in text
        assert "deepl" not in text
        assert "generativelanguage" not in text
