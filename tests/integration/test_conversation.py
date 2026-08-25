"""Tests for the Voice Normalizer conversation proxy."""

import logging
from typing import Any, Literal

import pytest
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import MATCH_ALL, STATE_UNAVAILABLE
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voice_normalizer.const import CONF_LOG_TEXT, DOMAIN

from .conftest import (
    MockConversationAgent,
    normalizer_entity_id,
    setup_normalizer,
)

SPELLED = "fortell om stav Zulu Ekko Ekko Kilo Romeo"
NORMALIZED = "fortell om zeekr"


def own_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Return only what this integration logged.

    Home Assistant's own conversation logging prints the request text at debug
    level; what this integration must not leak is what it logs itself.
    """
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith(f"custom_components.{DOMAIN}")
    )


async def converse(
    hass: HomeAssistant,
    entity_id: str,
    text: str,
    **kwargs: Any,
) -> conversation.ConversationResult:
    """Send ``text`` to a conversation agent."""
    kwargs.setdefault("conversation_id", None)
    kwargs.setdefault("context", Context())
    kwargs.setdefault("language", "nb")
    return await conversation.async_converse(hass, text=text, agent_id=entity_id, **kwargs)


async def test_setup_creates_a_conversation_entity(
    hass: HomeAssistant, normalizer: MockConfigEntry
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    assert entity_id.startswith("conversation.")
    assert hass.states.get(entity_id) is not None


async def test_text_without_spelling_is_passed_through(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)

    await converse(hass, entity_id, "slå på lyset")

    assert downstream.last_call.text == "slå på lyset"
    assert normalizer.runtime_data.statistics.transformed == 0


async def test_spelling_is_normalized_before_delegation(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)

    await converse(hass, entity_id, SPELLED)

    assert downstream.last_call.text == NORMALIZED
    assert normalizer.runtime_data.statistics.transformed == 1


async def test_conversation_context_is_preserved(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    context = Context(user_id="user-1")

    await converse(
        hass,
        entity_id,
        SPELLED,
        conversation_id="conversation-1",
        context=context,
        language="nb-NO",
        device_id="device-1",
        satellite_id="satellite-1",
    )

    call = downstream.last_call
    assert call.conversation_id == "conversation-1"
    assert call.language == "nb-NO"
    assert call.device_id == "device-1"
    assert call.satellite_id == "satellite-1"
    assert call.context is context
    assert call.agent_id == downstream.agent_id


async def test_multi_turn_conversation_keeps_the_same_id(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)

    first = await converse(hass, entity_id, "Fortell meg om Zeekr")
    second = await converse(
        hass, entity_id, "Hva koster den?", conversation_id=first.conversation_id
    )

    assert first.conversation_id == downstream.conversation_id
    assert second.conversation_id == first.conversation_id
    assert [call.conversation_id for call in downstream.calls] == [
        None,
        downstream.conversation_id,
    ]


async def test_downstream_response_is_returned_unchanged(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    downstream.response_text = "Zeekr er en bilprodusent."
    downstream.continue_conversation = True

    result = await converse(hass, entity_id, SPELLED)

    assert result.response.response_type is intent.IntentResponseType.ACTION_DONE
    assert result.response.speech["plain"]["speech"] == "Zeekr er en bilprodusent."
    assert result.continue_conversation is True


class _BrokenPipeline:
    """A pipeline that always fails, to prove normalization fails open."""

    normalizers: tuple[Any, ...] = ()

    def normalize(self, text: str) -> Any:
        """Raise, as a buggy normalizer would."""
        raise RuntimeError("boom")


async def test_normalizer_failure_forwards_the_original_text(
    hass: HomeAssistant,
    normalizer: MockConfigEntry,
    downstream: MockConversationAgent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    normalizer.runtime_data.pipeline = _BrokenPipeline()

    with caplog.at_level(logging.ERROR):
        result = await converse(hass, entity_id, "slå på kjøkkenlyset")

    assert downstream.last_call.text == "slå på kjøkkenlyset"
    assert result.response.response_type is intent.IntentResponseType.ACTION_DONE
    assert normalizer.runtime_data.statistics.normalization_failures == 1
    assert "Normalization failed" in caplog.text
    assert "boom" in caplog.text


async def test_downstream_exception_returns_a_safe_response(
    hass: HomeAssistant,
    normalizer: MockConfigEntry,
    downstream: MockConversationAgent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    downstream.error = RuntimeError("downstream exploded")

    with caplog.at_level(logging.ERROR):
        result = await converse(hass, entity_id, SPELLED)

    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert result.response.error_code is intent.IntentResponseErrorCode.UNKNOWN
    assert "ikke tilgjengelig" in result.response.speech["plain"]["speech"]
    assert normalizer.runtime_data.statistics.downstream_failures == 1
    assert "failed to handle the request" in caplog.text


async def test_downstream_home_assistant_error_is_surfaced(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    downstream.error = HomeAssistantError("agent is not ready")

    result = await converse(hass, entity_id, SPELLED)

    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert "agent is not ready" in result.response.speech["plain"]["speech"]


async def test_missing_downstream_agent_returns_an_error(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await setup_normalizer(hass, "conversation.does_not_exist")
    entity_id = normalizer_entity_id(hass, entry)

    with caplog.at_level(logging.ERROR):
        result = await converse(hass, entity_id, SPELLED)

    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert "conversation.does_not_exist" in result.response.speech["plain"]["speech"]
    assert entry.runtime_data.statistics.downstream_failures == 1
    assert "is not available" in caplog.text


async def test_english_error_message(hass: HomeAssistant) -> None:
    entry = await setup_normalizer(hass, "conversation.does_not_exist")
    entity_id = normalizer_entity_id(hass, entry)

    result = await converse(hass, entity_id, "tell me about it", language="en")

    assert "is not available right now" in result.response.speech["plain"]["speech"]


async def test_direct_self_routing_is_blocked_at_runtime(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    # The config flow prevents this, but a hand-edited config entry must not
    # take Home Assistant down with it.
    entry = await setup_normalizer(hass, "conversation.self_router", title="Self router")
    entity_id = normalizer_entity_id(hass, entry)
    assert entity_id == "conversation.self_router"

    with caplog.at_level(logging.ERROR):
        result = await converse(hass, entity_id, SPELLED)

    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert "løkke" in result.response.speech["plain"]["speech"]
    assert "Routing loop detected" in caplog.text


class _EchoBackAgent(conversation.AbstractConversationAgent):
    """A downstream agent that sends the request back to a normalizer."""

    def __init__(self, hass: HomeAssistant, target_entity_id: str) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.target_entity_id = target_entity_id
        self.calls = 0

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return the supported languages."""
        return ["nb"]

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Bounce the request straight back to the normalizer."""
        self.calls += 1
        return await conversation.async_converse(
            self.hass,
            text=user_input.text,
            conversation_id=user_input.conversation_id,
            context=user_input.context,
            language=user_input.language,
            agent_id=self.target_entity_id,
        )


async def test_indirect_routing_loop_is_stopped(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    loop_entry = MockConfigEntry(domain="mock_loop_agent", title="Loop agent")
    loop_entry.add_to_hass(hass)
    entry = await setup_normalizer(hass, loop_entry.entry_id, title="Loop normalizer")
    entity_id = normalizer_entity_id(hass, entry)
    agent = _EchoBackAgent(hass, entity_id)
    conversation.async_set_agent(hass, loop_entry, agent)

    with caplog.at_level(logging.ERROR):
        result = await converse(hass, entity_id, SPELLED)

    assert agent.calls == 1
    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert "Routing loop detected" in caplog.text


async def test_multiple_instances_coexist(
    hass: HomeAssistant, downstream: MockConversationAgent
) -> None:
    other_entry = MockConfigEntry(domain="mock_conversation_agent", title="Other agent")
    other_entry.add_to_hass(hass)
    other_agent = MockConversationAgent()
    other_agent.agent_id = other_entry.entry_id
    conversation.async_set_agent(hass, other_entry, other_agent)

    first = await setup_normalizer(hass, downstream.agent_id, title="Normalizer Norwegian")
    second = await setup_normalizer(
        hass, other_agent.agent_id, title="Normalizer LLM", spelling=False
    )

    first_entity = normalizer_entity_id(hass, first)
    second_entity = normalizer_entity_id(hass, second)
    assert first_entity != second_entity

    await converse(hass, first_entity, SPELLED)
    await converse(hass, second_entity, SPELLED)

    assert downstream.last_call.text == NORMALIZED
    # The second instance has spelling disabled, so it forwards the raw text.
    assert other_agent.last_call.text == SPELLED


async def test_entity_mirrors_the_downstream_agent(
    hass: HomeAssistant, normalizer: MockConfigEntry, downstream: MockConversationAgent
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)
    entity = hass.data[conversation.DATA_COMPONENT].get_entity(entity_id)

    assert entity.unique_id == normalizer.entry_id
    assert entity.supported_languages == downstream.supported_languages


async def test_entity_without_a_downstream_agent_accepts_every_language(
    hass: HomeAssistant,
) -> None:
    entry = await setup_normalizer(hass, "conversation.does_not_exist")
    entity_id = normalizer_entity_id(hass, entry)
    entity = hass.data[conversation.DATA_COMPONENT].get_entity(entity_id)

    assert entity.supported_languages == MATCH_ALL
    assert entity.supported_features is conversation.ConversationEntityFeature.CONTROL


async def test_debug_logging_hides_text_by_default(
    hass: HomeAssistant, normalizer: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)

    with caplog.at_level(logging.DEBUG, logger=f"custom_components.{DOMAIN}"):
        await converse(hass, entity_id, SPELLED)

    logged = own_log_text(caplog)
    assert "phonetic_spelling" in logged
    assert SPELLED not in logged
    assert NORMALIZED not in logged


async def test_debug_logging_can_include_text(
    hass: HomeAssistant, downstream: MockConversationAgent, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await setup_normalizer(hass, downstream.agent_id, **{CONF_LOG_TEXT: True})
    entity_id = normalizer_entity_id(hass, entry)

    with caplog.at_level(logging.DEBUG, logger=f"custom_components.{DOMAIN}"):
        await converse(hass, entity_id, SPELLED)

    logged = own_log_text(caplog)
    assert SPELLED in logged
    assert NORMALIZED in logged


async def test_unload_makes_the_entity_unavailable(
    hass: HomeAssistant, normalizer: MockConfigEntry
) -> None:
    entity_id = normalizer_entity_id(hass, normalizer)

    assert await hass.config_entries.async_unload(normalizer.entry_id)
    await hass.async_block_till_done()

    assert normalizer.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
