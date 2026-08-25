# Addendum: Standalone Home Assistant mode for `ha-voice-normalizer`

`ha-voice-normalizer` must work without `ha-voice-router`.

This is an explicit architectural requirement.

The project should support three deployment modes:

```text
1. Pure Python library
2. Standalone Home Assistant Conversation Agent
3. Processor/plugin inside ha-voice-router
```

The normalization core must be shared between all three modes.

Do not duplicate spelling or normalization logic inside the Home Assistant integration.

---

## Mode 1 — Pure Python library

The core functionality must work without Home Assistant installed.

Example:

```python
from ha_voice_normalizer import normalize_text

result = normalize_text(
    "stav Zulu Ekko Ekko Kilo Romeo",
    language="nb",
)

assert result.text == "zeekr"
```

This mode is primarily for:

* development
* unit tests
* command-line tools
* integration into other Python applications
* future reuse by `ha-voice-router`

The package must not import Home Assistant modules from its core normalization modules.

Keep dependencies minimal.

A structure such as this is preferred:

```text
src/
└── ha_voice_normalizer/
    ├── __init__.py
    ├── models.py
    ├── pipeline.py
    ├── spelling.py
    ├── aliases.py
    └── corrections.py
```

All Home Assistant-specific code must live separately.

---

# Mode 2 — Standalone Home Assistant Conversation Agent

Create an optional Home Assistant custom integration that allows `ha-voice-normalizer` to be selected directly as the Conversation Agent in an Assist pipeline.

Conceptually:

```text
Voice satellite
    ↓
STT
    ↓
ha-voice-normalizer
    ↓
normalized text
    ↓
configured downstream Conversation Agent
    ↓
response
    ↓
TTS
```

Example:

```text
Whisper:

"Fortell meg om stav Zulu Ekko Ekko Kilo Romeo"

↓ ha-voice-normalizer

"Fortell meg om zeekr"

↓ downstream agent

Ollama / Home Assistant / another Conversation Agent
```

The normalizer itself does not normally answer the request.

It acts as a transparent Conversation Agent proxy.

---

## Home Assistant integration architecture

Provide a Home Assistant custom component such as:

```text
custom_components/
└── voice_normalizer/
    ├── __init__.py
    ├── manifest.json
    ├── const.py
    ├── config_flow.py
    ├── conversation.py
    ├── diagnostics.py
    ├── strings.json
    └── translations/
```

The Home Assistant integration should import the standalone Python normalization core.

For example:

```python
from ha_voice_normalizer import normalize_text
```

Do not implement NATO parsing independently inside `conversation.py`.

---

# Conversation Agent behavior

The integration must implement the current supported Home Assistant `ConversationEntity` API.

Research the current Home Assistant developer documentation and current Home Assistant Core implementation before writing this layer.

Do not blindly copy old examples using deprecated or legacy APIs.

Conceptually:

```python
class VoiceNormalizerConversationEntity(ConversationEntity):

    async def _async_handle_message(
        self,
        user_input,
        chat_log,
    ):
        ...
```

The flow should be:

```text
receive ConversationInput
        ↓
extract text
        ↓
normalize locally
        ↓
create downstream request preserving context
        ↓
call configured Conversation Agent
        ↓
return downstream ConversationResult
```

---

# Preserve Conversation context

The proxy must preserve Home Assistant conversation semantics wherever possible.

When delegating to the downstream agent, preserve:

```text
language
conversation_id
Home Assistant Context
device/context information
conversation history where supported
```

Do not accidentally turn every voice request into a new independent conversation.

Multi-turn conversations such as:

```text
User:
"Fortell meg om Zeekr"

Assistant:
"..."

User:
"Hva koster den?"
```

should continue to work if the selected downstream Conversation Agent supports conversation history.

The normalizer must not become the owner of conversational state unless necessary.

It should primarily proxy it.

---

# Configurable downstream Conversation Agent

Standalone mode must allow the user to select which installed Home Assistant Conversation Agent receives the normalized request.

For example:

```text
Voice Normalizer
    ↓
Home Assistant
```

or:

```text
Voice Normalizer
    ↓
Ollama
```

or:

```text
Voice Normalizer
    ↓
Assist Canonicalizer
```

or:

```text
Voice Normalizer
    ↓
Closest Intent
```

