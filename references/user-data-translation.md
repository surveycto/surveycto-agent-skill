<!-- PRIMER: user-data-translation
  STATUS: drafted 2026-06-13 -->

# Translating user data (responses, comments, transcriptions)

This primer covers translating columns of collected user data in exported CSV
files (open-ended responses, enumerator notes, supervisor comments, audio
transcriptions) into a common working language, using OpenAI.

This is a different workflow from form-label translation. Read
[`translation.md`](translation.md) for form labels; read this for user data:

| | Form labels ([`translation.md`](translation.md)) | User data (this primer) |
| --- | --- | --- |
| Volume | Low (50-500 labels) | Can be very large |
| Sensitivity | Non-sensitive | Often sensitive; may contain PII |
| In conversation? | Yes, the agent translates directly | No, sent to an API by a script |
| Backing service | The agent's own ability | OpenAI |
| Credentials | None | An OpenAI API key ([`openai-credentials.md`](openai-credentials.md)) |

Read [`openai-credentials.md`](openai-credentials.md) first: it covers how to
authenticate without exposing the user's key, and how to coach a user who has
not set one up.

## Why this runs as a script, not in conversation

User data is too sensitive to pass through the agent's context or the
conversation logs, and there can be far too much of it to fit anyway. So the
agent runs the shipped module
[`assets/transcribe-translate/translation.py`](../assets/transcribe-translate/translation.py),
which reads the CSV, sends the text to OpenAI, and writes the translated CSV to
disk. The agent orchestrates and reports; it does not read the cells.

## Model selection (cheapest is the default)

Translation uses an OpenAI chat model. The user can pick:

- `cheap` -> `gpt-4.1-nano` (DEFAULT; lowest cost, strong multilingual quality)
- `better` -> `gpt-4o-mini` (slightly higher cost; use for nuanced/high-stakes text)

Pass `--model cheap|better` (or an explicit model id). Default to `cheap` and
only suggest `better` if the user reports quality concerns on nuanced text.

### On-device provider (NLLB, EXPERIMENT)

`--provider local` translates on-device with NLLB-200 (distilled-600M) instead of
OpenAI: no API key, no cost, and the cell text never leaves the machine, for
data-residency or offline use. Install the dependencies once with
`python3 setup_env.py --local-translate` (pip-only: transformers, torch,
sentencepiece, langdetect; cross-platform, no separate runtime). The source
language is auto-detected per cell; the target must be a language NLLB supports
(common survey languages are mapped). Quality is good on straightforward survey
text and close to the cloud models, but weaker on idiomatic or code-switched
text, so recommend a fluent-speaker spot-check for high-stakes use. Run
`python3 system_check.py` to confirm the machine has enough RAM (~3 GB). This is
experimental; the cloud provider remains the default and the most accurate.

## What the module gives you

- `estimate_cost(csv_path, columns, target_language, model=None)` counts billable
  characters/cells and returns an approximate USD cost (token-based; de-dup makes
  the real cost lower) plus the PII warning.
- `translate_csv(csv_path, columns, target_language, source_language, output_path,
  model=None, glossary_path=None, cache_path=None, confirm=False)` is the workhorse.
- `apply_glossary(text, glossary)` enforces preferred terminology.

Built in:
- **Cost gate.** `translate_csv` refuses to run unless `confirm=True`. Always call
  `estimate_cost` and confirm with the user first.
- **Length-validated output.** Each batch is sent with a strict instruction to
  return exactly one translation per input as a JSON array; the length is checked
  and retried, so the model cannot silently drop or merge cells.
- **Caching.** With a `cache_path`, raw translations are memoized (keyed on
  source/target language, model, and a hash of the source text). Re-translating a
  refreshed export only pays for changed cells.
- **De-duplication.** Identical source strings are translated once per run.
- **Skip-list.** Empty cells, pure numbers, single letters, and survey codes
  (`N/A`, `999`, `-99`, ...) are never sent.
- **Preserve originals.** A `<column>_<target_language>` column is added next to
  each source column; it never overwrites, and refuses to run if that column
  already exists.

