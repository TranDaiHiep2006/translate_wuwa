"""Application configuration loading (config/config.yaml).

Everything resolution dependent is expressed relative to a reference height
(1080p) and scaled at runtime, so no pixel value is hardcoded for a specific
monitor.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

REFERENCE_HEIGHT = 1080.0


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` into ``base`` and return ``base``."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@dataclass
class OverlayConfig:
    """Overlay rendering options (sizes are reference-1080p pixels)."""

    font_family: str = "Segoe UI"
    font_size: int = 20
    text_color: str = "#FFD54F"
    speaker_color: str = "#7FD8FF"
    background_color: str = "#000000"
    # 255 = fully opaque: the original English text is completely hidden.
    background_alpha: int = 255
    padding: int = 6
    margin: int = 10
    show_status: bool = True
    status_font_size: int = 16
    # How much the box may grow vertically before the font size is reduced.
    max_height_growth: float = 3.0


@dataclass
class TranslationConfig:
    """Translation engine options."""

    engine: str = "argos"
    device: str = "cpu"
    batch_size: int = 8
    max_workers: int = 1
    # Split a block into sentences and translate each one separately.
    split_sentences: bool = True
    # Sentence splitter: "regex" (fast, default) or "stanza" (the Argos one).
    sentence_splitter: str = "regex"
    # A block whose whole text is a UI label (Quest, Skill, Inventory, ...)
    # is left in English instead of being translated.
    skip_ui_labels: bool = True


@dataclass
class HUDConfig:
    """Live latency HUD options (item E of P3).

    The HUD is a diagnostic overlay: it shows the stage timings and the
    running median, never any translated text. It is OFF by default and is
    toggled with ``F9``.
    """

    enabled: bool = False
    hotkey: str = "F9"
    # Number of cycles kept for the running median.
    history: int = 10
    font_size: int = 14
    text_color: str = "#8CFF8C"
    background_color: str = "#101010"
    background_alpha: int = 200
    margin: int = 10


@dataclass
class SpeakerConfig:
    """Speaker detection options.

    ``ui_labels_path`` holds the blacklist of WuWa UI labels (Quest, Skill,
    Inventory, ...) and ``roster_path`` the list of known character names.
    Both files are plain YAML and can be edited by the user.
    """

    ui_labels_path: Path = PROJECT_ROOT / "config" / "ui_labels.yaml"
    roster_path: Path = PROJECT_ROOT / "config" / "roster.yaml"
    enabled: bool = True


@dataclass
class CaptureConfig:
    """Screen capture options."""

    backend: str = "auto"
    monitor: int = 0


@dataclass
class Config:
    """Top level configuration object."""

    source_lang: str = "en"
    target_lang: str = "vi"
    poll_ms: int = 200
    diff_threshold: float = 0.002
    debounce_ms: int = 120
    ocr_conf_min: float = 0.5
    min_line_chars: int = 2
    group_gap_px: int = 18
    speaker_gap_px: int = 120
    speaker_max_words: int = 3
    hotkey: str = "F8"

    # -- adaptive grouping (item D of P3) ---------------------------------
    # The grouping thresholds are derived from the measured font height of the
    # current frame instead of being fixed pixel values, so the grouping also
    # works on a font that is smaller than the one of the fixtures.
    adaptive_grouping: bool = True
    # group_gap_px = font_height * group_gap_ratio
    group_gap_ratio: float = 0.55
    # speaker_gap_px = font_height * speaker_gap_ratio
    speaker_gap_ratio: float = 3.0
    # Below this many detected lines the measured font height is not trusted
    # and the reference 1080p values are used instead.
    adaptive_min_lines: int = 2

    # -- ROI OCR -----------------------------------------------------------
    # Only the changed part of the screen is read by the OCR.
    roi_enabled: bool = True
    # Padding around the changed rectangle (reference pixels at 1080p height).
    roi_padding_px: int = 16
    # A changed area smaller than this (in pixels) cannot hold any text.
    roi_min_area: int = 400
    # Above this fraction of the screen the whole frame is read instead.
    roi_full_frame_threshold: float = 0.8
    # The whole frame is re-read at least this often (ms) to prune the blocks
    # whose text disappeared and to catch the text the ROI missed.
    roi_full_refresh_ms: int = 2000
    # ... or after this many frames, whichever comes first.
    roi_full_refresh_frames: int = 10

    # -- per-region ROI (item A of P3) -------------------------------------
    # The changed area is split into several disjoint rectangles instead of
    # one big union rectangle, so a change in two distant corners does not
    # cost a crop that covers the whole screen.
    roi_regions_enabled: bool = True
    # A region smaller than this (in pixels, scaled) is merged into its
    # nearest neighbour instead of being read on its own.
    roi_region_min_area: int = 1200
    # Maximum number of regions that are read in one frame.
    roi_max_regions: int = 4
    # Number of worker threads used to read the regions in parallel.
    roi_workers: int = 3
    # Two components of the diff mask that are on the same line and closer
    # than this (reference pixels at 1080p) belong to the same region. This
    # is what keeps a text line in one piece: the diff of a changed line is
    # made of one component per glyph.
    roi_region_merge_gap: int = 200
    # A region is expanded horizontally to at least this width (reference
    # pixels at 1080p). The diff of a changed line only covers the glyphs
    # that really changed, so the crop has to be wide enough for the OCR to
    # read the whole line.
    roi_region_min_width: int = 480
    # Above this fraction of the screen that changed, the tiled refresh is
    # used instead of one big crop: reading a grid of small tiles in
    # parallel is faster than reading one huge rectangle.
    roi_tiles_threshold: float = 0.01

    # -- tiled refresh (item A of P3) --------------------------------------
    # The scheduled refresh reads the frame as a grid of tiles and only the
    # changed tiles are read by the OCR.
    tiles_enabled: bool = True
    tile_cols: int = 4
    tile_rows: int = 3
    # A tile whose changed-pixel fraction is above this value is read.
    tile_changed_threshold: float = 0.004
    # Above this fraction of changed tiles the whole frame is read instead.
    tile_full_frame_ratio: float = 0.5
    # Number of worker threads used to read the tiles in parallel.
    tile_workers: int = 3
    # The thread count of the ONNX Runtime session of each tile worker.
    # With several tiles read at the same time the workers compete for the
    # same cores, so 2 threads per worker measured faster than 3.
    tile_intra_threads: int = 2

    # -- downscaled diff (item B of P3) ------------------------------------
    # The frame differencing runs on a downscaled copy of the frame.
    diff_downscale: int = 4
    # The full resolution diff is only used to refine the edges of a region.
    diff_refine_edges: bool = True

    # -- async pipeline (item C of P3) -------------------------------------
    # The OCR of a frame overlaps the translation of the previous frame.
    async_pipeline: bool = True
    # How many translations may be in flight at the same time.
    async_queue_size: int = 2

    # -- OCR engine --------------------------------------------------------
    # Number of ONNX Runtime intra-op threads. Measured on this machine:
    # 3 threads is the fastest stable setting for both the full frame and
    # the ROI crops.
    ocr_intra_threads: int = 3

    # The two-step read (item A of P3): the detection runs on a downscaled
    # copy of the frame and the recognition on the crops of the original
    # frame, in parallel. The detector is the slow part of the OCR and it
    # always runs at the size of the image it is given, so the only way to
    # make it faster is to give it a smaller image. The recognition keeps
    # the native pixel size of the text, so the accuracy is not lost.
    ocr_two_step: bool = True
    # The scale of the frame the detection runs on. Measured on the fixture
    # (j): 0.35 gives the same 10 text lines as the plain call and is
    # faster (972 ms -> 437 ms). 0.5 is the default because the 0.7x font
    # keeps its sentence-ending period at 0.5 (at 0.35 it is sometimes
    # lost), and it is still well under the 500 ms target.
    ocr_detect_scale: float = 0.5
    # Number of worker threads used to recognize the text lines in parallel.
    ocr_rec_workers: int = 8
    # The thread count of the ONNX Runtime session of each recognition
    # worker. The recognition of a single line is short, so 1 thread per
    # worker measured fastest (190 ms for 10 lines with 4 workers).
    ocr_rec_intra_threads: int = 1

    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    hud: HUDConfig = field(default_factory=HUDConfig)
    cache_db_path: Path = PROJECT_ROOT / "data" / "cache.db"
    sessions_dir: Path = PROJECT_ROOT / "data" / "sessions"
    glossary_path: Path = PROJECT_ROOT / "config" / "glossary.yaml"
    raw: Dict[str, Any] = field(default_factory=dict)

    # -- scaling -----------------------------------------------------------
    def scale(self, value: float, screen_height: int) -> float:
        """Scale a reference-1080p pixel ``value`` to ``screen_height``."""
        if screen_height <= 0:
            return float(value)
        return float(value) * (float(screen_height) / REFERENCE_HEIGHT)

    @property
    def cache_db_path_str(self) -> str:
        return str(self.cache_db_path)

    @property
    def sessions_dir_str(self) -> str:
        return str(self.sessions_dir)


def load_config(path: str | Path | None = None) -> Config:
    """Load the YAML configuration and return a :class:`Config`.

    Missing keys fall back to the dataclass defaults so the tool keeps working
    with a partial config file.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    defaults = Config()
    overlay_data = data.pop("overlay", {}) or {}
    translation_data = data.pop("translation", {}) or {}
    capture_data = data.pop("capture", {}) or {}
    speaker_data = data.pop("speaker", {}) or {}
    hud_data = data.pop("hud", {}) or {}
    cache_data = data.pop("cache", {}) or {}
    sessions_data = data.pop("sessions", {}) or {}
    glossary_data = data.pop("glossary", {}) or {}

    for key in ("overlay", "translation", "capture", "speaker", "hud"):
        data.pop(key, None)

    cfg = Config(**{k: v for k, v in data.items() if k in defaults.__dict__})
    cfg.overlay = OverlayConfig(**{**defaults.overlay.__dict__, **overlay_data})
    cfg.translation = TranslationConfig(
        **{**defaults.translation.__dict__, **translation_data}
    )
    cfg.capture = CaptureConfig(**{**defaults.capture.__dict__, **capture_data})
    cfg.speaker = SpeakerConfig(**{**defaults.speaker.__dict__, **speaker_data})
    cfg.hud = HUDConfig(**{**defaults.hud.__dict__, **hud_data})

    if cache_data.get("db_path"):
        cfg.cache_db_path = PROJECT_ROOT / cache_data["db_path"]
    if sessions_data.get("dir"):
        cfg.sessions_dir = PROJECT_ROOT / sessions_data["dir"]
    if glossary_data.get("path"):
        cfg.glossary_path = PROJECT_ROOT / glossary_data["path"]
    if speaker_data.get("ui_labels_path"):
        cfg.speaker.ui_labels_path = PROJECT_ROOT / speaker_data["ui_labels_path"]
    if speaker_data.get("roster_path"):
        cfg.speaker.roster_path = PROJECT_ROOT / speaker_data["roster_path"]

    cfg.raw = copy.deepcopy(data)
    return cfg
