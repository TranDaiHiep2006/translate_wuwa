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
from .roi import (
    ROI_CROP,
    ROI_FULL,
    ROI_SKIP,
    ROIResult,
    compute_roi,
    offset_lines,
)
from .sentences import (
    ProtectedText,
    Sentence,
    join_sentences,
    protect_numbers,
    restore_numbers,
    split_sentences,
)
from .speakers import DEFAULT_VOCABULARY, SpeakerVocabulary
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
    roi_action: str = ROI_FULL
    roi_rect: Optional[Tuple[int, int, int, int]] = None


class Translator:
    """Wraps a translation engine with glossary protection and caching.

    A block is translated sentence by sentence (when enabled), and every
    number of a sentence is protected by a placeholder, so the model can never
    lose a digit. The cache is used per sentence *and* per block.
    """

    def __init__(
        self,
        engine: BaseEngine,
        cache: TranslationCache,
        glossary: Glossary,
        split_sentences: bool = True,
        vocabulary: Optional[SpeakerVocabulary] = None,
        skip_ui_labels: bool = True,
    ) -> None:
        self.engine = engine
        self.cache = cache
        self.glossary = glossary
        self.split_sentences = split_sentences
        self.vocabulary = vocabulary or DEFAULT_VOCABULARY
        self.skip_ui_labels = skip_ui_labels
        self.number_corrections = 0
        # The translations of the sentences of the current batch.
        self._sentence_cache: Dict[Tuple[int, int], str] = {}

    # -- helpers -----------------------------------------------------------
    def _protect(self, text: str) -> Tuple[str, ProtectedText, Dict[str, str]]:
        """Glossary-protect the text and then protect its numbers."""
        protected_text, restore_map = self.glossary.protect(text)
        numbers = protect_numbers(protected_text)
        return numbers.text, numbers, restore_map

    def _restore(
        self,
        translated: str,
        original: str,
        numbers: ProtectedText,
        restore_map: Dict[str, str],
    ) -> Tuple[str, bool]:
        """Restore the glossary and the numbers, with the digit safety net."""
        restored = self.glossary.restore(translated, restore_map)
        fixed, corrected = restore_numbers(restored, original, numbers)
        if corrected:
            self.number_corrections += 1
            logger.warning(
                "the model mangled the digits of %r, they were restored", original
            )
        return fixed, corrected

    def _split(self, text: str) -> List[Sentence]:
        """Split a block into the sentences that are translated separately."""
        if not self.split_sentences:
            return [Sentence(text=text, separator="")]
        sentences = split_sentences(text)
        return sentences or [Sentence(text=text, separator="")]

    def _is_ui_label(self, text: str) -> bool:
        """Return True when the whole text is a UI label.

        A menu header ("Quest", "Inventory", ...) is not translated: it keeps
        its English name, because the player looks for the original label in
        the menu.
        """
        if not self.skip_ui_labels:
            return False
        stripped = text.strip()
        if not stripped or len(stripped.split()) > 2:
            return False
        return self.vocabulary.is_ui_label(stripped)

    def clear_sentence_cache(self) -> None:
        """Forget the sentence translations of the current batch."""
        self._sentence_cache = {}

    # -- API ---------------------------------------------------------------
    def translate_texts(self, texts: Sequence[str]) -> List[str]:
        """Translate a batch of blocks, using the cache when possible.

        Every block is split into sentences; each sentence is cached on its
        own, so a repeated sentence is a cache hit even when the surrounding
        block changed. Returns the translations in the same order as
        ``texts``.
        """
        if not texts:
            return []

        # -- level 1: the whole block ------------------------------------
        block_keys = [normalize(t) for t in texts]
        cached_blocks = self.cache.get_many(block_keys)
        results: List[Optional[str]] = [None] * len(texts)

        pending: List[Tuple[int, str]] = []
        for index, key in enumerate(block_keys):
            hit = cached_blocks.get(key)
            if hit is not None:
                results[index] = hit
            else:
                pending.append((index, texts[index]))

        # A block that is only a UI label is not translated at all.
        for index, text in list(pending):
            if self._is_ui_label(text):
                results[index] = text
                pending.remove((index, text))
                self.cache.set(normalize(text), text)

        # -- level 2: every sentence of the block -------------------------
        split_blocks: List[Tuple[int, List[Sentence]]] = []
        sentence_jobs: List[Tuple[int, int, Sentence]] = []
        for block_index, text in pending:
            sentences = self._split(text)
            split_blocks.append((block_index, sentences))
            for sentence_index, sentence in enumerate(sentences):
                sentence_jobs.append((block_index, sentence_index, sentence))

        sentence_keys = [normalize(job[2].text) for job in sentence_jobs]
        cached_sentences = self.cache.get_many(sentence_keys)

        to_translate: List[Tuple[int, int, Sentence]] = []
        for position, job in enumerate(sentence_jobs):
            hit = cached_sentences.get(sentence_keys[position])
            if hit is None:
                to_translate.append(job)
            else:
                self._sentence_cache[(job[0], job[1])] = hit

        if to_translate:
            protected: List[str] = []
            numbers: List[ProtectedText] = []
            restore_maps: List[Dict[str, str]] = []
            originals: List[str] = []
            for _, _, sentence in to_translate:
                text, num, restore_map = self._protect(sentence.text)
                protected.append(text)
                numbers.append(num)
                restore_maps.append(restore_map)
                originals.append(sentence.text)

            raw = self.engine.translate(protected)
            new_items: List[Tuple[str, str]] = []
            for position, (block_index, sentence_index, sentence) in enumerate(
                to_translate
            ):
                restored, _ = self._restore(
                    raw[position],
                    originals[position],
                    numbers[position],
                    restore_maps[position],
                )
                self._sentence_cache[(block_index, sentence_index)] = restored
                new_items.append((normalize(originals[position]), restored))
            self.cache.set_many(new_items)

        # -- rebuild the blocks ------------------------------------------
        for block_index, sentences in split_blocks:
            pieces = []
            for sentence_index, sentence in enumerate(sentences):
                piece = self._sentence_cache.get((block_index, sentence_index))
                if piece is None:  # pragma: no cover - defensive
                    piece = sentence.text
                pieces.append(piece)
            translation = join_sentences(
                [
                    Sentence(text=piece, separator=sentence.separator)
                    for piece, sentence in zip(pieces, sentences)
                ]
            )
            results[block_index] = translation
            self.cache.set(normalize(texts[block_index]), translation)

        return [r if r is not None else "" for r in results]