## Workflow

1. **Confirm credentials and environment.** If a "no OpenAI API key configured"
   error appears, switch to the coaching in
   [`openai-credentials.md`](openai-credentials.md). Make sure the client library
   is installed by running the bootstrap once (`python3 setup_env.py`); it prints
   a `VENV_PYTHON=<path>` line. Run the module with that interpreter. Do not rely
   on a bare `pip install openai`, which fails with
   `externally-managed-environment` (PEP 668) on modern macOS and Debian/Ubuntu.
2. **Identify the columns** to translate (read only the header; you do not need to
   read the data). Ask the user if unsure.
3. **Get the target language** as an ISO 639-1 code (`en`, `es`, `fr`, `sw`, ...).
4. **Estimate cost and show the PII warning.** Call `estimate_cost(...)`. Show the
   cell count, the approximate USD cost, and the one-line privacy reminder that the
   text is sent to OpenAI. Keep the privacy reminder on every run.
5. **Wait for explicit confirmation.** Never translate without showing the cost
   first, even if the user said "just do it" up front.
6. **Translate.** Call `translate_csv(...)` with `confirm=True` and a `cache_path`
   so re-runs are cheap. Pass `source_language=None` to let the model auto-detect
   per cell (handles mixed-language columns).
7. **Report, including spend.** Give the output path and the returned stats
   (translated, cached, skipped, chars sent). Always tell the user what this run
   actually cost and the running total: report `actual_usd_display` ("this run")
   and `total_spend_usd_display` ("total so far on this machine"). Do this on
   every paid run, not just the first. Do not paste translated content into chat
   unless asked for specific rows.

### Running it: use the CLI

Prefer the CLI: it handles credentials itself (`configure_openai()`) and prints
JSON you can report from. Run it with the interpreter that `setup_env.py` printed
(`VENV_PYTHON=<path>`); `python3` alone will not have `openai` installed. `PY`
below is that path, and `translation.py` lives in the skill's
`assets/transcribe-translate/` directory.

```bash
PY=<the VENV_PYTHON path from setup_env.py>
# 1. estimate: shows cells_to_translate, estimated_usd_display, pii_warning -> show the user, get confirmation
"$PY" translation.py estimate responses.csv --columns q_open,comments --target en
# 2. translate (only after confirmation). Omit --source to auto-detect mixed-language columns.
"$PY" translation.py translate responses.csv --columns q_open,comments \
    --target en --output responses_en.csv --cache translation-cache.db --confirm
```

Equivalent inside a generated Python script (run under the same interpreter):

```python
import openai_auth, translation
openai_auth.configure_openai()
est = translation.estimate_cost("responses.csv", ["q_open","comments"], "en")
# show est["estimated_usd_display"], est["cells_to_translate"], est["pii_warning"]; confirm
stats = translation.translate_csv(
    "responses.csv", ["q_open","comments"], target_language="en",
    source_language=None, output_path="responses_en.csv",
    cache_path="translation-cache.db", confirm=True)   # model="cheap" by default
print(stats["output_path"], stats["cells_translated"], stats["cells_cached"])
```

## Glossary handling

A glossary CSV (`source` + `target` or `target_<lang>` columns) enforces preferred
renderings of recurring terms. It is applied **after** translation as a
re-runnable overlay (the cache stores the raw translation, so changing the glossary
does not force a re-translation). The match is a case-insensitive whole-phrase
replacement, longest terms first; curate accordingly (it does not handle
inflection).

```csv
source,target_es,target_fr
household roster,roster del hogar,liste des membres du ménage
enumerator,encuestador,enquêteur
```

## Caching and re-runs

Pass a `cache_path` (e.g. `translation-cache.db`) so re-translating a refreshed
export only pays for changed cells. The cache contains source text and
translations, so it is sensitive: keep it with the user's data, not in a shared or
version-controlled location.

## Quality reminder

Machine translation of open-ended data is a starting point, not a finished
product. For anything driving analysis or reporting, recommend a fluent speaker
spot-check a sample of the output. This is a recommendation, not a gate.
