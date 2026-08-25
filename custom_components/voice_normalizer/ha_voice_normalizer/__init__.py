"""Deterministic normalization of speech-to-text output.

The first and main feature is phonetic spelling: turning dictated NATO alphabet
words into the word they spell, so that a downstream assistant sees ``zeekr``
instead of ``Zulu Ekko Ekko Kilo Romeo``.

Everything in this package is pure Python — no Home Assistant, no network, no
LLM::

    from ha_voice_normalizer import normalize_text

    result = normalize_text("stav Zulu Ekko Ekko Kilo Romeo", language="nb")
    assert result.text == "zeekr"
"""

from .aliases import AliasNormalizer
from .corrections import SttCorrectionNormalizer
from .models import (
    OP_ALIAS,
    OP_PHONETIC_SPELLING,
    OP_STT_CORRECTION,
    NormalizationOperation,
    NormalizationResult,
)
from .phrases import parse_phrase_lines
from .pipeline import NormalizationPipeline, Normalizer, normalize_text
from .spelling import (
    LETTER_VARIANTS,
    TRIGGERS_BY_LANGUAGE,
    SpellingMode,
    SpellingNormalizer,
    SpellingTrigger,
    normalize_spelling,
)

__version__ = "0.1.0"

__all__ = [
    "LETTER_VARIANTS",
    "OP_ALIAS",
    "OP_PHONETIC_SPELLING",
    "OP_STT_CORRECTION",
    "TRIGGERS_BY_LANGUAGE",
    "AliasNormalizer",
    "NormalizationOperation",
    "NormalizationPipeline",
    "NormalizationResult",
    "Normalizer",
    "SpellingMode",
    "SpellingNormalizer",
    "SpellingTrigger",
    "SttCorrectionNormalizer",
    "__version__",
    "normalize_spelling",
    "normalize_text",
    "parse_phrase_lines",
]
