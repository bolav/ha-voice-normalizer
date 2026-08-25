"""Text that must never be touched.

This component sits in front of smart-home commands, so a false positive is
worse than a missed spelling. Everything here goes through the pipeline
unchanged.
"""

import pytest

from ha_voice_normalizer import normalize_text


@pytest.mark.parametrize(
    "text",
    [
        # NATO code words are ordinary words too, and there is no trigger here.
        "Hotel India Golf",
        "November Oscar",
        "Jeg bor på Hotel India",
        "Golf er gøy",
        "Vi møtes på Hotel Bravo i november",
        "Papa og mamma spiller golf",
        "Whiskey er ikke min greie",
        # Ordinary house commands.
        "slå på lyset",
        "slå på kjøkkenlyset",
        "skru av lyset i stua",
        "hva er temperaturen på soverommet",
        # Trigger word without anything to spell.
        "stav",
        "stav noe for meg",
        "kan du stave det for meg",
        # Trigger with an unrecognized span (strict mode).
        "stav Zulu Ekko banan Romeo",
        "stav Hotel India kanskje",
    ],
)
def test_text_is_left_alone(text: str) -> None:
    result = normalize_text(text, "nb")
    assert result.text == text
    assert result.changed is False
    assert result.operations == []


def test_empty_text() -> None:
    result = normalize_text("", "nb")
    assert result.text == ""
    assert result.changed is False


def test_trigger_only_at_end_of_sentence() -> None:
    text = "det er ikke lett å stave"
    assert normalize_text(text, "nb").text == text
