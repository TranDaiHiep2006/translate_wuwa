"""Speaker detection: the UI-label blacklist and the character roster.

Two YAML files extend the built-in vocabulary:

* ``config/ui_labels.yaml`` - the blacklist of WuWa UI labels (Quest, Skill,
  Inventory, Settings, ...). A line that matches one of them is **never** a
  speaker.
* ``config/roster.yaml`` - the known character names. A short capitalised
  line above a dialogue is a speaker only when its name is in the roster, or
  when it ends with a colon and has 1-3 words (that keeps the NPC names that
  the game writes as ``Name: dialogue``).

The built-in vocabulary already covers the labels and the characters of the
P2 fixtures, so the tool behaves correctly even when the YAML files are
missing. The YAML files only *add* to it (and can remove a built-in entry
with the ``disable`` list).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import yaml

# The trailing colon of a label or of a "Name: dialogue" line.
_COLON = ":"
# A capitalised word (with the apostrophes and the dashes of the names).
CAP_WORD_RE = re.compile(r"^[A-Z][A-Za-z'\-]*$")

# The WuWa UI labels that are never a speaker name.
BUILTIN_UI_LABELS: List[str] = [
    "Quest",
    "Quests",
    "Quest Log",
    "Journal",
    "Objective",
    "Objectives",
    "Mission",
    "Missions",
    "Task",
    "Tasks",
    "Inventory",
    "Items",
    "Bag",
    "Backpack",
    "Skill",
    "Skills",
    "Ability",
    "Abilities",
    "Weapon",
    "Weapons",
    "Equipment",
    "Settings",
    "Setting",
    "Options",
    "Option",
    "Menu",
    "Map",
    "Character",
    "Characters",
    "Resonator",
    "Resonators",
    "Team",
    "Party",
    "Handbook",
    "Guide",
    "Tutorial",
    "Event",
    "Events",
    "Shop",
    "Store",
    "Mail",
    "Notice",
    "News",
    "Achievements",
    "Achievement",
    "Archive",
    "Codex",
    "Adventure",
    "Tower",
    "Controller",
    "Disc",
    "Echo",
    "Echoes",
    "Tacet Mark",
    "Upgrade",
    "Upgrades",
    "Details",
    "Info",
    "Information",
    "Instructions",
    "Description",
    "Rewards",
    "Reward",
    "Progress",
    "Rank",
    "Level",
    "Lv",
    "Attribute",
    "Attributes",
    "Combat",
    "Multiplayer",
    "Co-op",
    "Photograph",
    "Album",
    "Sound",
    "Graphics",
    "Display",
    "Controls",
    "Keybind",
    "Logout",
    "Exit",
    "Cancel",
    "Confirm",
    "Close",
    "Back",
    "Continue",
    "Skip",
    "Yes",
    "No",
    "OK",
]

# The playable Resonators and the well known NPCs.
BUILTIN_ROSTER: List[str] = [
    "Rover",
    "Jiyan",
    "Changli",
    "Carlotta",
    "Shorekeeper",
    "Encore",
    "Jinhsi",
    "Calcharo",
    "Yangyang",
    "Zhezhi",
    "Verina",
    "Sanada",
    "Cartethyia",
    "Augusta",
    "Iuno",
    "Zani",
    "Ciaccona",
    "Galbrena",
    "Phrolova",
    "Camellya",
    "Brant",
    "Lupa",
    "Youhu",
    "Lumi",
    "Mornye",
    "Aalto",
    "Xianyun",
    "Yuanwu",
    "Shenzhi",
    "Baizhi",
    "Lingyang",
    "Yinlin",
    "Septimont",
]


def normalize_label(text: str) -> str:
    """Normalise a label for the blacklist lookup.

    The text is lower-cased, the surrounding whitespace is removed and one
    optional trailing colon is dropped.
    """
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.endswith(_COLON):
        cleaned = cleaned[:-1]
    return cleaned.strip().lower()


class SpeakerVocabulary:
    """The UI-label blacklist and the character roster."""

    def __init__(
        self,
        ui_labels: Optional[Iterable[str]] = None,
        roster: Optional[Iterable[str]] = None,
        use_builtins: bool = True,
    ) -> None:
        self.ui_labels: Set[str] = set()
        self.roster: Set[str] = set()
        if use_builtins:
            for label in BUILTIN_UI_LABELS:
                self.add_ui_label(label)
            for name in BUILTIN_ROSTER:
                self.add_roster(name)
        for label in ui_labels or ():
            self.add_ui_label(label)
        for name in roster or ():
            self.add_roster(name)

    # -- construction ------------------------------------------------------
    def add_ui_label(self, label: str) -> None:
        """Add a UI label to the blacklist."""
        key = normalize_label(label)
        if key:
            self.ui_labels.add(key)

    def add_roster(self, name: str) -> None:
        """Add a character name to the roster."""
        key = normalize_label(name)
        if key:
            self.roster.add(key)

    def remove_ui_label(self, label: str) -> None:
        """Remove a UI label from the blacklist."""
        key = normalize_label(label)
        self.ui_labels.discard(key)

    def remove_roster(self, name: str) -> None:
        """Remove a character name from the roster."""
        key = normalize_label(name)
        self.roster.discard(key)

    @classmethod
    def from_files(
        cls,
        ui_labels_path: str | Path | None = None,
        roster_path: str | Path | None = None,
    ) -> "SpeakerVocabulary":
        """Load the blacklist and the roster from the YAML files.

        A missing file is not an error: the built-in vocabulary is used.
        """
        vocabulary = cls()
        vocabulary.load_ui_labels(ui_labels_path)
        vocabulary.load_roster(roster_path)
        return vocabulary

    def load_ui_labels(self, path: str | Path | None) -> None:
        """Add every label of the YAML file to the blacklist."""
        if not path:
            return
        file_path = Path(path)
        if not file_path.exists():
            return
        with file_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for label in data.get("labels", []) or []:
            self.add_ui_label(str(label))
        for label in data.get("disable", []) or []:
            self.remove_ui_label(str(label))

    def load_roster(self, path: str | Path | None) -> None:
        """Add every name of the YAML file to the roster."""
        if not path:
            return
        file_path = Path(path)
        if not file_path.exists():
            return
        with file_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        names: List[str] = []
        for key, value in data.items():
            if key == "disable":
                continue
            if isinstance(value, list):
                names.extend(str(name) for name in value)
        for name in names:
            self.add_roster(name)
        for name in data.get("disable", []) or []:
            self.remove_roster(str(name))

    # -- queries -----------------------------------------------------------
    def is_ui_label(self, text: str) -> bool:
        """Return True when ``text`` is a known UI label."""
        key = normalize_label(text)
        if not key:
            return False
        return key in self.ui_labels

    def in_roster(self, text: str) -> bool:
        """Return True when ``text`` is a known character name."""
        key = normalize_label(text)
        if not key:
            return False
        return key in self.roster

    def describe(self) -> str:
        """A short summary used in the logs."""
        return f"ui_labels={len(self.ui_labels)} roster={len(self.roster)}"


# The default vocabulary, so the module stays usable without the YAML files.
DEFAULT_VOCABULARY = SpeakerVocabulary()


def looks_like_name(
    text: str,
    vocabulary: Optional[SpeakerVocabulary] = None,
    max_words: int = 3,
) -> bool:
    """Return True when ``text`` may be the name of a speaker.

    The rules are:

    1. the text must not be a blacklisted UI label;
    2. the text must be 1-3 capitalised words;
    3. the name must be in the roster, **or** the text must end with a colon
       (that is how the game writes the name of an unknown NPC).
    """
    vocabulary = vocabulary or DEFAULT_VOCABULARY
    raw = (text or "").strip()
    if not raw or len(raw) > 40:
        return False
    if vocabulary.is_ui_label(raw):
        return False

    has_colon = raw.endswith(_COLON)
    name = raw[:-1].strip() if has_colon else raw
    if not name:
        return False
    words = name.split()
    if not 1 <= len(words) <= max_words:
        return False
    if not all(CAP_WORD_RE.match(word) for word in words):
        return False

    if vocabulary.in_roster(name):
        return True
    # Unknown names are only accepted with the explicit "Name:" form.
    return has_colon
