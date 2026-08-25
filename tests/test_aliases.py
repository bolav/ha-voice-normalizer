"""Tests for the alias and STT-correction layers."""

import pytest

from custom_components.voice_normalizer.ha_voice_normalizer import (
    OP_ALIAS,
    OP_STT_CORRECTION,
    AliasNormalizer,
    NormalizationResult,
    SttCorrectionNormalizer,
    parse_phrase_lines,
)


def test_alias_replaces_a_whole_word() -> None:
    normalizer = AliasNormalizer(aliases={"zeekr": "Zeekr"})
    text, operations = normalizer.normalize_text("fortell meg om zeekr")

    assert text == "fortell meg om Zeekr"
    (operation,) = operations
    assert operation.type == OP_ALIAS
    assert operation.source == "zeekr"
    assert operation.result == "Zeekr"
    assert operation.start == len("fortell meg om ")


def test_alias_matching_is_case_insensitive() -> None:
    normalizer = AliasNormalizer(aliases={"HASS": "Home Assistant"})
    assert normalizer.normalize_text("hva er hass")[0] == "hva er Home Assistant"


def test_alias_does_not_match_inside_a_word() -> None:
    normalizer = AliasNormalizer(aliases={"hass": "Home Assistant"})
    text = "det er en hasselnøtt"
    assert normalizer.normalize_text(text)[0] == text


def test_multi_word_alias_wins_over_a_shorter_one() -> None:
    normalizer = AliasNormalizer(aliases={"home": "Hjem", "home assistant": "Home Assistant"})
    assert normalizer.normalize_text("kjør home assistant")[0] == "kjør Home Assistant"


def test_alias_replaces_every_occurrence() -> None:
    normalizer = AliasNormalizer(aliases={"zeekr": "Zeekr"})
    text, operations = normalizer.normalize_text("zeekr og zeekr")
    assert text == "Zeekr og Zeekr"
    assert len(operations) == 2


def test_alias_that_changes_nothing_is_not_reported() -> None:
    normalizer = AliasNormalizer(aliases={"Zeekr": "Zeekr"})
    text, operations = normalizer.normalize_text("om Zeekr")
    assert text == "om Zeekr"
    assert operations == []


def test_empty_alias_table_is_a_no_op() -> None:
    result = NormalizationResult.unchanged("hva som helst")
    assert AliasNormalizer().normalize(result) is result


def test_stt_correction() -> None:
    normalizer = SttCorrectionNormalizer(corrections={"hjemme assistent": "Home Assistant"})
    text, operations = normalizer.normalize_text("spør hjemme assistent om været")

    assert text == "spør Home Assistant om været"
    (operation,) = operations
    assert operation.type == OP_STT_CORRECTION


def test_empty_correction_table_is_a_no_op() -> None:
    result = NormalizationResult.unchanged("hva som helst")
    assert SttCorrectionNormalizer().normalize(result) is result


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ("zeekr: Zeekr", {"zeekr": "Zeekr"}),
        ("zeekr = Zeekr", {"zeekr": "Zeekr"}),
        ("  Zeekr :  Zeekr  ", {"zeekr": "Zeekr"}),
        ("zeekr: Zeekr\nhass: Home Assistant", {"zeekr": "Zeekr", "hass": "Home Assistant"}),
        ("# a comment\n\nzeekr: Zeekr", {"zeekr": "Zeekr"}),
        ("home  assistant: Home Assistant", {"home assistant": "Home Assistant"}),
        # Half-typed or malformed lines are ignored rather than raising.
        ("zeekr", {}),
        (": Zeekr", {}),
        ("zeekr:", {}),
        ("", {}),
    ],
)
def test_parse_phrase_lines(lines: str, expected: dict[str, str]) -> None:
    assert parse_phrase_lines(lines) == expected
