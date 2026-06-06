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
6. Note the `cannot_verify` findings out loud to the user. These are real rules
   the validator cannot check offline (whether referenced forms are deployed,
   whether a unique ID is actually unique in stored data, subscription/license
   gates, ID collisions). A clean validator result does not clear these.

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
| `cannot_verify` | A real rule that needs a live server. | Surface to the user; cannot be cleared offline. |

Use `--json` for a machine-readable result (`{"ok", "counts", "findings"}`) when
you want to branch on specific rule ids.

## What the validator checks

This is the rule inventory, grouped by area, with the tier each finding uses.
The validator is the source of truth for the exact conditions; this list is for
your situational awareness so you can pre-empt the common mistakes.

### Structure and schema (errors)

- `<definition>` children must appear in schema order: `id`, `title`,
  `datasetType`, `fieldNames`, `formLinks`, `dataLinks`, `caseManagementOptions`,
  `idFormatOptions`, `discriminator`, `uniqueRecordField`, `allowOfflineUpdates`.
- `<dataLink>` children must appear in schema order: `dataLinkClass`,
  `dataLinkType`, `dataLinkState`, `dataLinkFormat`, `linkObjectId`, `fieldMap`,
  `joiningField`, `relevanceField`, `isAutoConfigured`. The most common mistake
  is placing `joiningField` before `fieldMap`.
- `id`, `title`, and `datasetType` are required in `<definition>`;
  `dataLinkClass`, `dataLinkType`, and `linkObjectId` are required in each
  `<dataLink>`.
- Unknown/unexpected elements in either container are rejected.
- Enumerations: `datasetType` in {SERVER, CLIENT, REPORT}; `discriminator` in
  {DATA, CASES, ENUMERATORS}; `dataLinkClass` in {FORM, FUSION_TABLE,
  SPREADSHEET}; `dataLinkType` in {INCOMING, OUTGOING}; `dataLinkState` in
  {ENABLED, DISABLED}; `entryMode` in {LIST, ENTRY, SCAN}.
- A `DOCTYPE` declaration is rejected outright (dataset definitions never carry
  one).

### Identity and type (errors)

- `id` must be non-blank and contain only numbers, letters, dashes, and
  underscores. It must not end with `_qc`.
- `title` must be non-blank.
- `CLIENT` and `REPORT` are never authored: `CLIENT` (desktop) datasets are no
  longer supported and `REPORT` datasets are system-managed. Emit `SERVER`.

### Effective discriminator (inferred)

The server infers the discriminator from the option blocks present, overriding a
conflicting `<discriminator>`: `<caseManagementOptions>` forces CASES, otherwise
`<idFormatOptions>` forces ENUMERATORS, otherwise the declared `<discriminator>`
(or DATA). A definition whose declared discriminator disagrees with the inferred
one gets a warning, because the inferred one is what actually applies.

### idFormatOptions, for enumerator datasets

- When an enumerator dataset omits `<idFormatOptions>`, the server defaults it to
  6 digits with no prefix or suffix (warning, not an error: add the block to
  control the ID format).
- When present, `<idFormatOptions>` must contain `<numberOfDigits>` (error).
- `prefix` and `suffix` must be alphanumeric only and at most 10 characters
  (error). A value like `ENU-` is rejected for the hyphen. Unicode letters are
  allowed (the server uses a Unicode alphanumeric check here).
- `numberOfDigits` must be an integer from 4 to 8 (default 6) (error).

### caseManagementOptions, for cases datasets

- When a cases dataset omits `<caseManagementOptions>`, the server defaults it to
  tree display (warning, not an error: add the block to control display/entry).
- When present, it must contain `displayMode`, `showFinalizedSentWhenTree`, and
  `showColumnsWhenTable` (error).
- `displayMode` must be `tree` or `table` (error).
- For `table`, `showColumnsWhenTable` must be non-empty and must include the
  `id` column (error).
- `otherUserCode`, when present, must be latin alphanumeric (ASCII letters and
  digits only) (error).

### Standard columns

- Enumerator datasets need `id` and `name` (warning if missing: the upload
  succeeds, but rows are rejected when enumerator data is inserted) and normally
  include `users` (warning if missing: silently loses per-user filtering,
  auto-selection, and the manager-code prompt). The standard set is
  `id,name,users`; append any extra columns after it.
- Cases datasets need `id`, `label`, and `formids` (warning if missing: the
  upload succeeds, but the case list fails to render in Collect without them).
  The full standard set is `id,label,formids,users,roles,sortby,enumerators`;
  the last four are recommendations.

### fieldNames (errors)

- No field may use the reserved name `rowId`.
- No field name may exceed 60 characters.
- A duplicated column is a warning.

### Field map and publishing rules

- The field map JSON must parse. Both shapes are accepted: the modern array
  (`[{"formField":..,"datasetField":..,"updateLogicAction":..}]`) and the legacy
  object (`{"formField":"datasetField"}`).
- No form field and no dataset field may be mapped more than once (error).
- `updateLogicAction`, when present, must be `REPLACE`, `ADD_TO_NUMERIC_VALUE`,
  or `CONCATENATE_TO_TEXT`.
- A `joiningField` must be present in the field map (error). When the joining
  field is mapped, its entry must use `REPLACE` (error).
- Long-format publishing (`<dataLinkFormat>1</dataLinkFormat>`) requires a
  `<joiningField>` (error).
- For wide-format incoming links into a dataset with a `uniqueRecordField`, the
  joining field should map to the unique record column, and the unique record
  column should be mapped by some entry (warnings; these are console-level
  publishing rules that bite when the link is saved or edited).

### Form cross-reference (only with `--form`)

The validator parses each supplied form `.xlsx` into the same field list the
server publishes: notes are excluded, group and repeat containers are not
fields, a field is repeated when any ancestor row is a `begin repeat` (plain
groups do not make a field repeated), `calculate` fields are included, and the
metadata fields the server always publishes (`SubmissionDate`, `formdef_version`,
`review_quality`, `KEY`) are available as map sources. Then it checks:

- Every form field named in the map exists in the form (error if not).
- A field that is repeated in the form must carry `*` on both sides of its map
  entry; a non-repeated field must not (error on mismatch in wide format).
- The joining field exists in the form (error if not), and for long format it
  must be inside a repeat group (error if not).
- For long format, every published field (and the relevance field) must be in the
  same repeat instance as the joining field, in a parent group, or outside all
  groups. A field from a different, sibling repeat group does not qualify (error).
- The relevance field, when set, exists in the form (warning if not).
- `<linkObjectId>` should equal the form's `form_id` (read from the form's
  settings sheet), not the file name. A mismatch with a supplied form is a
  warning.

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
