# SurveyCTO MCP server reference

Detailed reference for the SurveyCTO MCP server tools, patch semantics, concurrency, errors, and limits. Read this when you are using the MCP server to inspect or edit XLSForms, or when an MCP call returns an error you need to interpret.

For the high-level workflow and the template-first rule, see `SKILL.md`. The workflow there (`Workflow: create a new form`) is the entry point; this file is the deep dive.

## Contents

- Endpoint and client setup
- Preflight: verify upload egress before real work
- Tool surface
- Filter AST and expand options (`xls_get_rows` / `xls_get_row`)
- `xls_apply_patches` details (including patch op shapes)
- Concurrency contract
- Error envelope
- Limits worth remembering
- Worked examples

## Endpoint and client setup

Streamable HTTP transport, stateless, no auth: `https://assistant-be.surveycto.net/mcp`

stdio-only clients can wrap with `mcp-remote`:

```json
{
  "surveycto": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://assistant-be.surveycto.net/mcp"]
  }
}
```

In agent environments where tools must be loaded or selected before use, search/load tools matching `surveycto`, `xlsform`, or the raw tool names below. Names may be namespaced by the host (for example, `mcp__surveycto__start_xlsform_session`), but the operation names are the same.

## Preflight: verify upload egress before real work

The XLSForm session tools depend on outbound HTTPS to `assistant-be.surveycto.net` for both upload and download of XLSForm files with `curl`. In hosted sandboxes — most notably **Claude Cowork** — this egress is blocked by default and must be allowlisted by the user. Without it you can still call tools that don't transfer files (`get_surveycto_mcp_capabilities`, `kb_search`, `get_surveycto_primer`), but you cannot upload a workbook — which means you cannot meaningfully edit XLSForms.

**Before doing XLSForm work, run a one-shot upload check:**

1. Call `start_xlsform_session` with no arguments to get an `upload_url`.
2. Upload the bundled template using the returned `curl_example`: `curl -sS -F file=@assets/xlsform-template.xlsx <upload_url>`.
3. If the upload returns a `session_id` and `form_summary`, you're good — call `end_xlsform_session` to clean up and proceed with real work.

If the upload fails with a network error, **stop and resolve egress before continuing.** Tell the user:

- Working MCP upload/download is effectively required for usable XLSForm editing — the fallbacks below are substantially worse and likely to frustrate.
- If the SurveyCTO MCP server isn't installed yet, install it.
- If it's installed but egress is blocked, follow [`install.md`](install.md) in this skill (look for "Network egress") to allow outbound HTTPS to `*.surveycto.net`. In Cowork, the user might then need to **start a new chat** — egress changes don't reliably apply to in-progress chats.

Only proceed with the fallbacks below if the user has explicitly chosen to continue without working MCP egress and accepts a degraded experience.

### Fallbacks (avoid; document the trade-off to the user)

- **Inline `xlsx_base64` transport is not a workable substitute.** The server accepts it, but a real XLSForm encoded as base64 is too large to round-trip through agent tool-call parameters: the bundled 154 KB template alone becomes ~205 KB of base64 (~195K tokens), which exceeds typical agent read/parameter limits. Do not attempt to use inline base64 to work around blocked egress.
- **Generic spreadsheet tooling** (Python `openpyxl`, LibreOffice headless, etc.) can read and write cells but round-trips the SurveyCTO XLSForm template poorly — conditional formatting, formula recalculation state, help worksheets, named styles, and row coloring are commonly lost or corrupted. The user typically has to repair formatting by hand in Excel after every export. Use only if the user has explicitly chosen to proceed without MCP and has been warned.

The correct fix is almost always to unblock MCP egress, not work around it. Steer the user there first.

## Tool surface

