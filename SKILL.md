---
name: surveycto
description: >
  Design, edit, and debug SurveyCTO forms (XLSForm .xlsx files) and server
  datasets (XML definition files). Covers form logic, expressions, choice
  lists, repeat groups, skip patterns, constraints, calculations, dataset
  publishing, case management, Data Explorer workbook definitions, and
  field plug-ins (.fieldplugin.zip bundles attached to fields via
  "custom-name" appearances). Use when the user mentions SurveyCTO,
  XLSForm, ODK-based forms, survey forms, or data collection forms, or
  when working with .xlsx files that contain survey/choices/settings
  worksheets, XML files with dataset root elements, Excel workbook
  definitions for data monitoring dashboards, or .fieldplugin.zip plug-in
  bundles. New XLSForms always start from the bundled template at
  assets/xlsform-template.xlsx — never built from scratch.
license: Apache-2.0
metadata:
  author: SurveyCTO
  version: "1.0.0-beta.2"
---

# SurveyCTO Form and Dataset Authoring

SurveyCTO is a mobile data collection platform built on the XLSForm and ODK standards, with platform-specific extensions and divergences. This skill provides SurveyCTO domain expertise for the four definition file types you may encounter:

1. **XLSForm form definitions** (`.xlsx`) — survey instruments
2. **Dataset definitions** (`.xml`) — server dataset structure and publishing rules
3. **Data Explorer workbook definitions** (`.xlsx`) — monitoring dashboards
4. **Field plug-in bundles** (`.fieldplugin.zip`) — custom HTML/CSS/JS that takes over rendering of a single field

For a high-level orientation, read [`references/overview.md`](references/overview.md) first.

## Identifying SurveyCTO files

| File type | Format | How to recognize |
| --- | --- | --- |
| XLSForm | `.xlsx` | Worksheets named `survey`, `choices`, `settings` |
| Dataset definition | `.xml` | Root element `<dataset>` with `<definition>` child |
| Data Explorer workbook | `.xlsx` | Worksheets named `summaries`, `settings`, `global_filters`, `global_exclusions` |
| Field plug-in bundle | `.fieldplugin.zip` | Zip with `manifest.json`, `template.html`, `style.css`, `script.js` at the root; referenced from a field's `appearance` as `custom-<name>` |

## XLSForm starting point

Before choosing tools, before writing code, before reading further:

