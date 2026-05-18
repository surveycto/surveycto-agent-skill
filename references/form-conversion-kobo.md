<!-- PRIMER: form-conversion-kobo
  STATUS: drafted 2026-05-16 -->

# Converting a KoboToolbox XLSForm into a SurveyCTO XLSForm

> **Read [`form-conversion.md`](form-conversion.md) first** for the overall workflow and universal mapping concerns. **Then read [`form-conversion-odk.md`](form-conversion-odk.md)** — KoboToolbox is XLSForm/ODK-derived, so almost everything in the ODK reference applies to Kobo as well (column renames, expression rewrites, field-type mapping, settings handling, the same Other-please-specify pattern, the same gotchas). **This file only documents the Kobo-specific deltas on top of the ODK reference.**

In practice, converting from Kobo is the easiest of the four first-class source platforms — the format is nearly identical to a SurveyCTO XLSForm in most rows, and forms produced by Kobo's form builder are typically very clean. The work is: apply the ODK rewrites, expand the small set of `kobo--*` extensions by hand, and flag the bits that don't translate.

## What's the same as ODK

Everything in [`form-conversion-odk.md`](form-conversion-odk.md) applies, with no Kobo-specific override unless noted below:

- **Column renames** — `relevant`→`relevance` and double-colon → single-colon suffixes are both cosmetic when applying via MCP (the tools auto-normalize either form). Rewrite to SurveyCTO's documented conventions for tidiness, but it isn't required.
- **Expression rewrites** — `==`→`=`, `position(..)`→`index()`, `jr:choice-name(…)`→`choice-label(…)`. Same SurveyCTO conventions for `selected()`, `div`, etc.
- **Field-type mapping** — standard ODK types (`text`, `integer`, `decimal`, `select_one`, `select_multiple`, `note`, `calculate`, `date`, `datetime`, `time`, `geopoint`, `geoshape`, `geotrace`, `image`, `audio`, `video`, `file`, `barcode`, `acknowledge`, `begin group`/`end group`, `begin repeat`/`end repeat`, metadata types) all carry over.
- **Settings handling** — `form_title`, `form_id`, `default_language`, `instance_name` carry over; `version` is left alone (template formula handles it); `style: pages` / `style: theme-grid` / `public_key` / `submission_url` are dropped and flagged.
- **The same gotchas** — default-language column placement (the one that actually breaks forms); the `integer` 9-digit limit; hints don't render HTML. Header conventions like `relevant`/`relevance` and colon-count are cosmetic under MCP.

Don't re-implement those checks here — work through the ODK reference first, then apply the Kobo additions below.

## Kobo-specific extensions

KoboToolbox extends standard XLSForm with a small family of `kobo--*` features. They appear in the `type` column or as appearance modifiers. None of them map to a single SurveyCTO field type; each expands into a pattern of native SurveyCTO rows.

### `kobo--matrix` (matrix question)

Kobo's matrix layout renders a table of related questions sharing a common scale. It typically appears as a group-style structure in the `survey` worksheet (`type: begin_kobomatrix` / `end_kobomatrix`, or via `appearance: kobomatrix`; the exact form-builder output varies by Kobo version), with rows defined inside the group and the scale defined as a choice list referenced by the matrix group.

**SurveyCTO equivalent**: expand into a `begin group` / `end group` pair with `appearance=field-list`, with one `select_one <shared_list>` (or `select_multiple <shared_list>`) field per matrix row. This is exactly the pattern Qualtrics matrix questions translate to — see [`form-conversion-qualtrics.md`](form-conversion-qualtrics.md) for the worked structure if helpful.

**Per-row field naming**: Kobo's source matrix typically gives each row its own `name` (inside the `begin_kobomatrix` block). Carry those row names through, *but check for collisions form-wide* — a row named `frequency` inside a matrix collides with a top-level `frequency` question elsewhere in the form. If collision risk exists, prefix with the matrix's parent name: `<matrix_name>_<row_name>` (e.g., `wellbeing_physical`, `wellbeing_mental`). This matches the Qualtrics expansion convention in [`form-conversion-qualtrics.md`](form-conversion-qualtrics.md#sub-field-naming-for-expanded-questions). The group itself takes the matrix's parent name (`wellbeing`).

If the source matrix is read-only / display-only (a "score matrix" or "rating matrix" used purely for visual grouping), still emit the group + per-row fields; SurveyCTO has no read-only matrix display.

Flag every `kobo--matrix` expansion in the conversion report so the user can verify the layout matches their intent — the visual rendering won't be identical (SurveyCTO doesn't render a true matrix grid; each row is shown sequentially within the field-list group).

### `kobo--score` and `kobo--score-choices` (rating widget)

Kobo's rating widget renders a horizontal scale (often with star or numeric icons) for selecting a single score per question. It appears in the `survey` worksheet with `type: begin_score` / `end_score`, with the scale defined via `kobo--score-choices` referencing a choice list.

