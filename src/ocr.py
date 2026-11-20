"""OCR stage: RapidOCR (PP-OCR via ONNX Runtime, CPU).

The engine is loaded lazily so that importing this module never costs time or
memory when the tool only has to be configured.

Two detection resolutions are used:

* the **full frame** is read at its native size (PP-OCRv4 server detection
  model), because the whole screen has to be scanned anyway;
* a **ROI crop** is read in its native resolution. RapidOCR's default
  ``det_limit_type`` is ``min``, which *upscales* a small crop to a minimum
  side length - that made a ROI crop slower than the whole frame (measured
  1538 ms vs 893 ms). Reading the crop at its native resolution is both
  faster (265 ms vs 893 ms) and more accurate, because the text keeps the
  pixel size it had on the screen.

The whole frame can also be read with the **two-step** strategy
(:meth:`OCREngine.read_detect_recognize`): the *detection* runs on a
downscaled copy of the frame and the *recognition* runs on the crops of the
**original** frame, in parallel. The detector is the slow part of the OCR
(598 ms of the 972 ms of a full frame read) and it always runs at the size
of the image it is given, so the only way to make it faster is to give it a
smaller image. The recognition keeps the native pixel size of the text, so
the accuracy is not lost.

P3 adds a **pool** of engines: the RapidOCR detector is not re-entrant, so
the parallel reading of several regions or tiles needs one engine per worker
thread. The thread count of the ONNX Runtime sessions is configurable
(``ocr.intra_threads``); 3 threads measured fastest on this machine.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


def _box_overlaps(
    a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
) -> bool:
    """Return True when the two boxes overlap.

    A box that only touches the border of the other one does **not** count
    as an overlap: a text line that ends exactly on a tile border belongs
    to the next tile, not to both.
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    overlap_x = min(ax2, bx2) - max(ax1, bx1)
    overlap_y = min(ay2, by2) - max(ay1, by1)
    return overlap_x > 0 and overlap_y > 0


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
    machine (i5-12th gen, 16 cores) **3 threads** measured fastest for both
    the full frame and the ROI crops (the default was 2x slower).
    """

    def __init__(
        self,
        device: str = "cpu",
        intra_threads: int = 3,
        pool_size: int = 3,
        pool_intra_threads: int = 2,
        rec_pool_size: int = 8,
    ) -> None:
        self.device = device
        self.intra_threads = int(intra_threads)
        self.pool_size = max(1, int(pool_size))
        # The thread count of the workers of the parallel pool. With
        # several crops read at the same time, the workers compete for the
        # same cores, so fewer threads per worker is faster.
        self.pool_intra_threads = int(pool_intra_threads)
        # The size of the pool used to recognize the text lines in parallel
        # (the two-step read). The recognition of a single text line is
        # short, so a bigger pool pays off here.
        self.rec_pool_size = max(1, int(rec_pool_size))
        self._engine = None
        self._roi_engines: List[object] = []
        self._pool: Optional[ThreadPoolExecutor] = None
        self._pool_engines: List[object] = []
        self._pool_intra_threads: int = 0
        self._rec_pool: Optional[ThreadPoolExecutor] = None
        self._rec_engines: List[object] = []
        self._rec_intra_threads: int = 0

    # -- engines -----------------------------------------------------------
    def _make_engine(self, native_resolution: bool, intra_threads: Optional[int] = None):
        """Create a RapidOCR engine.

        ``native_resolution`` reads the image at its own size (used for the
        ROI crops and the tiles); otherwise the default settings are used.
        ``intra_threads`` overrides the thread count of the ONNX Runtime
        session.
        """
        from rapidocr_onnxruntime import RapidOCR  # lazy import

        threads = self.intra_threads if intra_threads is None else int(intra_threads)
        kwargs = {}
        if threads and threads > 0:
            kwargs["intra_op_num_threads"] = int(threads)
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
        if not self._roi_engines:
            self._roi_engines.append(self._make_engine(native_resolution=True))
        return self._roi_engines[0]

    def _ensure_pool(self) -> ThreadPoolExecutor:
        """Return the thread pool used for the parallel reads."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self.pool_size, thread_name_prefix="ocr"
            )
        return self._pool

    def _ensure_rec_pool(self, intra_threads: Optional[int] = None) -> None:
        """Create the engines used to recognize the text lines in parallel.

        The engines are only recreated when the requested thread count
        changed: recreating them would reload the models.
        """
        threads = (
            self.pool_intra_threads if intra_threads is None else int(intra_threads)
        )
        if self._rec_engines and self._rec_intra_threads == threads:
            return
        self._rec_engines = []
        self._rec_intra_threads = threads
        while len(self._rec_engines) < self.rec_pool_size:
            self._rec_engines.append(
                self._make_engine(native_resolution=True, intra_threads=threads)
            )

    def _ensure_rec_workers(self) -> ThreadPoolExecutor:
        """Return the thread pool used to recognize the text lines."""
        if self._rec_pool is None:
            self._rec_pool = ThreadPoolExecutor(
                max_workers=self.rec_pool_size, thread_name_prefix="ocr-rec"
            )
        return self._rec_pool

    def _ensure_roi_pool(self, intra_threads: Optional[int] = None) -> None:
        """Create the engines of the parallel pool (native resolution).

        The engines are only recreated when the requested thread count
        changed: recreating them would reload the models.
        """
        threads = (
            self.pool_intra_threads if intra_threads is None else int(intra_threads)
        )
        if self._pool_engines and self._pool_intra_threads == threads:
            return
        self._pool_engines = []
        self._pool_intra_threads = threads
        while len(self._pool_engines) < self.pool_size:
            self._pool_engines.append(
                self._make_engine(native_resolution=True, intra_threads=threads)
            )

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

    # -- the two-step read (detection small, recognition native) -----------
    def read_detect_recognize(
        self,
        image: np.ndarray,
        detect_scale: float = 0.35,
        workers: int = 8,
        intra_threads: int = 1,
    ) -> List[OCRLine]:
        """Read a whole frame with the two-step strategy.

        The **detection** runs on a copy of the frame scaled down by
        ``detect_scale``; the boxes it finds are scaled back to the full
        resolution and the **recognition** runs on the crops of the
        *original* frame, in parallel.

        The reason is that the detector always runs at the size of the image
        it is given: on a 1920x1080 frame it needs 598 ms of the 972 ms of
        the whole OCR, and giving it a 0.35 scale frame cuts that to about
        200 ms. The recognition of the crops of the original frame keeps
        the native pixel size of the text, so the text stays accurate.

        Measured on this machine (fixture j, 10 text lines): 972 ms for the
        plain call, 424 ms for this strategy, with the same 10 lines found.
        """
        engine = self._ensure_engine()
        try:
            import cv2
        except Exception:  # pragma: no cover - cv2 is a hard dependency
            return self.read(image)

        height, width = image.shape[:2]
        scale = float(detect_scale)
        if scale <= 0 or scale >= 1:
            return self.read(image)

        small = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

        # -- 1. the detection, on the small frame --------------------------
        boxes, _elapse = engine.auto_text_det(small)
        if boxes is None or len(boxes) < 1:
            return []

        factor = 1.0 / scale
        full_boxes = [np.asarray(box, dtype=np.float32) * factor for box in boxes]
        crops = engine.get_crop_img_list(image, full_boxes)
        if not crops:
            return []

        # -- 2. the recognition, on the native crops, in parallel -----------
        results = self._recognize_parallel(crops, workers, intra_threads)

        lines: List[OCRLine] = []
        for box, (text, score) in zip(full_boxes, results):
            if not text:
                continue
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            lines.append(
                OCRLine(
                    text=str(text).strip(),
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=float(score),
                )
            )
        lines.sort(key=lambda line: (line.top, line.left))
        return lines

    def _recognize_parallel(
        self,
        crops: Sequence[np.ndarray],
        workers: int,
        intra_threads: int,
    ) -> List[Tuple[str, float]]:
        """Recognize the crops of the text lines in parallel.

        The recognition model is not re-entrant, so every worker gets its
        own ONNX session (the models are shared on disk, the sessions are
        not). The result of every crop keeps the order of ``crops``.
        """
        if not crops:
            return []
        if len(crops) == 1:
            engine = self._ensure_roi_engine()
            return list(engine.text_rec([crops[0]])[0])

        self._ensure_rec_pool(intra_threads=intra_threads)
        pool = self._ensure_rec_workers()
        engines = list(self._rec_engines)

        def _recognize(index_and_crop):
            index, crop = index_and_crop
            engine = engines[index % len(engines)]
            result = engine.text_rec([crop])[0]
            return index, result[0] if result else ("", 0.0)

        results: List[Tuple[str, float]] = [("", 0.0)] * len(crops)
        for index, value in pool.map(_recognize, enumerate(crops)):
            results[index] = value
        return results

    # -- the tiled read ----------------------------------------------------
    def read_tiles(
        self,
        image: np.ndarray,
        tiles: Sequence[Tuple[int, int, int, int]],
        detect_scale: float = 0.35,
        workers: int = 8,
        intra_threads: int = 1,
    ) -> List[OCRLine]:
        """Read only the text lines that fall into the given tiles.

        The **detection** runs once on a downscaled copy of the whole frame,
        so a text line is never cut by a tile border: the detector finds the
        line as a whole and the line is then assigned to the tile it belongs
        to. Only the lines of the requested tiles are **recognized**, and
        they are recognized in parallel, on the crops of the original frame.

        This is the strategy that makes the tiled refresh fast *and* exact:
        reading the tiles separately (detection inside each tile) cut the
        text lines at the tile borders - measured on the fixture (j), the
        text "Cost 25 Astrite" became "Cost 25 As" and the rest was lost.

        ``tiles`` are the rectangles (x1, y1, x2, y2) of the changed tiles,
        in full-screen coordinates.
        """
        if not tiles:
            return []
        engine = self._ensure_engine()
        try:
            import cv2
        except Exception:  # pragma: no cover - cv2 is a hard dependency
            return self.read(image)

        height, width = image.shape[:2]
        scale = float(detect_scale)
        if scale <= 0 or scale >= 1:
            scale = 1.0

        if scale < 1.0:
            small = cv2.resize(
                image,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            small = image

        boxes, _elapse = engine.auto_text_det(small)
        if boxes is None or len(boxes) < 1:
            return []

        factor = 1.0 / scale
        full_boxes = [np.asarray(box, dtype=np.float32) * factor for box in boxes]

        # -- keep only the lines that fall into a requested tile ------------
        selected: List[int] = []
        for index, box in enumerate(full_boxes):
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            line_box = (min(xs), min(ys), max(xs), max(ys))
            for tile in tiles:
                if _box_overlaps(line_box, tile):
                    selected.append(index)
                    break
        if not selected:
            return []

        # -- recognize the selected lines, in parallel -----------------------
        crops = engine.get_crop_img_list(image, [full_boxes[i] for i in selected])
        results = self._recognize_parallel(crops, workers, intra_threads)

        lines: List[OCRLine] = []
        for index, (text, score) in zip(selected, results):
            if not text:
                continue
            box = full_boxes[index]
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            lines.append(
                OCRLine(
                    text=str(text).strip(),
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=float(score),
                )
            )
        lines.sort(key=lambda line: (line.top, line.left))
        return lines

    # -- parallel reading --------------------------------------------------
    def read_parallel(
        self, images: Sequence[np.ndarray], intra_threads: Optional[int] = None
    ) -> List[List[OCRLine]]:
        """Read several crops in parallel and return the lines of each crop.

        The RapidOCR detector is not re-entrant, so every worker gets its own
        engine instance (the models are shared on disk, the ONNX sessions are
        not). The result of every crop keeps the order of ``images``.

        ``intra_threads`` overrides the thread count of the ONNX Runtime
        sessions of the workers. It is useful because the best value
        depends on the number of crops: with 4 tiles in parallel, **2**
        threads per worker measured faster (289 ms) than 3 (364 ms) or 1
        (470 ms), because the workers compete for the same cores.
        """
        if not images:
            return []
        if len(images) == 1:
            return [self.read_roi(images[0])]

        self._ensure_roi_pool(intra_threads=intra_threads)
        pool = self._ensure_pool()
        engines = list(self._pool_engines)

        def _read(index_and_image):
            index, image = index_and_image
            engine = engines[index % len(engines)]
            result, _ = engine(image)
            return index, self._parse(result)

        results: List[List[OCRLine]] = [[] for _ in images]
        for index, lines in pool.map(_read, enumerate(images)):
            results[index] = lines
        return results

    def close(self) -> None:
        """Release the thread pools."""
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None
        if self._rec_pool is not None:
            self._rec_pool.shutdown(wait=False)
            self._rec_pool = None
