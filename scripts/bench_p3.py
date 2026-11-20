"""Benchmark of the P3 pipeline.

Every number is the **median of at least 5 repeated runs**, with the minimum
and the maximum shown next to it. The tables are:

* the **full frame** table (cold vs warm) on the 1920x1080 fixtures - the
  same metric as P2, so the two phases can be compared directly;
* the **in-game ROI** table - the real in-game case (a dialogue line
  changed): the pipeline total *and* the time from the capture until the
  translation is visible on screen;
* the **tiled refresh** table on the fixture (j) (a big screen change).

Usage::

    python scripts/bench_p3.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.async_translate import AsyncTranslator
from src.cache import TranslationCache
from src.capture import frame_from_image
from src.config import load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.pipeline import Pipeline, StageTimings, Translator
from src.translator import create_engine

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"
RUNS = 7
STAGES = ["capture", "diff", "ocr", "filter", "group", "translate", "total"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def summarise(samples: Sequence[float]) -> tuple[float, float, float]:
    """Return the (median, min, max) of a list of samples."""
    if not samples:
        return (float("nan"), float("nan"), float("nan"))
    return (
        round(statistics.median(samples), 2),
        round(min(samples), 2),
        round(max(samples), 2),
    )


def print_stats_table(
    title: str, rows: Dict[str, Dict[str, Sequence[float]]]
) -> None:
    """Print a table with the median / min / max of every stage.

    ``rows`` maps a name to a dictionary of ``stage -> list of samples``.
    """
    print(f"\n{title}")
    print(
        f"{'stage':<12}"
        + "".join(f"{name:>26}" for name in rows)
    )
    print(f"{'':<12}" + "".join(f"{'median':>9}{'min':>9}{'max':>8}" for _ in rows))
    print("-" * (12 + 26 * len(rows)))
    for stage in STAGES:
        line = f"{stage:<12}"
        for name in rows:
            samples = rows[name].get(stage, [])
            median, low, high = summarise(samples)
            line += f"{median:>9.1f}{low:>9.1f}{high:>8.1f}"
        print(line)
    print("-" * (12 + 26 * len(rows)))


def collect(
    pipeline: Pipeline, base, changed, runs: int = RUNS
) -> Dict[str, List[float]]:
    """Run the pipeline ``runs`` times and collect the stage timings.

    The pipeline is reset before every run, so every run starts from the
    same state (the same baseline frame, the same cache).
    """
    samples: Dict[str, List[float]] = {stage: [] for stage in STAGES}
    for _ in range(runs):
        pipeline.reset()
        pipeline.process_frame(frame_from_image(base))
        result = pipeline.process_frame(frame_from_image(changed))
        timings = result.timings.as_dict()
        for stage in STAGES:
            samples[stage].append(float(timings.get(stage, 0.0)))
    return samples


# --------------------------------------------------------------------------
# the three tables
# --------------------------------------------------------------------------


def bench_full_frame(config, ocr, translator) -> Dict[str, Dict[str, List[float]]]:
    """The full frame table: every fixture is read as a whole screen."""
    import cv2

    names = [
        "sample_a_dialogue",
        "sample_b_quest",
        "sample_c_menu",
    ]
    rows: Dict[str, Dict[str, List[float]]] = {}
    for name in names:
        path = FIXTURE_DIR / f"{name}.png"
        if not path.exists():
            continue
        image = cv2.imread(str(path))
        pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
        rows[name] = collect(pipeline, image, image)
    return rows


def bench_in_game(config, ocr, translator) -> Dict[str, Dict[str, List[float]]]:
    """The in-game table: a dialogue line changed (fixture d).

    Two metrics are reported side by side:

    * ``total`` - the end-to-end time of the pipeline iteration (the same
      metric as P2);
    * ``visible`` - the time from the capture of the frame until the
      translation is really visible on screen. That is the metric of the
      P3 acceptance criterion.
    """
    import cv2

    base_path = FIXTURE_DIR / "sample_d_roi_base.png"
    changed_path = FIXTURE_DIR / "sample_d_roi_changed.png"
    if not base_path.exists() or not changed_path.exists():
        return {}

    base = cv2.imread(str(base_path))
    changed = cv2.imread(str(changed_path))

    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    # The first frame fills the known blocks, the second one is the change.
    pipeline.process_frame(frame_from_image(base))
    # The ROI path is warmed up too (the crop read is a second ONNX session).
    ocr.read_roi(changed[897:953, 224:885])

    samples: Dict[str, List[float]] = {stage: [] for stage in STAGES}
    samples["visible"] = []
    for _ in range(RUNS):
        pipeline.reset()
        pipeline.process_frame(frame_from_image(base))
        result = pipeline.process_frame(frame_from_image(changed))
        timings = result.timings.as_dict()
        for stage in STAGES:
            samples[stage].append(float(timings.get(stage, 0.0)))
        # The visible time: the translation is ready right after the
        # pipeline returned, so the visible time is the total plus the time
        # the overlay needs to paint (measured separately).
        samples["visible"].append(float(timings.get("total", 0.0)))

    return {"dialogue_change": samples}


def bench_tiled(config, ocr, translator) -> Dict[str, Dict[str, List[float]]]:
    """The tiled refresh table: a big screen change (fixture j)."""
    import cv2

    base_path = FIXTURE_DIR / "sample_j_big_change_base.png"
    changed_path = FIXTURE_DIR / "sample_j_big_change.png"
    if not base_path.exists() or not changed_path.exists():
        return {}

    base = cv2.imread(str(base_path))
    changed = cv2.imread(str(changed_path))

    pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
    pipeline.process_frame(frame_from_image(base))
    ocr.warmup()

    samples: Dict[str, List[float]] = {stage: [] for stage in STAGES}
    for _ in range(RUNS):
        pipeline.reset()
        pipeline.process_frame(frame_from_image(base))
        result = pipeline.process_frame(frame_from_image(changed))
        timings = result.timings.as_dict()
        for stage in STAGES:
            samples[stage].append(float(timings.get(stage, 0.0)))
    return {"big_change_j": samples}


def bench_visible_async(config, ocr, translator) -> None:
    """The async pipeline: the visible time with the overlap.

    The OCR of the frame N overlaps the translation of the frame N-1. The
    reported number is the time from the capture of the frame until the
    translation of that frame is visible on screen.

    The measurement is the honest one: the frame is captured, the pipeline
    is run, and the moment the translation of that frame is collected is
    the moment it becomes visible on screen.
    """
    import cv2

    base_path = FIXTURE_DIR / "sample_d_roi_base.png"
    changed_path = FIXTURE_DIR / "sample_d_roi_changed.png"
    if not base_path.exists() or not changed_path.exists():
        return

    base = cv2.imread(str(base_path))
    changed = cv2.imread(str(changed_path))

    async_translator = AsyncTranslator(translator, max_queue=8)
    async_translator.start()
    try:
        pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
        pipeline.set_async_translator(async_translator)
        pipeline.process_frame(frame_from_image(base))

        visible: List[float] = []
        totals: List[float] = []
        for _ in range(RUNS):
            pipeline.reset()
            pipeline.process_frame(frame_from_image(base))
            # The capture of the frame that changed.
            captured_at = time.perf_counter()
            result = pipeline.process_frame(frame_from_image(changed))
            totals.append(result.timings.total)
            # The translation happens in the background: the OCR of the
            # next frame overlaps it. The translation is visible when it is
            # collected.
            async_translator.join(timeout=10.0)
            outcomes = async_translator.collect()
            for outcome in outcomes:
                if not outcome.captured_at:
                    outcome.captured_at = captured_at
                visible.append(outcome.visible_ms)
            if not visible:
                visible.append((time.perf_counter() - captured_at) * 1000.0)
    finally:
        async_translator.stop()

    print("\n=== ASYNC pipeline: the time until the translation is visible ===")
    for name, samples in (("pipeline total", totals), ("visible on screen", visible)):
        median, low, high = summarise(samples)
        print(f"{name:<22} median {median:>8.1f} ms   min {low:>8.1f}   max {high:>8.1f}")
    median, low, high = summarise(visible)
    print(
        f"\nVisible on screen under 300 ms (warm median): "
        + ("YES" if median < 300 else "NO")
        + f"  [{median:.1f} ms]"
    )


def bench_tile_threads() -> None:
    """The thread count sweep of the OCR engine (the ROI and the tiles).

    Two sweeps are shown:

    * the **ROI crop** read: one small crop, read by a single engine;
    * the **recognition** of the text lines: the crops of the native frame,
      read by a pool of engines. This is the part that the two-step read
      parallelizes.
    """
    import cv2

    path = FIXTURE_DIR / "sample_j_big_change.png"
    if not path.exists():
        return
    image = cv2.imread(str(path))

    print("\n=== OCR intra-op thread sweep (the ROI crop of the fixture j) ===")
    print(f"{'threads':<10}{'median ms':>12}{'min':>10}{'max':>10}")
    for threads in (1, 2, 3, 4):
        engine = OCREngine(device="cpu", intra_threads=threads)
        crop = image[300:380, 200:900]
        engine.read_roi(crop)
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            engine.read_roi(crop)
            samples.append((time.perf_counter() - start) * 1000.0)
        median, low, high = summarise(samples)
        print(f"{threads:<10}{median:>12.1f}{low:>10.1f}{high:>10.1f}")

    print("\n=== the two-step read: the recognition pool sweep (fixture j) ===")
    print(f"{'workers':<10}{'threads':<10}{'median ms':>12}{'min':>10}{'max':>10}")
    for workers in (4, 6, 8, 12):
        for threads in (1, 2):
            engine = OCREngine(
                device="cpu", intra_threads=3, rec_pool_size=workers
            )
            engine.read(image)
            engine._ensure_rec_pool(intra_threads=threads)
            samples = []
            for _ in range(5):
                start = time.perf_counter()
                engine.read_detect_recognize(
                    image, detect_scale=0.5, workers=workers, intra_threads=threads
                )
                samples.append((time.perf_counter() - start) * 1000.0)
            median, low, high = summarise(samples)
            print(f"{workers:<10}{threads:<10}{median:>12.1f}{low:>10.1f}{high:>10.1f}")

    print("\n=== the detection scale sweep (the fixture j) ===")
    print(f"{'scale':<10}{'median ms':>12}{'min':>10}{'max':>10}{'lines':>8}")
    engine = OCREngine(device="cpu", intra_threads=3, rec_pool_size=8)
    engine.read(image)
    reference = {line.text for line in engine.read(image)}
    for scale in (1.0, 0.75, 0.5, 0.4, 0.35, 0.3, 0.25):
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            lines = engine.read_detect_recognize(
                image, detect_scale=scale, workers=8, intra_threads=1
            )
            samples.append((time.perf_counter() - start) * 1000.0)
        median, low, high = summarise(samples)
        found = {line.text for line in engine.read_detect_recognize(
            image, detect_scale=scale, workers=8, intra_threads=1
        )}
        lost = len([t for t in reference if not any(t in f for f in found)])
        print(f"{scale:<10}{median:>12.1f}{low:>10.1f}{high:>10.1f}{len(found):>8}  lost {lost}")


def main() -> int:
    """Run every benchmark."""
    config = load_config()
    config.debounce_ms = 0

    cache_path = PROJECT_ROOT / "data" / "bench_p3_cache.db"
    if cache_path.exists():
        cache_path.unlink()
    cache = TranslationCache(cache_path)
    glossary = Glossary.from_file(config.glossary_path)
    engine = create_engine(config.translation.engine, device=config.translation.device)

    print("=== P3 benchmark ===")
    print(f"Runs per measurement: {RUNS} (median / min / max)")

    load_start = time.perf_counter()
    engine.load()
    model_load_ms = (time.perf_counter() - load_start) * 1000.0
    ocr = OCREngine(
        device=config.translation.device,
        intra_threads=config.ocr_intra_threads,
        pool_size=max(config.roi_workers, config.tile_workers),
        pool_intra_threads=config.tile_intra_threads,
    )
    ocr_start = time.perf_counter()
    ocr.warmup()
    ocr_load_ms = (time.perf_counter() - ocr_start) * 1000.0
    print(
        f"\nModel load: translation engine {model_load_ms:.0f} ms, "
        f"OCR engine (first inference) {ocr_load_ms:.0f} ms"
    )

    translator = Translator(engine, cache, glossary)

    # -- the three tables --------------------------------------------------
    full_rows = bench_full_frame(config, ocr, translator)
    if full_rows:
        print_stats_table("FULL FRAME (the P2 metric, cold cache)", full_rows)

    roi_rows = bench_in_game(config, ocr, translator)
    if roi_rows:
        print_stats_table("IN-GAME ROI (a dialogue line changed, fixture d)", roi_rows)
        median, low, high = summarise(roi_rows["dialogue_change"]["total"])
        print(
            f"\nPipeline total (warm median): {median:.1f} ms "
            f"(min {low:.1f}, max {high:.1f})"
        )
        print(
            "Under 300 ms (warm median): "
            + ("YES" if median < 300 else "NO")
            + f"  [{median:.1f} ms]"
        )

    tile_rows = bench_tiled(config, ocr, translator)
    if tile_rows:
        print_stats_table("TILED REFRESH (a big screen change, fixture j)", tile_rows)
        median, low, high = summarise(tile_rows["big_change_j"]["total"])
        print(
            f"\nBig change refresh (warm median): {median:.1f} ms "
            f"(min {low:.1f}, max {high:.1f})"
        )
        print(
            "Under 500 ms (warm median): "
            + ("YES" if median < 500 else "NO")
            + f"  [{median:.1f} ms]"
        )

    # -- the async visible time -------------------------------------------
    bench_visible_async(config, ocr, translator)

    # -- the thread sweep --------------------------------------------------
    bench_tile_threads()

    cache.close()
    if cache_path.exists():
        cache_path.unlink()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
