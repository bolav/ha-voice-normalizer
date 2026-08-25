"""Canonical-name layer.

Maps a decoded or misheard name to its canonical form::

    "zeekr"  ->  "Zeekr"
    "hass"   ->  "Home Assistant"

Kept strictly separate from :mod:`ha_voice_normalizer.spelling`: the spelling
engine knows letters, this layer knows names. The default table is empty —
brand knowledge belongs to the user's configuration, not to the library.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from .models import OP_ALIAS, NormalizationOperation, NormalizationResult
from .phrases import apply_phrases, build_phrase_pattern, normalize_phrase_table


@dataclass(slots=True)
class AliasNormalizer:
    """Replace known aliases with their canonical spelling.

    Args:
        aliases: Mapping of spoken/decoded form to canonical form. Keys are
            matched case-insensitively on whole words.
    """

    name: ClassVar[str] = "aliases"

    aliases: Mapping[str, str] = field(default_factory=dict)
    _table: dict[str, str] = field(init=False, repr=False, default_factory=dict)
    _pattern: re.Pattern[str] | None = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        """Compile the alias table once."""
        self._table = normalize_phrase_table(self.aliases)
        self._pattern = build_phrase_pattern(self._table)

    def normalize(self, result: NormalizationResult) -> NormalizationResult:
        """Return ``result`` with aliases replaced."""
        text, operations = self.normalize_text(result.text)
        if not operations:
            return result
        return result.applied(text, operations)

    def normalize_text(self, text: str) -> tuple[str, list[NormalizationOperation]]:
        """Return the rewritten text and the operations that produced it."""
        return apply_phrases(text, self._table, self._pattern, OP_ALIAS)
