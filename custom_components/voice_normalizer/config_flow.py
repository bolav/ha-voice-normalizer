"""Config and options flow for Voice Normalizer."""

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import conversation
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LANGUAGE, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    ConversationAgentSelector,
    ConversationAgentSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from ha_voice_normalizer import SpellingMode

from .const import (
    CONF_ALIAS_TABLE,
    CONF_ALIASES,
    CONF_CORRECTION_TABLE,
    CONF_CORRECTIONS,
    CONF_DOWNSTREAM_AGENT,
    CONF_LOG_TEXT,
    CONF_SPELLING,
    CONF_SPELLING_MODE,
    DEFAULT_NAME,
    DOMAIN,
    LANGUAGE_AUTO,
    LANGUAGE_OPTIONS,
)

DEFAULT_OPTIONS: Mapping[str, Any] = {
    CONF_LANGUAGE: LANGUAGE_AUTO,
    CONF_SPELLING: True,
    CONF_SPELLING_MODE: SpellingMode.STRICT.value,
    CONF_ALIASES: False,
    CONF_ALIAS_TABLE: "",
    CONF_CORRECTIONS: False,
    CONF_CORRECTION_TABLE: "",
    CONF_LOG_TEXT: False,
}


def _options_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Return the settings schema, pre-filled with ``defaults``."""

    def default(key: str) -> Any:
        return defaults.get(key, DEFAULT_OPTIONS.get(key))

    # The default must be present even when there is nothing to pre-fill. For a
    # required field with no default the frontend derives an initial value from
    # the selector type, and it has no rule for conversation_agent: it raises
    # "Selector conversation_agent not supported in initial form data" and the
    # dialog renders with no fields at all, silently — nothing reaches the Home
    # Assistant log. An empty string keeps the field out of that path, and
    # _validate turns it into a visible error.
    downstream_field = vol.Required(
        CONF_DOWNSTREAM_AGENT, default=default(CONF_DOWNSTREAM_AGENT) or ""
    )

    return vol.Schema(
        {
            downstream_field: ConversationAgentSelector(ConversationAgentSelectorConfig()),
            vol.Required(CONF_SPELLING, default=default(CONF_SPELLING)): BooleanSelector(),
            vol.Required(CONF_SPELLING_MODE, default=default(CONF_SPELLING_MODE)): SelectSelector(
                SelectSelectorConfig(
                    options=[mode.value for mode in SpellingMode],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="spelling_mode",
                )
            ),
            vol.Required(CONF_LANGUAGE, default=default(CONF_LANGUAGE)): SelectSelector(
                SelectSelectorConfig(
                    options=list(LANGUAGE_OPTIONS),
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                    translation_key="language",
                )
            ),
            vol.Required(CONF_ALIASES, default=default(CONF_ALIASES)): BooleanSelector(),
            vol.Optional(CONF_ALIAS_TABLE, default=default(CONF_ALIAS_TABLE)): TextSelector(
                TextSelectorConfig(multiline=True)
            ),
            vol.Required(CONF_CORRECTIONS, default=default(CONF_CORRECTIONS)): BooleanSelector(),
            vol.Optional(
                CONF_CORRECTION_TABLE, default=default(CONF_CORRECTION_TABLE)
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required(CONF_LOG_TEXT, default=default(CONF_LOG_TEXT)): BooleanSelector(),
        }
    )


def _own_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> frozenset[str]:
    """Return the entity ids this config entry owns."""
    registry = er.async_get(hass)
    return frozenset(
        entity.entity_id for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    )


def _validate(
    hass: HomeAssistant, options: Mapping[str, Any], own_entity_ids: frozenset[str]
) -> dict[str, str]:
    """Validate the submitted settings and return per-field errors."""
    agent_id = options.get(CONF_DOWNSTREAM_AGENT)
    if not agent_id:
        return {CONF_DOWNSTREAM_AGENT: "no_agent_selected"}
    if agent_id in own_entity_ids:
        # Delegating to ourselves would recurse until Home Assistant gives up.
        return {CONF_DOWNSTREAM_AGENT: "self_reference"}
    try:
        agent = conversation.async_get_agent(hass, agent_id)
    except ValueError:
        agent = None
    if agent is None:
        return {CONF_DOWNSTREAM_AGENT: "agent_not_found"}
    return {}


class VoiceNormalizerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Normalizer."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create a new normalizer instance."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = dict(user_input)
            name = options.pop(CONF_NAME, DEFAULT_NAME)
            errors = _validate(self.hass, options, frozenset())
            if not errors:
                return self.async_create_entry(title=name, data={}, options=options)

        defaults = {**DEFAULT_OPTIONS, **(user_input or {})}
        schema = vol.Schema(
            {vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): TextSelector()}
        ).extend(_options_schema(defaults).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VoiceNormalizerOptionsFlow:
        """Return the options flow."""
        return VoiceNormalizerOptionsFlow()


class VoiceNormalizerOptionsFlow(OptionsFlow):
    """Handle option changes without recreating the integration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the downstream agent and the enabled normalizers."""
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            errors = _validate(self.hass, user_input, _own_entity_ids(self.hass, self.config_entry))
            if not errors:
                return self.async_create_entry(data=user_input)
            defaults = {**defaults, **user_input}

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(defaults), errors=errors
        )