**SurveyCTO equivalent**: a `select_one <shared_scale_list>` field with `appearance=likert` for each scored question. Wrap multi-question score blocks in a `begin group` / `end group` with `appearance=field-list` to mimic the visual grouping. **Apply the same per-row naming check as `kobo--matrix`** — each scored sub-question becomes its own SurveyCTO field and needs a unique form-wide `name`; prefix with the score-block's parent name if there's collision risk.

If the source uses a numeric-icon scale, the choice `label` values can be the numeric labels (`1`, `2`, …, `5`) and SurveyCTO's `likert` appearance will render them as a horizontal radio scale. Flag if the source used star icons — SurveyCTO doesn't render stars natively; the user may want a [field plug-in](field-plugins.md).

### `kobo--rank` (ranking widget)

Kobo's ranking widget asks the respondent to order a list of options. It appears with `type: begin_rank` / `end_rank` and a list of items to rank.

**No SurveyCTO native equivalent.** The common manual pattern: a sequence of `select_one <list>` fields, one per rank position (`first_choice`, `second_choice`, `third_choice`, …), each with a `choice_filter` excluding values already chosen at higher ranks (`not(selected(${first_choice}, name)) and not(selected(${second_choice}, name))` etc., relying on a `name` filter column on the choice list).

Emit a `note` placeholder + flag in the conversion report rather than auto-generating the multi-field rank pattern. The user can author it once they know their preferred shape (forced-rank vs. optional rank, top-N vs. full list).

### `kobo--background-audio` / `background-audio` (continuous audio recording)

Kobo and current ODK both support background audio recording — the device records continuously from form start to form exit. Type column is `background-audio` (with `parameters="quality=voice-only"` or similar).

**SurveyCTO equivalent**: `audio audit` (a SurveyCTO-specific field type) is the closest native option, with its own parameters in the `appearance` column. Convert to `type=audio audit` with sensible defaults and flag for the user to confirm; the recording cadence and audio quality parameters are configured differently. See [`xlsform.md`](xlsform.md) for `audio audit` syntax.

If `audio audit` isn't a good fit for the user's use case, fall back to `type=audio` with `appearance=new` (manual recording per field) and flag the behavioral difference.

### `kobo--submission-url` (settings)

A custom submission endpoint URL in `settings`. Not transferable — SurveyCTO submissions go to the user's SurveyCTO server. Drop and flag.

## Form-builder naming conventions

Kobo's form builder auto-generates field `name` values from labels by lowercasing and replacing spaces with underscores. So a question labeled "What is your age?" gets `name = What_is_your_age` or `what_is_your_age` depending on Kobo version. The names are usually XLSForm-safe but occasionally include unwanted characters from the label (Unicode punctuation, accented letters).

