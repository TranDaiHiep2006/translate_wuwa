"""The pipeline: connect capture -> diff -> OCR -> filter -> group -> debounce
-> cache -> glossary -> translate -> overlay.

The pipeline measures the time spent in every stage so ``scripts/bench.py`` can
print real numbers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .cache import TranslationCache, normalize
from .capture import Frame
from .change import frame_diff
from .config import Config
from .filter import FilterReport, filter_lines
from .glossary import Glossary
from .grouping import TextBlock, build_blocks
from .ocr import OCREngine
from .translator import BaseEngine

logger = logging.getLogger(__name__)


@dataclass
class StageTimings:
    """Time spent in every stage of one pipeline iteration (milliseconds)."""

    capture: float = 0.0
    diff: float = 0.0
    ocr: float = 0.0
    filter: float = 0.0
    group: float = 0.0
    translate: float = 0.0
    render: float = 0.0
    total: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "capture": round(self.capture, 2),
            "diff": round(self.diff, 2),
            "ocr": round(self.ocr, 2),
            "filter": round(self.filter, 2),
            "group": round(self.group, 2),
            "translate": round(self.translate, 2),
            "render": round(self.render, 2),
            "total": round(self.total, 2),
        }


@dataclass
class TranslatedBlock:
    """A block with its Vietnamese translation."""

    block: TextBlock
    translation: str
    speaker: Optional[str] = None
    from_cache: bool = False

    @property
    def display_text(self) -> str:
        if self.speaker:
            return f"{self.speaker}: {self.translation}"
        return self.translation


@dataclass
class PipelineResult:
    """The result of one pipeline iteration."""

    blocks: List[TranslatedBlock] = field(default_factory=list)
    timings: StageTimings = field(default_factory=StageTimings)
    frame_changed: bool = True
    filter_report: FilterReport = field(default_factory=FilterReport)
    cache_hits: int = 0
    cache_misses: int = 0
    newly_translated: List[TranslatedBlock] = field(default_factory=list)


class Translator:
    """Wraps a translation engine with glossary protection and caching."""

    def __init__(
        self,
        engine: BaseEngine,
        cache: TranslationCache,
        glossary: Glossary,
    ) -> None:
        self.engine = engine
        self.cache = cache
        self.glossary = glossary

    def translate_texts(self, texts: Sequence[str]) -> List[str]:
        """Translate a batch of texts, using the cache when possible.

        Returns the translations in the same order as ``texts``.
        """
        if not texts:
            return []

        normalized = [normalize(t) for t in texts]
        cached = self.cache.get_many(normalized)

        results: List[Optional[str]] = [None] * len(texts)
        misses: List[Tuple[int, str]] = []
        for index, key in enumerate(normalized):
            hit = cached.get(key)
            if hit is not None:
                results[index] = hit
            else:
                misses.append((index, texts[index]))

        if misses:
            protected: List[str] = []
            restore_maps: List[Dict[str, str]] = []
            for _, original in misses:
                prot, restore = self.glossary.protect(original)
                protected.append(prot)
                restore_maps.append(restore)
            raw = self.engine.translate(protected)
            new_items = []
            for (index, original), translated, restore in zip(misses, raw, restore_maps):
                restored = self.glossary.restore(translated, restore)
                results[index] = restored
                new_items.append((normalize(original), restored))
            self.cache.set_many(new_items)

        return [r if r is not None else "" for r in results]


class Pipeline:
    """The full translation pipeline."""

    def __init__(
        self,
        config: Config,
        ocr_engine: Optional[OCREngine] = None,
        translator: Optional[Translator] = None,
    ) -> None:
        self.config = config
        self.ocr_engine = ocr_engine or OCREngine(device=config.translation.device)
        self.translator = translator
        self._previous_frame: Optional[np.ndarray] = None
        # block key -> first time we saw this block (debounce bookkeeping)
        self._pending: Dict[str, float] = {}
        # block key -> last translated result (kept on screen while stable)
        self._shown: Dict[str, TranslatedBlock] = {}

    # -- helpers -----------------------------------------------------------
    def _scale(self, screen_height: int) -> float:
        """Scale factor relative to the 1080p reference height."""
        return screen_height / 1080.0

    def _debounce_ready(self, key: str, now: float) -> bool:
        """Return True when the block has been stable long enough."""
        debounce_s = self.config.debounce_ms / 1000.0
        seen_at = self._pending.setdefault(key, now)
        return (now - seen_at) >= debounce_s

    def reset(self) -> None:
        """Forget the previous frame, the debounce state and the shown blocks."""
        self._previous_frame = None
        self._pending.clear()
        self._shown.clear()

    # -- main --------------------------------------------------------------
    def process_frame(self, frame: Frame, capture_ms: float = 0.0) -> PipelineResult:
        """Run the pipeline on a captured frame."""
        timings = StageTimings()
        timings.capture = capture_ms
        total_start = time.perf_counter()

        scale = self._scale(frame.height)

        # -- change detection ------------------------------------------------
        t0 = time.perf_counter()
        diff = frame_diff(
            frame.image,
            self._previous_frame,
            threshold=self.config.diff_threshold,
        )
        timings.diff = (time.perf_counter() - t0) * 1000.0

        if not diff.changed:
            self._previous_frame = frame.image.copy()
            timings.total = (time.perf_counter() - total_start) * 1000.0
            result = PipelineResult(frame_changed=False)
            result.timings = timings
            return result

        # -- OCR -------------------------------------------------------------
        t0 = time.perf_counter()
        lines = self.ocr_engine.read(frame.image)
        timings.ocr = (time.perf_counter() - t0) * 1000.0

        # -- filter ----------------------------------------------------------
        t0 = time.perf_counter()
        kept, report = filter_lines(
            lines,
            conf_min=self.config.ocr_conf_min,
            min_chars=self.config.min_line_chars,
        )
        timings.filter = (time.perf_counter() - t0) * 1000.0

        # -- grouping --------------------------------------------------------
        t0 = time.perf_counter()
        blocks = build_blocks(
            kept,
            gap_px=self.config.group_gap_px,
            speaker_gap_px=self.config.speaker_gap_px,
            scale=scale,
            max_words=self.config.speaker_max_words,
        )
        timings.group = (time.perf_counter() - t0) * 1000.0

        # -- debounce --------------------------------------------------------
        now = time.perf_counter()
        ready_blocks: List[TextBlock] = []
        waiting: List[TextBlock] = []
        for block in blocks:
            if self._debounce_ready(block.key, now):
                ready_blocks.append(block)
            else:
                waiting.append(block)

        # -- cache + translate ------------------------------------------------
        t0 = time.perf_counter()
        results: List[TranslatedBlock] = []
        newly: List[TranslatedBlock] = []
        hits = 0
        misses = 0

        to_translate: List[Tuple[int, TextBlock]] = []
        for block in ready_blocks:
            key = block.key
            previous = self._shown.get(key)
            if previous is not None and previous.block.text == block.text:
                # Nothing changed: reuse the translation, no model call.
                results.append(
                    TranslatedBlock(
                        block=block,
                        translation=previous.translation,
                        speaker=previous.speaker,
                        from_cache=True,
                    )
                )
                hits += 1
                continue
            cached = (
                self.translator.cache.get(normalize(block.text))
                if self.translator is not None
                else None
            )
            if cached is not None:
                hits += 1
                item = TranslatedBlock(
                    block=block, translation=cached, speaker=block.speaker, from_cache=True
                )
                results.append(item)
                self._shown[key] = item
            else:
                misses += 1
                to_translate.append((len(results), block))
                results.append(
                    TranslatedBlock(block=block, translation="", speaker=block.speaker)
                )

        if to_translate and self.translator is not None:
            translated = self.translator.translate_texts(
                [b.text for _, b in to_translate]
            )
            for position, (index, block) in enumerate(to_translate):
                item = TranslatedBlock(
                    block=block,
                    translation=translated[position],
                    speaker=block.speaker,
                    from_cache=False,
                )
                results[index] = item
                self._shown[block.key] = item
                newly.append(item)
        timings.translate = (time.perf_counter() - t0) * 1000.0

        # Blocks that are still settling keep their previous translation.
        for block in waiting:
            previous = self._shown.get(block.key)
            if previous is not None:
                results.append(
                    TranslatedBlock(
                        block=block,
                        translation=previous.translation,
                        speaker=previous.speaker,
                        from_cache=True,
                    )
                )

        # Drop the blocks that disappeared from the screen.
        current_keys = {b.key for b in blocks}
        for stale in [k for k in self._shown if k not in current_keys]:
            self._shown.pop(stale, None)

        self._previous_frame = frame.image.copy()

        timings.total = (time.perf_counter() - total_start) * 1000.0
        result = PipelineResult(
            blocks=results,
            timings=timings,
            frame_changed=True,
            filter_report=report,
            cache_hits=hits,
            cache_misses=misses,
            newly_translated=newly,
        )
        return result
