"""Diagnostics for Voice Normalizer.

Reports configuration and counters only. Request text, alias tables and
correction tables are never included: they can contain names, passwords spelled
out by voice, and other things that do not belong in a shared diagnostics file.
"""

from typing import Any

from homeassistant.components import conversation
from homeassistant.const import CONF_LANGUAGE
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

import ha_voice_normalizer

from . import VoiceNormalizerConfigEntry
from .const import (
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

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VoiceNormalizerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    options = {**entry.data, **entry.options}
    data = entry.runtime_data
    integration = await async_get_integration(hass, DOMAIN)
    agent_id = options.get(CONF_DOWNSTREAM_AGENT)

    try:
        agent = conversation.async_get_agent(hass, agent_id) if agent_id else None
    except ValueError:
        agent = None

    state = hass.states.get(agent_id) if agent_id and "." in agent_id else None

    return {
        "integration_version": str(integration.version),
        "core_library_version": ha_voice_normalizer.__version__,
        "configuration": {
            CONF_LANGUAGE: options.get(CONF_LANGUAGE),
            CONF_SPELLING: options.get(CONF_SPELLING),
            CONF_SPELLING_MODE: options.get(CONF_SPELLING_MODE),
            CONF_ALIASES: options.get(CONF_ALIASES),
            CONF_ALIAS_TABLE: REDACTED if options.get(CONF_ALIAS_TABLE) else "",
            CONF_CORRECTIONS: options.get(CONF_CORRECTIONS),
            CONF_CORRECTION_TABLE: REDACTED if options.get(CONF_CORRECTION_TABLE) else "",
            CONF_LOG_TEXT: options.get(CONF_LOG_TEXT),
        },
        "enabled_normalizers": [normalizer.name for normalizer in data.pipeline.normalizers],
        "downstream": {
            "agent_id": agent_id,
            "type": type(agent).__name__ if agent is not None else None,
            "available": agent is not None,
            "state": state.state if state else None,
        },
        "statistics": data.statistics.as_dict(),
    }
