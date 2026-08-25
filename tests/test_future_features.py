"""Behaviour that is designed for but not implemented yet.

These are marked xfail(strict=True) on purpose: they document the intended
semantics and will fail loudly the day the feature lands, so the roadmap and
the tests cannot quietly drift apart.
"""

import pytest

from ha_voice_normalizer import normalize_text

pytestmark = pytest.mark.xfail(strict=True, reason="planned, see the roadmap in README.md")


def test_spoken_digits() -> None:
    assert normalize_text("stav to fire null", "nb").text == "240"


def test_spoken_symbols() -> None:
    assert normalize_text("stav Alfa krøllalfa Bravo punktum Charlie", "nb").text == "a@b.c"


def test_dropping_the_carrier_phrase() -> None:
    # With an explicit "replace the whole phrase" policy configured, the
    # sentence should collapse instead of keeping "som staves".
    assert (
        normalize_text("Fortell meg om bilen som staves Zulu Ekko Ekko Kilo Romeo", "nb").text
        == "Fortell meg om bilen zeekr"
    )
