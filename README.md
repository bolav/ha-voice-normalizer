# HA Voice Normalizer

A Home Assistant conversation agent that spells out difficult words — names,
loanwords, and anything a TTS voice mangles — so spoken replies stay
understandable.

Status: scaffolding only. The integration itself lives under
`custom_components/` once it is written.

## Development

The Python toolchain is pinned by `pyproject.toml` + `uv.lock`
(Python 3.14, Home Assistant 2026.8.x, pytest + `pytest-homeassistant-custom-component`, ruff):

```sh
uv sync --all-groups
uv run pytest
uv run ruff check .
```
