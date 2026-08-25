# HA Voice Normalizer

Deterministic clean-up of speech-to-text output, before Home Assistant or an
LLM ever sees it.

The first and main feature is **phonetic spelling**: when you dictate a name
using the NATO alphabet, the words are turned back into the name.

```text
"stav Zulu Ekko Ekko Kilo Romeo"   ->  "zeekr"
"Fortell om stav Zulu Ekko Ekko Kilo Romeo"  ->  "Fortell om zeekr"
```

No LLM, no network, no vector database. Plain string handling, typically far
under a millisecond.

## The problem

Speech-to-text is good at ordinary sentences and bad at names. Ask Whisper for
a Chinese car brand in a Norwegian sentence and you get "Sikker", "Sekker" or
"Ziika" — never "Zeekr". Humans solve this by spelling the word out, and a
voice assistant should understand that the same way a human does:

```text
Voice satellite -> Whisper -> "Fortell meg om stav Zulu Ekko Ekko Kilo Romeo"
                            -> Voice Normalizer
                            -> "Fortell meg om zeekr"
                            -> your conversation agent (Home Assistant, Ollama, …)
```

Spelling is decoded by deterministic code, never by an LLM. An LLM guessing
"probably Zeekr" is exactly what this project exists to avoid.

## Three ways to use it

| Mode | What it is |
| --- | --- |
| Python library | `from ha_voice_normalizer import normalize_text` — no Home Assistant needed |
| Home Assistant integration | A conversation agent that normalizes and delegates to another agent |
| Inside `ha-voice-router` | The same library, imported by the router (future) |

The normalization core lives in
`custom_components/voice_normalizer/ha_voice_normalizer/` and knows nothing
about Home Assistant. The integration in `custom_components/voice_normalizer/`
is one adapter on top of it and contains no spelling logic of its own.

```text
                     ┌─ Python API
                     │
Normalization core ──┼─ Home Assistant conversation agent (this repo)
                     │
                     └─ ha-voice-router adapter (future)
```

## Python usage

```python
from ha_voice_normalizer import normalize_text

result = normalize_text("stav Zulu Ekko Ekko Kilo Romeo", language="nb")

result.text        # "zeekr"
result.changed     # True
result.operations  # [NormalizationOperation(type="phonetic_spelling", …)]
```

For repeated use, build the pipeline once:

```python
from ha_voice_normalizer import NormalizationPipeline

normalizer = NormalizationPipeline.create(language="nb", aliases={"zeekr": "Zeekr"})
result = normalizer.normalize(text)
```

There is also a CLI:

```sh
python -m ha_voice_normalizer --language nb "stav Zulu Ekko Ekko Kilo Romeo"
python -m ha_voice_normalizer --language nb --json "stav Alfa Bravo"
```

## How spelling is decoded

### Explicit triggers only

A sequence of NATO words is never decoded on its own, because most code words
are ordinary words — "Hotel India", "Golf", "November", "Oscar". Decoding only
starts after a trigger word:

| Language | Trigger | Behaviour |
| --- | --- | --- |
| Norwegian | `stav`, `bokstaver` | Imperative: the trigger is removed |
| Norwegian | `staves`, `stavet` | Part of the sentence: the trigger is kept |
| English | `spell` | Imperative: the trigger is removed |
| English | `spelled`, `spelt` | Part of the sentence: the trigger is kept |

```text
"stav Zulu Ekko Ekko Kilo Romeo"                 -> "zeekr"
"det staves Zulu Ekko Ekko Kilo Romeo"           -> "det staves zeekr"
"bilen heter, stav, Zulu Ekko Ekko Kilo Romeo"   -> "bilen heter zeekr"
```

Text outside the decoded span is copied through byte for byte: casing,
Norwegian letters, and spacing are all preserved.

### Norwegian STT variants

Every accepted spoken form is listed in `LETTER_VARIANTS` in
[`spelling.py`](custom_components/voice_normalizer/ha_voice_normalizer/spelling.py), with the official NATO
word first:

```text
a  alfa, alpha            h  hotel, hotell         v  victor, viktor
e  echo, ekko, eko        o  oscar, oskar          w  whiskey, whisky
j  juliett, juliet        x  x-ray, xray, "x ray"
```

