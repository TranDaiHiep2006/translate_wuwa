"""Screen capture backends: dxcam (DXGI Desktop Duplication) and mss.

The active backend is chosen at runtime; if the preferred one fails, the other
is used automatically. The resolution is always read from the capture library
at runtime - no resolution is hardcoded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class Frame:
    """A captured screen frame."""

    image: np.ndarray  # BGR uint8 array, like OpenCV
    width: int
    height: int
    timestamp: float

    @property
    def size(self) -> Tuple[int, int]:
        return (self.width, self.height)


class CaptureBackend:
    """Interface implemented by every capture backend."""

    name = "base"

    def grab(self) -> Frame:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class MssBackend(CaptureBackend):
    """Capture backend based on the ``mss`` library."""

    name = "mss"

    def __init__(self, monitor_index: int = 0) -> None:
        import mss  # imported lazily so the module stays importable

        self._mss = mss
        self._monitor_index = monitor_index
        self._sct = mss.mss()
        self._monitor = self._sct.monitors[self._monitor_index + 1]
        self._width = int(self._monitor["width"])
        self._height = int(self._monitor["height"])

    def grab(self) -> Frame:
        raw = self._sct.grab(self._monitor)
        # mss returns BGRA; drop alpha and convert to BGR for OpenCV.
        bgra = np.asarray(raw)[:, :, :3]
        return Frame(
            image=np.ascontiguousarray(bgra),
            width=self._width,
            height=self._height,
            timestamp=time.perf_counter(),
        )

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:  # pragma: no cover - defensive
            pass


class DxcamBackend(CaptureBackend):
    """Capture backend based on ``dxcam`` (DXGI Desktop Duplication).

    ``dxcam`` needs ``start()`` before the first ``grab()``; the capture
    thread then runs in the background and ``grab()`` returns the newest
    frame.
    """

    name = "dxcam"

    def __init__(self, monitor_index: int = 0) -> None:
        import dxcam  # imported lazily

        self._dxcam = dxcam
        self._camera = dxcam.create(output_idx=monitor_index, output_color="BGR")
        if self._camera is None:
            raise RuntimeError("dxcam could not create a capture device")
        self._width = int(self._camera.width)
        self._height = int(self._camera.height)
        if not self._width or not self._height:
            raise RuntimeError("dxcam returned an invalid output size")
        self._camera.start(target_fps=60)

    def grab(self) -> Frame:
        bgr = self._camera.grab()
        if bgr is None:
            bgr = self._camera.get_latest_frame()
        if bgr is None:
            raise RuntimeError("dxcam returned no frame")
        return Frame(
            image=np.ascontiguousarray(bgr),
            width=int(self._width),
            height=int(self._height),
            timestamp=time.perf_counter(),
        )

    def close(self) -> None:
        try:
            self._camera.release()
        except Exception:  # pragma: no cover - defensive
            pass


def create_backend(preferred: str = "auto", monitor_index: int = 0) -> CaptureBackend:
    """Create a capture backend.

    ``preferred`` may be ``"auto"``, ``"dxcam"`` or ``"mss"``. With ``"auto"``
    dxcam is tried first (usually faster); if it fails, mss is used. With an
    explicit preference the other backend is still used as a fallback.
    """
    order = ["dxcam", "mss"] if preferred in ("auto", "dxcam") else ["mss", "dxcam"]
    errors = []
    for name in order:
        try:
            if name == "dxcam":
                return DxcamBackend(monitor_index)
            return MssBackend(monitor_index)
        except Exception as exc:  # pragma: no cover - depends on machine
            errors.append(f"{name}: {exc}")
    raise RuntimeError("no capture backend available -> " + " | ".join(errors))


def detect_screen_size(backend: CaptureBackend) -> Tuple[int, int]:
    """Return the (width, height) of the captured region."""
    frame = backend.grab()
    return frame.width, frame.height


def benchmark_backends(
    monitor_index: int = 0, iterations: int = 30
) -> list[dict]:
    """Measure the average grab time of every available backend.

    Returns a list of dicts with the backend name, whether it worked, the
    average latency in milliseconds and the errors encountered.
    """
    results = []
    for name in ("mss", "dxcam"):
        entry = {
            "backend": name,
            "ok": False,
            "avg_ms": float("nan"),
            "error": "",
        }
        try:
            backend = (
                MssBackend(monitor_index)
                if name == "mss"
                else DxcamBackend(monitor_index)
            )
            backend.grab()  # warm-up
            start = time.perf_counter()
            for _ in range(iterations):
                backend.grab()
            elapsed = (time.perf_counter() - start) / iterations * 1000.0
            entry["ok"] = True
            entry["avg_ms"] = round(elapsed, 3)
            backend.close()
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)
    return results


def frame_from_image(image: np.ndarray) -> Frame:
    """Wrap an existing BGR array into a :class:`Frame` (used by tests)."""
    height, width = image.shape[:2]
    return Frame(
        image=image, width=int(width), height=int(height), timestamp=time.perf_counter()
    )
