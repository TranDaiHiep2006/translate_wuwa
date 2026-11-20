"""Tests for the SQLite translation cache (hit / miss / normalization)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache import TranslationCache, normalize


@pytest.fixture()
def cache(tmp_path: Path):
    """A fresh cache backed by a temporary database file."""
    db = TranslationCache(tmp_path / "cache.db")
    yield db
    db.close()


def test_normalize_strips_and_collapses_whitespace() -> None:
    """Normalization removes the padding and collapses the inner spaces."""
    assert normalize("  Hello   world  ") == "Hello world"
    assert normalize("Line1\n\tLine2 ") == "Line1 Line2"


def test_normalize_keeps_the_case() -> None:
    """Two texts that only differ in case are different cache keys."""
    assert normalize("Hello World") != normalize("hello world")


def test_cache_miss_then_hit(cache: TranslationCache) -> None:
    """An unknown source is a miss, after storing it becomes a hit."""
    assert cache.get("unknown sentence") is None
    cache.set("unknown sentence", "Mot chua biet")
    assert cache.get("unknown sentence") == "Mot chua biet"


def test_cache_hit_uses_the_normalized_key(cache: TranslationCache) -> None:
    """A source is found even when the whitespace differs."""
    cache.set("  Hello   world ", "Xin chao")
    assert cache.get("Hello world") == "Xin chao"
    assert cache.get("\nHello world\t") == "Xin chao"


def test_cache_set_many_and_get_many(cache: TranslationCache) -> None:
    """Batch insert and batch lookup work together."""
    cache.set_many([("one", "mot"), ("two", "hai")])
    found = cache.get_many(["one", "two", "three"])
    assert found["one"] == "mot"
    assert found["two"] == "hai"
    assert "three" not in found


def test_history_table_stores_the_entries(cache: TranslationCache) -> None:
    """Every translated block is recorded in the history table."""
    cache.add_history("Hello", "Xin chao", "10,20,30,40")
    rows = cache.history_entries()
    assert len(rows) == 1
    assert rows[0][1] == "Hello"
    assert rows[0][2] == "Xin chao"
    assert rows[0][3] == "10,20,30,40"
