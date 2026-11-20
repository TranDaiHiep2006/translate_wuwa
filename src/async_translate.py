"""Asynchronous translation stage (item C of P3).

The P2 pipeline was strictly sequential: the overlay had to wait for the
whole OCR + translation cycle before it could show anything. P3 overlaps the
two:

* the **OCR of frame N** runs while the **translation of frame N-1** is still
  being computed;
* the last translation stays on screen while the new one is computed - the
  overlay is never cleared just because a new frame is being processed.

The debounce, the cache and the session history behave exactly as before: a
block is written to the history file exactly once.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .ocr import OCRLine
from .pipeline import TextBlock, TranslatedBlock

logger = logging.getLogger(__name__)


@dataclass
class TranslationJob:
    """One block waiting to be translated."""

    block: TextBlock
    index: int
    created_at: float = field(default_factory=time.perf_counter)
    # The timestamp of the frame the block was read from. It is used to
    # measure how long the translation took to become visible on screen.
    captured_at: float = 0.0


@dataclass
class TranslationOutcome:
    """The result of a translation job."""

    item: TranslatedBlock
    index: int
    queued_at: float
    finished_at: float = field(default_factory=time.perf_counter)
    # The timestamp of the frame the block was read from.
    captured_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        """How long the translation took (from the queue to the result)."""
        return (self.finished_at - self.queued_at) * 1000.0

    @property
    def visible_ms(self) -> float:
        """How long it took from the capture to the visible translation.

        This is the metric of the P3 acceptance criterion: the time from
        the capture of the frame until the translation is really on screen.
        """
        if not self.captured_at:
            return self.duration_ms
        return (self.finished_at - self.captured_at) * 1000.0


class AsyncTranslator:
    """Runs the translation of the blocks in a background thread.

    The OCR thread only *queues* the blocks that need a translation; the
    worker thread calls the model. The results are collected by the caller
    with :meth:`collect`, which never blocks.
    """

    def __init__(self, translator, max_queue: int = 8) -> None:
        self._translator = translator
        self._max_queue = int(max_queue)
        self._lock = threading.Lock()
        self._queue: List[TranslationJob] = []
        self._results: List[TranslationOutcome] = []
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._in_flight = 0
        # The number of batches that were translated.
        self.completed = 0
        # The number of blocks that failed to be translated.
        self.failures = 0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Start the background translation thread."""
        if self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run, name="translate", daemon=True
        )
        self._worker.start()

    def stop(self) -> None:
        """Ask the background thread to stop."""
        self._stop.set()
        self._wake.set()

    # -- queueing ----------------------------------------------------------
    def submit(
        self, blocks: List[TextBlock], captured_at: float = 0.0
    ) -> None:
        """Queue the blocks that need a translation.

        The blocks are translated in one batch (the model is much faster with
        a batch than with one sentence at a time). ``captured_at`` is the
        timestamp of the frame the blocks were read from; it is used to
        measure the time until the translation is visible on screen.
        """
        if not blocks:
            return
        with self._lock:
            self._queue.extend(
                TranslationJob(block=block, index=index, captured_at=captured_at)
                for index, block in enumerate(blocks)
            )
        self._wake.set()

    @property
    def pending(self) -> int:
        """The number of blocks that are waiting or being translated."""
        with self._lock:
            return len(self._queue) + self._in_flight

    @property
    def busy(self) -> bool:
        """True when a translation is in flight."""
        return self.pending > 0

    # -- results -----------------------------------------------------------
    def collect(self) -> List[TranslationOutcome]:
        """Return the finished translations and remove them from the queue.

        Never blocks: the results that are not ready yet stay in the worker.
        """
        with self._lock:
            done = self._results
            self._results = []
        return done

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        """The body of the background thread."""
        while not self._stop.is_set():
            with self._lock:
                batch = self._queue[: self._max_queue]
                del self._queue[: len(batch)]
                self._in_flight = len(batch)

            if not batch:
                self._wake.wait(timeout=0.05)
                self._wake.clear()
                continue

            texts = [job.block.text for job in batch]
            failed = False
            try:
                self._translator.clear_sentence_cache()
                translations = self._translator.translate_texts(texts)
            except Exception:  # pragma: no cover - keep the tool alive
                logger.exception("the translation failed")
                translations = [""] * len(texts)
                failed = True

            now = time.perf_counter()
            with self._lock:
                for job, translation in zip(batch, translations):
                    self._results.append(
                        TranslationOutcome(
                            item=TranslatedBlock(
                                block=job.block,
                                translation=translation,
                                speaker=job.block.speaker,
                                from_cache=False,
                            ),
                            index=job.index,
                            queued_at=job.created_at,
                            finished_at=now,
                            captured_at=job.captured_at,
                        )
                    )
                self._in_flight = 0
                self.completed += 1
                if failed:
                    self.failures += 1

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait until the queue is empty and no translation is in flight.

        Only used by the tests and by the shutdown sequence: the normal loop
        never waits, it only collects the finished results.
        """
        deadline = None if timeout is None else time.perf_counter() + timeout
        while self.busy:
            if deadline is not None and time.perf_counter() > deadline:
                return
            time.sleep(0.005)
