"""Glossary: keep WuWa terms untranslated.

Every glossary term is replaced by a placeholder before the text is sent to the
translation model and restored afterwards, so the model never mangles the
proper nouns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

PLACEHOLDER_TEMPLATE = "XGLOSS{index}X"


class Glossary:
    """Holds the untranslated terms and performs protect/restore."""

    def __init__(self, terms: Dict[str, str] | None = None) -> None:
        # surface form -> display form
        self.terms: Dict[str, str] = dict(terms or {})
        self._sorted_terms = sorted(self.terms.keys(), key=len, reverse=True)

    # -- construction ------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path) -> "Glossary":
        """Load a glossary from a YAML file.

        The file format is ``terms: {Term: Display}`` plus an optional
        ``aliases: {surface: Term}`` section.
        """
        path = Path(path)
        data: dict = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        terms = data.get("terms", {}) or {}
        aliases = data.get("aliases", {}) or {}
        merged: Dict[str, str] = {str(k): str(v) for k, v in terms.items()}
        for surface, canonical in aliases.items():
            display = merged.get(str(canonical), str(canonical))
            merged[str(surface)] = display
        return cls(merged)

    # -- API ---------------------------------------------------------------
    def protect(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Replace every glossary term with a placeholder.

        Returns ``(protected_text, restore_map)`` where ``restore_map`` maps
        the placeholder back to the original display form.
        """
        if not text or not self._sorted_terms:
            return text, {}
        restore: Dict[str, str] = {}
        result = text
        for index, term in enumerate(self._sorted_terms):
            pattern = re.compile(
                r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", re.IGNORECASE
            )
            placeholder = PLACEHOLDER_TEMPLATE.format(index=index)
            if pattern.search(result):
                result = pattern.sub(placeholder, result)
                restore[placeholder] = self.terms[term]
        return result, restore

    def restore(self, text: str, restore_map: Dict[str, str]) -> str:
        """Restore the placeholders created by :meth:`protect`.

        The translation model sometimes drops a character of the placeholder
        ("XGLOSS3X" becomes "XGLOS3X"), so the match is forgiving. Only the
        placeholder token itself is replaced - the surrounding spaces are kept
        so the sentence spacing stays intact.
        """
        if not text or not restore_map:
            return text
        result = text
        # Longer numbers first so that "10" is not matched by the "1".
        for placeholder in sorted(restore_map, key=len, reverse=True):
            original = restore_map[placeholder]
            match = re.search(r"(\d+)", placeholder)
            number = re.escape(match.group(1)) if match else "0"
            loose = re.compile(
                r"X?GLO[A-Z]{0,6}\s?" + number + r"(?!\d)[A-Z]{0,3}",
                re.IGNORECASE,
            )
            result = loose.sub(original, result)
            result = result.replace(placeholder, original)
        return result

    def contains(self, text: str) -> bool:
        """Return True when the text contains at least one glossary term."""
        return bool(self.protect(text)[1])
