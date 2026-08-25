"""Tokenization helpers.

Tokens keep offsets into the string they came from, so normalizers can rewrite
individual spans while copying everything else through verbatim. The user's
sentence is never globally lowercased.
"""

import re
import unicodedata
from dataclasses import dataclass

# A letter is a base character plus any combining marks that decorate it. The
# marks matter: "å" may arrive composed (U+00E5) or decomposed (a + U+030A), and
# a combining mark is not a word character, so without this a decomposed "Ågot"
# would tokenize as "A" + "got" and never match a code word.
_LETTER = r"(?:[^\W\d_][\u0300-\u036f]*)"

# A word is a run of letters (any alphabet, so Norwegian æ/ø/å work), optionally
# joined by hyphens or apostrophes: "Zulu", "X-ray", "kjøkken-lyset".
# Digits are deliberately excluded; number/symbol spelling is a separate concern.
# The curly apostrophe is intentional: speech-to-text engines emit both.
_WORD_RE = re.compile(rf"{_LETTER}+(?:[-'’]{_LETTER}+)*")  # noqa: RUF001

_SENTENCE_BREAK_RE = re.compile(r"[.!?;:\n]")


@dataclass(frozen=True, slots=True)
class Token:
    """A word and its position in the source text."""

    text: str
    start: int
    end: int

    @property
    def key(self) -> str:
        """Return the case-insensitive lookup key for this token.

        NFC folds a decomposed "a + combining ring" into "å", so a code word
        matches however the transcriber chose to encode it. Only the key is
        normalized — ``text`` and the offsets still address the original string.
        """
        return unicodedata.normalize("NFC", self.text.casefold())


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
