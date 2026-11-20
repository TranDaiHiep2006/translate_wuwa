"""Benchmark the pipeline on the sample images.

Prints a table with the time per stage, the total end-to-end time and a
comparison between a cold run (empty cache, model just loaded) and a warm run
(100% cache hits).

Usage::

    python scripts/bench.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cache import TranslationCache
from src.capture import benchmark_backends, frame_from_image
from src.config import load_config
from src.glossary import Glossary
from src.ocr import OCREngine
from src.pipeline import Pipeline, Translator
from src.translator import create_engine

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"
STAGES = ["capture", "diff", "ocr", "filter", "group", "translate", "render", "total"]


def print_table(title: str, rows: dict[str, dict[str, float]]) -> None:
    """Print a simple aligned table of the measured numbers."""
    print(f"\n{title}")
    print("-" * 72)
    header = f"{'stage':<14}" + "".join(f"{name:>16}" for name in rows)
    print(header)
    print("-" * 72)
    for stage in STAGES:
        if stage not in next(iter(rows.values())):
            continue
        line = f"{stage:<14}"
        for name in rows:
            line += f"{rows[name].get(stage, float('nan')):>16.2f}"
        print(line)
    print("-" * 72)


def bench_capture() -> None:
    """Compare the capture backends on this machine."""
    print("\n=== Capture backend benchmark (real screen, 30 grabs) ===")
    results = benchmark_backends(iterations=30)
    print(f"{'backend':<12}{'ok':<6}{'avg ms':>12}  error")
    for entry in results:
        ok = "yes" if entry["ok"] else "no"
        avg = f"{entry['avg_ms']:.2f}" if entry["ok"] else "-"
        print(f"{entry['backend']:<12}{ok:<6}{avg:>12}  {entry['error']}")


def bench_engines() -> None:
    """Compare the two translation engines on the 10 sample sentences."""
    from src.translator import SAMPLE_SENTENCES, benchmark_engines

    print("\n=== Translation engine benchmark (10 game-style sentences) ===")
    results = benchmark_engines(("argos", "marian"), SAMPLE_SENTENCES)
    print(f"{'engine':<10}{'ok':<6}{'avg ms/sentence':>20}")
    for entry in results:
        ok = "yes" if entry["ok"] else "no"
        avg = f"{entry['avg_ms']:.2f}" if entry["ok"] else "-"
        print(f"{entry['engine']:<10}{ok:<6}{avg:>20}")
        if entry["error"]:
            print(f"    error: {entry['error']}")
    for entry in results:
        if not entry["ok"]:
            continue
        print(f"\n--- {entry['engine']} outputs ---")
        for source, output in zip(SAMPLE_SENTENCES, entry["outputs"]):
            print(f"  EN: {source}")
            print(f"  VI: {output}")


def run_pipeline_bench() -> None:
    """Measure the pipeline on the sample images (cold vs warm)."""
    config = load_config()
    config.debounce_ms = 0

    images = [
        FIXTURE_DIR / "sample_a_dialogue.png",
        FIXTURE_DIR / "sample_b_quest.png",
        FIXTURE_DIR / "sample_c_menu.png",
    ]
    images = [p for p in images if p.exists()]
    if not images:
        print("No fixtures found - run scripts/make_fixtures.py first.")
        return

    import cv2

    cache_dir = PROJECT_ROOT / "data"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "bench_cache.db"
    if db_path.exists():
        db_path.unlink()

    print("\n=== Pipeline benchmark ===")
    print(f"Screen resolution used: 1920x1080 (from the fixture images)")

    # --- cold run: empty cache, model just loaded -------------------------
    cache = TranslationCache(db_path)
    glossary = Glossary.from_file(config.glossary_path)
    engine = create_engine(config.translation.engine, device=config.translation.device)
    load_start = time.perf_counter()
    engine.load()
    model_load_ms = (time.perf_counter() - load_start) * 1000.0
    ocr = OCREngine(device=config.translation.device)
    ocr_start = time.perf_counter()
    ocr.warmup()
    ocr_load_ms = (time.perf_counter() - ocr_start) * 1000.0
    translator = Translator(engine, cache, glossary)

    print(
        f"\nModel load: translation engine {model_load_ms:.0f} ms, "
        f"OCR engine (first inference) {ocr_load_ms:.0f} ms"
    )

    cold_rows: dict[str, dict[str, float]] = {}
    for image_path in images:
        image = cv2.imread(str(image_path))
        frame = frame_from_image(image)
        pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
        result = pipeline.process_frame(frame)
        cold_rows[image_path.stem] = result.timings.as_dict()
    cache.close()

    # --- warm run: 100% cache hits ----------------------------------------
    cache = TranslationCache(db_path)
    translator = Translator(engine, cache, glossary)
    warm_rows: dict[str, dict[str, float]] = {}
    for image_path in images:
        image = cv2.imread(str(image_path))
        frame = frame_from_image(image)
        pipeline = Pipeline(config, ocr_engine=ocr, translator=translator)
        result = pipeline.process_frame(frame)
        warm_rows[image_path.stem] = result.timings.as_dict()
    cache.close()

    print_table(f"COLD run (empty cache)", cold_rows)
    print_table("WARM run (100% cache hits)", warm_rows)

    print("\n=== Conclusion ===")
    stages_only = [s for s in STAGES if s != "total"]
    slowest_cold = max(
        stages_only,
        key=lambda s: sum(row.get(s, 0.0) for row in cold_rows.values()),
    )
    slowest_warm = max(
        stages_only,
        key=lambda s: sum(row.get(s, 0.0) for row in warm_rows.values()),
    )
    avg_cold = sum(r["total"] for r in cold_rows.values()) / len(cold_rows)
    avg_warm = sum(r["total"] for r in warm_rows.values()) / len(warm_rows)
    print(f"Average end-to-end COLD: {avg_cold:.0f} ms")
    print(f"Average end-to-end WARM: {avg_warm:.0f} ms")
    print(f"Slowest stage (cold): {slowest_cold}")
    print(f"Slowest stage (warm): {slowest_warm}")
    print(
        "Under 0.5 s end-to-end (cold): "
        + ("YES" if avg_cold < 500 else "NO")
        + f"  [{avg_cold:.0f} ms]"
    )
    print(
        "Under 0.5 s end-to-end (warm): "
        + ("YES" if avg_warm < 500 else "NO")
        + f"  [{avg_warm:.0f} ms]"
    )


def main() -> int:
    """Run every benchmark."""
    bench_capture()
    bench_engines()
    run_pipeline_bench()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
