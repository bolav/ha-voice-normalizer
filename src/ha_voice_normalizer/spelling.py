"""Phonetic (NATO) spelling normalizer.

Turns dictated NATO alphabet words into the word they spell, but only inside an
explicitly triggered span::

    "stav Zulu Ekko Ekko Kilo Romeo"  ->  "zeekr"

Nothing happens without a trigger word, because plenty of NATO code words are
ordinary words ("Hotel India", "Golf", "November", "Oscar").

The engine knows letters, not brands: mapping ``zeekr`` to ``Zeekr`` is the job
of :mod:`ha_voice_normalizer.aliases`.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from .models import OP_PHONETIC_SPELLING, NormalizationOperation, NormalizationResult
from .tokens import Token, gap_text, has_sentence_break, tokenize

LETTER_VARIANTS: Mapping[str, tuple[str, ...]] = {
    "a": ("alfa", "alpha"),
    "b": ("bravo",),
    "c": ("charlie",),
    "d": ("delta",),
    "e": ("echo", "ekko", "eko"),
    "f": ("foxtrot",),
    "g": ("golf",),
    "h": ("hotel", "hotell"),
    "i": ("india",),
    "j": ("juliett", "juliet"),
    "k": ("kilo",),
    "l": ("lima",),
    "m": ("mike",),
    "n": ("november",),
    "o": ("oscar", "oskar"),
    "p": ("papa",),
    "q": ("quebec",),
    "r": ("romeo",),
    "s": ("sierra", "sera", "serah"),
    "t": ("tango",),
    "u": ("uniform",),
    "v": ("victor", "viktor"),
    "w": ("whiskey", "whisky"),
    "x": ("x-ray", "xray", "x ray"),
    "y": ("yankee",),
    "z": ("zulu",),
    "æ": ("ægir", "ærlig"),
    "ø": ("ørnulf", "østen"),
    "å": ("ågot", "åse"),
}
"""Letter -> accepted spoken variants.

The first entry is the official NATO code word. The extra entries are spellings
a Norwegian STT engine actually produces ("Ekko", "Hotell", "Oskar", "Viktor")
or common English variants. Every variant here is covered by a test; add new
ones the same way instead of guessing at what Whisper might emit.

NATO stops at Z, so æ/ø/å use the Norwegian Armed Forces extension (Ægir,
Ørnulf, Ågot) as the canonical word, with the civilian spelling alphabet
(Ærlig, Østen, Åse) accepted as an alternate — a speaker reaches for whichever
one they know. They live after "z" because that is where they sit in the
Norwegian alphabet.

