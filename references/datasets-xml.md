<!--
  PRIMER: datasets-xml
  STATUS: source-code-derived. Public SurveyCTO documentation does not fully
  document the dataset XML format, so this primer was originally derived from
  inspection of the SurveyCTO server source code (and validated against real
  exported dataset XML files). It is NOT regenerated from docs.surveycto.com
  via the README's "Regenerating primers" workflow. Update only when the
  underlying schema changes, and only by re-deriving from the source.
-->

# Dataset XML Definition Reference

SurveyCTO dataset definitions are XML files that define dataset structure, form attachments, and publishing rules. Data is stored separately as CSV. For full documentation, see [Introduction to advanced dataset usage](https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/01.datasets-intro.html) and [Working with server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461).

## Managing definitions

- **Download**: Design tab → select dataset → Download → Download definition
- **Upload**: Design tab → New dataset from definition → upload XML file
- **Update existing**: Download XML + CSV data, delete dataset, upload modified XML, re-upload CSV data (use Append mode)

Forms referenced in `<formLinks>` or `<dataLinks>` must be deployed before uploading.

## XML structure

```xml
<dataset>
  <definition>
    <id>dataset_id</id>                    <!-- Required: used in pulldata()/search() -->
    <title>Display Name</title>             <!-- Required -->
    <datasetType>SERVER</datasetType>       <!-- Required: SERVER, CLIENT, or REPORT -->
    <fieldNames>col1,col2,col3</fieldNames> <!-- Optional: column order/names -->

    <formLinks>                             <!-- Optional: forms that attach/pre-load this dataset -->
      <formLink>
        <formId>form_id</formId>
      </formLink>
    </formLinks>

    <dataLinks>                             <!-- Optional: data publishing rules -->
      <dataLink>
        <dataLinkClass>FORM</dataLinkClass>         <!-- Required: FORM or SPREADSHEET -->
        <dataLinkType>INCOMING</dataLinkType>        <!-- Required: INCOMING or OUTGOING -->
        <dataLinkState>ENABLED</dataLinkState>       <!-- Optional: ENABLED or DISABLED -->
        <dataLinkFormat>0</dataLinkFormat>           <!-- Optional: 0=wide (default), 1=long -->
        <linkObjectId>form_id</linkObjectId>         <!-- Required: form or file ID -->
        <fieldMap>JSON_MAPPING</fieldMap>             <!-- Optional: field-to-column mapping -->
        <joiningField>unique_id</joiningField>       <!-- Optional: unique ID for upserts -->
        <relevanceField>filter</relevanceField>      <!-- Optional: publish only when =1 -->
        <isAutoConfigured>false</isAutoConfigured>   <!-- Optional: default false -->
      </dataLink>
    </dataLinks>

    <caseManagementOptions>                 <!-- For case management datasets -->
      <displayMode>tree</displayMode>       <!-- Required: "tree" or "table" -->
      <showFinalizedSentWhenTree>true</showFinalizedSentWhenTree>
      <showColumnsWhenTable>                <!-- Required container -->
        <columnNames>col1</columnNames>
        <columnNames>col2</columnNames>
      </showColumnsWhenTable>
      <otherUserCode>OTHER</otherUserCode>  <!-- Optional; note capital C -->
      <entryMode>LIST</entryMode>           <!-- Optional: LIST, ENTRY, or SCAN -->
      <enumeratorDatasetId>enum_id</enumeratorDatasetId>  <!-- Optional -->
    </caseManagementOptions>

    <idFormatOptions>                       <!-- For enumerator datasets -->
      <prefix>ENU-</prefix>                 <!-- Optional -->
      <suffix>-2024</suffix>                <!-- Optional -->
      <numberOfDigits>4</numberOfDigits>    <!-- Required -->
      <allowCapitalLetters>false</allowCapitalLetters>  <!-- Optional -->
    </idFormatOptions>

    <discriminator>DATA</discriminator>                    <!-- Optional: DATA, CASES, or ENUMERATORS -->
    <uniqueRecordField>id</uniqueRecordField>              <!-- Optional: unique ID column -->
    <allowOfflineUpdates>false</allowOfflineUpdates>       <!-- Optional: default false -->
  </definition>

  <instance>                                <!-- Optional: version tracking -->
    <version>1</version>                    <!-- Resets to 1 on upload -->
  </instance>
</dataset>
```

## Required structure: element order and mandatory children

The server validates an uploaded definition against a strict schema. Two rules cause a silent upload rejection if broken, so follow them exactly:

- **`<definition>` children must appear in this order** (omit any that do not apply, but never reorder them): `id`, `title`, `datasetType`, `fieldNames`, `formLinks`, `dataLinks`, `caseManagementOptions`, `idFormatOptions`, `discriminator`, `uniqueRecordField`, `allowOfflineUpdates`. In particular, `caseManagementOptions` and `idFormatOptions` come before `discriminator` and `uniqueRecordField`, not after. `id`, `title`, and `datasetType` are required.
- **Mandatory children of the option blocks:**
  - `<caseManagementOptions>` must contain `displayMode`, `showFinalizedSentWhenTree`, and `showColumnsWhenTable`. `otherUserCode`, `entryMode`, and `enumeratorDatasetId` are optional. Use `<displayMode>table</displayMode>` for table view and `<displayMode>tree</displayMode>` for tree view.
  - `<idFormatOptions>` must contain `numberOfDigits`. `prefix`, `suffix`, and `allowCapitalLetters` are optional.