or another compatible installed agent.

Do not hardcode agent names or integration domains.

Enumerate available Conversation Agents using supported Home Assistant APIs.

---

# Example standalone chains

The user should be able to configure:

```text
Assist pipeline
    ↓
Voice Normalizer
    ↓
Ollama
```

for the simplest setup.

It should also be possible to use:

```text
Assist pipeline
    ↓
Voice Normalizer
    ↓
Assist Canonicalizer
    ↓
Ollama
```

if Assist Canonicalizer itself supports downstream delegation.

Or:

```text
Assist pipeline
    ↓
Voice Normalizer
    ↓
Closest Intent
    ↓
Ollama
```

The normalizer must not need to know how these downstream agents work internally.

Its responsibility ends at:

```text
normalize input
+
delegate
```

---

# Avoid routing loops

Standalone mode introduces a potential configuration hazard.

For example:

```text
Voice Normalizer
    ↓
Voice Normalizer
```

must be rejected.

More subtle recursion should also be considered:

```text
Voice Normalizer A
    ↓
Agent B
    ↓
Voice Normalizer A
```

Direct self-selection must at minimum be prevented in the Config Flow.

If practical, add runtime recursion protection using request metadata, context, or another safe mechanism.

If a loop is detected:

* stop processing
* log a useful error
* return a safe Home Assistant Conversation response

Never recurse indefinitely.

---

# Fail-open normalization

Text normalization should normally fail open.

Example:

```text
input:
"slå på kjøkkenlyset"

Normalizer raises unexpected internal exception.

Expected behavior:
delegate original text to downstream agent
```

A spelling normalizer failure should not make basic Home Assistant voice control unavailable.

Conceptually:

```python
try:
    result = normalize_text(user_input.text)
    downstream_text = result.text
except Exception:
    log_exception()
    downstream_text = user_input.text
```

Do not swallow exceptions silently.

Log sufficient information for diagnosis without logging secrets.

---

# Downstream failure behavior

A downstream Conversation Agent may be:

* unavailable
* removed
* disabled
* misconfigured
* timing out
* throwing an exception

Handle these conditions gracefully.

The integration should not crash Home Assistant.

Return a useful Conversation response explaining that the downstream assistant is unavailable.

Do not invent an answer to the user's original question.

---

# Do not use an LLM for normalization

Even when the selected downstream agent is Ollama or a cloud LLM:

```text
Voice Normalizer
```

must perform spelling and deterministic normalization locally before delegation.

Example:

```text
"stav Zulu Ekko Ekko Kilo Romeo"

↓ local deterministic code

"zeekr"

↓ Ollama
```

Never:

```text
"Zulu Ekko Ekko Kilo Romeo"

↓ LLM

"probably Zeekr"
```

for the spelling operation itself.

---

# Home Assistant Config Flow

Standalone mode must be configurable from the Home Assistant UI.

At minimum ask for:

```text
Name:
Voice Normalizer

Downstream Conversation Agent:
[ selectable installed agent ]

Language:
Auto / Norwegian / English / ...

Spelling normalization:
On

Alias normalization:
On/Off

Known STT corrections:
On/Off
```

For the MVP, only downstream agent selection and spelling enable/disable are mandatory.

Do not require YAML for normal use.

---

# Options Flow

After setup, allow the user to change:

* downstream Conversation Agent
* enabled normalizers
* strict/lenient spelling behavior
* language settings
* debugging

without deleting and recreating the integration.

---

# Multiple instances

Allow multiple configured normalizers if Home Assistant's architecture permits it cleanly.

Example:

```text
Voice Normalizer — Norwegian
    language=nb
    downstream=Home Assistant

Voice Normalizer — Multilingual
    language=auto
    downstream=Polyglot Assist

Voice Normalizer — LLM
    language=nb
    downstream=Ollama
```

Each should have its own Conversation Entity and configuration.

Use stable unique IDs.

---

# Debugging

Standalone mode must make it easy to see what text was changed.

Example debug log:

```text
Voice Normalizer request

language:
nb-NO

original:
"Fortell om stav Zulu Ekko Ekko Kilo Romeo"

normalized:
"Fortell om zeekr"

operations:
- phonetic_spelling
  source="Zulu Ekko Ekko Kilo Romeo"
  result="zeekr"

downstream:
conversation.ollama

normalization_time:
0.31 ms

downstream_time:
842 ms
```

