---
name: surveycto
description: >
  Design, edit, and debug SurveyCTO forms (XLSForm .xlsx files) and server
  datasets (XML definition files). Covers form logic, expressions, choice
  lists, repeat groups, skip patterns, constraints, calculations, dataset
  publishing, case management, and Data Explorer workbook definitions. Use
  when the user mentions SurveyCTO, XLSForm, ODK-based forms, survey forms,
  or data collection forms, or when working with .xlsx files that contain
  survey/choices/settings worksheets, XML files with dataset root elements,
  or Excel workbook definitions for data monitoring dashboards.
license: Apache-2.0
metadata:
  author: SurveyCTO
  version: "1.0"
---

# SurveyCTO Form and Dataset Authoring

SurveyCTO is a mobile data collection platform built on the XLSForm and ODK standards, with platform-specific extensions and divergences. This skill provides SurveyCTO domain expertise for the three definition file types you may encounter:

1. **XLSForm form definitions** (`.xlsx`) — survey instruments
2. **Dataset definitions** (`.xml`) — server dataset structure and publishing rules
3. **Data Explorer workbook definitions** (`.xlsx`) — monitoring dashboards

For a high-level orientation, read [`references/overview.md`](references/overview.md) first.

## Identifying SurveyCTO files

| File type | Format | How to recognize |
| --- | --- | --- |
| XLSForm | `.xlsx` | Worksheets named `survey`, `choices`, `settings` |
| Dataset definition | `.xml` | Root element `<dataset>` with `<definition>` child |
| Data Explorer workbook | `.xlsx` | Worksheets named `summaries`, `settings`, `global_filters`, `global_exclusions` |

## Tools you may have available

This skill is fully usable with no special tools — you have enough SurveyCTO knowledge embedded here and at the live documentation links to advise the user, describe edits in prose, and reason about forms. If additional tools are present, use them in the priority order below.

**Tool-selection rule for XLSForm work:** if the SurveyCTO MCP server tools are connected, you MUST use them for nontrivial XLSForm inspection, editing, validation, and export. Do not choose generic `bash`, `python`, `openpyxl`, LibreOffice, or spreadsheet tooling as the primary authoring path when SurveyCTO MCP tools are available. Generic tooling is only a fallback if MCP tools are unavailable, disconnected, or return an unrecoverable error.

### SurveyCTO MCP server (preferred when available)

The **SurveyCTO MCP server** is a public, no-auth MCP server that gives you capabilities specifically built for this domain. It is the primary tool path for nontrivial XLSForm work and current SurveyCTO knowledge-base lookup.

**Endpoint** (Streamable HTTP transport, stateless, no auth): `https://assistant-be.surveycto.net/mcp`

stdio-only clients can wrap with `mcp-remote`:

```json
{
  "surveycto": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://assistant-be.surveycto.net/mcp"]
  }
}
```

If the user is editing XLSForms or asking factual SurveyCTO questions and the MCP server isn't connected, mention that it exists, name the production URL, and offer to walk them through installing it. Don't insist; the skill works without it.

In agent environments where tools must be loaded or selected before use, search/load tools matching `surveycto`, `xlsform`, or the raw tool names below. Names may be namespaced by the host (for example, `mcp__surveycto__start_xlsform_session`), but the operation names are the same.

#### Tool surface

