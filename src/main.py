"""Entry point of the WuWa screen translation tool.

* A worker thread captures the screen, runs the OCR and the translation.
* The UI thread only renders the overlay.
* ``F8`` toggles the translation session ON/OFF.

Usage::

    python -m src.main
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

if __package__ in (None, ""):  # allow "python src/main.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from src.cache import TranslationCache
from src.capture import CaptureBackend, create_backend
from src.config import Config, load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.overlay import OverlayItem, OverlayState, OverlayWidget
from src.pipeline import Pipeline, PipelineResult, Translator
from src.session import SessionLog
from src.translator import create_engine

logger = logging.getLogger("translate_wuwa")


class WorkerSignals(QObject):
    """Signals emitted by the worker thread."""

    overlay_update = pyqtSignal(object)  # List[OverlayItem]
    status_update = pyqtSignal(bool)  # session active?
    log_message = pyqtSignal(str)


class TranslationWorker(threading.Thread):
    """Runs capture, OCR and translation in a background thread."""

    def __init__(
        self,
        config: Config,
        pipeline: Pipeline,
        session_log: SessionLog,
        backend: CaptureBackend,
        signals: WorkerSignals,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self.pipeline = pipeline
        self.session_log = session_log
        self.backend = backend
        self.signals = signals
        self._stop = threading.Event()
        self._toggle = threading.Event()
        self.active = False
        self.screen_size = (1920, 1080)
        self._lock = threading.Lock()

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
        result: PipelineResult = self.pipeline.process_frame(frame, capture_ms)

        if not result.frame_changed:
            return

        items: List[OverlayItem] = []
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
            if translated in result.newly_translated:
                self.session_log.append(
                    source=translated.block.text,
                    translation=translated.translation,
                    speaker=translated.speaker,
                )
        self._items = items
        self.signals.overlay_update.emit(items)

        logger.debug(
            "blocks=%d cache_hit=%d cache_miss=%d filter: %s",
            len(result.blocks),
            result.cache_hits,
            result.cache_misses,
            result.filter_report.describe(),
        )


def start_hotkey_listener(app_state: dict, worker: TranslationWorker) -> None:
    """Register the global hotkey (F8 by default) with pynput."""
    from pynput import keyboard

    hotkey = app_state.get("hotkey", "F8")

    def on_press(key):
        try:
            if getattr(key, "name", "").upper() == hotkey.upper():
                worker.toggle()
        except Exception:  # pragma: no cover - defensive
            logger.exception("hotkey handling failed")

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    app_state["listener"] = listener
    logger.info("global hotkey %s registered", hotkey)


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
    translator = Translator(engine, cache, glossary)

    ocr_engine = OCREngine(device=config.translation.device)
    pipeline = Pipeline(config, ocr_engine=ocr_engine, translator=translator)

    backend = create_backend(config.capture.backend, config.capture.monitor)
    logger.info("capture backend: %s", backend.name)

    # -- Qt ----------------------------------------------------------------
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    overlay = OverlayWidget(config.overlay)

    signals = WorkerSignals()
    worker = TranslationWorker(config, pipeline, session_log, backend, signals)

    def on_overlay_update(items: List[OverlayItem]) -> None:
        state = OverlayState(
            items=items,
            screen_width=worker.screen_size[0],
            screen_height=worker.screen_size[1],
            active=worker.active,
        )
        overlay.set_state(state)

    def on_status_update(active: bool) -> None:
        state = OverlayState(
            items=overlay._state.items,
            screen_width=worker.screen_size[0],
            screen_height=worker.screen_size[1],
            active=active,
        )
        overlay.set_state(state)

    signals.overlay_update.connect(on_overlay_update)
    signals.status_update.connect(on_status_update)

    overlay.show()
    start_hotkey_listener({"hotkey": config.hotkey}, worker)

    worker.start()

    logger.info("WuWa translator started. Press %s to toggle translation.", config.hotkey)

    try:
        qt_app.exec()
    finally:
        worker.stop()
        session_log.close()
        cache.close()
        try:
            backend.close()
        except Exception:  # pragma: no cover - defensive
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