## Base columns by discriminator (CASES and ENUMERATORS)

`<fieldNames>` is a free-form, comma-separated list, and the server does not reject a definition for missing columns. But case-management and enumerator datasets each have a standard column set that the SurveyCTO console always creates. When you author these by hand, reproduce the standard set by default so the file behaves like one created in the console, then append any extra columns the user asked for after the standard ones. Column order is not enforced by the server; follow the standard order for readability.

### ENUMERATORS datasets

Standard columns: `id,name,users`.

- `id` (required): unique enumerator ID. Set `<uniqueRecordField>id</uniqueRecordField>`.
- `name` (required): enumerator display name.
- `users` (include by default): comma-separated usernames controlling which users see each enumerator. Include it unless the user explicitly asks for no per-user filtering. It powers filtering the enumerator picker to the logged-in user, auto-selecting that user's own enumerator, and the manager-code prompt when someone picks a different enumerator. The console always creates this column, so omitting it produces a dataset that silently loses those behaviors. A blank value means that enumerator is shown to all users.
- Append any user-requested columns after these. For example, a requested `region` column gives `id,name,users,region`, not `id,name,region`.
- `<idFormatOptions>` is required for a new enumerator dataset and is validated (prefix, suffix, digit count, capital letters allowed). Gather these values from the user; do not invent them.

### CASES datasets

Standard columns, in this order: `id,label,formids,users,roles,sortby,enumerators`.

- Required: `id` (unique case ID), `label` (text shown in the case list), and `formids` (comma-separated form IDs for the case). A case dataset missing any of these three fails when Collect tries to render the case list.
- Conventional but technically optional: `users` (filter by username), `roles` (filter by user role), `sortby` (numeric sort order, low to high; cases sort by `id` when absent), and `enumerators` (filter by enumerator ID). Include all four by default to match the console and keep later filtering available; their per-row values may be left blank.
- `id` is the unique record field: `<uniqueRecordField>id</uniqueRecordField>`.

See [Enumerator management](https://docs.surveycto.com/04-monitoring-and-management/01-the-basics/01.z.enumerator-management.html) and [Case management](https://docs.surveycto.com/03-collecting-data/03-data-collection-workflow/02.case-management.html) for the column semantics.

## Field map JSON

The `<fieldMap>` element contains a JSON array mapping form fields to dataset columns:

```json
[{
  "formField": "name",
  "datasetField": "column",
  "updateLogicAction": "REPLACE",
  "updateLogicOptions": null
}]
```

### Update logic actions

| Action | Description |
| --- | --- |
| `REPLACE` | Replace the existing value (default) |
| `ADD_TO_NUMERIC_VALUE` | Add the form value to the existing numeric value |
| `CONCATENATE_TO_TEXT` | Append text to the existing value |

For `CONCATENATE_TO_TEXT`, set `updateLogicOptions`:
```json
{"separator": ", ", "position": "END"}
```

### Repeated fields

Repeated fields use `*` suffix in field map entries:
- `"formField": "field*"` maps to `"datasetField": "column*"` (wide format)

### fieldMap gotchas

- **`select_multiple` fields publish the field name directly.** SurveyCTO already stores `select_multiple` submission values as a space-separated string; do *not* invent a pre-joined helper field (e.g. `species_joined`) and point `formField` at it. Use the real `select_multiple` field name.
- **Every name in `fieldMap` must really exist in the form.** The publishing engine maps by literal field name; there is no form-side pre-processing layer. Verify each `formField` against the form's actual `survey` rows before uploading the dataset definition.

## Common modifications

| Task | What to change |
| --- | --- |
| Reorder columns | Edit `<fieldNames>` comma-separated list |
| Change dataset ID | Edit `<id>` (also update forms that reference it) |
| Attach to forms | Add `<formLink>` entries inside `<formLinks>` |
| Set up publishing | Add/configure `<dataLink>` entries inside `<dataLinks>` |
| Configure cases | Add/edit `<caseManagementOptions>` |
| Configure enumerator IDs | Add/edit `<idFormatOptions>` |

## Critical notes

- **Element names are case-sensitive**: `otherUserCode` (not `otherUsercode`), `showFinalizedSentWhenTree` (not `showfinalizedsentwhentree`).
- **Cannot upload if `<formLinks>` or `<dataLinks>` reference non-existent forms.** Deploy forms first.
- **`<showColumnsWhenTable>` contains multiple `<columnNames>` child elements**, not a single comma-separated string.
- **To modify an existing dataset**: Download XML + CSV, delete dataset, upload modified XML, then upload CSV data using Append mode.
- **`<version>` resets to 1** on each upload; it is managed by the server.

## Dataset types

| Type | Description |
| --- | --- |
| `SERVER` | Server-only dataset (not pre-loaded to devices) |
| `CLIENT` | Pre-loaded to devices for offline use (via `pulldata()` or `search()`) |
| `REPORT` | Reporting/export dataset |

## Discriminator values

| Value | Description |
| --- | --- |
| `DATA` | Standard data dataset |
| `CASES` | Case management dataset |
| `ENUMERATORS` | Enumerator assignment dataset |
