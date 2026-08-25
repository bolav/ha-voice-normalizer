"""Tests for the phonetic spelling normalizer."""

import unicodedata

import pytest

from custom_components.voice_normalizer.ha_voice_normalizer import (
    OP_PHONETIC_SPELLING,
    NormalizationResult,
    SpellingMode,
    SpellingNormalizer,
    normalize_spelling,
    normalize_text,
)
from custom_components.voice_normalizer.ha_voice_normalizer.spelling import resolve_languages


def spell(text: str, language: str | None = "nb") -> str:
    """Return ``text`` with spelling normalization applied."""
    return normalize_text(text, language).text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("stav Alfa", "a"),
        ("stav Zulu", "z"),
        ("stav Zulu Ekko Ekko Kilo Romeo", "zeekr"),
        ("stav Alfa Bravo Charlie", "abc"),
    ],
)
def test_basic_spelling(text: str, expected: str) -> None:
    assert spell(text) == expected


@pytest.mark.parametrize(
    "text",
    ["stav ZULU EKKO", "stav zulu ekko", "stav Zulu Ekko", "STAV Zulu ekko"],
)
def test_case_is_ignored(text: str) -> None:
    assert spell(text) == "ze"


@pytest.mark.parametrize(
    "text",
    [
        "stav Zulu Ekko Ekko Kilo Romeo",
        "stav Zulu Echo Echo Kilo Romeo",
        "stav Zulu Eko Eko Kilo Romeo",
    ],
)
def test_norwegian_echo_variants(text: str) -> None:
    assert spell(text) == "zeekr"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("stav Alfa", "a"),
        ("stav Alpha", "a"),
        ("stav Hotel", "h"),
        ("stav Hotell", "h"),
        ("stav Oscar", "o"),
        ("stav Oskar", "o"),
        ("stav Victor", "v"),
        ("stav Viktor", "v"),
        ("stav Whiskey", "w"),
        ("stav Whisky", "w"),
        ("stav Juliett", "j"),
        ("stav Juliet", "j"),
        ("stav Sierra", "s"),
        # Whisper clips the second syllable of "Sierra" in Norwegian speech.
        ("stav Sera", "s"),
        ("stav Serah", "s"),
        ("stav Zulu", "z"),
        # Norwegian has no voiced /z/, so a spoken "Zulu" transcribes as "Sulu".
        ("stav Sulu", "z"),
    ],
)
def test_spelling_variants(text: str, expected: str) -> None:
    assert spell(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Norwegian Armed Forces extension to NATO.
        ("stav Ægir", "æ"),
        ("stav Ørnulf", "ø"),
        ("stav Ågot", "å"),
        # Civilian Norwegian spelling alphabet.
        ("stav Ærlig", "æ"),
        ("stav Østen", "ø"),
        ("stav Åse", "å"),
    ],
)
def test_norwegian_letters(text: str, expected: str) -> None:
    assert spell(text) == expected


def test_norwegian_letters_case_is_ignored() -> None:
    assert spell("stav ÆGIR ØRNULF ÅGOT") == "æøå"
    assert spell("stav ægir ørnulf ågot") == "æøå"


def test_norwegian_letters_inside_a_word() -> None:
    # "Ålesund" is the point of the whole feature: a name a transcriber mangles.
    assert spell("stav Ågot Lima Ekko Sierra Uniform November Delta") == "ålesund"
    assert spell("Fortell om stav Bravo Lima Ågot Bravo Ærlig Romeo") == "Fortell om blåbær"


def test_norwegian_letters_accept_decomposed_input() -> None:
    # Some transcribers emit NFD: "Å" as "A" + combining ring above.
    composed = "stav Ågot Lima Ekko"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert spell(decomposed) == "åle"


def test_decomposed_text_outside_a_span_is_untouched() -> None:
    text = unicodedata.normalize("NFD", "slå på lyset på kjøkkenet")
    assert spell(text) == text


@pytest.mark.parametrize("text", ["stav X-ray", "stav Xray", "stav X ray", "stav x-Ray"])
def test_x_ray_variants(text: str) -> None:
    assert spell(text) == "x"


def test_x_ray_as_two_tokens_inside_a_span() -> None:
    assert spell("stav X ray Yankee Zulu") == "xyz"


def test_punctuation_between_letters_is_dropped() -> None:
    assert spell("stav: Zulu, Ekko, Ekko, Kilo, Romeo") == "zeekr"


def test_trailing_punctuation_is_kept() -> None:
    assert spell("stav Zulu Ekko.") == "ze."


