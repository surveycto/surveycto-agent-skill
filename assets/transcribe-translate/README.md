# Translate and transcribe user data (OpenAI)

Runtime modules the agent runs to translate exported response data and transcribe
audio captures, using a single OpenAI API key, while keeping the user's data and
key out of the conversation.

Read the reference primers for the agent-facing workflow:
- [`references/openai-credentials.md`](../../references/openai-credentials.md) the
  API-key handling and the never-reveal-the-key mandate (shared).
- [`references/user-data-translation.md`](../../references/user-data-translation.md)
  translating response/comment columns in a CSV.
- [`references/audio-transcription.md`](../../references/audio-transcription.md)
  transcribing audio captures.

## Files

| File | Purpose | Import-time deps |
| --- | --- | --- |
| `openai_auth.py` | Resolve the OpenAI key (env or chmod-600 config), set `OPENAI_API_KEY`, never print it. | standard library only |
| `translation.py` | estimate_cost, translate_csv (selectable chat model, length-validated structured output, dedup, cache, skip-list, glossary). | standard library only |
| `transcription.py` | estimate_cost, transcribe_files (selectable model, automatic chunking, cache). | standard library only |
| `setup_env.py` | One-time bootstrap: create the isolated venv and install `openai`. | standard library only |
| `usage_ledger.py` | Record actual OpenAI spend per run and a cumulative total at `~/.surveycto-skill/spend-ledger.json`; `show`/`reset` CLI. | standard library only |
| `pricing.py` / `pricing.json` | The OpenAI rate table (per-token / per-minute), kept as dated data not code. `show` prints rates + how current they are; `set-transcription`/`set-translation` refresh a rate. | standard library only |

`openai` is imported lazily, only when a call reaches the API, so the modules
import and their logic is unit-testable offline.

Both workflows report `actual_usd_display` (this run) and
`total_spend_usd_display` (cumulative) so the user is always told what they spent;
see `python3 assets/transcribe-translate/usage_ledger.py show`.

Install with the shipped bootstrap (run once):

```
python3 assets/transcribe-translate/setup_env.py            # translation + transcription
```

It creates an isolated environment at `~/.surveycto-skill/venv`, installs the
dependencies there, and prints the interpreter path on the last line as
`VENV_PYTHON=<path>`. Run every module with that interpreter (e.g.
`<path> assets/transcribe-translate/translation.py ...`). This avoids the PEP 668
`externally-managed-environment` error that a bare `pip install openai` hits on
modern macOS (Homebrew) and recent Debian/Ubuntu. The script is idempotent.

ffmpeg is also required for transcription (to measure audio duration and split
long files). Install it with `brew install ffmpeg` (macOS),
`sudo apt-get install ffmpeg` (Debian/Ubuntu), or from https://ffmpeg.org
(Windows). Without it, long audio cannot be chunked.

## Model selection (cheapest is the default)

- Translation: `--model cheap` (gpt-4.1-nano, default) or `better` (gpt-4o-mini), or a model id.
- Transcription: `--model fast` (gpt-4o-mini-transcribe, default), `accurate` (gpt-4o-transcribe), or `whisper` (whisper-1).

## Pricing (dated data, optionally refreshed in-flight)

OpenAI has no pricing API, so the rates that turn usage into dollars live in
`pricing.json` with the date they were last verified. `estimate` and `transcribe`/
`translate` report `rates_as_of` and `rates_source` so the user always knows how
current the figures are. At the start of a run the agent should offer to check
current prices online (so the estimate is accurate); if the user declines, the
stored rates are used. Refresh after reading the pricing page:

```bash
"$PY" assets/transcribe-translate/pricing.py show
"$PY" assets/transcribe-translate/pricing.py set-transcription gpt-4o-transcribe \
    --in-per-mtok 2.50 --out-per-mtok 10.00 --est-per-min 0.006 --as-of 2026-06-14
```

Estimates are approximate (transcription uses a per-minute figure); the actual
spend reported after a run is computed from the response's real usage: token
counts for the gpt-4o-* models, audio duration for whisper-1.

## Quick use (CLI)

Each module is a subcommand CLI that handles credentials itself: `translation.py`
has `estimate` and `translate`; `transcription.py` has `estimate` and `transcribe`.
Run it with the interpreter `setup_env.py` printed (`VENV_PYTHON=<path>`), shown
as `PY` below; plain `python3` will not have `openai` installed.

```bash
PY=<the VENV_PYTHON path from setup_env.py>
# translate (estimate first; --confirm only after showing cost + PII; omit --source to auto-detect)
"$PY" assets/transcribe-translate/translation.py estimate data.csv --columns notes --target en
"$PY" assets/transcribe-translate/translation.py translate data.csv --columns notes --target en \
    --output data_en.csv --cache translation-cache.db --confirm

# transcribe (needs ffmpeg on PATH)
"$PY" assets/transcribe-translate/transcription.py estimate a.mp3
"$PY" assets/transcribe-translate/transcription.py transcribe a.mp3 --output out.csv \
    --cache transcription-cache.db --confirm
```

Run `"$PY" assets/transcribe-translate/translation.py --help` or `"$PY" assets/transcribe-translate/transcription.py --help` for all flags
and examples. The same functions are importable if you prefer a script, but this
directory's name has a hyphen so it is not a package — add it to `sys.path` first:
`import sys; sys.path.insert(0, "assets/transcribe-translate"); import translation`
(then `openai_auth.configure_openai()`).

## The key rule, in code

`openai_auth` never prints the API key; `credentials_status()` returns only a
masked form, and errors carry no key material. The `confirm=True` cost gate
ensures no paid call runs without an explicit, cost-aware go-ahead.

## Tests

Offline tests (standard library only, no network, no OpenAI package) live in the
repo `tests/` directory. Run them from the repository root (not from this asset
folder), with plain `python3` (no venv needed, they use injected fakes):

```
python3 tests/test_openai_auth.py
python3 tests/test_translation.py
python3 tests/test_transcription.py
python3 tests/test_setup_env.py
python3 tests/test_usage_ledger.py
python3 tests/test_pricing.py
```

They use injected fake clients, so they exercise the surrounding logic
(credential masking, length-validated structured output, skip-list, cost math,
caching, dedup, glossary, chunk planning, per-file failure isolation) without
reaching OpenAI.