Apply the universal safe-name rule from [`form-conversion.md`](form-conversion.md#field-name-sanitization). Beyond that:

- If Kobo emitted leading-capital names (`What_is_your_age`), consider lowercasing for consistency with SurveyCTO conventions. Lowercase is conventional but not required; ask the user if you're unsure.
- Long auto-generated names from question labels can be unwieldy in expressions. Don't proactively shorten them — the user may want the descriptive names. Only flag if a name collision under sanitization forces disambiguation.

## Choice list deduplication

Kobo's form builder commonly emits per-question choice lists even when the choices are identical across many questions (a Likert 1–5 scale appearing in 20 different questions becomes 20 separate lists in the `choices` worksheet). Apply the deduplication rule from [`form-conversion.md`](form-conversion.md#choice-list-deduplication) — exact-string match on values and labels — to collapse these into one shared `list_name`. The result is a cleaner `choices` worksheet and a form that's easier to maintain in SurveyCTO.

## Settings

In addition to the ODK settings handling, Kobo adds a few worth flagging:

- **`form_title`** carries over verbatim. Kobo allows long titles with full punctuation; SurveyCTO accepts the same. No change needed.
- **Project-level metadata** (Kobo project description, sector, country) is not stored in the XLSForm — it lives in the Kobo project settings UI. Out of scope.
- **`kobo--submission-url`** (if present): drop, flag.

## Things that don't translate cleanly

Beyond the ODK list:

- **`kobo--matrix`** rendering — converts functionally but loses the table visual.
- **`kobo--score`** with star or graphic icons — converts to `likert` appearance but loses the icon rendering. Field plug-in is the path if iconography matters.
- **`kobo--rank`** — no auto-conversion; emit `note` + flag, user authors the manual rank pattern.
- **`kobo--background-audio`** rendering — `audio audit` has different parameters; verify with the user.
- **Kobo form-builder previews and themes** — Kobo lets users configure preview themes per project. Not portable.

## Kobo-specific gotchas

- **`begin_kobomatrix` / `end_kobomatrix`** and similar `_kobo` group markers will be **rejected by SurveyCTO** if left in. Always expand them into native `begin group` / `end group` (with `appearance=field-list`) before submitting the form.
- **Numeric vs text yes/no values.** Kobo's form builder sometimes emits yes/no choice lists with text values (`yes`, `no`) and sometimes with numeric (`1`, `0`). Preserve the source values, or normalize them deliberately, but don't dedupe or rewrite choice values without also rewriting every expression that references them. See [`form-conversion.md`](form-conversion.md#template-flexibility).
- **Language codes with region tags.** Kobo's column suffixes sometimes include region (`label::English (en)`, `label::Spanish (es-MX)`) or sometimes just the language. SurveyCTO uses readable language names (`label:English`, `label:Spanish`). Strip the locale tags and use language names; if the source has variants of the same base language (`en` and `en-GB`), ask the user how to handle them — usually pick one and drop the other. (Single-vs-double-colon is cosmetic; MCP tools normalize either form.)
- **`select_one_from_file <filename.csv>`** is sometimes used by Kobo for large external choice lists. Follow the clean conversion path in [`form-conversion-odk.md`](form-conversion-odk.md#external-data-csvs-and-datasets) — attach the CSV directly (Pattern A) for static per-form lookup data, or republish as a SurveyCTO dataset (Pattern B) for larger or shared data. Coach the user through the SurveyCTO-side attachment / dataset-upload steps in the conversion report.
- **Project-level form versioning** in Kobo is automatic — every save in the form builder bumps the version. Don't carry that version number into the SurveyCTO `version` cell; the template's formula recalculates on export.
- **`kobo--*` token spelling.** Kobo has used `kobomatrix` / `kobo--matrix` / `begin_kobomatrix` in different XLSForm dialects across versions. Match whatever the source uses, but **don't carry any `kobo--*` token into the SurveyCTO output** — it won't be recognized.

## Worked example

A small Kobo form snippet with a matrix question and its SurveyCTO equivalent.

**Source `survey` rows (Kobo):**

| type | name | label::English | label::Spanish |
| --- | --- | --- | --- |
| `begin_kobomatrix likert5` | `wellbeing` | `Rate the following aspects of your wellbeing:` | `Califica los siguientes aspectos de tu bienestar:` |
| `select_one likert5` | `physical` | `Physical health` | `Salud física` |
| `select_one likert5` | `mental` | `Mental health` | `Salud mental` |
| `select_one likert5` | `social` | `Social connections` | `Conexiones sociales` |
| `end_kobomatrix` | | | |

**Source `choices` rows:**

| list_name | name | label::English | label::Spanish |
| --- | --- | --- | --- |
| `likert5` | `1` | `Very poor` | `Muy mal` |
| `likert5` | `2` | `Poor` | `Mal` |
| `likert5` | `3` | `Fair` | `Regular` |
| `likert5` | `4` | `Good` | `Bien` |
| `likert5` | `5` | `Very good` | `Muy bien` |

**Target SurveyCTO `survey` rows:**

| type | name | label | label:Spanish | appearance |
| --- | --- | --- | --- | --- |
| `begin group` | `wellbeing` | `Rate the following aspects of your wellbeing:` | `Califica los siguientes aspectos de tu bienestar:` | `field-list` |
| `select_one likert5` | `physical` | `Physical health` | `Salud física` | `likert` |
| `select_one likert5` | `mental` | `Mental health` | `Salud mental` | `likert` |
| `select_one likert5` | `social` | `Social connections` | `Conexiones sociales` | `likert` |
| `end group` | `wellbeing` | | | |

**Target SurveyCTO `choices` rows** (note column rename `name` → `value` is not strictly necessary since SurveyCTO and the MCP server accept either, but you can rename to `value` for consistency):

| list_name | value | label | label:Spanish |
| --- | --- | --- | --- |
| `likert5` | `1` | `Very poor` | `Muy mal` |
| `likert5` | `2` | `Poor` | `Mal` |
| `likert5` | `3` | `Fair` | `Regular` |
| `likert5` | `4` | `Good` | `Bien` |
| `likert5` | `5` | `Very good` | `Muy bien` |

Conversion report items:

- `begin_kobomatrix likert5` / `end_kobomatrix` expanded into a `begin group` / `end group` pair with `appearance=field-list`. Each row inside the matrix becomes a separate `select_one likert5` field with `appearance=likert`. Functional equivalent; visual rendering differs (SurveyCTO renders the three questions sequentially, not as a single matrix table).
- Default-language label moved from `label::English` into the unsuffixed `label` column; `label::Spanish` becomes `label:Spanish` for cosmetic consistency with SurveyCTO conventions (MCP would also accept the double-colon form).
- `choices.name` renamed to `choices.value` to match the SurveyCTO convention (verify by inspecting the source workbook's column header).