Lookup keys are casefolded *and* NFC-normalized, so a decomposed "A + combining
ring" from a transcriber matches the composed "å" written here.
"""


@dataclass(frozen=True, slots=True)
class SpellingTrigger:
    """A word that switches spelling mode on.

    Attributes:
        word: The lowercase trigger word.
        consume: Whether the trigger is removed from the output.

    ``consume=True`` is for imperatives ("stav X Y Z" = "spell X Y Z"): the word
    addresses the assistant and is not part of the sentence, so it is dropped
    together with a comma directly in front of it. ``consume=False`` is for
    inflected forms ("bilen som staves X Y Z"), where the word carries meaning
    and only the letters are rewritten.
    """

    word: str
    consume: bool


TRIGGERS_BY_LANGUAGE: Mapping[str, tuple[SpellingTrigger, ...]] = {
    "nb": (
        SpellingTrigger("stav", consume=True),
        SpellingTrigger("bokstaver", consume=True),
        SpellingTrigger("staves", consume=False),
        SpellingTrigger("stavet", consume=False),
    ),
    "en": (
        SpellingTrigger("spell", consume=True),
        SpellingTrigger("spelled", consume=False),
        SpellingTrigger("spelt", consume=False),
    ),
}

_LANGUAGE_BASES: Mapping[str, str] = {"nb": "nb", "nn": "nb", "no": "nb", "en": "en"}


class SpellingMode(StrEnum):
    """How much of a spelled span has to be understood before rewriting it."""

    STRICT = "strict"
    """Rewrite only when the span runs to the end of the sentence.

    "stav Zulu Ekko banan Romeo" is left completely alone.
    """

    PARTIAL = "partial"
    """Rewrite the recognized letters and leave the rest of the sentence alone.

    "stav Zulu Ekko banan Romeo" becomes "ze banan Romeo".
    """


def resolve_languages(language: str | None) -> tuple[str, ...]:
    """Return which trigger sets apply to ``language``.

    ``None`` and ``"auto"`` enable every language. An unknown language also
    enables every language: triggers are specific enough that this is safer
    than silently disabling normalization.
    """
    if not language or language.casefold() == "auto":
        return tuple(TRIGGERS_BY_LANGUAGE)
    base = language.replace("_", "-").split("-")[0].casefold()
    key = _LANGUAGE_BASES.get(base)
    if key is None:
        return tuple(TRIGGERS_BY_LANGUAGE)
    return (key,)


def _build_letter_lookup(
    variants: Mapping[str, Iterable[str]],
) -> tuple[dict[str, str], int]:
    """Return a variant -> letter lookup and the longest variant's word count.

    Keys are built exactly the way :attr:`Token.key` builds them, NFC included,
    so both sides of the lookup agree on how "å" is spelled.
    """
    lookup: dict[str, str] = {}
    max_words = 1
    for letter, spoken in variants.items():
        for variant in spoken:
            key = " ".join(unicodedata.normalize("NFC", variant.casefold()).split())
            lookup[key] = letter
            max_words = max(max_words, len(key.split(" ")))
    return lookup, max_words


_LETTER_LOOKUP, _MAX_VARIANT_WORDS = _build_letter_lookup(LETTER_VARIANTS)

_TRIM_BEFORE_TRIGGER = " \t\n\r,;:"

STRICT_TRIGGER_LOOKAHEAD = 3
"""How far strict mode looks for a following trigger before rejecting a span.

