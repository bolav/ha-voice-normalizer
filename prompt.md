# LLM-prompt: Build `ha-voice-normalizer`

You are a senior Python developer with experience in speech recognition, text normalization, Home Assistant Assist, Norwegian language processing, and deterministic NLP.

Create an open-source project called:

`ha-voice-normalizer`

Its initial purpose is to normalize speech-to-text output before Home Assistant or an LLM processes it.

The first feature is phonetic spelling support.

Example:

```text
STT input:
"Zulu Ekko Ekko Kilo Romeo"

normalized:
"zeekr"
```

The system must be local, deterministic, fast, testable, and independent of any LLM.

## Scope

The project should eventually support multiple types of normalization:

```text
phonetic spelling
entity aliases
known STT corrections
capitalization/canonical names
Norwegian-specific transcription quirks
```

But implement phonetic spelling first.

Keep the normalization engine separate from Home Assistant-specific glue so it can later be:

* used by `ha-voice-router`
* packaged as a Python library
* embedded in another Home Assistant integration
* unit-tested without Home Assistant

## Core API

Start with a simple pure-Python API such as:

```python
normalize_text(text: str, language: str | None = None) -> NormalizationResult
```

or:

```python
normalize_spelling(text: str) -> str
```

Prefer returning metadata as the project develops:

```python
@dataclass
class NormalizationResult:
    original_text: str
    text: str
    changed: bool
    operations: list[NormalizationOperation]
```

Example:

```python
NormalizationResult(
    original_text="stav Zulu Ekko Ekko Kilo Romeo",
    text="zeekr",
    changed=True,
    operations=[
        ...
    ],
)
```

## Initial spelling feature

Support the NATO phonetic alphabet.

At minimum:

```text
Alfa / Alpha → A
Bravo → B
Charlie → C
Delta → D
Echo / Ekko → E
Foxtrot → F
Golf → G
Hotel → H
India → I
Juliett / Juliet → J
Kilo → K
Lima → L
Mike → M
November → N
Oscar → O
Papa → P
Quebec → Q
Romeo → R
Sierra → S
Tango → T
Uniform → U
Victor → V
Whiskey → W
X-ray → X
Yankee → Y
Zulu → Z
```

Take care with official NATO spellings versus common variants.

Do not make the parser dependent on exact capitalization.

## Norwegian STT variants

The practical input comes from Norwegian speech recognition.

Whisper may produce variants such as:

```text
Echo
Ekko
Eko

X-ray
Xray
X ray

Alpha
Alfa
```

Design aliases so multiple STT renderings can map to the same letter.

Do not overfit speculative Whisper errors without tests.

Create a clear data structure where observed variants can later be added.

For example:

```python
PHONETIC_ALIASES = {
    "a": {"alfa", "alpha"},
    "e": {"echo", "ekko", "eko"},
}
```

or a more suitable structure.

## Activation modes

Avoid automatically turning every sequence of NATO words into letters.

Words such as:

```text
Hotel
India
Golf
November
Oscar
```

are ordinary words and can easily create false positives.

Implement explicit spelling mode first.

Examples of phrases that should be considered:

```text
"stav Zulu Ekko Ekko Kilo Romeo"
→ "zeekr"

"det staves Zulu Ekko Ekko Kilo Romeo"
→ "det staves zeekr"

"bilen heter, stav, Zulu Ekko Ekko Kilo Romeo"
→ "bilen heter zeekr"
```

Design the parser so trigger words are configurable by language.

For Norwegian initial triggers consider:

```text
stav
staves
stavet
bokstaver
```

Do not assume all of these should behave identically without defining semantics and tests.

## Inline spelling

After explicit spelling mode works, support inline replacement.

Example:

```text
"Fortell meg om bilen som staves Zulu Ekko Ekko Kilo Romeo"
```

should become something like:

```text
"Fortell meg om bilen som staves zeekr"
```

or, if configured:

```text
"Fortell meg om bilen zeekr"
```

Prefer conservative transformation that preserves sentence meaning.

Do not remove surrounding words unless there is a clearly defined grammar for doing so.

## Multiple spelled segments

Design for eventual support of:

```text
"brukernavn stav Alfa Bravo Charlie og kode stav X-ray Yankee Zulu"
```

Result:

```text
"brukernavn abc og kode xyz"
```

The parser should not be based on one greedy regex that prevents multiple spans.

## Digits and symbols

Do not necessarily implement this in V0.1, but design for future support such as:

```text
null → 0
en → 1
to → 2
bindestrek → -
punktum → .
krøllalfa → @
```

Potential use cases:

```text
Wi-Fi passwords
device identifiers
registration numbers
email addresses
serial numbers
usernames
```

Keep symbols separate from NATO alphabet semantics.

## Canonical-name layer

Keep spelling decoding separate from name canonicalization.

For example:

```text
Zulu Ekko Ekko Kilo Romeo
↓ spelling
zeekr
↓ alias/canonicalization
Zeekr
```

Do NOT encode:

```python
"zulu ekko ekko kilo romeo": "Zeekr"
```

in the spelling engine.

The spelling engine should know letters, not brands.

Later, an alias module might contain:

```text
zeekr → Zeekr
hass → Home Assistant
```

These must be separate processors.

## Pipeline architecture

Design a small pipeline:

