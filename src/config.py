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
    background_color: str = "#000000"
    background_alpha: int = 140
    padding: int = 6
    margin: int = 10
    show_status: bool = True
    status_font_size: int = 16


@dataclass
class TranslationConfig:
    """Translation engine options."""

    engine: str = "argos"
    device: str = "cpu"
    batch_size: int = 8
    max_workers: int = 1


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
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
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
    cache_data = data.pop("cache", {}) or {}
    sessions_data = data.pop("sessions", {}) or {}
    glossary_data = data.pop("glossary", {}) or {}

    for key in ("overlay", "translation", "capture"):
        data.pop(key, None)

    cfg = Config(**{k: v for k, v in data.items() if k in defaults.__dict__})
    cfg.overlay = OverlayConfig(**{**defaults.overlay.__dict__, **overlay_data})
    cfg.translation = TranslationConfig(
        **{**defaults.translation.__dict__, **translation_data}
    )
    cfg.capture = CaptureConfig(**{**defaults.capture.__dict__, **capture_data})

    if cache_data.get("db_path"):
        cfg.cache_db_path = PROJECT_ROOT / cache_data["db_path"]
    if sessions_data.get("dir"):
        cfg.sessions_dir = PROJECT_ROOT / sessions_data["dir"]
    if glossary_data.get("path"):
        cfg.glossary_path = PROJECT_ROOT / glossary_data["path"]

    cfg.raw = copy.deepcopy(data)
    return cfg
