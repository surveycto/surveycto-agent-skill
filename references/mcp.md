# SurveyCTO MCP server reference

Detailed reference for the SurveyCTO MCP server tools, patch semantics, concurrency, errors, and limits. Read this when you are using the MCP server to inspect or edit XLSForms, or when an MCP call returns an error you need to interpret.

For the high-level workflow and the template-first rule, see `SKILL.md`. The workflow there (`Workflow: create a new form`) is the entry point; this file is the deep dive.

## Contents

- Endpoint and client setup
- Tool surface
- `xls_apply_patches` details
- Concurrency contract
- Error envelope
- Limits worth remembering

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

## Tool surface

| Tool | When to use |
| --- | --- |
| `get_surveycto_mcp_capabilities` | First call when unsure. Returns the canonical tool list, recommended workflows, available primer topics, server version, recalc availability, and the concurrency contract. |
| `kb_search(query, top_k=5)` | Any factual SurveyCTO question. Searches `www.surveycto.com`, `docs.surveycto.com`, `support.surveycto.com`. Returns `{title, url, excerpt}` hits. `top_k` capped at 20. **Quote source URLs in answers.** |
| `get_surveycto_primer(topic)` | Available primers at server-side: `overview`, `xlsform`, `expressions` (full set in the discovery payload's `available_primer_topics`). Mostly useful for callers without the skill installed; you already have these locally. |
| `start_xlsform_session(xlsx_base64?, original_filename?)` | Caller wants to inspect or edit an XLSForm. **Recommended: omit `xlsx_base64` first.** The server returns a short-lived `upload_url` and `curl_example`; upload with `curl -F file=@form.xlsx '<upload_url>'`. The upload response returns `session_id`, `expires_at`, `current_version`, `size_bytes`, `original_filename`, `form_summary`, `warnings`, `recommended_next_actions`. Use inline `xlsx_base64` only for small files when it will not burn model context. **Use the returned `form_summary` for orientation before paging rows.** |
| `get_xlsform_summary(session_id)` | Resuming an existing session (new agent context, after a long gap). Read-only and cheap. Returns the same `form_summary` shape plus `current_version` and `expires_at`. |
| `xls_get_rows(session_id, sheet, where?, order_by?, start, limit, columns?, expand?, …)` | Inspect rows. `limit` capped at 100. Use `expand=["choices","deps_in","deps_out","expressions_refs","groups_enclosing","deps_in_closure","deps_out_closure"]` as needed. Read-only; safe to call in parallel. |
| `xls_get_row(session_id, sheet, excel_row, columns?, expand?, …)` | Fetch one row by 1-based Excel row number. Same expand options. |
| `xls_apply_patches(session_id, patches, validate_only=false, return_form_summary=true, include_details=true)` | Make edits. Batch all related edits into one call. See `xls_apply_patches` details below. |
| `export_xlsform(session_id, version?, format="resource")` | Get the workbook back. Default `format="resource"` returns an `xlsform://{session_id}/{version}` URI, a formal `resource_link`, and an HTTPS `download_url` with `curl_example`. Prefer the `download_url` or resource link. Do **not** use `format="base64"` for real workbooks; it is only for tiny compatibility cases. **Recalc only runs when `version >= 2`** (post-edit); `version == 1` returns the original upload unchanged with `recalc.status="skipped"`. |
| `end_xlsform_session(session_id)` | Optional explicit cleanup. Usually skip it and let the session expire by TTL so `download_url` / resource links remain usable for follow-up requests. Idempotent. |

Resource: `xlsform://{session_id}/{version}` — read with `resources/read` for the recalculated bytes (or unchanged upload at version 1). `export_xlsform` also returns an HTTPS `download_url` tied to the session TTL; once the session expires, the server rejects the URL. Download it or hand it off before TTL expiry. MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## `xls_apply_patches` details

- **Batching:** Batch related edits into one call and serialize calls per `session_id`.
- **Patch ops:** Supported ops are `add_row`, `edit_row`, `delete_row`, `rename` (kinds: `field`, `group`, `list`, `language`, `column`), `change_setting`, and `delete_column`.
- **Allowed sheets:** Use `add_row`, `edit_row`, and `delete_row` only for `survey` and `choices`.
- **Settings:** Use `change_setting` for row-2 settings such as `form_title`, `form_id`, and `default_language`; do not use `edit_row` on `settings`.
- **Column aliases:** The server normalizes common aliases such as `constraint_message` -> `constraint message`, `required_message` -> `required message`, `read_only` -> `read only`, and `relevant` -> `relevance`.
- **Unknown columns:** Review `unknown_column_added` warnings. Custom/plugin columns can be intentional, but most accidental new columns are misspellings.
- **Large batches:** Set `return_form_summary=false` and `include_details=false`, then call `get_xlsform_summary` only when you need a fresh summary.
- **Dry runs:** Use `validate_only=true` for risky changes.

## Concurrency contract

- Reads run in parallel.
- `xls_apply_patches` **must** be serialized per `session_id`. Always batch related edits into a single call rather than firing off multiple patch calls.
- On collision the server returns a `session_conflict` error and does **not** auto-retry. Reload state with `get_xlsform_summary` (or `xls_get_rows` for the relevant sheet), re-derive the user's intent against the new state, and re-issue a single batched patch.

## Error envelope

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

## Limits worth remembering

- XLSForm upload: 50 MB.
- Session TTL: 24 h (check `expires_at` from start/summary).
- `xls_get_rows.limit`: 100 max — page through larger sheets.
- `kb_search.top_k`: 20 max.
