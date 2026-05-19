<!-- PRIMER: form-conversion-odk
  STATUS: drafted 2026-05-16 -->

# Converting an ODK XLSForm into a SurveyCTO XLSForm

> **Read [`form-conversion.md`](form-conversion.md) first.** It defines the overall workflow, the universal mapping concerns (field-name sanitization, choice-list deduplication, "Other, please specify", HTML/Markdown, multi-language, expression rewrites, form metadata), the conversion-report contract, and the validation checklist. This file only adds ODK-specific details.

ODK and SurveyCTO share a parent — both descend from the same XLSForm/XForms lineage — so most rows convert nearly 1:1. **The work is mostly column renames, expression rewrites, and flagging the small set of ODK-only features.** Many ODK forms convert cleanly enough that the conversion report ends up almost empty, which is the right outcome.

The catch: precisely because the two formats look almost identical, it's easy to miss the divergences. SurveyCTO and ODK use **different conventions** in places that look interchangeable. Don't skip the checks below just because a form "looks fine" — silent divergences silently break forms. See the gotchas already documented in [`xlsform.md`](xlsform.md) and re-applied below.

## Reading the source

Source is `.xlsx` with `survey`, `choices`, and `settings` worksheets — the same shape as a SurveyCTO XLSForm. Read it with the agent's xlsx skill or `openpyxl`:

```python
from openpyxl import load_workbook

wb = load_workbook(source_path, data_only=True)
survey = wb["survey"]
choices = wb["choices"]
settings = wb["settings"]
```

Note `data_only=True` to read formula-evaluated values rather than the formulas themselves — relevant if the source uses an Excel formula for `version`.

ODK XLSForms may also include extra worksheets you'll encounter in the wild:

