"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"


def _load(path: Path):
    import cv2

    if not path.exists():
        pytest.skip(f"missing fixture {path}; run scripts/make_fixtures.py")
    return cv2.imread(str(path))


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    """Path of the test fixtures folder."""
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def dialogue_image(fixture_dir: Path):
    """The 1920x1080 dialogue fixture (speaker name above 3 lines)."""
    return _load(fixture_dir / "sample_a_dialogue.png")


@pytest.fixture(scope="session")
def quest_image(fixture_dir: Path):
    """The 1920x1080 quest + skill fixture."""
    return _load(fixture_dir / "sample_b_quest.png")


@pytest.fixture(scope="session")
def menu_image(fixture_dir: Path):
    """The 1920x1080 menu + numbers fixture."""
    return _load(fixture_dir / "sample_c_menu.png")


@pytest.fixture(scope="session")
def scaled_image(fixture_dir: Path):
    """The 2560x1600 fixture (the dialogue image scaled up)."""
    return _load(fixture_dir / "sample_a_dialogue_2560x1600.png")


@pytest.fixture(scope="session")
def roi_base_image(fixture_dir: Path):
    """The reference frame of the ROI test (the dialogue + a last line)."""
    return _load(fixture_dir / "sample_d_roi_base.png")


@pytest.fixture(scope="session")
def roi_changed_image(fixture_dir: Path):
    """The same frame with only the last line changed."""
    return _load(fixture_dir / "sample_d_roi_changed.png")


@pytest.fixture(scope="session")
def long_image(fixture_dir: Path):
    """A long dialogue that has to be wrapped inside the bbox."""
    return _load(fixture_dir / "sample_e_long.png")


@pytest.fixture(scope="session")
def reward_image(fixture_dir: Path):
    """A quest block with the "Reward: 12000" line."""
    return _load(fixture_dir / "sample_f_reward.png")


@pytest.fixture(scope="session")
def ui_menu_image(fixture_dir: Path):
    """A menu with the Quest / Skill / Inventory / Settings labels."""
    return _load(fixture_dir / "sample_g_ui_menu.png")


@pytest.fixture(scope="session")
def two_corner_base(fixture_dir: Path):
    """The reference frame of the two-corner test (P3 fixture h)."""
    return _load(fixture_dir / "sample_h_two_corner_base.png")


@pytest.fixture(scope="session")
def two_corner_changed(fixture_dir: Path):
    """The same frame with the text of both corners changed (P3 fixture h)."""
    return _load(fixture_dir / "sample_h_two_corner_changed.png")


@pytest.fixture(scope="session")
def small_font_image(fixture_dir: Path):
    """The dialogue fixture with a 0.7x font (P3 fixture i)."""
    return _load(fixture_dir / "sample_i_small_font.png")


@pytest.fixture(scope="session")
def big_change_base(fixture_dir: Path):
    """The reference frame of the big screen change test (P3 fixture j)."""
    return _load(fixture_dir / "sample_j_big_change_base.png")


@pytest.fixture(scope="session")
def big_change(fixture_dir: Path):
    """The same frame with a big menu opened over the screen (P3 fixture j)."""
    return _load(fixture_dir / "sample_j_big_change.png")