Variants are added when they are actually observed — each one has a test.
Guessing at what a transcriber might emit is how false positives get in.

### Æ, Ø and Å

NATO stops at Z, so the Norwegian letters use the Norwegian Armed Forces
extension as the canonical code word, and accept the civilian spelling alphabet
as an alternate — a speaker reaches for whichever one they know:

```text
æ  ægir, ærlig
ø  ørnulf, østen
å  ågot, åse
```

```text
"stav Ågot Lima Ekko Sierra Uniform November Delta"  ->  "ålesund"
"Fortell om stav Bravo Lima Ågot Bravo Ærlig Romeo"  ->  "Fortell om blåbær"
```

They sort after `z` in `LETTER_VARIANTS`, which is where they sit in the
Norwegian alphabet. Lookup keys are casefolded *and* NFC-normalized, so a
transcriber that emits a decomposed "a + combining ring" matches the composed
"å" in the table. Only the lookup key is normalized — the text outside a
decoded span still comes through exactly as it arrived.

### False-positive policy

Predictable behaviour beats clever parsing for something that sits in front of
smart-home commands. The default mode is **strict**:

- Without a trigger word, nothing is ever decoded.
- After a trigger, code words are read until an unknown word appears.
- The span is only rewritten if it ends cleanly — at the end of the text, at
  sentence punctuation, or right before another trigger (this is what makes
  multi-segment dictation work).
- Anything else is left completely alone.

```text
"Hotel India Golf"            -> unchanged (no trigger)
"stav Zulu Ekko banan Romeo"  -> unchanged (strict: "banan" is not a letter)
"stav Hotel India kanskje"    -> unchanged (strict: trailing ordinary word)

"brukernavn stav Alfa Bravo Charlie og kode stav X-ray Yankee Zulu"
    -> "brukernavn abc og kode xyz"
```

`partial` mode rewrites what it understood and leaves the rest:
`"stav Zulu Ekko banan Romeo"` becomes `"ze banan Romeo"`. It is opt-in.

### Layers

```text
input -> SpellingNormalizer -> AliasNormalizer -> SttCorrectionNormalizer -> output
```

The spelling engine knows **letters, not brands**. Mapping `zeekr` to `Zeekr`
is a separate, user-configured layer, as is fixing phrases a transcriber
reliably gets wrong. Each layer can be enabled and tested on its own, and the
order is yours to choose when you build a pipeline by hand.

## Home Assistant integration

Voice Normalizer registers a conversation agent that you select in your Assist
pipeline. It normalizes the text and hands it to the conversation agent you
configured; it never answers by itself.

```text
Assist pipeline -> Voice Normalizer -> Ollama
Assist pipeline -> Voice Normalizer -> Home Assistant
Assist pipeline -> Voice Normalizer -> any other installed conversation agent
```

Behaviour worth knowing:

- **Transparent delegation.** Language, conversation id, Home Assistant
  context, device id, satellite id and extra system prompt are all forwarded,
  and the downstream response is returned untouched. Multi-turn conversations
  keep working, because the normalizer owns no conversation state: it does not
  open a chat log of its own, so the downstream agent stays the sole owner of
  the history.
- **Fail-open normalization.** If normalization raises, the original text is
  forwarded and the error is logged. A spelling bug must never stop
  "slå på lyset" from working.
- **Downstream failures.** A missing, unloaded or throwing agent produces a
  spoken error ("the conversation agent … is not available"), in Norwegian or
  English. It never invents an answer.
- **Loop protection.** Selecting the normalizer itself is rejected in the
  options flow, and blocked again at runtime. Indirect loops (A → B → A) are
  caught by request-scoped state and stopped with a logged error.
- **Multiple instances.** Add as many normalizers as you like, each with its
  own entity, language and downstream agent.

### Setup

The component carries the core library inside it, so there is nothing to
install and nothing to fetch: `manifest.json` declares no requirements.

**HACS.** ⋮ → *Custom repositories* → this repository, type **Integration** →
Download. HACS resolves a repository to its latest GitHub *release*; with no
release published it falls back to the head commit and then asks GitHub for it
as a branch, which 404s. Publish a release before installing this way.

