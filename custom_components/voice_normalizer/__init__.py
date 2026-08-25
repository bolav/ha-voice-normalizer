"""The Voice Normalizer integration.

A transparent conversation-agent proxy: it normalizes the text coming out of
speech-to-text and hands the result to the conversation agent of your choice.
It never answers on its own.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LANGUAGE, Platform
from homeassistant.core import HomeAssistant

from .const import LANGUAGE_AUTO, LOGGER
from .normalizer import VoiceNormalizerData, build_pipeline

PLATFORMS: tuple[Platform, ...] = (Platform.CONVERSATION,)

type VoiceNormalizerConfigEntry = ConfigEntry[VoiceNormalizerData]


async def async_setup_entry(hass: HomeAssistant, entry: VoiceNormalizerConfigEntry) -> bool:
    """Set up Voice Normalizer from a config entry."""
    options = {**entry.data, **entry.options}
    pipeline = build_pipeline(options, options.get(CONF_LANGUAGE, LANGUAGE_AUTO))
    entry.runtime_data = VoiceNormalizerData(pipeline=pipeline)
    LOGGER.debug(
        "Setting up %s with normalizers %s",
        entry.title,
        [normalizer.name for normalizer in pipeline.normalizers],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoiceNormalizerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: VoiceNormalizerConfigEntry) -> None:
    """Reload the entry so option changes take effect immediately."""
    await hass.config_entries.async_reload(entry.entry_id)
