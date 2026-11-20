"""SQLite cache and history storage (file ``data/cache.db``).

Two tables:

* ``cache``    - translation cache: ``source`` (normalized) -> ``translation``.
* ``history``  - every translated block ever rendered, with its timestamp,
  source text, translation and bounding box.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalize a source string for cache lookups.

    Strips leading/trailing whitespace and collapses internal whitespace
    runs into single spaces. The letter case is kept, so two different
    sentences that only differ in case are cached separately.
    """
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


class TranslationCache:
    """SQLite backed translation cache (thread safe)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    source TEXT PRIMARY KEY,
                    translation TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    source TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    bbox TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp);
                """
            )
            self._conn.commit()

    # -- cache -------------------------------------------------------------
    def get(self, source: str) -> Optional[str]:
        """Return the cached translation for ``source`` or None."""
        key = normalize(source)
        if not key:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT translation FROM cache WHERE source = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set(self, source: str, translation: str) -> None:
        """Store a translation in the cache."""
        key = normalize(source)
        if not key:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (source, translation, created_at) "
                "VALUES (?, ?, ?)",
                (key, translation, time.time()),
            )
            self._conn.commit()

    def get_many(self, sources: Iterable[str]) -> dict[str, Optional[str]]:
        """Look up several sources at once. Returns ``{normalized: translation}``."""
        keys = [normalize(s) for s in sources if normalize(s)]
        if not keys:
            return {}
        placeholders = ",".join("?" * len(keys))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT source, translation FROM cache WHERE source IN ({placeholders})",
                keys,
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def set_many(self, items: Iterable[Tuple[str, str]]) -> None:
        """Store several ``(source, translation)`` pairs at once."""
        rows = [
            (normalize(src), tr, time.time())
            for src, tr in items
            if normalize(src) and tr
        ]
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO cache (source, translation, created_at) "
                "VALUES (?, ?, ?)",
                rows,
            )
            self._conn.commit()

    # -- history -----------------------------------------------------------
    def add_history(
        self, source: str, translation: str, bbox: str, timestamp: Optional[float] = None
    ) -> None:
        """Record a translated block in the history table."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO history (timestamp, source, translation, bbox) "
                "VALUES (?, ?, ?, ?)",
                (
                    timestamp if timestamp is not None else time.time(),
                    source,
                    translation,
                    bbox,
                ),
            )
            self._conn.commit()

    def history_entries(self, limit: int = 100) -> List[Tuple[float, str, str, str]]:
        """Return the most recent history entries."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, source, translation, bbox FROM history "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - defensive
                pass
