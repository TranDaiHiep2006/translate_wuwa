"""Session history: append-only text files in ``data/sessions/``.

One file per session. The file name is ``YYYY-MM-DD_HH-MM-SS.txt`` based on the
session start time. Each translated block is appended exactly once.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class SessionLog:
    """Appends translated blocks to a session history file."""

    def __init__(self, sessions_dir: str | Path) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = None
        self._path: Optional[Path] = None
        self._written: set[str] = set()
        self._start_time: Optional[datetime] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self, now: Optional[datetime] = None) -> Path:
        """Open a new session file and return its path."""
        start = now or datetime.now()
        name = start.strftime("%Y-%m-%d_%H-%M-%S.txt")
        path = self.sessions_dir / name
        # Avoid collisions if a session is started within the same second.
        counter = 1
        while path.exists():
            name = start.strftime("%Y-%m-%d_%H-%M-%S") + f"_{counter}.txt"
            path = self.sessions_dir / name
            counter += 1
        self._file = path.open("w", encoding="utf-8")
        self._path = path
        self._written.clear()
        self._start_time = start
        return path

    def close(self) -> Optional[Path]:
        """Close the current session file."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                finally:
                    self._file = None
            path = self._path
            self._path = None
            self._written.clear()
            return path

    def read_entries(self, path: str | Path) -> List[str]:
        """Read back the entries of a session file."""
        file_path = Path(path)
        if not file_path.exists():
            return []
        raw = file_path.read_text(encoding="utf-8")
        return [e for e in raw.split("\n\n") if e.strip()]
    # -- writing -----------------------------------------------------------
    def append(
        self,
        source: str,
        translation: str,
        speaker: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Optional[str]:
        """Append one translated block to the session file.

        Returns the written entry, or None when the block was already written
        (every block is appended exactly once).
        """
        key = f"{speaker or ''}|{source.strip()}"
        with self._lock:
            if self._file is None:
                return None
            if key in self._written:
                return None
            self._written.add(key)
            stamp = datetime.fromtimestamp(timestamp or time.time())
            head = f"[{stamp.strftime('%H:%M:%S')}]"
            if speaker:
                head += f" {speaker}: {translation}"
            else:
                head += f" {translation}"
            entry = f"{head}\n  EN: {source.strip()}"
            self._file.write(entry + "\n\n")
            self._file.flush()
            return entry

    # -- inspection --------------------------------------------------------
    @property
    def path(self) -> Optional[Path]:
        """Path of the currently open session file."""
        return self._path

    @property
    def active(self) -> bool:
        """True when a session file is open."""
        return self._file is not None

    def entries(self) -> List[str]:
        """Return the entries of the current (or last) session file."""
        if self._path is None:
            return []
        return self.read_entries(self._path)
