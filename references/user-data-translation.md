<!-- PRIMER: user-data-translation
  STATUS: drafted 2026-06-06 -->

# Translating user data (responses, comments, transcriptions)

This primer covers **translating columns of collected user data** in exported
CSV files: open-ended responses, enumerator notes, supervisor comments, and
audio transcriptions. It uses Google Cloud Translation as the backing service.

This is a different workflow from form-label translation. Read
[`translation.md`](translation.md) for form labels; read this for user data. The
distinction matters:

| | Form labels ([`translation.md`](translation.md)) | User data (this primer) |
| --- | --- | --- |
| Volume | Low (50-500 labels) | Can be very large |
| Sensitivity | Non-sensitive | Often sensitive; may contain PII |
| In conversation? | Yes, the agent translates directly | No, sent to an API by a script; the agent never ingests the cells |
| Backing service | The agent's own ability | Google Cloud Translation |
| Credentials | None | A Google service-account file ([`google-cloud-credentials.md`](google-cloud-credentials.md)) |

Read [`google-cloud-credentials.md`](google-cloud-credentials.md) first: it
covers how to authenticate without ever exposing the user's secret, and how to
coach a user who has not set up credentials yet.

## Why this runs as a script, not in conversation

User data is too sensitive to pass through the agent's context or the
conversation logs, and there can be far too much of it to fit anyway. So the
agent does not read the cell contents and translate them itself. Instead it
runs the shipped module
[`assets/google-cloud/translation.py`](../assets/google-cloud/translation.py),
which reads the CSV, sends the text directly to Google Cloud Translation, and
writes the translated CSV to disk. The agent orchestrates and reports; it does
not ingest the data cell by cell.

## What the module gives you

[`assets/google-cloud/translation.py`](../assets/google-cloud/translation.py)
exposes composable pieces (not a single "translate CSV" button, because users'
needs vary):

- `estimate_cost(csv_path, columns, target_language)` counts billable
  characters and returns the estimated USD cost and free-tier status.
- `detect_languages(csv_path, column, sample_size=100)` samples cells and
  reports detected source languages with a confidence figure. This is a metered
  Google call that sends the sampled cells to Google, so it carries the same
  privacy consideration as translation; it is bounded to `sample_size` cells, so
  for the default it stays well inside the free tier. It returns the same
  `pii_warning` for you to show the user.
- `translate_csv(csv_path, columns, target_language, source_language,
  output_path, glossary_path=None, cache_path=None, confirm=False)` is the
  workhorse.
- `apply_glossary(text, glossary)` post-processes a translation to enforce
  preferred terminology.

Built into `translate_csv`:

- **Cost gate.** It refuses to run unless `confirm=True`. Always call
  `estimate_cost` and confirm with the user first.
- **Caching.** With a `cache_path`, translations are memoized in SQLite keyed on
  the source language, target language, and a hash of the source text.
  Re-translating a re-downloaded dataset only pays for cells whose text changed.
- **De-duplication within a run.** Identical source strings are sent once.
- **Skip-list.** Empty cells, pure numbers, single letters, and common survey
  codes (`N/A`, `999`, `-99`, and the like) are never sent to the API.
- **Preserve originals.** It adds a `<column>_<target_language>` column next to
  each source column and never overwrites the original. If that output column
  already exists, it refuses to run rather than clobber data.
- **Batching with backoff.** Requests are chunked, with exponential backoff on
  transient API errors.

## Workflow: translate columns in a CSV

1. **Confirm credentials are set up.** Run the credential check (or just try the
   operation). If it raises a "no credentials configured" error, switch to the
   coaching flow in [`google-cloud-credentials.md`](google-cloud-credentials.md).
   Confirm the client library is installed (`pip install google-cloud-translate`).
2. **Identify the columns.** Read the CSV header (column names only; you do not
   need to read the data) and work out which columns hold free text versus
   codes, IDs, or numbers. Ask the user which columns to translate if they have
   not said.
3. **Get the target language** as an ISO 639-1 code (`en`, `es`, `fr`, `sw`,
   ...). Ask if unspecified.
