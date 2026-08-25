"""Fixtures for the Home Assistant integration tests."""

import pathlib
from collections.abc import AsyncGenerator
from typing import Any, Literal

import pytest
from homeassistant.components import conversation
from homeassistant.const import CONF_LANGUAGE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voice_normalizer.const import (
    CONF_DOWNSTREAM_AGENT,
    CONF_SPELLING,
    DEFAULT_NAME,
    DOMAIN,
    LANGUAGE_AUTO,
)

COMPONENT_DIR = pathlib.Path(__file__).parents[2] / "custom_components" / DOMAIN

MOCK_AGENT_DOMAIN = "mock_conversation_agent"


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Make this repository's custom_components visible to Home Assistant."""
    config_dir = pathlib.Path(hass_tmp_config_dir)
    custom_components = config_dir / "custom_components"
    custom_components.mkdir(exist_ok=True)
    (custom_components / DOMAIN).symlink_to(COMPONENT_DIR)
    return str(config_dir)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations for every test in this directory."""


@pytest.fixture(autouse=True)
async def setup_conversation(hass: HomeAssistant) -> None:
    """Set up the components the proxy delegates through."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})


class MockConversationAgent(conversation.AbstractConversationAgent):
    """A downstream conversation agent that records what it was asked."""

    def __init__(self) -> None:
        """Initialize the agent."""
        self.agent_id = ""
        self.calls: list[conversation.ConversationInput] = []
        self.response_text = "Zeekr er en bilprodusent."
        self.conversation_id = "downstream-conversation-id"
        self.continue_conversation = False
        self.error: Exception | None = None

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return the languages this agent claims to support."""
        return ["nb", "en"]

    @property
    def last_call(self) -> conversation.ConversationInput:
        """Return the most recent request."""
        return self.calls[-1]

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Answer a request, or blow up if the test asked for that."""
        self.calls.append(user_input)
        if self.error is not None:
            raise self.error
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(self.response_text)
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id or self.conversation_id,
            continue_conversation=self.continue_conversation,
        )


@pytest.fixture
async def downstream(hass: HomeAssistant) -> AsyncGenerator[MockConversationAgent]:
    """Register a downstream conversation agent and return it."""
    entry = MockConfigEntry(domain=MOCK_AGENT_DOMAIN, title="Mock agent")
    entry.add_to_hass(hass)
    agent = MockConversationAgent()
    agent.agent_id = entry.entry_id
    conversation.async_set_agent(hass, entry, agent)
    yield agent
    conversation.async_unset_agent(hass, entry)


def normalizer_options(agent_id: str, **overrides: Any) -> dict[str, Any]:
    """Return config entry options pointing at ``agent_id``."""
    return {
        CONF_DOWNSTREAM_AGENT: agent_id,
        CONF_SPELLING: True,
        CONF_LANGUAGE: LANGUAGE_AUTO,
        **overrides,
    }


async def setup_normalizer(
    hass: HomeAssistant,
    agent_id: str,
    *,
    title: str = DEFAULT_NAME,
    **overrides: Any,
) -> MockConfigEntry:
    """Set up a Voice Normalizer instance and return its config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_NAME: title},
        options=normalizer_options(agent_id, **overrides),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def normalizer_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the conversation entity id created by ``entry``."""
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 1
    return entities[0].entity_id


@pytest.fixture
async def normalizer(hass: HomeAssistant, downstream: MockConversationAgent) -> MockConfigEntry:
    """Set up a normalizer delegating to the mock downstream agent."""
    return await setup_normalizer(hass, downstream.agent_id)
