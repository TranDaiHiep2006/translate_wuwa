"""Live latency HUD (item E of P3).

A small overlay in a corner of the screen that shows the last measured stage
timings and the running median of the last cycles. It is a **diagnostic**
tool: it shows numbers only, never a translated text.

The HUD reads the very same :class:`~src.pipeline.StageTimings` that
``scripts/bench.py`` prints, so the numbers on the screen are the numbers of
the benchmark. It is OFF by default and is toggled with ``F9``.

The HUD never takes the focus, never blocks the game input and never slows
the main overlay: it is painted by the same widget as the translations, from
a small snapshot of the timings.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional

from .config import HUDConfig
from .pipeline import StageTimings


@dataclass
class HUDSnapshot:
    """The numbers the HUD shows.

    ``timings`` are the last measured stage timings and ``median_total`` is
    the running median of the total over the last cycles.
    """

    timings: StageTimings = field(default_factory=StageTimings)
    median_total: float = 0.0
    cycles: int = 0
    action: str = ""


class HUDState:
    """Keeps the last timings and the running median.

    The class is deliberately free of any Qt dependency, so it can be tested
    without a Qt application.
    """

    def __init__(self, history: int = 10) -> None:
        self.history = max(1, int(history))
        self._totals: List[float] = []
        self.last = HUDSnapshot()
        self.enabled = False

    # -- updates -----------------------------------------------------------
    def update(self, timings: StageTimings, action: str = "") -> HUDSnapshot:
        """Record a new cycle and return the new snapshot."""
        total = float(timings.total)
        self._totals.append(total)
        if len(self._totals) > self.history:
            del self._totals[: len(self._totals) - self.history]
        self.last = HUDSnapshot(
            timings=timings,
            median_total=statistics.median(self._totals) if self._totals else 0.0,
            cycles=len(self._totals),
            action=action,
        )
        return self.last

    # -- queries -----------------------------------------------------------
    @property
    def median_total(self) -> float:
        """The running median of the total over the last cycles."""
        return self.last.median_total

    @property
    def cycles(self) -> int:
        """The number of cycles that are kept."""
        return len(self._totals)

    def toggle(self) -> bool:
        """Show or hide the HUD. Returns the new state."""
        self.enabled = not self.enabled
        return self.enabled

    def reset(self) -> None:
        """Forget the recorded cycles."""
        self._totals.clear()
        self.last = HUDSnapshot()


def format_hud_lines(snapshot: HUDSnapshot) -> List[str]:
    """Return the text lines the HUD shows.

    The lines are the stage timings of the last cycle, the running median of
    the total and the number of cycles that are kept.
    """
    timings = snapshot.timings
    return [
        f"capture {timings.capture:7.1f} ms",
        f"diff    {timings.diff:7.1f} ms",
        f"ocr     {timings.ocr:7.1f} ms",
        f"group   {timings.group:7.1f} ms",
        f"transl. {timings.translate:7.1f} ms",
        f"render  {timings.render:7.1f} ms",
        f"TOTAL   {timings.total:7.1f} ms",
        f"median  {snapshot.median_total:7.1f} ms  (n={snapshot.cycles})",
    ]
