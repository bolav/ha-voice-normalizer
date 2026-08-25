"""Tests for the diagnostics payload."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voice_normalizer.const import (
    CONF_ALIAS_TABLE,
    CONF_ALIASES,
)
from custom_components.voice_normalizer.diagnostics import (
    REDACTED,
    async_get_config_entry_diagnostics,
)

from .conftest import MockConversationAgent, normalizer_entity_id, setup_normalizer
from .test_conversation import SPELLED, converse


async def test_diagnostics_report_configuration_and_counters(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    await converse(hass, normalizer_entity_id(hass, normalizer), SPELLED)

    diagnostics = await async_get_config_entry_diagnostics(hass, normalizer)

    assert diagnostics["integration_version"] == "0.1.0"
    assert diagnostics["core_library_version"] == "0.1.0"
    assert diagnostics["enabled_normalizers"] == ["spelling"]
    assert diagnostics["downstream"] == {
        "agent_id": downstream.agent_id,
        "type": "MockConversationAgent",
        "available": True,
        "state": None,
    }
    assert diagnostics["statistics"]["requests"] == 1
    assert diagnostics["statistics"]["transformed"] == 1
    assert diagnostics["statistics"]["normalization_failures"] == 0
    assert diagnostics["statistics"]["downstream_failures"] == 0
    assert diagnostics["statistics"]["average_normalization_ms"] >= 0


async def test_diagnostics_redact_the_alias_table(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    entry = await setup_normalizer(
        hass,
        downstream.agent_id,
        **{CONF_ALIASES: True, CONF_ALIAS_TABLE: "hemmelig: Hemmelig"},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["configuration"][CONF_ALIAS_TABLE] == REDACTED
    assert "hemmelig" not in str(diagnostics)
    assert diagnostics["downstream"]["agent_id"] == downstream.agent_id
    assert diagnostics["enabled_normalizers"] == ["spelling", "aliases"]


async def test_diagnostics_report_a_missing_downstream_agent(hass: HomeAssistant) -> None:
    entry = await setup_normalizer(hass, "conversation.does_not_exist")

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["downstream"]["available"] is False
    assert diagnostics["downstream"]["type"] is None
