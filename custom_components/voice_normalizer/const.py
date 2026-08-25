"""Constants for the Voice Normalizer integration."""

import logging
from typing import Final

DOMAIN: Final = "voice_normalizer"
LOGGER: Final = logging.getLogger(__package__)

CONF_DOWNSTREAM_AGENT: Final = "downstream_agent"
CONF_SPELLING: Final = "spelling"
CONF_SPELLING_MODE: Final = "spelling_mode"
CONF_ALIASES: Final = "aliases"
CONF_ALIAS_TABLE: Final = "alias_table"
CONF_CORRECTIONS: Final = "corrections"
CONF_CORRECTION_TABLE: Final = "correction_table"
CONF_LOG_TEXT: Final = "log_text"

DEFAULT_NAME: Final = "Voice Normalizer"
LANGUAGE_AUTO: Final = "auto"
LANGUAGE_OPTIONS: Final = (LANGUAGE_AUTO, "nb", "en")
