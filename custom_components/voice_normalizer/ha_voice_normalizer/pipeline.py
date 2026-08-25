"""The normalization pipeline.

A pipeline is an ordered list of normalizers, each of which takes a result and
returns a new one. Nothing here knows about Home Assistant.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol, Self

from .aliases import AliasNormalizer
from .corrections import SttCorrectionNormalizer
from .models import NormalizationResult
from .spelling import SpellingMode, SpellingNormalizer


class Normalizer(Protocol):
    """The contract every pipeline stage implements."""

    name: str

    def normalize(self, result: NormalizationResult) -> NormalizationResult:
        """Return a new result with this normalizer's changes applied."""
        ...


@dataclass(slots=True)
class NormalizationPipeline:
    """Run text through a sequence of normalizers.

    Exceptions are *not* swallowed here. Callers that must keep working when a
    normalizer misbehaves — such as the Home Assistant proxy — are responsible
    for falling back to the original text.
    """

    normalizers: Sequence[Normalizer] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        *,
        language: str | None = None,
        spelling: bool = True,
        spelling_mode: SpellingMode | str = SpellingMode.STRICT,
        aliases: Mapping[str, str] | None = None,
        corrections: Mapping[str, str] | None = None,
    ) -> Self:
        """Build the standard pipeline.

        Args:
            language: Language tag such as ``"nb"``; ``None`` enables every
                language's spelling triggers.
            spelling: Whether to decode phonetic spelling.
            spelling_mode: ``"strict"`` (default) or ``"partial"``.
            aliases: Canonical-name table, or ``None`` to skip that stage.
            corrections: Known-STT-correction table, or ``None`` to skip it.
        """
        normalizers: list[Normalizer] = []
        if spelling:
            normalizers.append(
                SpellingNormalizer(language=language, mode=SpellingMode(spelling_mode))
            )
        if aliases:
            normalizers.append(AliasNormalizer(aliases=aliases))
        if corrections:
            normalizers.append(SttCorrectionNormalizer(corrections=corrections))
        return cls(normalizers=tuple(normalizers))

    def normalize(self, text: str) -> NormalizationResult:
        """Run ``text`` through every normalizer in order."""
        result = NormalizationResult.unchanged(text)
        for normalizer in self.normalizers:
            result = normalizer.normalize(result)
        return result


@lru_cache(maxsize=16)
def _default_pipeline(language: str | None, spelling_mode: str) -> NormalizationPipeline:
    """Return a cached pipeline for the table-free default configuration."""
    return NormalizationPipeline.create(language=language, spelling_mode=spelling_mode)


def normalize_text(
    text: str,
    language: str | None = None,
    *,
    spelling_mode: SpellingMode | str = SpellingMode.STRICT,
    aliases: Mapping[str, str] | None = None,
    corrections: Mapping[str, str] | None = None,
) -> NormalizationResult:
    """Normalize ``text`` with the standard pipeline.

    This is the convenience entry point::

        result = normalize_text("stav Zulu Ekko Ekko Kilo Romeo", language="nb")
        assert result.text == "zeekr"

    Long-running callers should build a :class:`NormalizationPipeline` once and
    reuse it instead.
    """
    if aliases or corrections:
        pipeline = NormalizationPipeline.create(
            language=language,
            spelling_mode=spelling_mode,
            aliases=aliases,
            corrections=corrections,
        )
    else:
        pipeline = _default_pipeline(language, SpellingMode(spelling_mode).value)
    return pipeline.normalize(text)