| Tool | When to use |
| --- | --- |
| `get_surveycto_mcp_capabilities` | First call when unsure. Returns the canonical tool list, recommended workflows, available primer topics, server version, recalc availability, and the concurrency contract. |
| `kb_search(query, top_k=5)` | Any factual SurveyCTO question. Searches `www.surveycto.com`, `docs.surveycto.com`, `support.surveycto.com`. Returns `{title, url, excerpt}` hits. `top_k` capped at 20. **Quote source URLs in answers.** |
| `get_surveycto_primer(topic)` | Available primers at server-side: `overview`, `xlsform`, `expressions` (full set in the discovery payload's `available_primer_topics`). Mostly useful for callers without the skill installed; you already have these locally. |
| `start_xlsform_session(xlsx_base64?, original_filename?)` | Caller wants to inspect or edit an XLSForm. **Always use the upload URL flow** — omit `xlsx_base64`; the server returns a short-lived `upload_url` and `curl_example`, and you upload with `curl -F file=@form.xlsx '<upload_url>'`. The upload response returns `session_id`, `expires_at`, `current_version`, `size_bytes`, `original_filename`, `form_summary`, `warnings`, `recommended_next_actions`. **Do not use inline `xlsx_base64` for real workbooks** — the bytes have to go through model context in both directions, and even the 154 KB bundled template (~205 KB base64, ~195K tokens) exceeds typical agent read/parameter limits. **Use the returned `form_summary` for orientation before paging rows.** |
| `get_xlsform_summary(session_id)` | Resuming an existing session (new agent context, after a long gap). Read-only and cheap. Returns the same `form_summary` shape plus `current_version` and `expires_at`. |
| `xls_get_rows(session_id, sheet, where?, order_by?, start, limit, columns?, expand?, survey_row_kind?, …)` | Inspect rows. `limit` capped at 100; response includes `more_results: bool`. `survey_row_kind` is `"all"` (default) \| `"fields"` (skip group/repeat markers) \| `"groups"` (only begin group/repeat rows; end row auto-attached). Use `expand=["choices","deps_in","deps_out","expressions_refs","groups_enclosing","deps_in_closure","deps_out_closure"]` as needed. See *Filter AST and expand options* below for details. Read-only; safe to call in parallel. |
| `xls_get_row(session_id, sheet, excel_row, columns?, expand?, …)` | Fetch one row by 1-based Excel row number (2 = first data row). Same expand options as `xls_get_rows`. For `begin group`/`begin repeat` rows, the response also includes `group_end_excel_row` and `group_end_row`. |
| `xls_apply_patches(session_id, patches, validate_only=false, return_form_summary=true, include_details=true)` | Make edits. Batch all related edits into one call. See `xls_apply_patches` details below. |
| `export_xlsform(session_id, version?, format="resource")` | Get the workbook back. Default `format="resource"` returns an `xlsform://{session_id}/{version}` URI, a formal `resource_link`, and an HTTPS `download_url` with `curl_example`. Prefer the `download_url` or resource link. Do **not** use `format="base64"` for real workbooks — it routes the full file through model context in the return value (a 150 KB workbook is ~195K tokens of base64, beyond typical agent read/parameter limits). **Recalc only runs when `version >= 2`** (post-edit); `version == 1` returns the original upload unchanged with `recalc.status="skipped"`. |
| `end_xlsform_session(session_id)` | Optional explicit cleanup. Usually skip it and let the session expire by TTL so `download_url` / resource links remain usable for follow-up requests. Idempotent. |

Resource: `xlsform://{session_id}/{version}` — read with `resources/read` for the recalculated bytes (or unchanged upload at version 1). `export_xlsform` also returns an HTTPS `download_url` tied to the session TTL; once the session expires, the server rejects the URL. Download it or hand it off before TTL expiry. MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## Filter AST and expand options

### Common read semantics

- **Sheets**: `"survey"` | `"choices"` | `"settings"`.
- **Ordering**: lexical (operands normalized to strings; `None` sorts as `""`). **Exception**: `excel_row` is always compared and sorted **numerically**, in every operator and in `order_by`. Default ordering is `excel_row` ascending.
- **Pagination**: `limit` capped at 100. `start` is a 0-based offset into the filtered/sorted result set (**not** an Excel row). The response's `more_results: bool` indicates whether further pages exist.
- **Projection (`columns`)**: when omitted, defaults are `{excel_row, name, type}` (survey) or `{excel_row, list_name, value}` (choices), plus all non-empty worksheet columns in header order. Request only what you need.
- **Fulltext virtual columns**: `labels_concat_lower` and `hints_concat_lower` are not worksheet columns but are addressable in filters and projection. They aggregate every `label`/`hint` (across all language columns) into one lowercased string each.
- **Fulltext defaults** (when `{"fulltext": ["pattern"]}` is used without naming fields): survey scans `name` + `labels_concat_lower` + `hints_concat_lower`; choices scans `name`/`value` + `labels_concat_lower`.

### Filter AST (`where.ast`)

| Shape | Meaning |
| --- | --- |
| `{"eq": ["field", "value"]}` | exact match (`field == value`) |
| `{"in": ["field", ["v1", "v2", ...]]}` | field matches any value in the list |
| `{"between": ["field", low, high, "inclusive"\|"exclusive"]}` | range filter |
| `{"regex": ["field", "(?i)pattern"]}` | regex match |
| `{"has": ["field"]}` | field has a non-null/non-empty value |
| `{"fulltext": ["(?i)pattern"]}` | search the sheet's default fulltext fields |
| `{"fulltext": [["f1","f2",...], "(?i)pattern"]}` | search specific fields |
| `{"and": [...]}`, `{"or": [...]}`, `{"not": expr}` | combinators |

All comparisons are lexical (operands stringified) **except** `excel_row`, which is always numeric.

### Expand options (survey only)

| Option | Meaning |
| --- | --- |
| `choices` | For each `select_one`/`select_multiple` seed, the matching `choices` rows. |
| `deps_out` | For each seed, fields it references in its expressions (`relevance`/`constraint`/`calculation`/`choice_filter`) — edges going **out**. |
| `deps_in` | For each seed, fields that reference it — edges coming **in**. |
| `deps_out_closure` / `deps_in_closure` | Transitive expansion across multiple levels. Use `expand_max_depth` and `expand_row_limit_per_seed` to bound breadth. |
| `expressions_refs` | Per expression slot, the parsed set of referenced field names. |
| `groups_enclosing` | Ancestor groups of each seed; project them with `groups_enclosing_columns`. |

`closure_include_group_dependencies` (default `true`) seeds closure traversal with enclosing group names too.

## `xls_apply_patches` details

- **Batching:** Batch related edits into one call and serialize calls per `session_id`.
- **Allowed sheets:** Use `add_row`, `edit_row`, and `delete_row` only for `survey` and `choices`.
- **Settings:** Use `change_setting` for row-2 settings — the patch-addressable keys are `form_id`, `form_title`, `default_language`, and `instance_name` ([submission-naming pattern](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/05.naming-forms.html)). Other settings columns (`public_key`, `submission_url`, etc.) cannot be set via `change_setting`. Do not use `edit_row` on `settings`. `change_setting` creates the `settings` sheet if it is missing.
- **No `add_column` or `move_row`:** There is no `add_column` op — write the new column name in `add_row` / `edit_row` `values` to create it (see *Implicit column creation* below). There is no `move_row` op either; row reordering is not supported. The nearest workaround is `delete_row` plus a fresh `add_row` at the target position, but you will lose any columns you don't re-specify.
- **`settings.version`:** Never patch it. The bundled template uses an auto-incrementing formula; `export_xlsform` recalculates it.
- **Row-index stability:** All `excel_row` and `insert_before_excel_row` values are interpreted against the **original sheet state at the start of the call**. The tool adjusts indices internally across deletes and inserts so later operations in the same call still refer to the intended original rows. This is why batching all related edits into one call is the correct pattern — issuing them across separate calls forces you to recompute indices yourself.
- **Implicit column creation:** When `add_row` or `edit_row` writes a column name that isn't an existing header, the tool creates the new column header immediately after the existing headers (a contiguous block). The response includes an `unknown_column_added` warning so you can review the result — most accidental new columns are misspellings, but custom/plug-in columns are legitimate.
- **Column aliases:** The server normalizes common aliases such as `constraint_message` -> `constraint message`, `required_message` -> `required message`, `read_only` -> `read only`, and `relevant` -> `relevance`.
- **Minimal edits:** Only the specific cells/headers needed are written; formatting, formulas, conditional formatting, and other workbook content are preserved.
- **Atomicity:** If any patch fails, no changes are saved and the call returns an error.
- **Large batches:** Set `return_form_summary=false` and `include_details=false`, then call `get_xlsform_summary` only when you need a fresh summary.
- **Dry runs:** Use `validate_only=true` for risky changes.

### Patch op shapes

```jsonc
{"op": "add_row", "sheet": "survey"|"choices",
 "values": {"col": "value", ...},
 "insert_before_excel_row": 5}            // optional; appends when absent

{"op": "edit_row", "sheet": "survey"|"choices",
 "excel_row": 7, "values": {"col": "value", ...}}

{"op": "delete_row", "sheet": "survey"|"choices", "excel_row": 7}

{"op": "rename", "kind": "field",    "old_name": "...", "new_name": "..."}
{"op": "rename", "kind": "group",    "old_name": "...", "new_name": "..."}
{"op": "rename", "kind": "list",     "old_list_name": "...", "new_list_name": "..."}
{"op": "rename", "kind": "language", "old_language": "...", "new_language": "..."}
{"op": "rename", "kind": "column",
 "sheet": "survey"|"choices"|"settings",
 "old_header": "...", "new_header": "..."}

{"op": "change_setting",
 "form_id": "...", "form_title": "...", "default_language": "...",
 "instance_name": "concat('R-', ${respondent_id})"}

{"op": "delete_column",
 "sheet": "survey"|"choices"|"settings", "header": "..."}
```

Notes on `rename`:

- `kind="field"` / `kind="group"` update `${name}` references throughout the survey sheet.
- `kind="list"` updates the `choices` sheet's `list_name` cells and the list name inside `select_one`/`select_multiple` types on the survey sheet.
- `kind="language"` updates language-suffixed headers across survey and choices, and updates `default_language` when applicable.
- **`new_language=""` is the suffix-stripping idiom**: it removes the language suffix entirely from all matching column headers (e.g. `label:English (en)` → `label`, not `label:`). Use this to clean up forms where the default language was mistakenly suffixed.
- `kind="column"` is a direct header rename with no semantic side effects; use when you need precise control on a single sheet.

When to use which:

- Use `rename kind=language new_language=""` to strip suffixes from **all** matching columns across survey and choices.
- Use `rename kind=column` to rename a single header on one sheet without semantic side effects.
- Use `delete_column` to completely remove a column and its data.

### Trust patch success; verify once at the end

The most expensive context drain on long XLSForm builds is not the patch responses themselves (those become cheap with `return_form_summary=false` and `include_details=false`) — it is the *anxiety loop* of re-fetching `get_xlsform_summary` and paging `xls_get_rows` after every batch to confirm the patch "really" applied. The server applies patches atomically; that confirmation is unnecessary and, on multi-form builds, has been the proximate cause of running out of context before file delivery.

- A successful `xls_apply_patches` response — no `error` field, an incremented `new_version`, no unexpected entries in `summary.warnings`, and per-op counts in `summary` (`rows_added`, `rows_edited`, `rows_deleted`, `columns_added`, `columns_renamed`, `columns_deleted`, `fields_renamed`, `groups_renamed`, `lists_renamed`, `languages_renamed`, `settings_changed`) that match what you sent — is sufficient confirmation that the server applied the batch atomically. The patches you sent are the patches in the workbook.
- All four success signals above are present regardless of `include_details`. The `include_details=false` mode only drops `summary.details` (the per-op trace listing each affected `excel_row` and similar); the per-op *counts* live at `summary.rows_added` / `rows_edited` / `rows_deleted` / … and `summary.warnings` always remains. For large batches, set `return_form_summary=false` and `include_details=false`. This is the **default recommendation** for sizable batches, not a fallback for when responses feel slow.
- **Do not** call `get_xlsform_summary` or page `xls_get_rows` after *every* batch to double-check correctness. That is anxiety, not verification, and it burns context.
- **Do** verify once at the end of the build, ideally from a sub-agent (see *Conserving context with sub-agents* in `SKILL.md`), comparing the final `form_summary` and a few spot-check rows against the intended plan. One verification pass at the end is enough.
- If a specific patch *fails* — `session_conflict`, validation error, an unknown-column warning you did not expect — that is a different situation. Reload state with `get_xlsform_summary` (or targeted `xls_get_rows`), re-derive intent, and re-issue a single batched patch.

## Concurrency contract

- Reads run in parallel.
- `xls_apply_patches` **must** be serialized per `session_id`. Always batch related edits into a single call rather than firing off multiple patch calls.
- On collision the server returns a `session_conflict` error and does **not** auto-retry. Reload state with `get_xlsform_summary` (or `xls_get_rows` for the relevant sheet), re-derive the user's intent against the new state, and re-issue a single batched patch.

## Error envelope

Tool responses use `{"error": {"code": str, "message": str, "data": {...}}}`. React per code:

| Code | Reaction |
| --- | --- |
| `session_not_found` | Session is invalid or expired (TTL 24h). Tell the user; do not retry. Start a fresh session if they want to continue. |
| `session_conflict` | Concurrent write collision. Reload state and re-derive intent (see concurrency contract above). |
| `xlsx_too_large` | Input exceeds 50 MB. Ask the user to slim the workbook. |
| `invalid_xlsform` | Input is not a valid XLSForm (bad ZIP, missing sheets, etc.). Surface the message; suggest starting from the bundled template. |
| `recalc_environment_broken` | Server-side misconfiguration. Surface to the user/operator; not recoverable client-side. |
| `primer_not_found` | Unknown primer topic. Re-check `available_primer_topics` from discovery. |
| `tool_error` | Internal failure. Safe to retry once, then bail and report. |

## Limits worth remembering

- XLSForm upload: 50 MB.
- Session TTL: 24h (check `expires_at` from start/summary).
- `xls_get_rows.limit`: 100 max — page through larger sheets.
- `kb_search.top_k`: 20 max.

## Multi-form / multi-session builds

When one chat covers several forms, a few operational rules keep the build resilient. (Session TTL itself is rarely the issue — 24h easily covers any realistic single-chat build — but partial progress is still worth banking.)

- **Export each form as soon as it is in a deliverable state**, before moving on to the next one, and hand the `download_url` (or the downloaded file) to the user immediately. Once the user has the file, the rest of the build can crash, lose context, or be interrupted without losing finished work. Do not treat "export at the end of the chat" as the only delivery step.
- **One session per form, opened in parallel**, is preferable to serially uploading, editing, exporting, and re-uploading the next form. Reads across sessions are independent and safe to interleave; only `xls_apply_patches` calls need to be serialized per `session_id`.
- **Plan for host file-write restrictions.** Some hosts (notably Claude Cowork's workspace mount) allow creating new files but block overwriting existing ones without explicit user permission. When this is a possibility, download each `export_xlsform` result into a fresh outputs directory or under a versioned filename rather than overwriting the workspace copy — that way the build does not stall on a permission prompt mid-export.

## Worked examples

### Reading

Find all groups (a fast way to learn a form's overall structure):

```json
{
  "session_id": "<sid>",
  "sheet": "survey",
  "survey_row_kind": "groups",
  "start": 0,
  "limit": 100
}
```

Find all survey rows that mention "age" anywhere in name/label/hint:

```json
{
  "session_id": "<sid>",
  "sheet": "survey",
  "where": {"ast": {"fulltext": ["(?i)age"]}},
  "start": 0,
  "limit": 25
}
```

Get the field named `gender` plus everything that depends on it transitively, its enclosing groups, and the choices for its list:

```json
{
  "session_id": "<sid>",
  "sheet": "survey",
  "where": {"ast": {"eq": ["name", "gender"]}},
  "expand": ["deps_in_closure", "groups_enclosing", "choices"],
  "expand_max_depth": null,
  "expand_row_limit_per_seed": 200
}
```

### Writing

Append a `select_one` field:

```json
{
  "session_id": "<sid>",
  "patches": [
    {"op": "add_row", "sheet": "survey",
     "values": {"type": "select_one gender", "name": "gender",
                "label": "Please select your gender:"}}
  ]
}
```

Delete a row and edit a later row in the same batch — `excel_row` values are interpreted against the original sheet, so `3` still means the third original row:

```json
{
  "session_id": "<sid>",
  "patches": [
    {"op": "delete_row", "sheet": "survey", "excel_row": 2},
    {"op": "edit_row", "sheet": "survey", "excel_row": 3,
     "values": {"hint": "Please answer honestly."}}
  ]
}
```

Add new translation columns implicitly:

```json
{
  "session_id": "<sid>",
  "patches": [
    {"op": "edit_row", "sheet": "survey", "excel_row": 2,
     "values": {"label:Newlang": "First question",
                "hint:Newlang": "Please answer carefully"}}
  ]
}
```

Strip the language suffix from every matching column (e.g., when the default language was mistakenly suffixed):

```json
{
  "session_id": "<sid>",
  "patches": [
    {"op": "rename", "kind": "language",
     "old_language": "English (en)", "new_language": ""}
  ]
}
```

Rename a choice list — updates the choices sheet AND the `select_one`/`select_multiple` references on the survey sheet:

```json
{
  "session_id": "<sid>",
  "patches": [
    {"op": "rename", "kind": "list",
     "old_list_name": "occupation", "new_list_name": "occupation_v2"}
  ]
}
```
