"""Entry point of the WuWa screen translation tool.

* A worker thread captures the screen, runs the OCR and the translation.
* The UI thread only renders the overlay.
* ``F8`` toggles the translation session ON/OFF.
* ``F9`` toggles the live latency HUD (item E of P3).

Usage::

    python -m src.main

P3 changes:

* the translation runs in a **background thread**, so the OCR of the next
  frame overlaps the translation of the current one (item C);
* a **display watcher** detects a change of the captured area and restarts
  the capture backend, so the tool follows the game to another monitor
  without being restarted (item F);
* the live latency HUD can be toggled with ``F9`` (item E).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

if __package__ in (None, ""):  # allow "python src/main.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from src.async_translate import AsyncTranslator
from src.cache import TranslationCache
from src.capture import CaptureBackend, create_backend
from src.config import Config, load_config
from src.display import DisplayWatcher
from src.glossary import Glossary
from src.hud import HUDState
from src.ocr import OCREngine
from src.overlay import OverlayItem, OverlayState, OverlayWidget
from src.pipeline import Pipeline, PipelineResult, Translator
from src.session import SessionLog
from src.speakers import SpeakerVocabulary
from src.translator import create_engine

logger = logging.getLogger("translate_wuwa")


class WorkerSignals(QObject):
    """Signals emitted by the worker thread."""

    overlay_update = pyqtSignal(object)  # List[OverlayItem]
    status_update = pyqtSignal(bool)  # session active?
    log_message = pyqtSignal(str)
    hud_update = pyqtSignal(object)  # Optional[HUDSnapshot]


class TranslationWorker(threading.Thread):
    """Runs capture, OCR and translation in a background thread."""

    def __init__(
        self,
        config: Config,
        pipeline: Pipeline,
        session_log: SessionLog,
        backend: CaptureBackend,
        signals: WorkerSignals,
        watcher: Optional[DisplayWatcher] = None,
        async_translator: Optional[AsyncTranslator] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self.pipeline = pipeline
        self.session_log = session_log
        self.backend = backend
        self.signals = signals
        self.watcher = watcher
        self.async_translator = async_translator
        self._stop = threading.Event()
        self._toggle = threading.Event()
        self.active = False
        self.screen_size = (1920, 1080)
        self._lock = threading.Lock()
        # The HUD state (item E of P3).
        self.hud = HUDState(history=config.hud.history)
        # The blocks whose translation is still running, by block key.
        self._pending: Dict[str, OverlayItem] = {}
        # The last measured time from the capture to the visible translation.
        self.last_visible_ms: float = 0.0
        # The number of times the captured area changed.
        self.display_changes: int = 0

    # -- lifecycle ---------------------------------------------------------
    def toggle(self) -> bool:
        """Toggle the translation session. Returns the new state."""
        with self._lock:
            self.active = not self.active
            state = self.active
        if state:
            self.session_log.start()
            self.pipeline.reset()
            logger.info("translation ON - session file: %s", self.session_log.path)
        else:
            self.session_log.close()
            logger.info("translation OFF")
        self.signals.status_update.emit(state)
        self.signals.overlay_update.emit([] if not state else self._current_items())
        return state

    def stop(self) -> None:
        """Ask the worker to stop."""
        self._stop.set()

    # -- helpers -----------------------------------------------------------
    def _current_items(self) -> List[OverlayItem]:
        return getattr(self, "_items", [])

    def _toggle_hud(self) -> bool:
        """Show or hide the live latency HUD. Returns the new state."""
        state = self.hud.toggle()
        logger.info("latency HUD %s", "ON" if state else "OFF")
        self._emit_overlay()
        return state

    def _emit_overlay(self) -> None:
        """Send the current overlay items to the UI thread."""
        self.signals.overlay_update.emit(list(self._current_items()))

    # -- display hot-plug --------------------------------------------------
    def _check_display(self, frame) -> None:
        """Poll the display watcher with the size of the captured frame.

        The call is cheap (a size comparison); the DPI is only queried and
        the capture is only restarted when the size really changed.
        """
        if self.watcher is None:
            return
        changed = self.watcher.observe((frame.width, frame.height))
        if not changed:
            return

        self.display_changes += 1
        # The capture backend was recreated: the new one is used from now on.
        if self.watcher.backend is not None:
            self.backend = self.watcher.backend
        # The pipeline forgets the previous frame: the resolution changed,
        # so the whole screen has to be read again.
        self.pipeline.reset()
        self.screen_size = (frame.width, frame.height)
        logger.info("display change: %s", self.watcher.describe())

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        """Capture / OCR / translate until the tool is closed."""
        poll_s = max(0.02, self.config.poll_ms / 1000.0)
        while not self._stop.is_set():
            loop_start = time.perf_counter()
            if self.active:
                try:
                    self._iterate()
                except Exception:  # pragma: no cover - keep the tool alive
                    logger.exception("pipeline iteration failed")
            else:
                time.sleep(poll_s)
            elapsed = time.perf_counter() - loop_start
            time.sleep(max(0.0, poll_s - elapsed))

    def _iterate(self) -> None:
        """One capture -> OCR -> translate -> overlay iteration."""
        capture_start = time.perf_counter()
        frame = self.backend.grab()
        capture_ms = (time.perf_counter() - capture_start) * 1000.0

        self.screen_size = (frame.width, frame.height)
        self._check_display(frame)

        result: PipelineResult = self.pipeline.process_frame(frame, capture_ms)

        # -- the translations that the background worker has finished ------
        finished = self.pipeline.collect_translations()
        for item in finished:
            if not item.translation.strip():
                continue
            overlay_item = OverlayItem(
                key=item.block.key,
                bbox=item.block.bbox,
                text=item.translation,
                speaker=item.speaker,
            )
            self._pending[item.block.key] = overlay_item
            self.session_log.append(
                source=item.block.text,
                translation=item.translation,
                speaker=item.speaker,
            )

        if not result.frame_changed:
            if finished:
                self._emit_overlay()
                self._emit_hud(result)
            return

        items: List[OverlayItem] = []
        new_ids = {id(block) for block in result.newly_translated}
        for translated in result.blocks:
            if not translated.translation.strip():
                continue
            items.append(
                OverlayItem(
                    key=translated.block.key,
                    bbox=translated.block.bbox,
                    text=translated.translation,
                    speaker=translated.speaker,
                )
            )
            if id(translated) in new_ids:
                self.session_log.append(
                    source=translated.block.text,
                    translation=translated.translation,
                    speaker=translated.speaker,
                )

        # The blocks whose translation is still running keep their previous
        # overlay item, so the text never blinks.
        known = {item.key for item in items}
        for key, overlay_item in self._pending.items():
            if key not in known:
                items.append(overlay_item)

        items.sort(key=lambda item: (item.bbox[1], item.bbox[0]))
        self._items = items
        self._emit_overlay()
        self._emit_hud(result)

        logger.debug(
            "blocks=%d cache_hit=%d cache_miss=%d filter: %s",
            len(result.blocks),
            result.cache_hits,
            result.cache_misses,
            result.filter_report.describe(),
        )

    def _emit_hud(self, result: PipelineResult) -> None:
        """Update the HUD with the timings of this cycle."""
        if not self.hud.enabled:
            return
        snapshot = self.hud.update(result.timings, result.roi_action)
        self.signals.hud_update.emit(snapshot)


def start_hotkey_listener(app_state: dict, worker: TranslationWorker) -> None:
    """Register the global hotkeys (F8 to toggle, F9 for the HUD).

    ``pynput`` is used when it is available; when it is not, the hotkeys are
    registered as Qt shortcuts instead (they only work while the overlay
    has the focus in that case, but the overlay never takes the focus, so
    the tool stays usable).
    """
    hotkey = app_state.get("hotkey", "F8")
    hud_hotkey = app_state.get("hud_hotkey", "F9")

    def on_press(key):
        try:
            name = getattr(key, "name", "").upper()
            if name == hotkey.upper():
                worker.toggle()
            elif name == hud_hotkey.upper():
                worker._toggle_hud()
        except Exception:  # pragma: no cover - defensive
            logger.exception("hotkey handling failed")

    try:
        from pynput import keyboard

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        app_state["listener"] = listener
        logger.info("global hotkey %s registered", hotkey)
        logger.info("global hotkey %s (HUD) registered", hud_hotkey)
    except Exception:
        logger.warning(
            "pynput is not available: the %s / %s hotkeys are not global",
            hotkey,
            hud_hotkey,
        )


def enable_dpi_awareness() -> None:
    """Make the process per-monitor DPI aware before any window is created.

    Without this the overlay would be positioned in the virtual (scaled) pixel
    space on a 125% / 150% display, so it would not sit exactly over the
    original text.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        except Exception:
            pass
        # Fallback for older Windows versions.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        user32.SetProcessDPIAware()
    except Exception:  # pragma: no cover - defensive
        pass


