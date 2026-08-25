"""Data model shared by every normalizer.

The model is intentionally tiny: a result carries the original text, the current
text, and a list of the transformations that produced it. Nothing here depends
on Home Assistant.
"""

from dataclasses import dataclass, field
from typing import Any, Self

OP_PHONETIC_SPELLING = "phonetic_spelling"
"""Operation type emitted by :class:`ha_voice_normalizer.spelling.SpellingNormalizer`."""

OP_ALIAS = "alias"
"""Operation type emitted by :class:`ha_voice_normalizer.aliases.AliasNormalizer`."""

OP_STT_CORRECTION = "stt_correction"
"""Operation type emitted by :class:`ha_voice_normalizer.corrections.SttCorrectionNormalizer`."""


@dataclass(frozen=True, slots=True)
class NormalizationOperation:
    """A single text transformation performed by one normalizer.

    Attributes:
        type: Stable identifier of the transformation, e.g. ``phonetic_spelling``.
        source: The matched text, exactly as it appeared in the input.
        result: The text that replaced ``source``.
        start: Start offset of ``source``.
        end: End offset of ``source`` (exclusive).

    Offsets refer to the text *as it entered the normalizer that produced the
    operation*, which is not necessarily the original pipeline input. When
    several normalizers run, only the first one's offsets are guaranteed to
    match ``NormalizationResult.original_text``.
    """

    type: str
    source: str
    result: str
    start: int
    end: int

    def as_dict(self) -> dict[str, Any]:
        """Return the operation as a JSON-serializable dict."""
        return {
            "type": self.type,
            "source": self.source,
            "result": self.result,
            "start": self.start,
            "end": self.end,
        }


@dataclass(slots=True)
class NormalizationResult:
    """The outcome of running text through a normalizer or a whole pipeline."""

    original_text: str
    text: str
    operations: list[NormalizationOperation] = field(default_factory=list)

    @classmethod
    def unchanged(cls, text: str) -> Self:
        """Return a result that represents "nothing happened to this text"."""
        return cls(original_text=text, text=text, operations=[])

    @property
    def changed(self) -> bool:
        """Return whether the text differs from the original text."""
        return self.text != self.original_text

    def applied(
        self, text: str, operations: list[NormalizationOperation]
    ) -> NormalizationResult:
        """Return a new result with ``text`` and ``operations`` appended.

        The original result is left untouched, so normalizers stay side-effect
        free and are safe to reuse across calls.
        """
        return NormalizationResult(
            original_text=self.original_text,
            text=text,
            operations=[*self.operations, *operations],
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the result as a JSON-serializable dict."""
        return {
            "original_text": self.original_text,
            "text": self.text,
            "changed": self.changed,
            "operations": [operation.as_dict() for operation in self.operations],
        }
