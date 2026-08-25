"""Known speech-to-text corrections.

For phrases a given STT model reliably gets wrong::

    "hjemme assistent"  ->  "Home Assistant"

Mechanically the same as :mod:`ha_voice_normalizer.aliases`, but a separate
processor so it can be enabled, tested and debugged on its own — an alias table
describes names, a correction table describes a transcriber's mistakes.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from .models import OP_STT_CORRECTION, NormalizationOperation, NormalizationResult
from .phrases import apply_phrases, build_phrase_pattern, normalize_phrase_table


@dataclass(slots=True)
class SttCorrectionNormalizer:
    """Replace known mis-transcriptions with the intended phrase.

    Args:
        corrections: Mapping of misheard phrase to intended phrase. Keys are
            matched case-insensitively on whole words.
    """

    name: ClassVar[str] = "corrections"

    corrections: Mapping[str, str] = field(default_factory=dict)
    _table: dict[str, str] = field(init=False, repr=False, default_factory=dict)
    _pattern: re.Pattern[str] | None = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        """Compile the correction table once."""
        self._table = normalize_phrase_table(self.corrections)
        self._pattern = build_phrase_pattern(self._table)

    def normalize(self, result: NormalizationResult) -> NormalizationResult:
        """Return ``result`` with known transcription errors corrected."""
        text, operations = self.normalize_text(result.text)
        if not operations:
            return result
        return result.applied(text, operations)

    def normalize_text(self, text: str) -> tuple[str, list[NormalizationOperation]]:
        """Return the rewritten text and the operations that produced it."""
        return apply_phrases(text, self._table, self._pattern, OP_STT_CORRECTION)