4. **Estimate cost and show the PII warning.** Call `estimate_cost(...)`. Show
   the user the billable character count, the estimated USD cost, whether it
   falls in the free tier, and the one-line privacy reminder that the source
   text will be sent to Google's servers. Keep the privacy reminder on every
   run; it can be brief on later runs in the same session.
5. **Wait for explicit confirmation.** Do not proceed until the user confirms.
   Never run translation without showing the cost first, even if the user said
   "just do it" up front. Show the cost, then ask once.
6. **Detect source languages if mixed or unknown.** If the user is not sure of
   the source language, or the column may mix languages, run
   `detect_languages(...)` on a sample and report what you find. Pass
   `source_language=None` to `translate_csv` to let the API auto-detect per
   cell, or pass a fixed code if the column is uniform.
7. **Translate.** Call `translate_csv(...)` with `confirm=True` and a
   `cache_path` so re-runs are cheap. Use a glossary if the user has one (see
   below).
8. **Report.** Tell the user the output path and summarize the returned stats:
   how many cells were translated, served from cache, and skipped, and how many
   characters were actually billed. Do not paste the translated content into the
   conversation unless the user explicitly asks to see specific rows.

Example (inside a generated script):

```python
import google_cloud_auth
import translation

google_cloud_auth.configure_google_auth()

est = translation.estimate_cost("responses.csv", ["q_open", "comments"], "en")
# show est["estimated_usd"], est["cells_to_translate"], est["pii_warning"] to the user
# ... after the user confirms ...
stats = translation.translate_csv(
    "responses.csv",
    ["q_open", "comments"],
    target_language="en",
    source_language=None,        # auto-detect per cell
    output_path="responses_en.csv",
    cache_path="translation-cache.db",
    confirm=True,
)
print(stats["output_path"], stats["cells_translated"], stats["cells_cached"])
```

## Glossary handling

A glossary enforces the user's preferred rendering of recurring domain terms
(household, enumerator, plot, and so on). The glossary is a CSV with a `source`
column and either a `target` column or per-language `target_<lang>` columns:

```csv
source,target_es,target_fr
household roster,roster del hogar,liste des membres du ménage
anthropometry,antropometría,anthropométrie
enumerator,encuestador,enquêteur
```

`translate_csv` applies the glossary **after** the API call by default: the
model produces fluent output and the glossary then overrides terminology on top.
This is more robust than pre-substituting terms (which risks ungrammatical
output when the target term does not inflect the way the source did), at the
cost of paying to translate terms that get overridden. The substitution is a
simple case-insensitive whole-phrase replacement, longest terms first; it does
not handle inflection or agreement, so curate the glossary with that in mind.

## Caching and re-runs

Pass a `cache_path` (for example `translation-cache.db`) so that re-translating
a refreshed export only pays for changed cells. The cache contains source text
and translations, so it is sensitive. Store it alongside the user's data, not in
a shared or version-controlled location. The skill `.gitignore` template ignores
the default cache names; if the user keeps their work in a git repository,
confirm the cache is ignored.

## Mixed-language columns

If a single column mixes languages (Spanish and Quechua cells, say), the default
behavior translates each cell into the target language regardless of its source
(best for downstream analysis). If the user would rather preserve nuance and
handle mixed cells manually, run `detect_languages` first and discuss the split
with them before translating.

## Limits and out of scope

- This translates data in CSV exports. It does not translate form definitions
  (labels, choice lists); that is form-label translation, see
  [`translation.md`](translation.md).
- It uses Google Cloud Translation standard NMT. DeepL, Azure, custom-trained
  models, and Google's LLM translation mode are out of scope.
- Very large files are handled by batching and caching, not by streaming; for
  extremely large exports, translate the columns the user actually needs rather
  than the whole file.

## Quality reminder

Machine translation of open-ended data is a starting point, not a finished
product. For anything that will drive analysis or reporting, recommend that a
fluent speaker spot-check a sample of the output, especially for sensitive or
high-stakes items. This is a recommendation, not a gate; the user decides what
is appropriate for their context.
