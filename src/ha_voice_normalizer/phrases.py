"""Whole-word phrase replacement, shared by the alias and correction layers.

Both layers do the same thing mechanically — replace a known phrase with a
canonical one — and differ only in intent, so the matching lives here once.
"""

import re
from collections.abc import Mapping

from .models import NormalizationOperation


def build_phrase_pattern(phrases: Mapping[str, str]) -> re.Pattern[str] | None:
    """Return a case-insensitive pattern matching any phrase as whole words.

    Longer phrases are tried first so "home assistant" wins over "home".
    Returns ``None`` when there is nothing to match.
    """
    if not phrases:
        return None
    ordered = sorted(phrases, key=len, reverse=True)
    alternatives = "|".join(re.escape(phrase) for phrase in ordered)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def apply_phrases(
    text: str,
    phrases: Mapping[str, str],
    pattern: re.Pattern[str] | None,
    operation_type: str,
) -> tuple[str, list[NormalizationOperation]]:
    """Replace every phrase occurrence in ``text``.

    ``phrases`` must be keyed by casefolded phrase. Text outside the matches is
    copied through unchanged.
    """
    if pattern is None:
        return text, []

    operations: list[NormalizationOperation] = []
    pieces: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        source = match.group()
        replacement = phrases[" ".join(source.casefold().split())]
        if replacement == source:
            continue
        pieces.append(text[cursor : match.start()])
        pieces.append(replacement)
        cursor = match.end()
        operations.append(
            NormalizationOperation(
                type=operation_type,
                source=source,
                result=replacement,
                start=match.start(),
                end=match.end(),
            )
        )

    if not operations:
        return text, []

    pieces.append(text[cursor:])
    return "".join(pieces), operations


def normalize_phrase_table(phrases: Mapping[str, str]) -> dict[str, str]:
    """Return ``phrases`` with casefolded, whitespace-collapsed keys."""
    return {
        " ".join(key.casefold().split()): value
        for key, value in phrases.items()
        if key.strip()
    }


def parse_phrase_lines(text: str) -> dict[str, str]:
    """Parse a ``phrase: replacement`` line list, as used by the UI options.

    Blank lines and ``#`` comments are ignored. Lines without a separator are
    ignored too, so a half-typed line cannot break normalization.
    """
    phrases: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        separator = min(
            (line.find(char) for char in (":", "=") if char in line),
            default=-1,
        )
        if separator <= 0:
            continue
        key = line[:separator].strip()
        value = line[separator + 1 :].strip()
        if key and value:
            phrases[key] = value
    return normalize_phrase_table(phrases)
