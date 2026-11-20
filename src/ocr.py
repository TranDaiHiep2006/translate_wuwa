"""OCR stage: RapidOCR (PP-OCR via ONNX Runtime, CPU).

The engine is loaded lazily so that importing this module never costs time or
memory when the tool only has to be configured.

Two detection resolutions are used:

* the **full frame** is read with the default settings (PP-OCRv4 server
  detection model), because the whole screen has to be scanned anyway;
* a **ROI crop** is read in its native resolution. RapidOCR's default
  ``det_limit_type`` is ``min``, which *upscales* a small crop to a minimum
  side length - that made a ROI crop slower than the whole frame (measured
  1538 ms vs 893 ms). Reading the crop at its native resolution is both
  faster (265 ms vs 893 ms) and more accurate, because the text keeps the
  pixel size it had on the screen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class OCRLine:
    """A single OCR text line with its bounding box and confidence."""

    text: str
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 in screen pixels
    confidence: float

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def top(self) -> int:
        return self.bbox[1]

    @property
    def bottom(self) -> int:
        return self.bbox[3]

    @property
    def left(self) -> int:
        return self.bbox[0]

    @property
    def right(self) -> int:
        return self.bbox[2]

    @property
    def center_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2.0


class OCREngine:
    """Thin wrapper around RapidOCR returning :class:`OCRLine` objects.

    ``intra_threads`` controls the ONNX Runtime intra-op thread count. On this
    machine (i5-12th gen, 16 cores) 5 threads was the fastest setting and cut
    the OCR time roughly in half compared to the default.
    """

    def __init__(self, device: str = "cpu", intra_threads: int = 5) -> None:
        self.device = device
        self.intra_threads = intra_threads
        self._engine = None
        self._roi_engine = None

    # -- engines -----------------------------------------------------------
    def _make_engine(self, native_resolution: bool):
        """Create a RapidOCR engine.

        ``native_resolution`` reads the image at its own size (used for the
        ROI crops); otherwise the default settings are used.
        """
        from rapidocr_onnxruntime import RapidOCR  # lazy import

        kwargs = {}
        if self.intra_threads and self.intra_threads > 0:
            kwargs["intra_op_num_threads"] = int(self.intra_threads)
        if native_resolution:
            # "max" never upscales the image, so a small crop stays small.
            kwargs["det_limit_type"] = "max"
            kwargs["det_limit_side_len"] = 2000
        return RapidOCR(**kwargs)

    def _ensure_engine(self):
        """Return the engine used for the full frame."""
        if self._engine is None:
            self._engine = self._make_engine(native_resolution=False)
        return self._engine

    def _ensure_roi_engine(self):
        """Return the engine used for the ROI crops (native resolution)."""
        if self._roi_engine is None:
            self._roi_engine = self._make_engine(native_resolution=True)
        return self._roi_engine

    def warmup(self) -> float:
        """Load the models and run a dummy inference. Returns the elapsed ms.

        Both engines are warmed up: the one for the full frame and the one
        for the ROI crops. They hold the same models but a different
        detection resolution, so they are two separate ONNX sessions.

        The dummy image carries real text, so the recognition model is
        initialized too - a blank image would only load the detection model.
        """
        dummy = self._dummy_image()
        start = time.perf_counter()
        self.read(dummy)
        self.read_roi(dummy)
        return (time.perf_counter() - start) * 1000.0

    @staticmethod
    def _dummy_image() -> np.ndarray:
        """A small image with some text on it."""
        try:
            import cv2

            image = np.zeros((64, 320, 3), dtype=np.uint8)
            cv2.putText(
                image,
                "Warmup 123",
                (8, 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            return image
        except Exception:  # pragma: no cover - cv2 is a hard dependency
            return np.zeros((64, 320, 3), dtype=np.uint8)

    # -- reading -----------------------------------------------------------
    def _parse(self, result) -> List[OCRLine]:
        """Convert a RapidOCR result into :class:`OCRLine` objects."""
        lines: List[OCRLine] = []
        if not result:
            return lines
        for item in result:
            try:
                points, text, score = item[0], item[1], item[2]
            except (IndexError, TypeError):  # pragma: no cover - defensive
                continue
            if text is None:
                continue
            xs = [int(p[0]) for p in points]
            ys = [int(p[1]) for p in points]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            lines.append(
                OCRLine(text=str(text).strip(), bbox=bbox, confidence=float(score))
            )
        return lines

    def read(self, image: np.ndarray) -> List[OCRLine]:
        """Run OCR on a BGR image and return the detected lines."""
        engine = self._ensure_engine()
        result, _ = engine(image)
        return self._parse(result)

    def read_roi(self, image: np.ndarray) -> List[OCRLine]:
        """Run OCR on a BGR crop at its native resolution.

        The returned bboxes are relative to the crop; the caller has to add
        the crop origin to get the full-screen coordinates.
        """
        engine = self._ensure_roi_engine()
        result, _ = engine(image)
        return self._parse(result)
