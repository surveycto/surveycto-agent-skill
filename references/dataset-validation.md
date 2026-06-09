<!--
  PRIMER: dataset-validation
  STATUS: source-code-derived. The rules below mirror what the SurveyCTO server
  and its interactive console enforce when a dataset is created or edited. They
  were derived from the server source (dataset.xsd, DatasetValidationUtils.java,
  DatasetServiceImpl.java, DatasetManagerImpl.java, XFormManagerImpl.java,
  DatasetUtils.java) and are re-implemented in
  assets/dataset-validation/validate_dataset.py. Update this primer and that
  script together, and only by re-deriving from the source. If the server rules
  change, the script can drift; treat its output as a strong check, not a
  guarantee.
-->

# Dataset Validation

When you author or edit a server dataset definition (`.xml`), the SurveyCTO
server validates it on upload and the console enforces further rules on the
publishing configuration. An agent writing this XML by hand cannot see those
rules, so it produces definitions that look right but fail on upload or quietly
misbehave once a form publishes into them. This skill ships a validator that
re-implements those rules so you can check and self-correct locally, with no
server round-trip.

**This is mandatory: after creating or editing any dataset definition XML, run
the validator and resolve every error before handing the file to the user.**
Read [`references/datasets-xml.md`](datasets-xml.md) first for the format
itself; this primer is about checking your output against the server's rules.

## Workflow: validate and self-correct

1. Write or edit the dataset definition `.xml` as described in
   [`datasets-xml.md`](datasets-xml.md).
2. Gather the referenced form files. For any `<dataLink>` that publishes a form
   into the dataset, the matching form `.xlsx` lets the validator check the
   field map against the form's real fields (field existence, repeat-group
   membership, the `*` suffix). Supply them whenever you have them.
3. Run the validator:

   ```
   python3 assets/dataset-validation/validate_dataset.py path/to/dataset.xml \
       --form path/to/form1.xlsx --form path/to/form2.xlsx
   ```

   Resolve `assets/` relative to the skill's root directory. Omit `--form` to
   run the dataset-only checks; add one `--form` per referenced form to enable
   the field-map cross-checks.
4. Read the findings. Fix every `error`, then re-run until no errors remain. Do
   not stop at the first error; the validator reports all of them at once.
5. Weigh the `warning` and `recommendation` findings. Apply them unless the user
   explicitly asked for the non-standard shape (for example, an enumerator
   dataset deliberately without a `users` column). When you keep a flagged
   choice, say so to the user and why.
6. Relay the "Before uploading, confirm on the server" checklist to the user.
   These are real preconditions the validator cannot check offline (whether the
   referenced forms are deployed and their form_id matches the linkObjectId,
   whether the dataset id is free, whether a linked enumerator dataset exists,
   subscription gates). A clean validator result does not clear them, so pass
   them on as a short pre-upload checklist.

Run the validator yourself; do not ask the user to run it. If your host supports
sub-agents, validation is a good candidate to delegate, but you own the fixes.

## Output

Findings come in four tiers. The process exits non-zero when any `error` is
present, so you can gate on the exit code.

| Tier | Meaning | What to do |
| --- | --- | --- |
| `error` | The server or its schema rejects this on upload, or a publishing rule that breaks data collection. | Must fix before delivering. |
| `warning` | The server accepts the upload, but behavior is degraded, or a console-level publishing rule will reject the configuration when the link is saved or edited. | Fix unless the user asked for it; explain if you keep it. |
| `recommendation` | Best practice or a console convention that is not enforced. | Apply by default; optional. |
| `cannot_verify` | A real precondition that needs a live server. | Rendered as one consolidated "Before uploading, confirm on the server" checklist; relay it to the user. Cannot be cleared offline. |

The text output lists errors, warnings, and recommendations as tagged lines, then
the `cannot_verify` items as a single deduplicated checklist (so multiple form
references collapse into one "deploy these forms" line). Use `--json` for a
machine-readable result (`{"ok", "counts", "findings"}`), where each
`cannot_verify` item is still a separate finding, when you want to branch on
specific rule ids.

## What the validator checks

You do not need the full rule list in context: the validator reports each
problem with a clear message, a location, and (often) a fix, so act on what it
prints. In short, it covers the schema structure (element order, required
children, enumerations, lexical types), the id/title/type rules, the
`idFormatOptions` and `caseManagementOptions` value rules, the standard column
sets, the `uniqueRecordField` rules, and the field-map and long-format
publishing rules (including the cases behind a joining field missing from the
map or a field mapped twice). With a `--form`, it also checks the field map
against the form's real fields. The most important of these rules are also in
[`datasets-xml.md`](datasets-xml.md); for the exact conditions, read the
validator source (its header cites the server files each rule comes from).

## What the validator cannot check

These need a live server and are surfaced as `cannot_verify`, never silently
passed:

- Whether forms referenced in `<formLinks>` and `<dataLinks>` are deployed.
- Whether a `uniqueRecordField` is actually present and unique across stored
  rows.
- Subscription/license gates (offline updates, streaming into server datasets,
  exact maximum field count).
- Whether the `id` collides with an existing form or dataset ID.
- Whether a linked `enumeratorDatasetId` exists and is accessible.

Always pass these on to the user; the validator passing does not.

## Drift

These rules are transcribed from the SurveyCTO server source, not generated from
public docs. If the server changes its rules, the validator can fall behind.
Rules are far more often added than removed, so drift usually means the validator
is slightly less helpful rather than wrong, but treat a clean result as a strong
check and not a substitute for a real upload. The script header lists the source
files behind each rule for re-derivation.
