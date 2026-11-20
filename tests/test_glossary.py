"""Tests for the glossary (terms must stay untranslated)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.glossary import Glossary


def test_terms_are_replaced_by_a_placeholder() -> None:
    """Every glossary term is protected before the translation."""
    glossary = Glossary({"Rover": "Rover", "Tacet Field": "Tacet Field"})
    protected, restore = glossary.protect("The Rover entered the Tacet Field.")
    assert "Rover" not in protected
    assert "Tacet Field" not in protected
    assert len(restore) == 2


def test_the_terms_are_restored_after_the_translation() -> None:
    """The placeholders are replaced by the original English terms again."""
    glossary = Glossary({"Rover": "Rover", "Tacet Field": "Tacet Field"})
    protected, restore = glossary.protect("The Rover entered the Tacet Field.")
    restored = glossary.restore(protected, restore)
    assert "Rover" in restored
    assert "Tacet Field" in restored


def test_a_term_inside_a_word_is_not_replaced() -> None:
    """A word that only contains the term as a substring is untouched."""
    glossary = Glossary({"Rover": "Rover"})
    protected, restore = glossary.protect("Roverous Rovers rover")
    assert "Roverous" in protected
    assert restore


def test_the_glossary_file_is_loaded() -> None:
    """The shipped config/glossary.yaml is readable and contains the terms."""
    path = PROJECT_ROOT / "config" / "glossary.yaml"
    glossary = Glossary.from_file(path)
    assert "Rover" in glossary.terms
    assert "Resonator" in glossary.terms
    assert "Tacet Field" in glossary.terms
    assert "Waveplate" in glossary.terms


def test_a_text_without_a_term_is_unchanged() -> None:
    """A text without glossary terms is returned untouched."""
    glossary = Glossary({"Rover": "Rover"})
    protected, restore = glossary.protect("Hello there, how are you?")
    assert protected == "Hello there, how are you?"
    assert restore == {}


def test_the_aliases_are_also_protected() -> None:
    """An alias (different surface form) is protected as well."""
    glossary = Glossary.from_file(PROJECT_ROOT / "config" / "glossary.yaml")
    protected, restore = glossary.protect("The resonators are coming.")
    assert restore
    restored = glossary.restore(protected, restore)
    assert "Resonator" in restored