**Without HACS**, from the *Terminal & SSH* add-on or its sidebar web terminal:

```sh
git clone https://github.com/bolav/ha-voice-normalizer /config/ha-voice-normalizer

mkdir -p /config/custom_components
ln -s /config/ha-voice-normalizer/custom_components/voice_normalizer \
      /config/custom_components/voice_normalizer
```

The symlink points into the clone, so `git pull` plus a restart is the update.

Either way:

1. Restart Home Assistant.
2. *Settings → Devices & Services → Add integration → Voice Normalizer*.
3. Pick the downstream conversation agent, then select Voice Normalizer as the
   conversation agent of your Assist pipeline.

Everything is configurable from the UI, before and after setup: downstream
agent, spelling on/off, strict/partial, language, alias table, correction
table, and debug logging. No YAML.

### Debugging

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.voice_normalizer: debug
```

By default the log shows what happened without the transcript:

```text
Normalizer request (language=nb, 0.036 ms, downstream=conversation.ollama):
41 characters, changed=True, operations=['phonetic_spelling']
Downstream agent conversation.ollama answered in 842.0 ms
```

Turn on *Log request text* in the options to include the original text, the
normalized text and every operation. It is off by default because voice
transcripts can contain anything, including a password someone just spelled
out.

Diagnostics (*⋮ → Download diagnostics* on the config entry) report the
integration version, enabled normalizers, downstream agent and its
availability, request counters and average normalization time. Alias and
correction tables are redacted, and transcripts are never included.

## Packaging

The repository holds both halves, with the core nested inside the integration:

```text
custom_components/voice_normalizer/                     the integration (HACS)
custom_components/voice_normalizer/ha_voice_normalizer/ the core (published to PyPI)
```

HACS copies only `custom_components/voice_normalizer/`, and nothing else. With
the core nested inside it, that one copy carries the library too: `manifest.json`
declares no requirements, so a HACS install needs no PyPI package, no pip, no
build backend and no network at boot.

There is still exactly one copy of the core. `[tool.hatch.build.targets.wheel]`
points at the nested directory, so the wheel published to PyPI exposes it as a
top-level `ha_voice_normalizer` exactly as before, and `ha-voice-router` can
depend on it normally. Only the path inside this repository changed.

The cost is that the core's own tests import it by its in-repo path
(`custom_components.voice_normalizer.ha_voice_normalizer`), and running the CLI
from a checkout needs that path too:

```sh
python -m custom_components.voice_normalizer.ha_voice_normalizer --language nb "stav Alfa Bravo"
```

Installed from PyPI, it is plain `python -m ha_voice_normalizer`.

## Development

```sh
uv sync --all-groups
uv run pytest
uv run ruff check .
```

Tests import the core by its in-repo path, and the Home Assistant tests under `tests/integration/` run
against a real Home Assistant instance with a mock downstream agent.

The test suite covers the normalization core at 100%: basic decoding, casing,
Norwegian variants, punctuation, inline and multi-segment spans, strict versus
partial policy, and a long list of sentences that must never change. On the
Home Assistant side it covers delegation, context preservation, fail-open
normalization, downstream failures, loop prevention, multiple instances,
config/options flow and diagnostics.

Planned behaviour that does not exist yet lives in `tests/test_future_features.py`
as strict xfails, so the roadmap cannot quietly drift away from the tests.

## Roadmap

- **v0.1** — NATO spelling with explicit triggers, strict policy ✅
- **v0.2** — Norwegian variants, punctuation handling ✅
- **v0.3** — inline spelling spans ✅
- **v0.4** — multiple spans in one sentence ✅
- **v0.5** — alias and known-STT-correction layers ✅
- **v0.6** — spoken digits and symbols (`null` → `0`, `krøllalfa` → `@`)
- **v0.7** — integration with `ha-voice-router`

Scope is deliberately narrow. Voice Normalizer normalizes text and delegates to
exactly one agent. Choosing *between* agents, confidence-based routing and
fallback policies belong to `ha-voice-router`.

## License

MIT — see [LICENSE](LICENSE).
