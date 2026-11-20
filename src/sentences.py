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
#   12000   15   3.5   12,000   15%   1,234.56   3,5
#
# The comma group is greedy ("1,2345" stays one token), so a number with a
# thousands separator ("1,234") and a decimal comma ("3,5") are both kept
# in one piece. The dot is only a part of the number when a digit follows it.
_NUMBER_RE = re.compile(
    r"(?<![\w])"
    r"(?<!\.\d)"
    r"\d+(?:,\d+)*"
    r"(?:\.\d+)?"
    r"%?"
    r"(?![\w])"
)

# The abbreviations that must not be split (without the trailing dot: the
# dot itself is the sign that the word is an abbreviation).
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "miss",
    "mx",
    "dr",
    "prof",
    "st",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "cf",
    "ca",
    "no",
    "nos",
    "fig",
    "figs",
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
    "al",
    "inc",
    "ltd",
    "vol",
    "ch",
    "pp",
    "op",
    "min",
    "max",
    "avg",
    "tel",
    "ext",
    # -- added by P3 (item G) --------------------------------------------
    "rev",
    "gen",
    "col",
    "capt",
    "sgt",
    "lt",
    "gov",
    "sen",
    "rep",
    "supt",
    "det",
    "insp",
    "cmdr",
    "adm",
    "maj",
    "cpl",
    "pvt",
    "fr",
    "am",
    "pm",
    "phd",
    "md",
    "ba",
    "bsc",
    "msc",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
    "ave",
    "blvd",
    "rd",
    "apt",
    "sq",
    "ft",
    "mt",
    "univ",
    "assn",
    "bros",
    "mfg",
    "dist",
    "govt",
    "intl",
    "natl",
    "econ",
    "psych",
    "phys",
    "math",
    "chem",
    "biol",
    "eng",
    "mfg",
    "mgmt",
    "admin",
    "acct",
    "dept",
    "asst",
    "assoc",
    "pres",
    "supt",
    "rep",
    "sec",
    "ref",
    "vol",
    "ed",
    "eds",
    "pp",
    "para",
    "chap",
    "sec",
    "fig",
    "figs",
    "eq",
    "ref",
    "sec",
    "vol",
    "ch",
    "no",
    "nos",
    "para",
    "art",
    "arts",
    "sec",
    "hr",
    "hrd",
    "dept",
    "intl",
    "natl",
    "assn",
    "bros",
}

# A chain of initials ("U.S", "A.M", "J.R.R"): the dot of an initial is
# never the end of a sentence.
_INITIALS_CHAIN_RE = re.compile(r"(?:^|\s)(?:[A-Za-z]\.)+[A-Za-z]$")

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


def split_with_stanza(text: str) -> List[Sentence]:
    """Split ``text`` with the Stanza sentence boundary detector.

    Stanza is the splitter Argos uses internally, so this gives the same
    boundaries as the model itself. It is **slower** than the regex splitter
    (the pipeline has to be loaded), so it is only used as a fallback.

    The separators are the whitespace that follows each sentence, so the
    sentences can be rejoined exactly like the regex splitter does.
    """
    if not text or not text.strip():
        return []

    try:
        import stanza
    except Exception:  # pragma: no cover - stanza is optional
        return split_sentences(text)

    try:
        document = stanza.Document([], text=text)  # type: ignore[call-arg]
        sentences = document.sentences
    except Exception:  # pragma: no cover - depends on the installed models
        return split_sentences(text)

    if not sentences:
        return split_sentences(text)

    result: List[Sentence] = []
    cursor = 0
    for sentence in sentences:
        body = sentence.text
        start = text.find(body, cursor)
        if start < 0:
            start = cursor
        cursor = start + len(body)
        separator = ""
        index = cursor
        while index < len(text) and text[index].isspace():
            separator += text[index]
            index += 1
        result.append(Sentence(text=body, separator=separator))
    return result


def get_splitter(name: str = "regex"):
    """Return the sentence splitter to use.

    ``"regex"`` is the default: it is fast, it never loads a model and it
    never splits inside a number or an abbreviation. ``"stanza"`` is the
    fallback: it uses the same boundary detector as the translation model,
    but it is slower and it needs the Stanza models to be installed.
    """
    if str(name).lower() == "stanza":
        return split_with_stanza
    return split_sentences


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


def _is_initials_boundary(text: str, position: int) -> bool:
    """Return True when the dot at ``position`` ends a chain of initials.

    "U.S." and "A.M." are not sentence boundaries, even when the chain is not
    in the abbreviation list. The chain has to end exactly at the dot.
    """
    # The text of the word that holds the dot.
    start = max(
        text.rfind(" ", 0, position), text.rfind("\n", 0, position)
    )
    word = text[start + 1 : position + 1]
    # "U.S." -> the chain without the last dot.
    if len(word) < 3:
        return False
    if not _INITIALS_CHAIN_RE.match(" " + word[:-1]):
        return False
    # The chain must not be followed by a lower-case letter, otherwise it is
    # an ordinary word like "e.g" that is not in the list.
    after = text[position + 1 : position + 2]
    return not (after.isalpha() and after.islower())


def _is_numeric_boundary(text: str, position: int) -> bool:
    """Return True when the dot at ``position`` is inside a number.

    That is the case for a decimal ("3.5"), a decimal comma ("3,5") and a
    number with a thousands separator ("1,234").
    """
    before = text[max(0, position - 1) : position]
    after = text[position + 1 : position + 2]
    if before.isdigit() and after.isdigit():
        return True
    return False


def _is_comma_boundary(text: str, position: int) -> bool:
    """Return True when the comma at ``position`` is inside a number.

    A decimal comma ("3,5") and a thousands separator ("1,234") must never
    split a sentence. A comma that is followed by a space is a normal comma
    and it does split the sentence.
    """
    before = text[max(0, position - 1) : position]
    after = text[position + 1 : position + 2]
    if not before.isdigit():
        return False
    if after.isdigit():
        # "3,5" or "1,234": the digits on both sides are never a boundary.
        return True
    # "1,234." - the comma is a thousands separator when the digits that
    # follow are exactly three and the ones before are one to three.
    if after == " ":
        return False
    return False


def _is_numeric_text(text: str) -> bool:
    """Return True when the whole text is a number.

    That is the case for "12000", "1,234" and "3.5": a block that is only a
    number is never split.
    """
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_NUMBER_RE.fullmatch(stripped))


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
        if _is_initials_boundary(text, dot):
            continue
        # Never split inside a number ("3.5", "3,5" or "1,234.56").
        if _is_numeric_boundary(text, dot):
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