def test_imperative_trigger_is_consumed() -> None:
    assert spell("bilen heter, stav, Zulu Ekko Ekko Kilo Romeo") == "bilen heter zeekr"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("det staves Zulu Ekko Ekko Kilo Romeo", "det staves zeekr"),
        ("det stavet Zulu Ekko Ekko Kilo Romeo", "det stavet zeekr"),
    ],
)
def test_inflected_trigger_is_kept(text: str, expected: str) -> None:
    assert spell(text) == expected


def test_inline_spelling_in_a_sentence() -> None:
    assert (
        spell("Fortell meg om bilen som staves Zulu Ekko Ekko Kilo Romeo")
        == "Fortell meg om bilen som staves zeekr"
    )
    assert spell("Fortell meg om stav Zulu Ekko Ekko Kilo Romeo") == "Fortell meg om zeekr"


def test_multiple_segments() -> None:
    assert (
        spell("brukernavn stav Alfa Bravo Charlie og kode stav X-ray Yankee Zulu")
        == "brukernavn abc og kode xyz"
    )


def test_multiple_segments_in_separate_sentences() -> None:
    assert spell("stav Alfa Bravo. Og stav Kilo Oscar.") == "ab. Og ko."


def test_strict_mode_leaves_a_broken_span_alone() -> None:
    text = "stav Zulu Ekko banan Romeo"
    assert spell(text) == text


def test_strict_mode_rejects_trailing_ordinary_words() -> None:
    text = "stav Hotel India kanskje"
    assert spell(text) == text


def test_partial_mode_converts_what_it_understands() -> None:
    normalizer = SpellingNormalizer(language="nb", mode=SpellingMode.PARTIAL)
    text, _ = normalizer.normalize_text("stav Zulu Ekko banan Romeo")
    assert text == "ze banan Romeo"


def test_partial_mode_is_not_the_default() -> None:
    assert SpellingNormalizer().mode is SpellingMode.STRICT


def test_min_letters_can_require_longer_spans() -> None:
    normalizer = SpellingNormalizer(language="nb", min_letters=2)
    assert normalizer.normalize_text("stav Alfa")[0] == "stav Alfa"
    assert normalizer.normalize_text("stav Alfa Bravo")[0] == "ab"


def test_english_triggers() -> None:
    assert spell("spell Zulu Ekko Ekko Kilo Romeo", "en") == "zeekr"
    assert spell("it is spelled Alfa Bravo", "en") == "it is spelled ab"


def test_norwegian_triggers_are_inactive_for_english() -> None:
    text = "stav Alfa Bravo"
    assert spell(text, "en") == text


def test_auto_language_accepts_every_trigger() -> None:
    assert spell("stav Alfa Bravo", None) == "ab"
    assert spell("spell Alfa Bravo", None) == "ab"
    assert spell("stav Alfa Bravo", "auto") == "ab"


def test_unknown_language_falls_back_to_every_trigger() -> None:
    # Better to keep working for a language we have not tuned than to silently
    # disable normalization for it.
    assert spell("stav Alfa Bravo", "sv") == "ab"
    assert resolve_languages("sv") == resolve_languages(None)


def test_regional_language_tags_are_understood() -> None:
    assert spell("stav Alfa Bravo", "nb-NO") == "ab"
    assert spell("spell Alfa Bravo", "en-US") == "ab"


def test_operation_metadata() -> None:
    text = "Fortell om stav Zulu Ekko Ekko Kilo Romeo"
    result = normalize_text(text, "nb")

    assert result.original_text == text
    assert result.text == "Fortell om zeekr"
    assert result.changed is True

    (operation,) = result.operations
    assert operation.type == OP_PHONETIC_SPELLING
    assert operation.source == "Zulu Ekko Ekko Kilo Romeo"
    assert operation.result == "zeekr"
    assert operation.start == text.index("Zulu")
    assert operation.end == len(text)
    assert text[operation.start : operation.end] == operation.source


def test_unchanged_text_reports_no_operations() -> None:
    result = normalize_text("slå på kjøkkenlyset", "nb")
    assert result.changed is False
    assert result.operations == []
    assert result.text == result.original_text


def test_normalizer_returns_the_same_result_object_when_nothing_changed() -> None:
    result = NormalizationResult.unchanged("ingenting å gjøre her")
    assert SpellingNormalizer(language="nb").normalize(result) is result


def test_normalize_spelling_helper() -> None:
    assert normalize_spelling("stav Zulu Ekko Ekko Kilo Romeo", "nb") == "zeekr"


def test_norwegian_letters_survive() -> None:
    text = "slå på lyset på kjøkkenet"
    assert spell(text) == text


def test_whitespace_outside_spans_is_preserved() -> None:
    assert spell("hei   der,  stav Alfa Bravo") == "hei   der ab"


def test_multiline_text() -> None:
    assert spell("stav Alfa Bravo\nog resten") == "ab\nog resten"