```text
input
 ↓
SpellingNormalizer
 ↓
AliasNormalizer
 ↓
STTCorrectionNormalizer
 ↓
output
```

Each normalizer should be independently enabled and testable.

Something like:

```python
class Normalizer(Protocol):
    def normalize(
        self,
        result: NormalizationResult
    ) -> NormalizationResult:
        ...
```

is acceptable if useful, but avoid unnecessary framework complexity in V0.1.

## No LLM

This is a strict requirement for the spelling path.

Do not use:

* Ollama
* OpenAI
* embeddings
* vector databases
* semantic search

to decode phonetic spelling.

The operation should be deterministic and typically complete in far less than one millisecond for ordinary voice queries.

## Fail-safe behavior

If the parser is uncertain, prefer leaving the text unchanged.

Example:

```text
"Hotel India var veldig fint"
```

must not silently become:

```text
"hi var veldig fint"
```

because no spelling trigger was present.

Likewise:

```text
"stav Hotel India kanskje"
```

should have clearly defined behavior when a token after the spelling trigger is not recognized.

Consider policies such as:

```text
strict:
convert only when entire span is valid

partial:
convert recognized tokens until an invalid token occurs
```

Default to conservative/strict behavior.

## Unicode and tokenization

Handle:

* Norwegian letters
* punctuation
* commas
* repeated whitespace
* hyphenated terms
* case-insensitive matching

Do not globally lowercase the user's sentence merely to simplify parsing.

Preserve original text outside normalized spans.

## Debug metadata

When transformation happens, optionally expose data such as:

```json
{
  "type": "phonetic_spelling",
  "source": "Zulu Ekko Ekko Kilo Romeo",
  "result": "zeekr",
  "start": 15,
  "end": 43
}
```

This will be useful when integrated with `ha-voice-router`.

## Testing

Tests are a major part of the project.

Create comprehensive tests including:

### Basic

```text
stav Alfa → a
stav Zulu → z
stav Zulu Ekko Ekko Kilo Romeo → zeekr
```

### Case

```text
stav ZULU EKKO → ze
stav zulu ekko → ze
```

### Norwegian variants

```text
stav Zulu Echo Echo Kilo Romeo → zeekr
stav Zulu Eko Eko Kilo Romeo → zeekr
```

only if those aliases are explicitly supported.

### False positives

These must remain unchanged:

```text
Hotel India Golf
November Oscar
Jeg bor på Hotel India
Golf er gøy
```

### Punctuation

Test:

```text
stav: Zulu, Ekko, Ekko, Kilo, Romeo
```

### Invalid tokens

Test conservative handling of:

```text
stav Zulu Ekko banan Romeo
```

### Inline

Test embedded spelling inside longer Norwegian sentences.

### Multiple segments

Add tests even if the first MVP does not implement the feature yet; mark future tests appropriately rather than creating misleading passing tests.

## Project structure

Use a clean layout such as:

```text
ha-voice-normalizer/
├── src/
│   └── ha_voice_normalizer/
│       ├── __init__.py
│       ├── models.py
│       ├── pipeline.py
│       ├── spelling.py
│       ├── aliases.py
│       └── corrections.py
├── tests/
│   ├── test_spelling.py
│   ├── test_false_positives.py
│   └── test_pipeline.py
├── pyproject.toml
├── README.md
└── LICENSE
```

If embedding directly as a Home Assistant custom component makes packaging substantially easier, explain the trade-off.

My preference is that the core normalizer remains a standalone Python package.

## Home Assistant integration

Do not make Home Assistant integration the first milestone.

First make this work:

```python
from ha_voice_normalizer import normalize_text

result = normalize_text(
    "stav Zulu Ekko Ekko Kilo Romeo",
    language="nb"
)

assert result.text == "zeekr"
```

After the library is solid, propose one or both integration paths:

### Option A

Used internally by `ha-voice-router`.

```text
HA Voice
↓
ha-voice-router
↓
ha-voice-normalizer
↓
handlers
```

### Option B

Standalone Home Assistant Conversation proxy integration.

```text
HA Voice
↓
ha-voice-normalizer
↓
configured downstream Conversation Agent
```

Explain the advantages and disadvantages.

## README

Document:

* the problem being solved
* why phonetic spelling is useful with STT
* examples
* Norwegian/NATO behavior
* false-positive policy
* Python usage
* Home Assistant architecture
* future roadmap

Include examples such as:

```text
Zulu Ekko Ekko Kilo Romeo → zeekr
```

## Development milestones

Implement in this order:

### V0.1

Pure Python NATO spelling parser with explicit trigger.

### V0.2

Norwegian aliases and robust punctuation handling.

### V0.3

Inline spelling spans.

### V0.4

Multiple spans.

### V0.5

Alias and known-STT-correction pipeline.

### V0.6

Integration with `ha-voice-router`.

Do not jump ahead to complex integrations before V0.1 is well tested.

## Quality requirements

Use:

* Python type hints
* dataclasses where useful
* pytest
* clear error handling
* minimal dependencies
* deterministic behavior
* documented public API

Aim for very high test coverage for the normalization core.

The code should be boring, explicit, and easy to audit.

This component sits in front of smart-home commands, so predictable behavior is more important than clever NLP.

Before implementing, first propose:

1. grammar
2. tokenization strategy
3. data model
4. false-positive policy
5. test matrix
6. package architecture

Then implement the smallest useful V0.1.
