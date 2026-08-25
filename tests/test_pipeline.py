"""Tests for the pipeline and the public API."""

import pytest

from ha_voice_normalizer import (
    AliasNormalizer,
    NormalizationPipeline,
    NormalizationResult,
    SpellingMode,
    SpellingNormalizer,
    SttCorrectionNormalizer,
    normalize_text,
)
from ha_voice_normalizer.__main__ import main


def test_readme_example() -> None:
    result = normalize_text("stav Zulu Ekko Ekko Kilo Romeo", language="nb")
    assert result.text == "zeekr"


def test_spelling_feeds_the_alias_layer() -> None:
    pipeline = NormalizationPipeline.create(language="nb", aliases={"zeekr": "Zeekr"})
    result = pipeline.normalize("Fortell om stav Zulu Ekko Ekko Kilo Romeo")

    assert result.text == "Fortell om Zeekr"
    assert [operation.type for operation in result.operations] == [
        "phonetic_spelling",
        "alias",
    ]


def test_pipeline_can_be_built_stage_by_stage() -> None:
    pipeline = NormalizationPipeline(
        normalizers=(
            SttCorrectionNormalizer(corrections={"sekr": "stav Zulu Ekko Ekko Kilo Romeo"}),
            SpellingNormalizer(language="nb"),
            AliasNormalizer(aliases={"zeekr": "Zeekr"}),
        )
    )
    assert pipeline.normalize("sekr").text == "Zeekr"


def test_disabled_spelling() -> None:
    pipeline = NormalizationPipeline.create(language="nb", spelling=False)
    assert pipeline.normalizers == ()
    assert pipeline.normalize("stav Alfa Bravo").text == "stav Alfa Bravo"


def test_spelling_mode_accepts_a_string() -> None:
    pipeline = NormalizationPipeline.create(language="nb", spelling_mode="partial")
    assert pipeline.normalize("stav Alfa Bravo banan").text == "ab banan"


def test_unknown_spelling_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="nonsense"):
        NormalizationPipeline.create(spelling_mode="nonsense")


def test_normalize_text_with_tables() -> None:
    result = normalize_text(
        "stav Zulu Ekko Ekko Kilo Romeo",
        "nb",
        aliases={"zeekr": "Zeekr"},
        corrections={"noe": "noe annet"},
    )
    assert result.text == "Zeekr"


def test_default_pipelines_are_reused() -> None:
    assert normalize_text("stav Alfa", "nb").text == "a"
    assert normalize_text("stav Alfa", "nb").text == "a"


def test_result_as_dict() -> None:
    result = normalize_text("stav Alfa Bravo", "nb")
    assert result.as_dict() == {
        "original_text": "stav Alfa Bravo",
        "text": "ab",
        "changed": True,
        "operations": [
            {
                "type": "phonetic_spelling",
                "source": "Alfa Bravo",
                "result": "ab",
                "start": 5,
                "end": 15,
            }
        ],
    }


def test_result_applied_does_not_mutate_the_previous_result() -> None:
    first = NormalizationResult.unchanged("a")
    second = first.applied("b", [])

    assert first.text == "a"
    assert second.text == "b"
    assert second.original_text == "a"
    assert first.operations is not second.operations


def test_spelling_mode_values() -> None:
    assert SpellingMode("strict") is SpellingMode.STRICT
    assert SpellingMode("partial") is SpellingMode.PARTIAL


def test_cli_prints_normalized_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--language", "nb", "stav", "Zulu", "Ekko", "Ekko", "Kilo", "Romeo"]) == 0
    assert capsys.readouterr().out.strip() == "zeekr"


def test_cli_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--language", "nb", "--json", "stav Alfa"]) == 0
    assert '"result": "a"' in capsys.readouterr().out
