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
    group_gap_px: int = 28
    speaker_gap_px: int = 60
    speaker_max_words: int = 3
    hotkey: str = "F8"

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

    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
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
    cache_data = data.pop("cache", {}) or {}
    sessions_data = data.pop("sessions", {}) or {}
    glossary_data = data.pop("glossary", {}) or {}

    for key in ("overlay", "translation", "capture", "speaker"):
        data.pop(key, None)

    cfg = Config(**{k: v for k, v in data.items() if k in defaults.__dict__})
    cfg.overlay = OverlayConfig(**{**defaults.overlay.__dict__, **overlay_data})
    cfg.translation = TranslationConfig(
        **{**defaults.translation.__dict__, **translation_data}
    )
    cfg.capture = CaptureConfig(**{**defaults.capture.__dict__, **capture_data})
    cfg.speaker = SpeakerConfig(**{**defaults.speaker.__dict__, **speaker_data})

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