class Pipeline:
    """The full translation pipeline."""

    def __init__(
        self,
        config: Config,
        ocr_engine: Optional[OCREngine] = None,
        translator: Optional[Translator] = None,
        vocabulary: Optional[SpeakerVocabulary] = None,
    ) -> None:
        self.config = config
        self.ocr_engine = ocr_engine or OCREngine(device=config.translation.device)
        self.translator = translator
        if vocabulary is None and config.speaker.enabled:
            vocabulary = SpeakerVocabulary.from_files(
                config.speaker.ui_labels_path, config.speaker.roster_path
            )
        self.vocabulary = vocabulary
        self._previous_frame: Optional[np.ndarray] = None
        # block key -> first time we saw this block (debounce bookkeeping)
        self._pending: Dict[str, float] = {}
        # The blocks that are currently on the screen.
        self._known: List[TranslatedBlock] = []
        # The number of consecutive full frame refreshes that did not confirm
        # a block (only used for the blocks outside the ROI).
        self._missing: Dict[str, int] = {}
        # The full frame is re-read every X ms / X frames.
        self._last_full_ocr: float = 0.0
        self._frames_since_full: int = 0

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
        self._known.clear()
        self._missing.clear()
        self._last_full_ocr = 0.0
        self._frames_since_full = 0

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

        # -- ROI -------------------------------------------------------------
        roi = self._decide_roi(diff, frame)

        if roi.action == ROI_SKIP:
            self._previous_frame = frame.image.copy()
            timings.total = (time.perf_counter() - total_start) * 1000.0
            result = PipelineResult(frame_changed=False)
            result.timings = timings
            result.roi_action = roi.action
            return result

        # -- OCR -------------------------------------------------------------
        t0 = time.perf_counter()
        if roi.action == ROI_CROP and roi.roi is not None:
            x1, y1, x2, y2 = roi.roi
            crop = frame.image[y1:y2, x1:x2]
            lines = offset_lines(self.ocr_engine.read_roi(crop), x1, y1)
        else:
            lines = self.ocr_engine.read(frame.image)
        timings.ocr = (time.perf_counter() - t0) * 1000.0

        if roi.action == ROI_FULL:
            self._last_full_ocr = time.perf_counter()
            self._frames_since_full = 0

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
            vocabulary=self.vocabulary,
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
            previous = self._find_known(block.text)
            if previous is not None:
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
            else:
                misses += 1
                to_translate.append((len(results), block))
                results.append(
                    TranslatedBlock(block=block, translation="", speaker=block.speaker)
                )

        if to_translate and self.translator is not None:
            self.translator.clear_sentence_cache()
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
                newly.append(item)
        timings.translate = (time.perf_counter() - t0) * 1000.0

        # Blocks that are still settling keep their previous translation.
        for block in waiting:
            previous = self._find_known(block.text)
            if previous is not None:
                results.append(
                    TranslatedBlock(
                        block=block,
                        translation=previous.translation,
                        speaker=previous.speaker,
                        from_cache=True,
                    )
                )

        # -- merge with the blocks outside the ROI ---------------------------
        results = self._merge_with_known_blocks(results, blocks, roi.action)

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
            roi_action=roi.action,
            roi_rect=roi.roi,
        )
        return result

    # -- known blocks ------------------------------------------------------
    def _find_known(self, text: str) -> Optional[TranslatedBlock]:
        """Return the known block with the same source text."""
        key = normalize(text)
        for item in self._known:
            if normalize(item.block.text) == key:
                return item
        return None

    # -- ROI helpers -------------------------------------------------------
    def _decide_roi(self, diff, frame: Frame) -> ROIResult:
        """Decide what the OCR has to read for this frame."""
        config = self.config
        screen_area = frame.width * frame.height
        if not config.roi_enabled:
            return ROIResult(
                action=ROI_FULL,
                changed_area=screen_area,
                screen_area=screen_area,
                reason="ROI disabled",
            )

        now = time.perf_counter()
        need_full = (
            self._last_full_ocr == 0.0
            or (now - self._last_full_ocr) * 1000.0 >= config.roi_full_refresh_ms
            or self._frames_since_full >= config.roi_full_refresh_frames
        )
        self._frames_since_full += 1

        scale = self._scale(frame.height)
        roi = compute_roi(
            diff.diff_mask,
            padding=int(round(config.scale(config.roi_padding_px, frame.height))),
            width=frame.width,
            height=frame.height,
            min_area=int(round(config.roi_min_area * scale * scale)),
            full_frame_threshold=config.roi_full_frame_threshold,
        )

        if need_full and roi.action == ROI_CROP:
            # The periodic full frame refresh catches the text the ROI missed.
            roi.action = ROI_FULL
            roi.roi = None
            roi.reason = roi.reason + " (periodic full refresh)"
        return roi

    # -- block merging -----------------------------------------------------
    @staticmethod
    def _overlap_ratio(
        a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
    ) -> float:
        """Return the fraction of ``a`` that overlaps ``b`` (0..1)."""
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0, min(ay2, by2) - max(ay1, by1))
        inter = inter_w * inter_h
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        if area_a <= 0:
            return 0.0
        return inter / float(area_a)

    def _merge_with_known_blocks(
        self,
        results: List[TranslatedBlock],
        blocks: List[TextBlock],
        action: str,
    ) -> List[TranslatedBlock]:
        """Keep the translations of the text that did not change.

        The ROI only contains the part of the screen that changed, so the
        blocks outside the ROI are still valid. They are kept until a full
        frame refresh confirms that their text is gone.
        """
        new_texts = {normalize(b.text) for b in blocks}
        new_boxes = [b.bbox for b in blocks]

        kept: List[TranslatedBlock] = []
        for old in self._known:
            old_key = normalize(old.block.text)
            same_text = old_key in new_texts
            overlapped = any(
                self._overlap_ratio(old.block.bbox, box) > 0.5 for box in new_boxes
            )

            if same_text or overlapped:
                # The block was read again: the new result replaces it.
                self._missing.pop(old_key, None)
                continue

            if action == ROI_CROP:
                # Outside the ROI the old block is still valid.
                kept.append(old)
                continue

            # A full frame refresh knows the whole screen: the text is gone.
            # The block is removed after two confirmations.
            count = self._missing.get(old_key, 0) + 1
            self._missing[old_key] = count
            if count >= 2:
                self._missing.pop(old_key, None)
                continue
            kept.append(old)

        # The blocks that were read again are not missing any more.
        for block in blocks:
            self._missing.pop(normalize(block.text), None)

        merged = kept + list(results)
        # The order of the overlay items must follow the reading order.
        merged.sort(key=lambda item: (item.block.bbox[1], item.block.bbox[0]))
        # A copy is stored: the caller receives ``merged`` and must not see
        # it change when the pipeline is reset.
        self._known = list(merged)
        return merged