| Tool | When to use |
| --- | --- |
| `get_surveycto_mcp_capabilities` | First call when unsure. Returns the canonical tool list, recommended workflows, available primer topics, server version, recalc availability, and the concurrency contract. |
| `kb_search(query, top_k=5)` | Any factual SurveyCTO question. Searches `www.surveycto.com`, `docs.surveycto.com`, `support.surveycto.com`. Returns `{title, url, excerpt}` hits. `top_k` capped at 20. **Quote source URLs in answers.** |
| `get_surveycto_primer(topic)` | Available primers at server-side: `overview`, `xlsform`, `expressions` (full set in the discovery payload's `available_primer_topics`). Mostly useful for callers without the skill installed; you already have these locally. |
| `start_xlsform_session(xlsx_base64?, original_filename?)` | Caller wants to inspect or edit an XLSForm. **Recommended: omit `xlsx_base64` first.** The server returns a short-lived `upload_url` and `curl_example`; upload with `curl -F file=@form.xlsx '<upload_url>'`. The upload response returns `session_id`, `expires_at`, `current_version`, `size_bytes`, `original_filename`, `form_summary`, `warnings`, `recommended_next_actions`. Use inline `xlsx_base64` only for small files when it will not burn model context. **Use the returned `form_summary` for orientation before paging rows.** |
| `get_xlsform_summary(session_id)` | Resuming an existing session (new agent context, after a long gap). Read-only and cheap. Returns the same `form_summary` shape plus `current_version` and `expires_at`. |
| `xls_get_rows(session_id, sheet, where?, order_by?, start, limit, columns?, expand?, …)` | Inspect rows. `limit` capped at 100. Use `expand=["choices","deps_in","deps_out","expressions_refs","groups_enclosing","deps_in_closure","deps_out_closure"]` as needed. Read-only; safe to call in parallel. |
| `xls_get_row(session_id, sheet, excel_row, columns?, expand?, …)` | Fetch one row by 1-based Excel row number. Same expand options. |
| `xls_apply_patches(session_id, patches, validate_only=false, return_form_summary=true, include_details=true)` | Make edits. Batch all related edits into one call. See `xls_apply_patches` details below for op-to-sheet rules, settings edits, column aliases, output-size flags, and dry-run behavior. |
| `export_xlsform(session_id, version?, format="resource")` | Get the workbook back. Default `format="resource"` returns an `xlsform://{session_id}/{version}` URI, a formal `resource_link`, and an HTTPS `download_url` with `curl_example`. Prefer the `download_url` or resource link. Do **not** use `format="base64"` for real workbooks; it is only for tiny compatibility cases. **Recalc only runs when `version >= 2`** (post-edit); `version == 1` returns the original upload unchanged with `recalc.status="skipped"`. |
| `end_xlsform_session(session_id)` | Optional explicit cleanup. Usually skip it and let the session expire by TTL so `download_url` / resource links remain usable for follow-up requests. Idempotent. |

Resource: `xlsform://{session_id}/{version}` — read with `resources/read` for the recalculated bytes (or unchanged upload at version 1). `export_xlsform` also returns an HTTPS `download_url` tied to the session TTL; once the session expires, the server rejects the URL. Download it or hand it off before TTL expiry. MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

##### `xls_apply_patches` Details

- **Batching:** Batch related edits into one call and serialize calls per `session_id`.
- **Patch ops:** Supported ops are `add_row`, `edit_row`, `delete_row`, `rename` (kinds: `field`, `group`, `list`, `language`, `column`), `change_setting`, and `delete_column`.
- **Allowed sheets:** Use `add_row`, `edit_row`, and `delete_row` only for `survey` and `choices`.
- **Settings:** Use `change_setting` for row-2 settings such as `form_title`, `form_id`, and `default_language`; do not use `edit_row` on `settings`.
- **Column aliases:** The server normalizes common aliases such as `constraint_message` -> `constraint message`, `required_message` -> `required message`, `read_only` -> `read only`, and `relevant` -> `relevance`.
- **Unknown columns:** Review `unknown_column_added` warnings. Custom/plugin columns can be intentional, but most accidental new columns are misspellings.
- **Large batches:** Set `return_form_summary=false` and `include_details=false`, then call `get_xlsform_summary` only when you need a fresh summary.
- **Dry runs:** Use `validate_only=true` for risky changes.

#### Recommended workflow

1. **First call (or when unsure)**: `get_surveycto_mcp_capabilities` to learn the current tool list and primer topics.
2. **Factual SurveyCTO questions**: `kb_search` → quote the returned URLs in your answer.
3. **Create, inspect, or edit an XLSForm**:
   1. Start from the bundled template for new forms, or from the user's existing workbook. For a new form, copy the template to the output path, then immediately upload that copy into an MCP session. Do not inspect or mutate the template workbook before uploading unless MCP tools are unavailable.
   2. `start_xlsform_session` (or `get_xlsform_summary` if resuming an existing `session_id`) → for a local file, omit `xlsx_base64`, run the returned `curl_example`, then store the `session_id` from the upload response. The upload response includes `form_summary`; read it carefully before making follow-up row queries.
   3. **Take a starting inventory from `form_summary` before patching or paging rows.** Explicitly note the existing starter rows and next append location; exact survey and choices column names already present; existing choice lists and stored values (especially reusable lists such as `yesno`); settings values (`form_id`, `form_title`, `default_language`, `version`); template metadata/calculation rows; and any `errors` or warnings. Do not assume column spellings or choice values from memory. Reuse existing columns/lists where appropriate, or intentionally change them before writing dependent expressions.
   4. `xls_get_rows` / `xls_get_row` to inspect the rows you intend to touch. Parallel calls are fine.
   5. `xls_apply_patches` — **batch all related edits into one call**. Use `validate_only=true` on the full batch before committing risky or large changes. For new forms, add survey rows and choices with `add_row`; update settings with `change_setting` rather than `edit_row`; do not edit the `.xlsx` with Python when MCP is available. For large batches, set `return_form_summary=false` and `include_details=false`, then call `get_xlsform_summary` only when you need a fresh summary.
   6. `export_xlsform` → hand the resulting `download_url`/`curl_example` or resource link back to the user. The server handles XLSX preservation and formula recalculation. Avoid `format="base64"` for real workbooks.
   7. Usually leave the session open until TTL expiry. Only call `end_xlsform_session` if the user explicitly wants server-side cleanup and no further downloads/follow-up edits are needed.

#### Concurrency contract

- Reads run in parallel.
- `xls_apply_patches` **must** be serialized per `session_id`. Always batch related edits into a single call rather than firing off multiple patch calls.
- On collision the server returns a `session_conflict` error and does **not** auto-retry. Reload state with `get_xlsform_summary` (or `xls_get_rows` for the relevant sheet), re-derive the user's intent against the new state, and re-issue a single batched patch.

#### Error envelope

Tool responses use `{"error": {"code": str, "message": str, "data": {...}}}`. React per code:

| Code | Reaction |
| --- | --- |
| `session_not_found` | Session is invalid or expired (TTL 24 h). Tell the user; do not retry. Start a fresh session if they want to continue. |
| `session_conflict` | Concurrent write collision. Reload state and re-derive intent (see concurrency contract above). |
| `xlsx_too_large` | Input exceeds 50 MB. Ask the user to slim the workbook. |
| `invalid_xlsform` | Input is not a valid XLSForm (bad ZIP, missing sheets, etc.). Surface the message; suggest starting from the bundled template. |
| `recalc_environment_broken` | Server-side misconfiguration. Surface to the user/operator; not recoverable client-side. |
| `primer_not_found` | Unknown primer topic. Re-check `available_primer_topics` from discovery. |
| `tool_error` | Internal failure. Safe to retry once, then bail and report. |

#### Limits worth remembering

- XLSForm upload: 50 MB.
- Session TTL: 24 h (check `expires_at` from start/summary).
- `xls_get_rows.limit`: 100 max — page through larger sheets.
- `kb_search.top_k`: 20 max.

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
1. Copy `assets/xlsform-template.xlsx` to the desired output path.
2. If MCP tools are available, pass the copied file to `start_xlsform_session` via the upload URL flow and apply edits with `xls_apply_patches`.
3. If MCP tools are unavailable, open the copied file and edit it in place — add your content into the existing worksheets.

**Never do any of the following:**
- Do NOT create a new `.xlsx` file from scratch.
- Do NOT create new worksheets and build the structure yourself.
- Do NOT delete and recreate worksheets from the template.
- Do NOT "rebuild" the form "properly" — the template IS the proper starting point.

**Why the template is mandatory:** It contains conditional formatting rules, help worksheets, column headers, starter metadata fields, formula-based versioning, and pre-formatted rows that cannot be reliably recreated programmatically. Skipping the template produces files that are technically valid but painful for humans to edit in Excel.

The template provides:
- **survey** worksheet with correct column headers and starter metadata fields (`start`, `end`, `deviceid`, `phonenumber`)
- **choices** worksheet with headers and a `yesno` choice list
- **settings** worksheet with headers and an auto-updating `version` formula
- **help-survey**, **help-choices**, **help-settings** worksheets with reference documentation
- Conditional formatting rules that color-code rows by field type

### Editing rules (apply to every path)

- **Preserve all existing worksheets** — including `help-survey`, `help-choices`, `help-settings` and any other sheets present in the template or existing form.
- **Preserve existing formatting** — do not clear or overwrite conditional formatting, column widths, or cell styles.
- **Only write to rows that contain or will contain data.** Don't touch unused rows below your content; don't write empty strings or `None` to clear already-empty cells.
- **Append new rows after existing data.** Do not assume a fixed starter-row count — the template ships with several pre-populated metadata/calculation rows (`start`, `end`, `deviceid`, `phonenumber`, `username`, `device_info`, `duration`, `caseid`) and an existing form may have any number of rows. With MCP, `add_row` appends automatically; you do not need to compute a row index, but you can derive one from `form_summary` (`counts.n_rows`, or the largest `excel_row` in `survey_preview_rows`) or by paging `xls_get_rows` if you need it. Without MCP, scan the workbook for the first row in `survey` (and `choices`) where `type`/`list_name` and the surrounding columns are all empty, and append there.
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

## References

| Primer | When to read |
| --- | --- |
| [`references/overview.md`](references/overview.md) | First — orientation, file types, how they fit together |
| [`references/xlsform.md`](references/xlsform.md) | Editing or debugging an XLSForm — full mechanics |
| [`references/expressions.md`](references/expressions.md) | Any expression work (relevance, constraint, calculation, choice_filter) |
| [`references/datasets-xml.md`](references/datasets-xml.md) | Server dataset XML definitions |
| [`references/data-explorer.md`](references/data-explorer.md) | Data Explorer dashboards |

## Key documentation links

- [Designing forms: core concepts](https://docs.surveycto.com/02-designing-forms/01-core-concepts/)
- [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html)
- [Grouping and repeating questions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html)
- [Using constraints to validate responses](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html)
- [Implementing skip patterns with relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html)
- [Introduction to advanced dataset usage](https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/01.datasets-intro.html)
- [Working with server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461)
- [Advanced use of Data Explorer workbooks](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html)
- [SurveyCTO Support Center](https://support.surveycto.com)
