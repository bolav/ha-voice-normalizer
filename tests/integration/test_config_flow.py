"""Tests for the config and options flow."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_LANGUAGE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voice_normalizer.const import (
    CONF_ALIAS_TABLE,
    CONF_ALIASES,
    CONF_CORRECTION_TABLE,
    CONF_CORRECTIONS,
    CONF_DOWNSTREAM_AGENT,
    CONF_LOG_TEXT,
    CONF_SPELLING,
    CONF_SPELLING_MODE,
    DOMAIN,
)

from .conftest import MockConversationAgent, normalizer_entity_id, setup_normalizer
from .test_conversation import NORMALIZED, SPELLED, converse


def user_input(agent_id: str, **overrides: Any) -> dict[str, Any]:
    """Return a filled-in form."""
    return {
        CONF_DOWNSTREAM_AGENT: agent_id,
        CONF_SPELLING: True,
        CONF_SPELLING_MODE: "strict",
        CONF_LANGUAGE: "nb",
        CONF_ALIASES: False,
        CONF_ALIAS_TABLE: "",
        CONF_CORRECTIONS: False,
        CONF_CORRECTION_TABLE: "",
        CONF_LOG_TEXT: False,
        **overrides,
    }


async def test_user_flow(hass: HomeAssistant, downstream: MockConversationAgent) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input(downstream.agent_id, **{CONF_NAME: "Norsk normalizer"}),
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Norsk normalizer"
    assert result["options"][CONF_DOWNSTREAM_AGENT] == downstream.agent_id
    assert CONF_NAME not in result["options"]

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await converse(hass, normalizer_entity_id(hass, entry), SPELLED)
    assert downstream.last_call.text == NORMALIZED


async def test_user_flow_rejects_an_unknown_agent(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input("conversation.nope", **{CONF_NAME: "Nope"})
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DOWNSTREAM_AGENT: "agent_not_found"}

    # The form can be corrected without starting over.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input(downstream.agent_id, **{CONF_NAME: "Fixed"})
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_multiple_entries_are_allowed(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    for name in ("First", "Second"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input(downstream.agent_id, **{CONF_NAME: name})
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY

    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_options_flow_changes_the_downstream_agent(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    from homeassistant.components import conversation

    other_entry = MockConfigEntry(domain="mock_conversation_agent", title="Other agent")
    other_entry.add_to_hass(hass)
    other_agent = MockConversationAgent()
    other_agent.agent_id = other_entry.entry_id
    conversation.async_set_agent(hass, other_entry, other_agent)

    entry = await setup_normalizer(hass, downstream.agent_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input(other_agent.agent_id, **{CONF_SPELLING: False})
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DOWNSTREAM_AGENT] == other_agent.agent_id

    # The entry was reloaded, so the new settings are live.
    await converse(hass, normalizer_entity_id(hass, entry), SPELLED)
    assert not downstream.calls
    assert other_agent.last_call.text == SPELLED


async def test_options_flow_rejects_self_reference(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    entry = await setup_normalizer(hass, downstream.agent_id)
    entity_id = normalizer_entity_id(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input(entity_id)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DOWNSTREAM_AGENT: "self_reference"}
    assert entry.options[CONF_DOWNSTREAM_AGENT] == downstream.agent_id


async def test_options_flow_keeps_alias_tables(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    entry = await setup_normalizer(hass, downstream.agent_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input(
            downstream.agent_id,
            **{CONF_ALIASES: True, CONF_ALIAS_TABLE: "zeekr: Zeekr"},
        ),
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await converse(hass, normalizer_entity_id(hass, entry), SPELLED)
    assert downstream.last_call.text == "fortell om Zeekr"
