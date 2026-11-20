"""Benchmark the two translation engines on the 10 sample sentences.

Usage::

    python scripts/bench_translation.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.translator import SAMPLE_SENTENCES, benchmark_engines


def main() -> int:
    """Compare Argos and MarianMT on the same sentences."""
    results = benchmark_engines(("argos", "marian"), SAMPLE_SENTENCES)
    print(f"{'engine':<10}{'ok':<6}{'avg ms/sentence':>20}{'total ms':>12}")
    for entry in results:
        ok = "yes" if entry["ok"] else "no"
        avg = f"{entry['avg_ms']:.2f}" if entry["ok"] else "-"
        total = f"{entry.get('total_ms', 0):.2f}" if entry["ok"] else "-"
        print(f"{entry['engine']:<10}{ok:<6}{avg:>20}{total:>12}")
        if entry["error"]:
            print(f"    ERROR: {entry['error']}")

    for entry in results:
        if not entry["ok"]:
            continue
        print(f"\n--- {entry['engine']} ---")
        for index, (source, output) in enumerate(
            zip(SAMPLE_SENTENCES, entry["outputs"]), start=1
        ):
            print(f"{index:>2}. EN: {source}")
            print(f"    VI: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