- **New form** → Step 1 is ALWAYS a literal file copy from `assets/xlsform-template.xlsx` to the output path (for example, `cp assets/xlsform-template.xlsx <output_path>` in a Unix shell). The template is bundled with this skill at `assets/xlsform-template.xlsx` (resolve relative to the skill's root directory). Then proceed with the tooling rules below, uploading or opening the *copied* file.
- **Existing form** → load the user's workbook as-is; do not regenerate it.
- **NEVER** create an `.xlsx` from scratch. This rule applies regardless of which tools are available — it is not an MCP-only requirement and there is no fallback exemption. See [Anti-pattern: building the workbook from scratch](#anti-pattern-building-the-workbook-from-scratch) for the specific tools and idioms to avoid.

This rule is the most commonly-skipped step in this skill. If you are about to call `openpyxl.Workbook()`, `pandas.ExcelWriter` against a new path, `libreoffice --headless` to create a new file, or any code that writes XLSX bytes from scratch, stop and copy the template instead.

## Tools you may have available

This skill is fully usable with no special tools — you have enough SurveyCTO knowledge embedded here and at the live documentation links to advise the user, describe edits in prose, and reason about forms. If additional tools are present, use them in the priority order below.

**Tool-selection rule for XLSForm work:** if the SurveyCTO MCP server tools are connected, you MUST use them for nontrivial XLSForm inspection, editing, validation, and export. Do not choose generic `bash`, `python`, `openpyxl`, LibreOffice, or spreadsheet tooling as the primary authoring path when SurveyCTO MCP tools are available. Generic tooling is only a fallback if MCP tools are unavailable, disconnected, or return an unrecoverable error.

### SurveyCTO MCP server (preferred when available)

The **SurveyCTO MCP server** is a public, no-auth MCP server with capabilities built for this domain (XLSForm session inspect/edit/export and SurveyCTO knowledge-base search). Endpoint: `https://assistant-be.surveycto.net/mcp` (Streamable HTTP, stateless, no auth). If the server isn't connected when the user is editing XLSForms or asking factual SurveyCTO questions, mention it exists and offer to help install it; don't insist.

Before using any SurveyCTO MCP tool, read [`references/mcp.md`](references/mcp.md). It is mandatory for MCP usage; do not guess tool signatures, patch semantics, concurrency rules, error handling, or limits from this abbreviated overview.

#### Recommended workflow

1. **Before any MCP tool call**: read [`references/mcp.md`](references/mcp.md), then call `get_surveycto_mcp_capabilities` when unsure to learn the current tool list and primer topics.
2. **Factual SurveyCTO questions**: `kb_search` → quote the returned URLs in your answer.
3. **Create a new XLSForm**: follow the [Workflow: create a new form](#workflow-create-a-new-form) below — it is the canonical sequence and enforces the template-first rule.
4. **Inspect or edit an existing XLSForm**:
   1. Load the user's workbook (do not regenerate). `start_xlsform_session` for a fresh upload, or `get_xlsform_summary` if resuming an existing `session_id`.
   2. **Take a starting inventory from `form_summary` before patching or paging rows.** Note existing column names, choice lists (especially reusable ones like `yesno`), settings values, and any warnings. Do not assume spellings or values from memory.
   3. `xls_get_rows` / `xls_get_row` to inspect rows you intend to touch. Parallel calls are fine.
   4. `xls_apply_patches` — **batch all related edits into one call**. Use `validate_only=true` on the full batch for risky changes. Update settings via `change_setting`, not `edit_row`. For large batches set `return_form_summary=false` and `include_details=false`.
   5. `export_xlsform` → hand the `download_url` or resource link to the user. Avoid `format="base64"` for real workbooks. **If the form references any `custom-<name>` appearances, remind the user to attach the matching `.fieldplugin.zip` files in the SurveyCTO console at upload time** — this skill and the MCP server only edit local files.
   6. Usually leave the session open until TTL expiry; only call `end_xlsform_session` for explicit cleanup.

### Generic spreadsheet/xlsx tooling

Use generic xlsx, Excel, Python/openpyxl, LibreOffice, or spreadsheet tools only when SurveyCTO MCP tools are not available or have failed in a way you cannot recover from. These tools can read and edit `.xlsx` files cell by cell, but they do not understand SurveyCTO form semantics, MCP session concurrency, or server-side formula recalculation. If you must use generic tooling, explicitly tell the user you are falling back because the MCP tools are unavailable or failed, then follow the editing rules in the *Working with XLSForm .xlsx files* section below.

### Web fetch

If you can fetch URLs, the most authoritative live sources are:

- [docs.surveycto.com](https://docs.surveycto.com) — product documentation
- [support.surveycto.com](https://support.surveycto.com) — Support Center articles
- [www.surveycto.com](https://www.surveycto.com) — site/marketing content

Prefer these over the bundled primers when verifying current product behavior.

### No file tooling at all

You can still help: describe edits in prose ("add a row to the `survey` worksheet with `type=integer`, `name=age`, `label=Age in years`, `constraint=. >= 0 and . <= 120`"), explain expressions, debug logic, and validate the user's draft against the rules below. The user can apply changes themselves.

## Authority hierarchy for knowledge questions

When the user asks about SurveyCTO product behavior, conventions, or documentation, prefer sources in this order:

1. **MCP `kb_search` / `get_surveycto_primer`** if available — current, indexed, authoritative.
2. **Live web fetch** of `docs.surveycto.com`, `support.surveycto.com`, `www.surveycto.com` if you can.
3. **Bundled primers** in [`references/`](references/) — stable summaries, may lag the live docs.
4. **General XLSForm/ODK knowledge** — only with an explicit caveat that SurveyCTO has diverged in places (`=` vs `==`, `index()` vs `position()`, `choice-label()` vs `jr:choice-name()`, `relevance` column name, `selected()` for `select_multiple`, etc.).

Cite which level you're answering from when it matters.

## XLSForm overview

An XLSForm is an XLSX workbook with three worksheets:

- **survey** — every question, group, repeat, and calculation is a row
- **choices** — choice lists for `select_one` and `select_multiple` fields
- **settings** — form-wide settings (title, ID, version, language, encryption)

### Key columns (survey worksheet)

| Column | Purpose |
| --- | --- |
| `type` | Field type: `text`, `integer`, `decimal`, `select_one [list]`, `select_multiple [list]`, `note`, `calculate`, `date`, `geopoint`, `image`, `begin group`, `end group`, `begin repeat`, `end repeat`, etc. |
| `name` | Unique variable name (no spaces/punctuation); becomes the export column |
| `label` | Prompt text (supports `label:Language` for translations) |
| `relevance` | Skip logic expression controlling when the row appears |
| `constraint` | Validation expression (`.` = current value) |
| `calculation` | Expression for `calculate` fields |
| `choice_filter` | Expression filtering choices for select fields |
| `appearance` | Display options (`minimal`, `quick`, `likert`, `field-list`, etc.) |
| `repeat_count` | Number of repetitions for repeat groups |

### Key columns (choices worksheet)

| Column | Purpose |
| --- | --- |
| `list_name` | Choice list name (referenced by `select_one [list]` / `select_multiple [list]`) |
| `value` | Stored code for the choice |
| `label` | Display text (supports `label:Language`) |

### Core mechanics

- `${fieldname}` references another field's value in expressions.
- `.` refers to the current field's proposed value (used in constraints).
- Groups (`begin group` / `end group`) organize fields; a `relevance` on the group controls all contents.
- Repeats (`begin repeat` / `end repeat`) repeat a block; `repeat_count` sets the number.
- Field names must be unique across the entire form.

**Full reference**: [`references/xlsform.md`](references/xlsform.md).

## SurveyCTO expression conventions

SurveyCTO uses XPath-like expressions with several platform-specific conventions. **Always use these instead of standard ODK equivalents:**

| Use this (SurveyCTO) | Not this (ODK/XPath) | Context |
| --- | --- | --- |
| `=` | `==` | Equality comparison |
| `index()` | `position()` | Current repeat instance number |
| `choice-label()` | `jr:choice-name()` | Get choice label text |
| `relevance` column | `relevant` column | Skip logic column name |
| `div` | `/` | Division operator in expressions |

### Select field conventions

- For `select_one`: both `${field} = 'value'` and `selected(${field}, 'value')` work.
- For `select_multiple`: **always use `selected()`**. The `=` operator does not work for multi-select.

### String literals

Use single quotes for string literals: `${field} = 'yes'`

Exception: when the string contains single quotes, use double quotes:
`if(${yesno} = 1, "a string with 'quotes' in it", "no quotes")`

### Common expression patterns

**Skip logic (relevance):** `${consent} = 'yes'`

**Constraint with range:** `. >= 0 and . <= 120`

**Calculated age from date of birth:** `int((today() - ${dob}) div 365.25)`

**Conditional value:** `if(${gender} = 'female', 'F', 'M')`

**Pull data from attached dataset:** `pulldata('households', 'head_name', 'hhid', ${household_id})`

**Random assignment (calculate once):** `once(if(random() < 0.5, 'treatment', 'control'))`

**Full expression reference**: [`references/expressions.md`](references/expressions.md). Live documentation: [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html).

## Working with XLSForm .xlsx files

This section applies regardless of which file-tooling path you're using (SurveyCTO MCP server, generic xlsx tool, or describing edits in prose for the user to apply). The rules are the same; only the mechanism differs. When MCP tools are connected, use this section to plan and validate edits, but apply the edits through `xls_apply_patches` and export through `export_xlsform`.

### CRITICAL: Always start from the template

Every new XLSForm **must** start from the bundled template at [`assets/xlsform-template.xlsx`](assets/xlsform-template.xlsx).

**How to use the template:**
1. Make a literal file copy from `assets/xlsform-template.xlsx` to the output path (for example, `cp assets/xlsform-template.xlsx <output_path>` in a Unix shell; resolve `assets/` relative to the skill's root directory). Do not regenerate the file.
2. If MCP tools are available, pass the copied file to `start_xlsform_session` via the upload URL flow and apply edits with `xls_apply_patches`.
3. If MCP tools are unavailable, open the copied file and edit it in place — add your content into the existing worksheets.

**Never do any of the following:**
- Do NOT create a new `.xlsx` file from scratch.
- Do NOT create new worksheets and build the structure yourself.
- Do NOT delete and recreate worksheets from the template.
- Do NOT "rebuild" the form "properly" — the template IS the proper starting point.

#### Anti-pattern: building the workbook from scratch

Never run any of these for a new form:

- `from openpyxl import Workbook; wb = Workbook()` (or any other code that constructs a fresh workbook object and adds `survey`/`choices`/`settings` sheets to it)
- `pandas.ExcelWriter(<new_path>)` or `pandas.DataFrame.to_excel(<new_path>)` against a path that doesn't already contain the template's contents
- `libreoffice --headless --convert-to xlsx` starting from a non-template source
- Writing XLSX bytes directly (zipfile + `xl/worksheets/*.xml`)

These produce a technically valid but unusable form: no conditional formatting, no `help-survey`/`help-choices`/`help-settings` sheets, no `caseid` row, no hidden audit calculations, no reusable `yesno` choice list, no auto-updating `version` formula, and no color-coded row styling. The user has to redo the work in Excel by hand. Copy `assets/xlsform-template.xlsx` instead — this is true even when MCP tools are unavailable and you fall back to `openpyxl` for editing. The fallback is for *editing*, not for *creation from scratch*.

#### Workflow: create a new form

Follow these steps in order:

1. Make a literal file copy from `assets/xlsform-template.xlsx` to the output path. Do not create a new workbook object, generate worksheets, or convert from another source.
2. If MCP tools are available, read [`references/mcp.md`](references/mcp.md), then upload the copied file via `start_xlsform_session`. If MCP is unavailable, open the copied workbook directly with the best available spreadsheet/XLSX tooling.
3. Read the starting structure fully before editing. With MCP, use the returned `form_summary`; without MCP, inspect the workbook sheets directly. Note next append location, exact column names already present, existing reusable choice lists, and current settings values.
4. Apply related edits in one batch. With MCP, use a single `xls_apply_patches` call and `change_setting` for `form_id`, `form_title`, and `default_language`; without MCP, write directly into the copied workbook's existing worksheets.
5. Export or save the result. With MCP, use `export_xlsform` and hand the `download_url` to the user. Remind the user to attach any required `.fieldplugin.zip` files in the SurveyCTO console at upload time.

**Why the template is mandatory:** It contains conditional formatting rules, help worksheets, column headers, starter metadata fields, formula-based versioning, and pre-formatted rows that cannot be reliably recreated programmatically. Skipping the template produces files that are technically valid but painful for humans to edit in Excel.

The template provides:
- **survey** worksheet with correct column headers and starter metadata fields, including hidden audit calculations and a `caseid` row
- **choices** worksheet with headers and a `yesno` choice list
- **settings** worksheet with headers and an auto-updating `version` formula
- **help-survey**, **help-choices**, **help-settings** worksheets with reference documentation
- Conditional formatting rules that color-code rows by field type

### Editing rules (apply to every path)

- **Preserve all existing worksheets** — including `help-survey`, `help-choices`, `help-settings` and any other sheets present in the template or existing form.
- **Preserve existing formatting** — do not clear or overwrite conditional formatting, column widths, or cell styles.
- **Only write to rows that contain or will contain data.** Don't touch unused rows below your content; don't write empty strings or `None` to clear already-empty cells.
- **Append new rows after existing data.** Do not assume a fixed starter-row count — the template ships with several pre-populated metadata and calculation rows (including hidden audit calculations and a `caseid` row), and an existing form may have any number of rows. With MCP, `add_row` appends automatically; you do not need to compute a row index, but you can derive one from `form_summary` (`counts.n_rows`, or the largest `excel_row` in `survey_preview_rows`) or by paging `xls_get_rows` if you need it. Without MCP, scan the workbook for the first row in `survey` (and `choices`) where `type`/`list_name` and the surrounding columns are all empty, and append there.
- **Don't overwrite the `version` cell** in `settings` — it contains an auto-updating formula. (The MCP server's `export_xlsform` recalculates this for you.)
- **Use plain labels by default.** SurveyCTO does not render Markdown in labels, hints, notes, or messages. Prefer plain text; use simple inline HTML only when it materially helps. See [Label, Hint, And Message Formatting](references/xlsform.md#label-hint-and-message-formatting).

### Editing workflow

1. **Start from the right base** — copy the template (new forms) or load the existing workbook.
2. **Read the existing structure** so you know what's there.
   - With MCP available: upload first with `start_xlsform_session`, then use the returned `form_summary` as the starting overview. Call `xls_get_rows` only when you need more detail than the summary provides.
   - Without MCP: open and read all three sheets.
3. **Plan the edits** — identify the rows to add/modify and the cell values.
4. **Apply** — write cell values into the appropriate rows and columns.
   - With MCP available: `xls_apply_patches`.
   - Without MCP: write cells directly.
5. **Validate** against the checklist below.
6. **Save / export** — with MCP available, `export_xlsform` runs formula recalculation and returns the file; without MCP, save the workbook and use the best available recalculation path.

### Common operations

- **Add a field**: write `type`, `name`, and `label` (at minimum) into the next empty row in `survey`. Place it in the correct position relative to groups and repeats.
- **Add a choice list**: write `list_name`, `value`, `label` rows in `choices`. Ensure `list_name` matches what's referenced in the `select_one`/`select_multiple` type.
- **Add a group**: `begin group` row and matching `end group` row with the same `name`. Place fields between them.
- **Add a repeat**: `begin repeat` / `end repeat` rows with matching `name`. Set `repeat_count` if needed.
- **Add skip logic**: write the expression into the `relevance` column on the target row.
- **Add a constraint**: write the expression into `constraint` (use `.` for current value); write a user-facing message into `constraint message`.
- **Add a calculation**: row with `type=calculate`, unique `name`, expression in `calculation`.
- **Update settings**: with MCP, use `change_setting` for `form_title`, `form_id`, and `default_language`. Without MCP, write those values into row 2 of `settings`. Leave `version` alone.

### Validation checklist

After editing, verify:

- [ ] All `name` values are unique across the entire form
- [ ] No `name` contains spaces or special punctuation
- [ ] Every `begin group` has a matching `end group` (same `name`)
- [ ] Every `begin repeat` has a matching `end repeat` (same `name`)
- [ ] Groups and repeats are properly nested (no overlapping)
- [ ] Every `select_one [list]` / `select_multiple [list]` references a list that exists in `choices`
- [ ] Every choice list has at least one row with a `value` and `label`
- [ ] `${fieldname}` references in expressions point to fields that exist
- [ ] Expressions use SurveyCTO conventions (`=` not `==`, `index()` not `position()`, etc.)
- [ ] Labels, hints, notes, and messages use plain text or simple inline HTML fragments, not Markdown
- [ ] `settings` has `form_title` and `form_id`
- [ ] Every `custom-<name>` appearance in the form has a corresponding `<name>.fieldplugin.zip` that the user will attach to the form
- [ ] When handing the form back to the user, **explicitly remind them to attach every required `.fieldplugin.zip` in the SurveyCTO console at upload time.** The skill and MCP server only edit local files; they do not upload or attach anything for the user

## Dataset XML definitions

Dataset definitions are XML files with a `<dataset>` root element. They define column structure, form attachments, and publishing rules.

### Key elements

| Element | Purpose |
| --- | --- |
| `<id>` | Dataset ID used in `pulldata()` and `search()` calls |
| `<title>` | Display name |
| `<datasetType>` | `SERVER`, `CLIENT`, or `REPORT` |
| `<fieldNames>` | Comma-separated column names/order |
| `<formLinks>` | Forms that attach this dataset for pre-loading |
| `<dataLinks>` | Publishing rules (incoming from forms, outgoing to files) |
| `<caseManagementOptions>` | Case management display and workflow config |
| `<uniqueRecordField>` | Column used as unique key for upserts |

### Critical notes

- Element names are **case-sensitive** (e.g., `otherUserCode`, not `otherUsercode`).
- Forms in `<formLinks>` and `<dataLinks>` must be deployed before uploading the definition.
- `<showColumnsWhenTable>` contains multiple `<columnNames>` child elements, not a comma-separated string.

**Full reference**: [`references/datasets-xml.md`](references/datasets-xml.md).

## Data Explorer workbook definitions

Data Explorer workbooks are XLSX files with four worksheets: `summaries`, `settings`, `global_filters`, `global_exclusions`.

The `summaries` worksheet defines visualizations. Each row is a summary with a `type` (`text`, `categorical`, `numeric`, `temporal`, `scatterplot`, `crosstab`, …) and a `field` reference. Groups use `begin group` / `end group` with matching `label` values.

**Full reference**: [`references/data-explorer.md`](references/data-explorer.md).

## Field plug-ins

A field plug-in is a `.fieldplugin.zip` bundle (HTML/CSS/JS at the zip root) that takes over the rendering of a single form field. Plug-ins are supported only on `text`, `integer`, `decimal`, `select_one`, and `select_multiple` fields, and they run inside SurveyCTO Collect (Android), SurveyCTO Collect for iOS, and web forms.

### When to use a field plug-in

Default to native field types and appearances. Plug-ins add real cost — attachment management, version bumps, aggressive caching, and cross-platform (Android/iOS/web) testing — so reach for them only when a native field can't deliver the needed behavior or UX. Decide in this order:

1. **Native fields and appearances first.** Most needs are met by built-in `type`/`appearance` combinations.
2. **Use as-is from the [field plug-in catalog](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog).** If a maintained catalog plug-in already does what's needed, attach it without authoring anything.
3. **Customize an existing plug-in.** Download the closest catalog plug-in or SurveyCTO `baseline-*` repo as a ZIP from GitHub (`Code → Download ZIP`), or clone/fork it if the user is comfortable with Git, then edit the four files at the bundle root.
4. **Start from the bundled template.** [`assets/field-plugin-template/`](assets/field-plugin-template/) is an intentionally minimal text-only skeleton — useful for an offline starting point or the smallest possible reading surface, but it omits several behaviors that `baseline-text` ships (see *What the bundled template omits* in [`references/field-plugins.md`](references/field-plugins.md)). Add those back manually if you need them.

**Agent behavior rule:** when a form could benefit from a plug-in, present the trade-offs (added complexity vs. functionality/UX gained) and confirm with the user before adding any plug-in dependency. Unless the user has explicitly directed plug-in use, do not add `custom-<name>` appearances or attach `.fieldplugin.zip` files unilaterally.

### Use an existing plug-in in a form

1. Attach the `.fieldplugin.zip` to the form (Form Designer → Attachments, or as a regular form attachment when uploading the XLSForm).
2. On the field, set `appearance` to `custom-<filenamestem>` — the part of the zip filename before `.fieldplugin.zip`, e.g. `myplugin.fieldplugin.zip` → `custom-myplugin` — with optional `(key=value, …)` parameters.

### Authoring (when the user wants to build a plug-in)

Follow the decision order above. Concretely:

- **Preferred starting point:** download the closest **SurveyCTO baseline plug-in** for the field type (`baseline-text`, `baseline-integer`, `baseline-decimal`, `baseline-select_one`, `baseline-select_multiple`) — or a closely related catalog plug-in — as a ZIP from GitHub's *Code → Download ZIP* button, then customize it. If the user prefers a Git workflow, cloning or forking works equally well; otherwise no Git tooling is required.
- **Minimal/offline alternative:** copy [`assets/field-plugin-template/`](assets/field-plugin-template/). It is original code, not a copy of `baseline-text`, and intentionally leaves out several baseline behaviors (media rendering, HTML-entity unescaping in label/hint, standard `numbers`/`numbers_decimal`/`numbers_phone` appearance handling, soft-keyboard invocation, default `placeholder` fallback, read-only display of empty values). See `references/field-plugins.md` for the full list.
- Edit the four files at the bundle root: `manifest.json`, `template.html`, `style.css`, `script.js`. Always use triple-brace Mustache for `{{{LABEL}}}` and `{{{HINT}}}` (they may contain HTML).
- Re-package as `<name>.fieldplugin.zip` with all files at the zip root (subdirectories get flattened on upload). Bump `manifest.version` on every re-upload.

### Testing

- **Local fast loop:** [`assets/field-plugin-test-harness/`](assets/field-plugin-test-harness/) ships `validate.mjs` (static checks) and `preview.html` (a single self-contained browser harness that renders the plug-in against editable fixtures with a stubbed host bridge). The harness works as an inline HTML/JS artifact in agent UIs that support them — pre-populate the textareas with the plug-in source and update them as the plug-in evolves.
- **Final validation:** the in-product **field plug-in console** in the form designer's test view. Required before deployment; the local harness's stubs are not a complete substitute for real Android/iOS/web form runtimes.

For everything else — full manifest schema, form API (field properties, runtime CSS classes, provided/called JS functions), parameters and metadata model, Android-only intent and phone APIs, and common pitfalls — see [`references/field-plugins.md`](references/field-plugins.md).

## Common patterns

### Cascading selects

Filter choices in one field based on the selection in another:

1. In `choices`, add a `filter` column (e.g., `region`) to the child list.
2. In `survey`, set `choice_filter` on the child field: `region = ${region}`.

### Pre-loaded data lookup with `pulldata()`

1. Create a `CLIENT` dataset with the lookup data.
2. Attach it to the form via `<formLinks>` in the dataset definition.
3. Use `pulldata('dataset_id', 'column_to_return', 'lookup_column', ${key_field})` in a `calculation`.

### Dynamic select list from pre-loaded data

1. Create a `CLIENT` dataset and attach it to the form.
2. In `survey`, set `type` to `select_one listname` and `appearance` to `search('dataset_id')` (or a more specific search expression).
3. In `choices`, add one row for `listname` where `value` and `label` contain column names from the dataset (not literal values).

See [`references/xlsform.md`](references/xlsform.md) for `search()` syntax patterns.

### Random sampling from a repeat group

1. Inside the repeat: `calculate` field with `calculation = once(random())`.
2. Outside the repeat: `rank-index(1, ${random_calc})` returns the index of the randomly-selected instance.

### Use a custom field plug-in

Before adding a plug-in to a form, confirm with the user that the added complexity is worth the gained functionality, and remind them they will need to attach the `.fieldplugin.zip` themselves when uploading the form.

Attach the `.fieldplugin.zip` to the form, then set `appearance` on the field to `custom-<filenamestem>` with any parameters the plug-in expects. The `<filenamestem>` is the part of the zip filename before `.fieldplugin.zip` (for example, `phonenumber.fieldplugin.zip` → `custom-phonenumber`). The `name` field inside `manifest.json` is a human-readable display name and does **not** drive the appearance.

| type | name | appearance |
| --- | --- | --- |
| `text` | `phone` | `custom-phonenumber(country='US', placeholder=${default_format})` |

Parameter values are evaluated by the form before the plug-in loads, so `${field}` references and full SurveyCTO expressions work. In the plug-in, read parameters with `getPluginParameter('country')` rather than indexing `fieldProperties.PARAMETERS`. Full reference: [`references/field-plugins.md`](references/field-plugins.md).

### Publishing form data to a dataset

In the dataset XML, add a `<dataLink>` with:

- `<dataLinkClass>FORM</dataLinkClass>`
- `<dataLinkType>INCOMING</dataLinkType>`
- `<linkObjectId>form_id</linkObjectId>`
- `<fieldMap>` with JSON mapping form fields to dataset columns

## Debugging common issues

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Form won't upload | Duplicate `name` values | Search for duplicates in the `name` column |
| Form won't upload | Unbalanced groups/repeats | Check every `begin`/`end` pair |
| Field never appears | Incorrect `relevance` expression | Verify syntax; verify referenced fields exist |
| Constraint never passes | Wrong use of `.` vs `${fieldname}` | In constraints, `.` is the current field; `${fieldname}` is another field |
| Choices missing | `list_name` mismatch | `select_one [list]` must match a `list_name` in `choices` |
| `select_multiple` logic fails | Using `=` instead of `selected()` | Always use `selected(${field}, 'value')` |
| Date comparison fails | Comparing string to date | Wrap with `date()`: `${field} > date('2024-01-01')` |
| Dataset won't upload | Referenced form not deployed | Deploy all forms in `<formLinks>` and `<dataLinks>` first |
| Dataset element ignored | Case-sensitivity error | Check exact casing (e.g., `otherUserCode`) |
| Plug-in field doesn't appear / `custom-<name>` ignored | Plug-in `.fieldplugin.zip` not attached, name mismatch, or unsupported field type | Re-attach the zip; confirm the `custom-<name>` token matches the **`.fieldplugin.zip` filename stem** (e.g. `myplugin.fieldplugin.zip` → `custom-myplugin`), not `manifest.name`; plug-ins only work on `text`/`integer`/`decimal`/`select_one`/`select_multiple` |
| Plug-in answer not saved | `setAnswer` not called, or `select_multiple` value joined with commas | Wire input events to `setAnswer(value)`; for `select_multiple`, pass a **space**-separated list |
| Plug-in attachments 404 at runtime | Files placed in subdirectories inside the zip | Flatten the zip — every file at the root, no duplicate basenames |

## References

| Primer | When to read |
| --- | --- |
| [`references/overview.md`](references/overview.md) | First — orientation, file types, how they fit together |
| [`references/xlsform.md`](references/xlsform.md) | Editing or debugging an XLSForm — full mechanics |
| [`references/expressions.md`](references/expressions.md) | Any expression work (relevance, constraint, calculation, choice_filter) |
| [`references/datasets-xml.md`](references/datasets-xml.md) | Server dataset XML definitions |
| [`references/data-explorer.md`](references/data-explorer.md) | Data Explorer dashboards |
| [`references/field-plugins.md`](references/field-plugins.md) | Field plug-in authoring, packaging, form API, and testing |

## Key documentation links

- [Designing forms: core concepts](https://docs.surveycto.com/02-designing-forms/01-core-concepts/)
- [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html)
- [Grouping and repeating questions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html)
- [Using constraints to validate responses](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html)
- [Implementing skip patterns with relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html)
- [Introduction to advanced dataset usage](https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/01.datasets-intro.html)
- [Working with server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461)
- [Advanced use of Data Explorer workbooks](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html)
- [Using field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html)
- [Field plug-in developer documentation (GitHub)](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/developer-docs-home.md)
- [SurveyCTO Support Center](https://support.surveycto.com)