def main(argv: Optional[List[str]] = None) -> int:
    """Start the tool."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    enable_dpi_awareness()
    config = load_config()

    # -- resources ---------------------------------------------------------
    cache = TranslationCache(config.cache_db_path)
    glossary = Glossary.from_file(config.glossary_path)
    session_log = SessionLog(config.sessions_dir)

    engine = create_engine(config.translation.engine, device=config.translation.device)
    vocabulary = (
        SpeakerVocabulary.from_files(
            config.speaker.ui_labels_path, config.speaker.roster_path
        )
        if config.speaker.enabled
        else None
    )
    translator = Translator(
        engine,
        cache,
        glossary,
        split_sentences=config.translation.split_sentences,
        vocabulary=vocabulary,
        skip_ui_labels=config.translation.skip_ui_labels,
    )

    ocr_engine = OCREngine(
        device=config.translation.device,
        intra_threads=config.ocr_intra_threads,
        pool_size=max(config.roi_workers, config.tile_workers),
    )
    pipeline = Pipeline(
        config, ocr_engine=ocr_engine, translator=translator, vocabulary=vocabulary
    )

    backend = create_backend(config.capture.backend, config.capture.monitor)
    logger.info("capture backend: %s", backend.name)

    # -- the background translator (item C of P3) ---------------------------
    async_translator: Optional[AsyncTranslator] = None
    if config.async_pipeline:
        async_translator = AsyncTranslator(
            translator, max_queue=max(1, config.async_queue_size * 4)
        )
        async_translator.start()
        pipeline.set_async_translator(async_translator)
        logger.info("async pipeline: the translation runs in a background thread")

    # -- the display watcher (item F of P3) --------------------------------
    watcher = DisplayWatcher(config, backend=backend)
    watcher.observe()  # the baseline observation

    # -- Qt ----------------------------------------------------------------
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    overlay = OverlayWidget(config.overlay, config.hud)

    signals = WorkerSignals()
    worker = TranslationWorker(
        config,
        pipeline,
        session_log,
        backend,
        signals,
        watcher=watcher,
        async_translator=async_translator,
    )

    def on_overlay_update(items: List[OverlayItem]) -> None:
        state = OverlayState(
            items=items,
            screen_width=worker.screen_size[0],
            screen_height=worker.screen_size[1],
            active=worker.active,
            hud=worker.hud.last if worker.hud.enabled else None,
        )
        overlay.set_state(state)

    def on_status_update(active: bool) -> None:
        state = OverlayState(
            items=overlay._state.items,
            screen_width=worker.screen_size[0],
            screen_height=worker.screen_size[1],
            active=active,
            hud=worker.hud.last if worker.hud.enabled else None,
        )
        overlay.set_state(state)

    def on_hud_update(snapshot) -> None:
        state = OverlayState(
            items=overlay._state.items,
            screen_width=worker.screen_size[0],
            screen_height=worker.screen_size[1],
            active=worker.active,
            hud=snapshot,
        )
        overlay.set_state(state)

    signals.overlay_update.connect(on_overlay_update)
    signals.status_update.connect(on_status_update)
    signals.hud_update.connect(on_hud_update)

    overlay.show()
    start_hotkey_listener(
        {"hotkey": config.hotkey, "hud_hotkey": config.hud.hotkey}, worker
    )

    worker.start()

    logger.info(
        "WuWa translator started. Press %s to toggle translation, %s for the HUD.",
        config.hotkey,
        config.hud.hotkey,
    )

    try:
        qt_app.exec()
    finally:
        worker.stop()
        if async_translator is not None:
            async_translator.stop()
        session_log.close()
        cache.close()
        try:
            backend.close()
        except Exception:  # pragma: no cover - defensive
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