Avoid logging full request text by default if this creates unnecessary privacy exposure.

Provide an explicit debug option for verbose text logging.

---

# Diagnostics

Implement Home Assistant diagnostics if appropriate.

Diagnostics may include:

```text
integration version
enabled normalizers
language configuration
downstream agent ID/type
number of transformations
number of normalization failures
average normalization latency
```

Diagnostics must redact:

* API keys
* tokens
* passwords
* sensitive conversation contents

Do not include voice transcripts by default.

---

# Standalone test strategy

In addition to pure Python tests, test the Home Assistant proxy behavior.

Important cases:

## No transformation

```text
input:
"slå på lyset"

normalized:
"slå på lyset"

downstream receives:
"slå på lyset"
```

## Spelling transformation

```text
input:
"fortell om stav Zulu Ekko Ekko Kilo Romeo"

downstream receives:
"fortell om zeekr"
```

## Context preservation

Verify:

```text
language
conversation_id
HA Context
```

are correctly forwarded.

## Downstream response

Verify that the response from the downstream agent is returned unchanged where appropriate.

## Normalizer exception

Verify original text is forwarded.

## Downstream exception

Verify a safe Home Assistant error response is produced.

## Self-routing

Verify selecting the same Voice Normalizer instance as downstream is prevented.

## Multiple instances

Verify two normalizer entities with different downstream agents can coexist.

---

# HACS installation

Standalone Home Assistant mode should be distributable through HACS.

Repository layout should therefore support both:

```text
Python core
+
Home Assistant custom integration
```

Choose either:

### Monorepo

```text
ha-voice-normalizer/
├── src/
│   └── ha_voice_normalizer/
├── custom_components/
│   └── voice_normalizer/
├── tests/
├── hacs.json
└── pyproject.toml
```

or another layout that works cleanly with Home Assistant/HACS packaging.

Explain any packaging constraints before implementation.

Prefer one repository unless there is a strong technical reason to split the library and Home Assistant integration into separate repositories.

---

# Important separation of responsibilities

The standalone normalizer is not intended to become a full router.

Its responsibility should remain:

```text
INPUT
  ↓
NORMALIZE
  ↓
DELEGATE TO ONE AGENT
```

Not:

```text
INPUT
  ↓
decide between Home Assistant/Ollama/cloud/search/etc.
```

That responsibility belongs to `ha-voice-router`.

This separation is intentional.

Therefore:

## `ha-voice-normalizer`

owns:

```text
spelling
aliases
STT correction
text normalization
transparent delegation
```

## `ha-voice-router`

owns:

```text
multiple handlers
confidence-based routing
fallback policies
local/cloud routing
LLM selection
internet-search gating
```

---

# Compatibility with future `ha-voice-router`

The public normalization API must be usable directly without going through the Home Assistant proxy.

Future integration should look approximately like:

```python
from ha_voice_normalizer import NormalizationPipeline

normalizer = NormalizationPipeline(...)

result = normalizer.normalize(context.text)

context.text = result.text
```

The router should not need to instantiate the standalone Home Assistant Conversation Agent just to use the normalizer.

Think of:

```text
ha-voice-normalizer core
```

as the reusable library.

The Home Assistant Conversation Agent is merely one adapter:

```text
                     ┌─ Python API
                     │
Normalization Core ──┼─ HA standalone adapter
                     │
                     └─ ha-voice-router adapter
```

This separation should be enforced in the code structure.

---

# Standalone MVP

The first Home Assistant standalone milestone should support exactly this:

```text
Home Assistant Voice
        ↓
Whisper
        ↓
Voice Normalizer
        ↓
"stav Zulu Ekko Ekko Kilo Romeo"
        ↓
"zeekr"
        ↓
configured Conversation Agent
        ↓
response
```

MVP requirements:

1. `ConversationEntity`
2. Config Flow
3. downstream agent selector
4. spelling normalizer
5. transparent delegation
6. conversation/context preservation
7. self-loop prevention
8. fail-open normalization
9. useful debug logging
10. tests

Do not add sophisticated routing to this project.

Once this works reliably, it should be usable as a complete standalone Home Assistant integration even if `ha-voice-router` is never installed.