- **`entities`** — declares an ODK Central Entity List (see [§ ODK Entities](#odk-entities) below).
- **`external_choices`** — choices loaded from `select_one_from_file` / `select_multiple_from_file` references.
- **`itemsets.csv` / other attached CSVs** — for `pulldata()` or `select_*_from_file` lookups (sit alongside the workbook, not inside it).

Inventory all of them before patching.

**Crucially: do not use the SurveyCTO MCP XLSForm tools on the source workbook.** Those tools assume SurveyCTO conventions; pointing them at an ODK form will misinterpret columns and may flag warnings that aren't real ODK problems. The MCP tools are for the SurveyCTO-side target only.

## Column renames

ODK and SurveyCTO use a few different column-header conventions:

- ODK's skip-logic column is **`relevant`**; SurveyCTO's documented column is **`relevance`**.
- ODK / standard XLSForm uses **double-colon suffixes** (`label::Spanish`, `media::image`, `media::image::Spanish`, `hint::Spanish`); SurveyCTO docs and the bundled template use **single-colon** (`label:Spanish`, `media:image`, `media:image:Spanish`).

**The SurveyCTO MCP XLSForm tools accept either form and normalize automatically** — `relevant`/`relevance` and single-vs-double-colon are both handled transparently. When applying edits through MCP, you don't have to rewrite these. If you're producing the workbook without MCP, or if the user wants the output to match SurveyCTO's documented conventions exactly, rewrite to `relevance` and single-colon suffixes for consistency.

Everything else carries over without rename: `type`, `name`, `label`, `hint`, `constraint`, `constraint message`, `required`, `required message`, `appearance`, `calculation`, `choice_filter`, `default`, `read only`, `repeat_count`, `parameters`. (`parameters` is used by ODK for some types like `audit`/`background-audio`; SurveyCTO supports it as well.)

**Hint cells are an exception** to the HTML-carryover rule from [`form-conversion.md`](form-conversion.md#html-and-markdown-in-labels) — SurveyCTO doesn't render HTML in hints. If the source uses HTML in hints, strip to plain text.

## Expression rewrites

ODK XPath expressions are mostly compatible with SurveyCTO, but a few SurveyCTO-specific conventions must be applied to every expression cell (`relevance`, `constraint`, `calculation`, `choice_filter`, and any expression embedded in `label`/`hint` via `${...}`):

| Replace | With | Where |
| --- | --- | --- |
| `==` | `=` | Equality comparison. Standard XPath and most ODK forms already use `=`, but forms authored by people coming from JavaScript or Python sometimes have `==` — search and replace. |
| `position(..)` | `index()` | Repeat-instance number. SurveyCTO explicitly recommends `index()` because `position(..)` can fail in some nested-group cases. |
| `jr:choice-name(${field}, '${field}')` | `choice-label(${field}, ${field})` | Look up the label for the current value of a `select_one` field. Single quotes around the field name are no longer needed. |
| `selected(${field}, 'value')` | `selected(${field}, 'value')` | Same. SurveyCTO requires `selected()` for `select_multiple` comparisons. `${field} = 'value'` works for `select_one` only. |
| `${field} div 10`, `${field} / 10` | `${field} div 10` | SurveyCTO uses `div`, not `/`, for division — same as XPath. ODK forms usually already do this; flag any `/` divisions you find. |
| `coalesce(a, b)` | `coalesce(a, b)` | Same in both. |

ODK's date functions (`today()`, `now()`, `date(...)`, `format-date(...)`, `format-date-time(...)`, `decimal-date-time(...)`) work the same in SurveyCTO. Numeric functions (`int()`, `round()`, `abs()`, `min()`, `max()`, `sum()`, `count()`) are the same. String functions (`concat()`, `substr()`, `string-length()`, `regex()`, `contains()`, `starts-with()`, `ends-with()`) are the same.

For anything you're unsure about, search [`expressions.md`](expressions.md) or run a quick `kb_search` against the SurveyCTO docs before emitting.

## Field-type mapping

Most ODK field types map directly:

| ODK / standard XLSForm `type` | SurveyCTO target | Notes |
| --- | --- | --- |
| `text`, `integer`, `decimal` | same | Same. SurveyCTO `integer` is limited to 9 digits — flag if the source clearly expects larger values and recommend `text` with `appearance=numbers` instead. |
| `select_one <list>`, `select_multiple <list>` | same | Same. Confirm `selected()` is used for any expressions comparing against `select_multiple`. |
| `note` | same | Same. |
| `calculate` | same | Same; rewrite the `calculation` expression per the table above. |
| `date`, `datetime`, `time` | same | Same. |
| `geopoint`, `geoshape`, `geotrace` | same | Same. SurveyCTO `geoshape`/`geotrace` are Android-only — flag if the source form will be deployed via web. |
| `image`, `audio`, `video`, `file` | same | Same. |
| `barcode` | same | Same; reminder that web forms don't support barcode. |
| `acknowledge` | same | Same (renders as a single confirmation checkbox). |
| `begin group` / `end group`, `begin repeat` / `end repeat` | same | Same. |
| `start`, `end`, `today`, `deviceid`, `phonenumber`, `username`, `email` | same | Metadata field types; same in both. SurveyCTO additionally has `caseid`, `subscriberid`, `simserial`. |
| `audit` | same | SurveyCTO supports `audit`. Parameters (e.g., `location-priority=balanced;location-min-interval-seconds=60`) may need adjustment; check [`xlsform.md`](xlsform.md). |
| `background-audio` | not supported natively | Flag in the report. SurveyCTO has `audio audit` for similar use cases — recommend that as a manual replacement. |
| `rank` | not supported natively | No native rank-order field in SurveyCTO. Emit as a `note` placeholder showing the choice list, and flag in the report so the user can design a manual ranking pattern (sequence of `select_one` fields with `choice_filter` excluding previously-picked values, for example). |
| `range` | `integer` or `decimal` with `constraint` | ODK's `range` type with `parameters="start=0 end=100 step=1"` becomes `integer` (or `decimal` if `step` has decimals) with `constraint = . >= 0 and . <= 100`. SurveyCTO has no equivalent of `range`'s slider rendering — flag the rendering difference. |
| `select_one_from_file <filename>`, `select_multiple_from_file <filename>` | `select_one <list>` / `select_multiple <list>` driven by a SurveyCTO dataset or attached CSV | ODK loads choices from an attached CSV / GeoJSON / XML file at runtime. SurveyCTO has a clean equivalent — see [§ External data: CSVs and datasets](#external-data-csvs-and-datasets) below for the full conversion path. |
| `csv-external` | (no separate type — just attach the CSV) | ODK's `csv-external` declares an attached CSV for `pulldata()`. SurveyCTO doesn't use a separate row for this — the user simply attaches the CSV to the form and the converted `pulldata()` calls work against it. Drop the `csv-external` row(s) from the output. See [§ External data: CSVs and datasets](#external-data-csvs-and-datasets). |
| `xml-external` | (republish as a SurveyCTO dataset) | ODK's `xml-external` declares an XML secondary instance. SurveyCTO uses datasets (not XML secondary instances) for the same use case. Drop the row and convert the data to a SurveyCTO dataset — see [§ External data: CSVs and datasets](#external-data-csvs-and-datasets). |

## External data: CSVs and datasets

ODK's external-data features (`select_one_from_file <name>.csv`, `select_multiple_from_file`, `csv-external`, `xml-external`, `pulldata()` against attached CSVs, ODK Central Entity Lists) **all have clean SurveyCTO equivalents.** This is one of the better-supported parts of the conversion, not a lossy area — but the user has to do a small amount of attachment / upload work on the SurveyCTO side that you can't automate from inside the form.

The two SurveyCTO patterns:

### Pattern A — attached CSV with `pulldata()`

For small-to-medium static lookup data the user wants attached directly to the form (no server dataset needed):

1. **Keep the CSV file** the source form referenced. Don't transform it; SurveyCTO reads CSV attachments directly.
2. **In the converted XLSForm**, rewrite each `pulldata('<filename>', 'column', 'lookup_column', ${field})` call as-is — the function signature is identical in SurveyCTO. (`<filename>` is the CSV filename without the `.csv` extension, just like ODK.)
3. **Drop any `csv-external` rows** from the source. SurveyCTO doesn't need a row to declare the attachment; the file just sits alongside the form.
4. **Tell the user** to attach the CSV when uploading the form: in the SurveyCTO form designer, the user adds the CSV as a regular form attachment. The user-facing instruction in your handoff message and the conversion report should be specific — name the CSV file(s) they need to attach.

This is the right pattern for: per-form lookup data, static reference tables, one-off CSVs that don't need to be shared across forms or updated server-side.

### Pattern B — SurveyCTO dataset (with optional dynamic select)

For data that should live on the server (shared across forms, updated independently, populated by other forms, or used to drive dynamic `select_*` choice lists):

1. **Author a server dataset definition** for the CSV / GeoJSON / XML data. Read [`datasets-xml.md`](datasets-xml.md) for the XML schema, dataset types (`SERVER` vs `CLIENT` vs `REPORT`), `<fieldNames>`, `<uniqueRecordField>`, `<formLinks>`, and `<dataLinks>`. Choose `CLIENT` if the data is read-only lookup; choose `SERVER` if the user will publish into it from other forms.
2. **In the converted XLSForm**, choose one of:
   - **Static-select against a SurveyCTO dataset**: `select_one <list>` where the choices in the `choices` worksheet have `value` and `label` referring to dataset columns, and the field has `appearance=search('<dataset_id>')`. See the [Dynamic select list from pre-loaded data](../SKILL.md#dynamic-select-list-from-pre-loaded-data) pattern in `SKILL.md`. This replaces ODK's `select_one_from_file`.
   - **`pulldata()` against the dataset**: `pulldata('<dataset_id>', '<column>', '<lookup_column>', ${field})`. Functionally identical to CSV `pulldata()`; just point at the dataset ID instead of a filename.
3. **Coach the user through the SurveyCTO server steps**, with concrete instructions in your handoff message and the conversion report:
   - Open the SurveyCTO console → **Design** → **Datasets** (or **Server Dataset Manager**).
   - **Create the dataset from the XML definition file you produced** (upload the dataset definition `.xml`, which sets up the dataset structure).
   - **Populate the dataset by uploading the CSV** of data (or publish from another form — for `SERVER` datasets).
   - **Deploy the dataset** so attached forms can use it.
   - Upload the converted XLSForm; SurveyCTO will recognize the dataset attachment via the form's references.

This is the right pattern for: large reference tables, data shared across multiple forms, data that gets updated server-side, anywhere ODK Central was using Entity Lists.

### Choosing between A and B

A is simpler when:

- The data is small and static.
- Only this one form uses it.
- The user doesn't need server-side updates.

B is the right call when:

- The data is large, frequently updated, or used by multiple forms.
- The source used ODK Entity Lists (B is the only SurveyCTO equivalent).
- The source used `select_one_from_file` against a large GeoJSON / XML / large CSV — the dataset path scales better than the per-form attachment path.

When you're not sure which the user wants, **ask**. Either path is a legitimate conversion; the choice depends on operational preferences the user owns.

### What to put in the conversion report

For every source external-data reference (per `select_*_from_file`, per `csv-external`, per `pulldata()`, per Entity List), the report should list:

- The source declaration (file name or entity-list name).
- Which target pattern the converter chose (A or B).
- The exact action the user must take on the SurveyCTO side (attach this CSV at form upload, or create this dataset on the server first).
- If pattern B: a pointer to the dataset XML definition the converter produced (or a clear note that the user must author one — see `datasets-xml.md`).

## Settings

`settings` worksheet keys translate mostly 1:1, with a few notable exceptions:

| ODK setting | SurveyCTO | Notes |
| --- | --- | --- |
| `form_title` | `form_title` | Same. Set via `change_setting`. |
| `form_id` | `form_id` | Same. Set via `change_setting`. |
| `version` | `version` | **Don't carry over the source's `version` value.** The SurveyCTO template ships with an auto-updating formula that `export_xlsform` recalculates. Leave it alone. |
| `default_language` | `default_language` | Same. Set via `change_setting`. |
| `instance_name` | `instance_name` | Same column name and semantics. |
| `style` | `style` | ODK styles `pages`, `theme-grid`, `theme-grid no-text-transform` don't have SurveyCTO equivalents. SurveyCTO has its own theming model (managed in the server console, not in `settings`). **Drop `style` from the conversion and flag** — the user configures appearance on the SurveyCTO side. |
| `public_key` | (encryption setup is server-side in SurveyCTO) | ODK's encryption via `public_key` and `submission_url` doesn't transfer. SurveyCTO encryption is configured per form on the server. Drop both and flag — the user enables encryption on the SurveyCTO server console after upload. |
| `submission_url` | (not applicable) | SurveyCTO's submission endpoint is determined by the user's server, not the form. Drop. |
| `allow_choice_duplicates` | not supported | XLSForm requires unique choice `value`s within a `list_name` in SurveyCTO. If the ODK form relied on duplicates (e.g., for cascading selects with shared labels but distinct filter columns), the conversion will fail validation. Flag and ask the user to disambiguate values. |
| `auto_send`, `auto_delete` | (not applicable) | ODK Collect device-side behaviors. SurveyCTO has its own equivalents in Collect settings on the device. Drop and flag. |

## ODK Entities

ODK Central supports **Entity Lists** — a data-management feature where form submissions can create, update, and reference entities (records in a shared list). Declared via a dedicated **`entities`** worksheet in the XLSForm with columns `list_name`, `label`, and (optionally) `entity_id`, `create_if`, `update_if`. Forms reference the entity list as `select_one <list_name>` or `select_multiple <list_name>`, and on submission Central writes the marked fields into the entity list.

**SurveyCTO uses server datasets for the same use case** — and the conversion path is the dataset-driven pattern (Pattern B) in [§ External data: CSVs and datasets](#external-data-csvs-and-datasets) above. The nearest equivalents:

- **Server datasets** (`datasetType=SERVER`) with form-side `<dataLinks>` for incoming publication (when a form creates or updates entities) and `<formLinks>` for pre-loading (when a form reads entities). See [`datasets-xml.md`](datasets-xml.md).
- **Case management** for the case-list pattern specifically (a designated dataset whose rows represent cases that one or more forms work against). See [`overview.md`](overview.md#forms-datasets-and-data-flow).

The conversion:

1. **Drop the `entities` worksheet entirely** from the output XLSForm. SurveyCTO doesn't recognize it, and the dataset replaces it.
2. **Author the matching SurveyCTO dataset XML** for each Entity List, following [`datasets-xml.md`](datasets-xml.md). For an Entity List that's read-only in this form, a `CLIENT` dataset is usually right; for one that this form creates/updates, a `SERVER` dataset with `<dataLinks>` is right.
3. **Translate `entities` `save_to` mappings** (which ODK uses to mark form fields that write into the entity list on submission) into `<dataLink>` field mappings in the dataset XML (`FORM` class, `INCOMING` type, mapping form-field names to dataset-column names).
4. **Translate references to the entity list** (typically `select_one <entity_list_name>`) into `select_one <list>` rows in the converted form, with `appearance=search('<dataset_id>')` for dynamic loading. The `choices` worksheet gets one row per dataset where `value` and `label` reference dataset column names.
5. **Coach the user through the dataset upload steps** in the handoff message and the conversion report — see [§ External data: CSVs and datasets](#external-data-csvs-and-datasets) for the concrete instruction list.

Entity Lists are a relatively new ODK feature, so users coming from ODK Central may not be familiar with SurveyCTO's dataset model. Set expectations and explain the equivalence when you spot an `entities` worksheet.

## Appearances

Most appearances carry over without change: `minimal`, `quick`, `compact`, `likert`, `field-list`, `multiline`, `numbers`, `numbers_decimal`, `numbers_phone`, `signature`, `annotate`, `draw`, `no-buttons`, `horizontal`, `randomized`.

A few ODK appearances behave differently or aren't supported:

| ODK appearance | SurveyCTO | Notes |
| --- | --- | --- |
| `map`, `placement-map` | `appearance=maps` (`geopoint`), `placement-map` | Roughly compatible names; verify map provider configuration on the SurveyCTO side. |
| `printer` | not supported as a render appearance | Use SurveyCTO's [printable forms](https://docs.surveycto.com/02-designing-forms/02-additional-topics/04.printable-copies.html) feature instead. Flag. |
| `pages` (group) | use `field-list` per page | ODK's `pages` appearance on a group paginates the children; SurveyCTO uses `field-list` on each "page" group. May require restructuring the group hierarchy. Flag. |
| `theme-grid` | (no direct equivalent) | SurveyCTO's grid-rendering is configured separately. Drop. |

For any unfamiliar appearance, `kb_search` against `docs.surveycto.com` before guessing.

## "Other, please specify"

ODK forms typically implement "Other, please specify" with the universal pattern (`select_one` with an `other` choice plus a sibling `text` with `relevance = selected(${parent}, 'other')`) — the same pattern SurveyCTO uses. Carry over as-is; no conversion needed beyond the column/expression rewrites.

If the source uses ODK's `or_other` choice modifier (rare — a non-standard XLSForm shorthand some processors accept), expand it into the explicit pattern: add an `other` choice row and a sibling `text` field manually.

## Things that don't translate cleanly

Most ODK features have direct SurveyCTO equivalents. External data (CSVs, Entity Lists, secondary instances) converts cleanly via the two patterns in [§ External data: CSVs and datasets](#external-data-csvs-and-datasets) — the user has some attachment / upload work to do on the SurveyCTO side, but the form-side conversion is mechanical. The remaining exceptions to flag:

- **`rank`** — no native rank field in SurveyCTO. Recommend a sequence of `select_one` fields with `choice_filter` excluding prior picks, or document as a hand-completion item.
- **`background-audio`** — no native equivalent. Recommend `audio audit` field types.
- **`range`** rendering — SurveyCTO has no slider widget native to the type; the converted `integer`/`decimal` field renders as a numeric input. Functional but visually different.
- **`public_key` / `submission_url` / encryption configuration** — server-side in SurveyCTO; drop the form-side keys and instruct the user to configure encryption on the server console.
- **`style: pages`** and **`style: theme-grid`** — SurveyCTO doesn't use these; the form structure may need manual paging (use `field-list` groups per intended page).
- **`allow_choice_duplicates`** — SurveyCTO requires unique `value` per `list_name`. Disambiguate.
- **ODK Central submission/review flows** (entity management, draft submissions, reviewState) — these are server-side concepts in Central with no direct SurveyCTO analogue. Out of scope for the form-instrument conversion.

## ODK-specific gotchas

- **Column-header conventions are cosmetic when MCP tools are in use.** SurveyCTO MCP XLSForm tools accept both `relevant` and `relevance`, and both single- and double-colon suffixes — they normalize internally. Rewrite to SurveyCTO's documented conventions (`relevance`, single-colon) for tidiness, but don't treat this as a critical step. Without MCP (raw workbook editing), prefer the documented conventions.
- **Default-language column placement.** ODK and SurveyCTO have the same rule — default language in the unsuffixed column — but ODK form-builders sometimes emit forms with the default language only in `label::English` (or `label:English`), leaving the base `label` column empty. **This breaks in SurveyCTO regardless of the colon convention.** If you see this pattern, copy the default-language column into the unsuffixed `label` column (and adjust `settings.default_language` accordingly). See [`xlsform.md`](xlsform.md) and the gotcha in [`form-conversion.md`](form-conversion.md#multi-language-carry-over).
- **`integer` 9-digit limit.** SurveyCTO `integer` is capped at 9 digits. If the source clearly expects larger values (IDs, phone numbers stored as integers), convert the field to `text` with `appearance=numbers` (digits-only keyboard) and adjust constraints accordingly.
- **`select_one_from_file` is not a SurveyCTO type.** Don't emit it. Either convert to a static `select_one <list>` (if the CSV is small enough to inline into `choices`) or to a `select_one <list>` with `appearance=search('<dataset_id>')` against a SurveyCTO dataset the user will publish separately.
- **`jr:choice-name()` signature differs from `choice-label()`.** ODK's `jr:choice-name(${field}, '${field}')` quotes the field name in the second argument; SurveyCTO's `choice-label(${field}, ${field})` keeps both arguments but uses a plain field reference for the second. Don't carry the quoted field name over verbatim.
- **`position(..)` vs `index()` is real, not cosmetic.** SurveyCTO documentation explicitly recommends `index()` because `position(..)` can fail in nested groups. Always rewrite.
- **Forms with custom XForms-level extensions** (raw XML edits, `<bind>` attributes not surfaced in the XLSForm columns, custom widget extensions) may not be representable in an XLSForm at all. If the source XLSForm was hand-edited or post-processed before deployment, the XLSForm may not capture everything the deployed form does. Flag if the user mentions this; recommend they re-export the canonical XLSForm.

## Worked example

A small ODK form snippet and its SurveyCTO equivalent.

**Source `survey` row (ODK):**

| type | name | label::English | label::Spanish | hint::English | required | relevant | calculation | media::image |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `integer` | `age` | `How old are you?` | `¿Cuántos años tienes?` | `Years` | `yes` | `${consent} == 'yes'` | | `age_diagram.png` |

**Source `settings` row (ODK):**

| form_title | form_id | version | default_language | style | public_key |
| --- | --- | --- | --- | --- | --- |
| `Household survey` | `hh_survey_2026` | `2026051601` | `English` | `pages` | `MIIBIjAN…` |

**Target SurveyCTO `survey` row:**

| type | name | label | label:Spanish | hint | required | relevance | calculation | media:image |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `integer` | `age` | `How old are you?` | `¿Cuántos años tienes?` | `Years` | `yes` | `${consent} = 'yes'` | | `age_diagram.png` |

**Target SurveyCTO `settings` row** (set via `change_setting`, not by copying):

| form_title | form_id | default_language |
| --- | --- | --- |
| `Household survey` | `hh_survey_2026` | `English` |

Conversion report items for this snippet:

- Default-language label moved from `label::English` into the unsuffixed `label` column (this one matters — leaving the base empty breaks SurveyCTO).
- Header rewrites for tidiness (MCP would accept either form): `relevant` → `relevance`, `label::Spanish` → `label:Spanish`, `media::image` → `media:image`.
- `style: pages` dropped — SurveyCTO doesn't use `style: pages`; the form may need manual paging via `field-list` groups if the user wants the same multi-screen rendering.
- `public_key` dropped — encryption is configured server-side in SurveyCTO; user enables it on the SurveyCTO console after upload.
- `version` not carried over — SurveyCTO uses an auto-updating formula in the template.
- Expression rewrite: `${consent} == 'yes'` → `${consent} = 'yes'`. (No-op if the source already used `=`.)
