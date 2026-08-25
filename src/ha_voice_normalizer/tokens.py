"""Tokenization helpers.

Tokens keep offsets into the string they came from, so normalizers can rewrite
individual spans while copying everything else through verbatim. The user's
sentence is never globally lowercased.
"""

import re
from dataclasses import dataclass

# A word is a run of letters (any alphabet, so Norwegian æ/ø/å work), optionally
# joined by hyphens or apostrophes: "Zulu", "X-ray", "kjøkken-lyset".
# Digits are deliberately excluded; number/symbol spelling is a separate concern.
# The curly apostrophe is intentional: speech-to-text engines emit both.
_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")  # noqa: RUF001

_SENTENCE_BREAK_RE = re.compile(r"[.!?;:\n]")


@dataclass(frozen=True, slots=True)
class Token:
    """A word and its position in the source text."""

    text: str
    start: int
    end: int

    @property
    def key(self) -> str:
        """Return the case-insensitive lookup key for this token."""
        return self.text.casefold()


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into word tokens, ignoring punctuation and whitespace."""
    return [Token(match.group(), match.start(), match.end()) for match in _WORD_RE.finditer(text)]


def gap_text(text: str, left: Token, right: Token) -> str:
    """Return the raw text between two tokens."""
    return text[left.end : right.start]


def has_sentence_break(text: str) -> bool:
    """Return whether ``text`` contains punctuation that ends a phrase.

    A comma is *not* a break: commas routinely separate dictated letters
    ("stav: Zulu, Ekko, Kilo").
    """
    return _SENTENCE_BREAK_RE.search(text) is not None
