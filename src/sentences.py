"""Sentence splitting and number protection for the translation stage.

Two problems are solved here:

**Sentence splitting.** The Argos model re-tokenizes a whole paragraph and
can lose a digit or mangle a number. A block is therefore split into
sentences and every sentence is translated on its own, then the sentences
are rejoined with their original separators.

**Number protection.** The digit loss also happens inside a single sentence
(``Reward: 12000`` alone becomes ``Phần thưởng:2000``), so every number,
percentage and decimal is replaced by a placeholder token before the text
reaches the model and restored exactly afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# The placeholder token used for a number. The model keeps "XNUM0X" intact
# (measured with the Argos en->vi model), so the digits always survive.
NUMBER_TOKEN = "XNUM{index}X"
PERCENT_TOKEN = "XPCT{index}X"

# A number, a decimal, a percentage or a number with a thousands separator.
#   12000   15   3.5   12,000   15%   1,234.56
_NUMBER_RE = re.compile(
    r"(?<![\w.])"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"%?"
    r"(?![\w])"
)

# The abbreviations that must not be split (without the trailing dot: the
# dot itself is the sign that the word is an abbreviation).
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "st",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "no",
    "lv",
    "hp",
    "mp",
    "sp",
    "exp",
    "co",
    "lt",
    "jr",
    "sr",
    "approx",
    "dept",
    "est",
    "fig",
}

# The end of a sentence: a dot, an exclamation or a question mark, followed by
# a space and an upper-case letter (or the end of the text).
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")


@dataclass
class Sentence:
    """One sentence of a block, with the separator that follows it."""

    text: str
    separator: str = " "

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return f"{self.text}{self.separator!r}"


@dataclass
class ProtectedText:
    """A text whose numbers were replaced by placeholders."""

    text: str
    restore_map: Dict[str, str] = field(default_factory=dict)
    numbers: List[str] = field(default_factory=list)

    def restore(self, translated: str) -> str:
        """Put the original numbers back into ``translated``."""
        if not translated:
            return translated
        result = translated
        # The longest token first, so "XNUM10X" is not eaten by "XNUM1X".
        for token in sorted(self.restore_map, key=len, reverse=True):
            result = result.replace(token, self.restore_map[token])
        return result


def protect_numbers(text: str) -> ProtectedText:
    """Replace every number of ``text`` with a placeholder token.

    The token format (``XNUM0X``) was chosen because the Argos model leaves
    it untouched, so the digits always come back exactly as they were.
    """
    if not text:
        return ProtectedText(text=text or "")

    restore_map: Dict[str, str] = {}
    numbers: List[str] = []
    counter = 0

    def _replace(match: "re.Match[str]") -> str:
        nonlocal counter
        raw = match.group(0)
        token = NUMBER_TOKEN.format(index=counter)
        counter += 1
        restore_map[token] = raw
        numbers.append(raw)
        return token

    return ProtectedText(
        text=_NUMBER_RE.sub(_replace, text),
        restore_map=restore_map,
        numbers=numbers,
    )


def digits_of(text: str) -> List[str]:
    """Return the digits of ``text`` in order, as separate strings."""
    return re.findall(r"\d+", text or "")


def _is_abbreviation_boundary(text: str, position: int) -> bool:
    """Return True when the dot at ``position`` ends an abbreviation."""
    prefix = text[:position].lower()
    last_space = max(prefix.rfind(" "), prefix.rfind("\n"), prefix.rfind("\t"))
    word = prefix[last_space + 1 :] if last_space >= 0 else prefix
    return word.strip() in _ABBREVIATIONS


def split_sentences(text: str) -> List[Sentence]:
    """Split ``text`` into sentences.

    The split never happens inside a number, a decimal or a known
    abbreviation, so ``Reward: 12000`` stays one single unit and
    ``Complete the quest. Reward: 12000`` becomes two sentences.
    """
    if not text or not text.strip():
        return []

    sentences: List[Sentence] = []
    start = 0
    length = len(text)

    for match in _SENTENCE_END_RE.finditer(text):
        end = match.start()
        # The dot that ends the sentence.
        dot = text.rfind(".", start, end + 1)
        if dot < 0:
            dot = text.rfind("!", start, end + 1)
        if dot < 0:
            dot = text.rfind("?", start, end + 1)
        if dot < 0:
            continue
        if _is_abbreviation_boundary(text, dot):
            continue
        # Never split inside a number ("3.5" or "1,234.56").
        if text[dot - 1 : dot + 1] == ".5" or re.match(r"\d\.\d", text[max(0, dot - 3) : dot + 2]):
            continue

        chunk = text[start:end]
        if chunk.strip():
            sentences.append(Sentence(text=chunk, separator=match.group(0)))
        start = match.end()

    tail = text[start:]
    if tail.strip():
        sentences.append(Sentence(text=tail, separator=""))

    return sentences


def join_sentences(sentences: Sequence[Sentence]) -> str:
    """Rejoin the sentences with their original separators."""
    return "".join(f"{s.text}{s.separator}" for s in sentences)


def restore_numbers(
    translated: str, original: str, protected: ProtectedText
) -> Tuple[str, bool]:
    """Restore the numbers of a translated sentence.

    The placeholders are put back first. Then the digits of the translation
    are compared with the digits of the original: when they differ, the
    digits of the translation are replaced by the original ones (in order)
    and the second return value is True.
    """
    result = protected.restore(translated)

    original_digits = digits_of(original)
    translated_digits = digits_of(result)
    if original_digits == translated_digits:
        return result, False

    # Safety net: the model mangled a digit, put the original ones back.
    if not original_digits:
        return result, False

    iterator = iter(original_digits)

    def _swap(match: "re.Match[str]") -> str:
        try:
            return next(iterator)
        except StopIteration:  # pragma: no cover - defensive
            return match.group(0)

    fixed = re.sub(r"\d+", _swap, result)
    return fixed, True
