"""Tests of the per-monitor hot-plug support (item F of P3).

The tests use a fake capture backend: the real one needs a DXGI device and
two Desktop Duplication sessions cannot run at the same time, so the
behaviour is verified with a mock.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.display import (
    DEFAULT_DPI,
    DisplayState,
    DisplayWatcher,
    list_displays,
    read_dpi,
)


class FakeBackend:
    """A capture backend that only remembers whether it was closed."""

    name = "fake"

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.closed = False
        self.grabs = 0

    def grab(self):
        from src.capture import Frame
        import numpy as np

        self.grabs += 1
        return Frame(
            image=np.zeros((self.height, self.width, 3), dtype=np.uint8),
            width=self.width,
            height=self.height,
            timestamp=0.0,
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def config():
    return load_config()


def test_the_first_observation_is_the_baseline(config) -> None:
    """The first observation is not a change: it only records the size."""
    backend = FakeBackend()
    watcher = DisplayWatcher(config, backend=backend)
    assert watcher.observe((1920, 1080)) is False
    assert watcher.detections == 0
    assert watcher.restarts == 0


def test_an_unchanged_size_is_not_a_change(config) -> None:
    """The same size twice: nothing happens."""
    watcher = DisplayWatcher(config, backend=FakeBackend())
    watcher.observe((1920, 1080))
    assert watcher.observe((1920, 1080)) is False
    assert watcher.detections == 0
    assert watcher.restarts == 0


def test_a_changed_size_is_detected(config) -> None:
    """A different size is a change of the captured area."""
    watcher = DisplayWatcher(config, backend=FakeBackend())
    watcher.observe((1920, 1080))
    assert watcher.observe((2560, 1440)) is True
    assert watcher.detections == 1


def test_the_restart_is_counted(config) -> None:
    """Every detected change restarts the capture."""
    created = []

    def factory():
        backend = FakeBackend()
        created.append(backend)
        return backend

    watcher = DisplayWatcher(config, backend=FakeBackend(), backend_factory=factory)
    watcher.observe((1920, 1080))
    watcher.observe((2560, 1440))
    assert watcher.restarts == 1
    assert len(created) == 1


def test_the_old_backend_is_closed_and_a_new_one_is_created(config) -> None:
    """The old backend is closed before the new one is created.

    DXGI Desktop Duplication does not allow two capture sessions on the
    same output at the same time, so the old one has to be closed first.
    """
    old = FakeBackend()
    new = FakeBackend()
    watcher = DisplayWatcher(config, backend=old, backend_factory=lambda: new)
    result = watcher.restart_capture()
    assert old.closed is True
    assert result is new
    assert watcher.backend is new


def test_the_callback_is_called_on_a_change(config) -> None:
    """The registered callback is called with the new state."""
    seen = []
    watcher = DisplayWatcher(config, backend=FakeBackend())
    watcher.on_changed(seen.append)
    watcher.observe((1920, 1080))
    watcher.observe((1280, 720))
    assert len(seen) == 1
    assert isinstance(seen[0], DisplayState)
    assert seen[0].size == (1280, 720)


def test_the_scale_is_the_height_over_1080(config) -> None:
    """The scale factor is the height of the display over 1080."""
    watcher = DisplayWatcher(config, backend=FakeBackend())
    watcher.observe((1920, 1080))
    assert watcher.scale() == pytest.approx(1.0)
    watcher.observe((1920, 1440))
    assert watcher.scale() == pytest.approx(1440 / 1080.0)


def test_the_description_contains_the_numbers(config) -> None:
    """The description holds the size, the DPI, the detections and the restarts."""
    watcher = DisplayWatcher(config, backend=FakeBackend())
    watcher.observe((1920, 1080))
    watcher.observe((2560, 1440))
    description = watcher.describe()
    assert "2560x1440" in description
    assert "dpi" in description
    assert "detections 1" in description
    assert "restarts 1" in description


def test_a_failing_factory_keeps_the_old_backend(config) -> None:
    """When the new backend cannot be created, the old one is kept."""
    old = FakeBackend()

    def broken():
        raise RuntimeError("no capture device")

    watcher = DisplayWatcher(config, backend=old, backend_factory=broken)
    assert watcher.restart_capture() is None
    assert watcher.backend is old
    assert watcher.restarts == 0


def test_the_display_state_describes_itself() -> None:
    """The state of a display is described in one line."""
    state = DisplayState(index=0, width=1920, height=1080, dpi=96)
    description = state.describe()
    assert "1920x1080" in description
    assert "96 dpi" in description


def test_reading_the_dpi_never_fails() -> None:
    """The DPI can always be read: 96 when it is unknown."""
    dpi = read_dpi(0)
    assert dpi > 0
    assert dpi == DEFAULT_DPI or dpi > 0


def test_the_displays_can_be_listed() -> None:
    """The list of the displays is returned (it may be empty off Windows)."""
    displays = list_displays()
    assert isinstance(displays, list)
    for display in displays:
        assert display.width > 0
        assert display.height > 0