Covers the words that glue two dictated segments together ("... Charlie **og
kode** stav X-ray ...") without accepting a whole sentence of loose text.
"""


@dataclass(frozen=True, slots=True)
class _Span:
    """A stretch of text to replace, plus what to replace it with."""

    start: int
    end: int
    replacement: str
    operation: NormalizationOperation


@dataclass(slots=True)
class SpellingNormalizer:
    """Decode explicitly triggered NATO spelling spans.

    Args:
        language: Language tag such as ``"nb"``, ``"nb-NO"`` or ``None``/``"auto"``.
        mode: Strict (default) or partial handling of unrecognized words.
        min_letters: Shortest span that may be rewritten.
    """

    name: ClassVar[str] = "spelling"

    language: str | None = None
    mode: SpellingMode = SpellingMode.STRICT
    min_letters: int = 1
    _triggers: dict[str, bool] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        """Flatten the trigger tables for the configured language."""
        self._triggers = {
            trigger.word: trigger.consume
            for language in resolve_languages(self.language)
            for trigger in TRIGGERS_BY_LANGUAGE[language]
        }

    def normalize(self, result: NormalizationResult) -> NormalizationResult:
        """Return ``result`` with all spelled spans decoded."""
        text, operations = self.normalize_text(result.text)
        if not operations:
            return result
        return result.applied(text, operations)

    def normalize_text(self, text: str) -> tuple[str, list[NormalizationOperation]]:
        """Return the rewritten text and the operations that produced it."""
        spans = self._find_spans(text)
        if not spans:
            return text, []

        pieces: list[str] = []
        cursor = 0
        for span in spans:
            pieces.append(text[cursor : span.start])
            pieces.append(span.replacement)
            cursor = span.end
        pieces.append(text[cursor:])
        return "".join(pieces), [span.operation for span in spans]

    def _find_spans(self, text: str) -> list[_Span]:
        """Scan for trigger words and collect every rewritable span."""
        tokens = tokenize(text)
        spans: list[_Span] = []
        index = 0
        while index < len(tokens):
            consume = self._triggers.get(tokens[index].key)
            if consume is None:
                index += 1
                continue

            letters, next_index = self._read_letters(text, tokens, index + 1)
            if len(letters) < self.min_letters or not letters:
                index += 1
                continue

            if self.mode is SpellingMode.STRICT and not self._is_terminated(
                text, tokens, next_index
            ):
                # Something we do not understand follows the letters, so this is
                # probably not a spelling at all. Leave the whole span alone.
                index = next_index
                continue

            spans.append(self._build_span(text, tokens, index, next_index, letters, consume))
            index = next_index
        return spans

    def _read_letters(
        self, text: str, tokens: list[Token], start: int
    ) -> tuple[list[str], int]:
        """Read the run of code words starting at ``start``.

        Returns the decoded letters and the index of the first token that is not
        part of the run.
        """
        letters: list[str] = []
        index = start
        while index < len(tokens):
            match = self._match_variant(text, tokens, index)
            if match is None:
                break
            letter, length = match
            letters.append(letter)
            index += length
        return letters, index

    def _match_variant(
        self, text: str, tokens: list[Token], index: int
    ) -> tuple[str, int] | None:
        """Return the letter and token count of the code word at ``index``.

        Longer code words win, so "x ray" is preferred over a bare "x".
        """
        for length in range(min(_MAX_VARIANT_WORDS, len(tokens) - index), 0, -1):
            key = self._variant_key(text, tokens, index, length)
            if key is not None and (letter := _LETTER_LOOKUP.get(key)) is not None:
                return letter, length
        return None

    def _variant_key(
        self, text: str, tokens: list[Token], index: int, length: int
    ) -> str | None:
        """Return the lookup key for ``length`` tokens starting at ``index``.

        Multi-word code words ("x ray") only match when nothing but whitespace
        separates the tokens.
        """
        keys = [tokens[index].key]
        for offset in range(1, length):
            if gap_text(text, tokens[index + offset - 1], tokens[index + offset]).strip():
                return None
            keys.append(tokens[index + offset].key)
        return " ".join(keys)

    def _is_terminated(self, text: str, tokens: list[Token], next_index: int) -> bool:
        """Return whether the letter run ends cleanly (the strict-mode gate).

        A run ends cleanly at the end of the text, at sentence punctuation, or
        just before another spelling trigger — the last case is what makes
        "brukernavn stav Alfa Bravo Charlie og kode stav X-ray Yankee Zulu"
        work. Anything else ("stav Zulu Ekko banan Romeo") is treated as a
        sentence that merely happens to contain code words, and is left alone.
        """
        if next_index >= len(tokens):
            return True
        if has_sentence_break(gap_text(text, tokens[next_index - 1], tokens[next_index])):
            return True
        lookahead = tokens[next_index : next_index + STRICT_TRIGGER_LOOKAHEAD]
        return any(token.key in self._triggers for token in lookahead)

    def _build_span(
        self,
        text: str,
        tokens: list[Token],
        trigger_index: int,
        next_index: int,
        letters: list[str],
        consume_trigger: bool,
    ) -> _Span:
        """Turn a decoded run of letters into a replacement span."""
        letters_start = tokens[trigger_index + 1].start
        letters_end = tokens[next_index - 1].end
        word = "".join(letters)

        if consume_trigger:
            start = tokens[trigger_index].start
            while start > 0 and text[start - 1] in _TRIM_BEFORE_TRIGGER:
                start -= 1
            replacement = f" {word}" if start > 0 else word
        else:
            start = letters_start
            replacement = word

        return _Span(
            start=start,
            end=letters_end,
            replacement=replacement,
            operation=NormalizationOperation(
                type=OP_PHONETIC_SPELLING,
                source=text[letters_start:letters_end],
                result=word,
                start=letters_start,
                end=letters_end,
            ),
        )


def normalize_spelling(text: str, language: str | None = None) -> str:
    """Decode spelled spans in ``text`` and return the resulting text."""
    normalized, _ = SpellingNormalizer(language=language).normalize_text(text)
    return normalized
