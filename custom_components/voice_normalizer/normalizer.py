"""Glue between config entry options and the standalone normalization core.

All spelling/alias logic lives in the ``ha_voice_normalizer`` package; this
module only translates Home Assistant options into a pipeline and keeps a few
counters for diagnostics.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .const import (
    CONF_ALIAS_TABLE,
    CONF_ALIASES,
    CONF_CORRECTION_TABLE,
    CONF_CORRECTIONS,
    CONF_SPELLING,
    CONF_SPELLING_MODE,
    LANGUAGE_AUTO,
)
from .ha_voice_normalizer import NormalizationPipeline, SpellingMode, parse_phrase_lines


def build_pipeline(options: Mapping[str, Any], language: str) -> NormalizationPipeline:
    """Build the normalization pipeline described by ``options``.

    ``language`` is the configured language; ``auto`` enables every language's
    spelling triggers.
    """
    aliases = (
        parse_phrase_lines(options.get(CONF_ALIAS_TABLE, "")) if options.get(CONF_ALIASES) else None
    )
    corrections = (
        parse_phrase_lines(options.get(CONF_CORRECTION_TABLE, ""))
        if options.get(CONF_CORRECTIONS)
        else None
    )
    return NormalizationPipeline.create(
        language=None if language == LANGUAGE_AUTO else language,
        spelling=options.get(CONF_SPELLING, True),
        spelling_mode=SpellingMode(options.get(CONF_SPELLING_MODE, SpellingMode.STRICT)),
        aliases=aliases,
        corrections=corrections,
    )


@dataclass(slots=True)
class NormalizerStatistics:
    """Counters exposed through diagnostics.

    Deliberately free of any transcript data.
    """

    requests: int = 0
    transformed: int = 0
    normalization_failures: int = 0
    downstream_failures: int = 0
    normalization_time_ms: float = 0.0

    @property
    def average_normalization_ms(self) -> float:
        """Return the mean normalization time in milliseconds."""
        if not self.requests:
            return 0.0
        return self.normalization_time_ms / self.requests

    def as_dict(self) -> dict[str, Any]:
        """Return the counters as a JSON-serializable dict."""
        return {
            "requests": self.requests,
            "transformed": self.transformed,
            "normalization_failures": self.normalization_failures,
            "downstream_failures": self.downstream_failures,
            "average_normalization_ms": round(self.average_normalization_ms, 4),
        }


@dataclass(slots=True)
class VoiceNormalizerData:
    """Runtime data stored on the config entry."""

    pipeline: NormalizationPipeline
    statistics: NormalizerStatistics = field(default_factory=NormalizerStatistics)
