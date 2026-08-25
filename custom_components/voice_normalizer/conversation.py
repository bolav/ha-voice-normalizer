"""Conversation platform for Voice Normalizer.

The entity is a transparent proxy: normalize the text, hand it to the
configured downstream agent, return that agent's answer untouched.
"""

import logging
import time
from contextvars import ContextVar
from typing import Any, Literal, override

from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

import ha_voice_normalizer
from ha_voice_normalizer import NormalizationResult

from . import VoiceNormalizerConfigEntry
from .const import CONF_DOWNSTREAM_AGENT, CONF_LOG_TEXT, DOMAIN, LOGGER

_ACTIVE_NORMALIZERS: ContextVar[frozenset[str]] = ContextVar(
    "voice_normalizer_active", default=frozenset()
)
"""Normalizer entities currently waiting on a downstream agent.

Best-effort recursion protection for chains such as A -> B -> A. It travels
with the asyncio context, so it survives ``await`` but not an agent that
dispatches the request to an unrelated task.
"""

_MESSAGES: dict[str, dict[str, str]] = {
    "downstream_unavailable": {
        "en": "The conversation agent {agent} is not available right now.",
        "nb": "Samtaleagenten {agent} er ikke tilgjengelig nå.",
    },
    "loop": {
        "en": "Voice Normalizer is configured in a loop, so the request was stopped.",
        "nb": "Voice Normalizer er satt opp i en løkke, så forespørselen ble stoppet.",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoiceNormalizerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the conversation entity for a config entry."""
    async_add_entities([VoiceNormalizerConversationEntity(entry)])


class VoiceNormalizerConversationEntity(conversation.ConversationEntity):
    """A conversation agent that normalizes text and delegates the rest."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: VoiceNormalizerConfigEntry) -> None:
        """Initialize the proxy entity."""
        self._entry = entry
        self._options: dict[str, Any] = {**entry.data, **entry.options}
        self._resolving_downstream = False
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ha-voice-normalizer",
            model="Voice Normalizer",
            sw_version=ha_voice_normalizer.__version__,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _downstream_agent_id(self) -> str:
        """Return the configured downstream conversation agent id."""
        return self._options[CONF_DOWNSTREAM_AGENT]

    @property
    def _downstream_agent(self) -> Any | None:
        """Return the downstream agent object, or ``None`` if unavailable.

        Resolves to ``None`` for a self-reference and for re-entrant lookups
        (A -> B -> A): mirroring another agent's attributes must never recurse,
        not even while Home Assistant is only rendering entity state.
        """
        if self.hass is None or self._resolving_downstream:
            return None
        agent_id = self._downstream_agent_id
        if agent_id == self.entity_id:
            return None

        self._resolving_downstream = True
        try:
            return conversation.async_get_agent(self.hass, agent_id)
        except ValueError:
            return None
        finally:
            self._resolving_downstream = False

    @property
    @override
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Mirror the downstream agent's languages; we add no restrictions."""
        agent = self._downstream_agent
        if agent is None:
            return MATCH_ALL
        return agent.supported_languages

    @property
    @override
    def supported_features(self) -> conversation.ConversationEntityFeature:
        """Mirror the downstream agent's features, e.g. whether it can control the house."""
        agent = self._downstream_agent
        if isinstance(agent, conversation.ConversationEntity):
            return agent.supported_features
        return conversation.ConversationEntityFeature.CONTROL

    @override
    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Normalize the request, then let the downstream agent answer it.

        This deliberately overrides ``async_process`` instead of implementing
        ``_async_handle_message``: opening a chat log here would make this
        entity a second owner of the conversation, and every user message would
        end up in the history twice once the downstream agent opens its own log
        for the same conversation id. A proxy should own no conversation state.
        """
        data = self._entry.runtime_data
        data.statistics.requests += 1
        agent_id = self._downstream_agent_id

        if agent_id == self.entity_id or self.entity_id in _ACTIVE_NORMALIZERS.get():
            LOGGER.error(
                "Routing loop detected: %s is configured to delegate to %s. "
                "Pick a different downstream conversation agent",
                self.entity_id,
                agent_id,
            )
            return self._error_result(user_input, "loop")

        text = self._normalize(user_input)

        if self._downstream_agent is None:
            data.statistics.downstream_failures += 1
            LOGGER.error("Downstream conversation agent %s is not available", agent_id)
            return self._error_result(user_input, "downstream_unavailable", agent=agent_id)

        started = time.perf_counter()
        token = _ACTIVE_NORMALIZERS.set(_ACTIVE_NORMALIZERS.get() | {self.entity_id})
        try:
            result = await conversation.async_converse(
                self.hass,
                text=text,
                conversation_id=user_input.conversation_id,
                context=user_input.context,
                language=user_input.language,
                agent_id=agent_id,
                device_id=user_input.device_id,
                satellite_id=user_input.satellite_id,
                extra_system_prompt=user_input.extra_system_prompt,
            )
        except Exception:
            data.statistics.downstream_failures += 1
            LOGGER.exception("Conversation agent %s failed to handle the request", agent_id)
            return self._error_result(user_input, "downstream_unavailable", agent=agent_id)
        finally:
            _ACTIVE_NORMALIZERS.reset(token)

        LOGGER.debug(
            "Downstream agent %s answered in %.1f ms",
            agent_id,
            (time.perf_counter() - started) * 1000,
        )
        return result

    def _normalize(self, user_input: conversation.ConversationInput) -> str:
        """Return the normalized text, falling back to the original on failure.

        Normalization is a convenience, not a gatekeeper: a bug in here must
        never stop "slå på lyset" from reaching the house.
        """
        data = self._entry.runtime_data
        started = time.perf_counter()
        try:
            result = data.pipeline.normalize(user_input.text)
        except Exception:
            data.statistics.normalization_failures += 1
            LOGGER.exception(
                "Normalization failed for a %d character request; "
                "forwarding the original text to %s",
                len(user_input.text),
                self._downstream_agent_id,
            )
            return user_input.text

        elapsed_ms = (time.perf_counter() - started) * 1000
        data.statistics.normalization_time_ms += elapsed_ms
        if result.changed:
            data.statistics.transformed += 1
        self._log_request(user_input, result, elapsed_ms)
        return result.text

    def _log_request(
        self,
        user_input: conversation.ConversationInput,
        result: NormalizationResult,
        elapsed_ms: float,
    ) -> None:
        """Log what the normalizer did, without leaking transcripts by default."""
        if not LOGGER.isEnabledFor(logging.DEBUG):
            return

        if self._options.get(CONF_LOG_TEXT):
            LOGGER.debug(
                "Normalizer request (language=%s, %.3f ms, downstream=%s): %r -> %r via %s",
                user_input.language,
                elapsed_ms,
                self._downstream_agent_id,
                result.original_text,
                result.text,
                [operation.as_dict() for operation in result.operations],
            )
        else:
            LOGGER.debug(
                "Normalizer request (language=%s, %.3f ms, downstream=%s): "
                "%d characters, changed=%s, operations=%s "
                "(enable the 'log request text' option to see the text)",
                user_input.language,
                elapsed_ms,
                self._downstream_agent_id,
                len(user_input.text),
                result.changed,
                [operation.type for operation in result.operations],
            )

    def _error_result(
        self,
        user_input: conversation.ConversationInput,
        message_key: str,
        **placeholders: str,
    ) -> conversation.ConversationResult:
        """Return a spoken error instead of inventing an answer."""
        language = (user_input.language or "en").split("-")[0].casefold()
        messages = _MESSAGES[message_key]
        message = messages.get(language, messages["en"]).format(**placeholders)

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, message)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id
        )
