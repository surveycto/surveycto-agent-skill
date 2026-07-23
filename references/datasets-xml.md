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
    <datasetType>SERVER</datasetType>       <!-- Required: always SERVER (see Dataset types) -->
    <fieldNames>col1,col2,col3</fieldNames> <!-- Optional: column order/names -->

    <formLinks>                             <!-- Include even if empty: forms that attach/pre-load this dataset -->
      <formLink>
        <formId>form_id</formId>
      </formLink>
    </formLinks>

    <dataLinks>                             <!-- Include even if empty: data publishing rules -->
      <dataLink>                            <!-- Children MUST appear in the order below -->
        <dataLinkClass>FORM</dataLinkClass>         <!-- Required: FORM or SPREADSHEET -->
        <dataLinkType>INCOMING</dataLinkType>        <!-- Required: INCOMING or OUTGOING -->
        <dataLinkState>ENABLED</dataLinkState>       <!-- Optional: ENABLED or DISABLED -->
        <dataLinkFormat>0</dataLinkFormat>           <!-- Optional: 0=wide (default), 1=long -->
        <linkObjectId>form_id</linkObjectId>         <!-- Required: form or file ID -->
        <fieldMap>JSON_MAPPING</fieldMap>             <!-- Optional: field-to-column mapping. Must come BEFORE joiningField -->
        <joiningField>unique_id</joiningField>       <!-- Optional: unique ID for upserts -->
        <relevanceField>filter</relevanceField>      <!-- Publish only when =1. Always include for long format (empty when unused); see Long format publishing -->
        <isAutoConfigured>false</isAutoConfigured>   <!-- Optional: default false -->
        <publishPartialData>false</publishPartialData> <!-- Do NOT include by default (most servers reject it on import). Add it only to enable real-time dataset publishing on a server that supports the feature. -->
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
      <prefix>ENU</prefix>                  <!-- Optional: alphanumeric only, max 10 chars -->
      <suffix>2024</suffix>                 <!-- Optional: alphanumeric only, max 10 chars -->
      <numberOfDigits>4</numberOfDigits>    <!-- Required: 4 to 8 (default 6) -->
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

The server validates an uploaded definition against a strict schema and then against value rules that the schema does not express. Both kinds of rules reject the upload (HTTP 400) if broken, so follow them exactly.

Structure rules:

- **`<definition>` children must appear in this order** (omit any that do not apply, but never reorder them): `id`, `title`, `datasetType`, `fieldNames`, `formLinks`, `dataLinks`, `caseManagementOptions`, `idFormatOptions`, `discriminator`, `uniqueRecordField`, `allowOfflineUpdates`. In particular, `caseManagementOptions` and `idFormatOptions` come before `discriminator` and `uniqueRecordField`, not after. `id`, `title`, and `datasetType` are required.
- **Always include `<formLinks>` and `<dataLinks>`, even when empty** (`<formLinks/>`, `<dataLinks/>`). The schema marks them optional, but the import path dereferences them unconditionally, so omitting either makes the upload fail with a server error. Inside the option blocks, child order does not matter (`caseManagementOptions`, `idFormatOptions`, the `formLink`, and the `<dataset>` root use order-independent content); only the `<definition>` and `<dataLink>` sequences are order-sensitive.
- **Mandatory children of the option blocks:**
  - `<caseManagementOptions>` must contain `displayMode`, `showFinalizedSentWhenTree`, and `showColumnsWhenTable`. `otherUserCode`, `entryMode`, and `enumeratorDatasetId` are optional. Use `<displayMode>table</displayMode>` for table view and `<displayMode>tree</displayMode>` for tree view.
  - `<idFormatOptions>` must contain `numberOfDigits`. `prefix`, `suffix`, and `allowCapitalLetters` are optional.

Value rules (not enforced by the schema, so easy to miss; each one rejects the upload):

- **`<uniqueRecordField>` (when set on a DATA dataset) must be one of the names in `<fieldNames>`.** A new dataset whose unique record field is not an existing column is rejected with `Sorry, the field "..." doesn't exist in the dataset`. This applies to long format too (use the dataset column the joining field maps into, not the bare form field). Cases and enumerator datasets ignore the supplied value and force `id`.
- **Boolean elements use the XSD lexical space `true`, `false`, `1`, `0` (lowercase only).** `TRUE`, `True`, or `yes` are rejected by schema validation. Integer elements (`numberOfDigits`, `dataLinkFormat`) must be bare integers; a `dataLinkFormat` other than `0` or `1` is silently treated as wide.

- **`<numberOfDigits>` must be an integer from 4 to 8** (default 6). There is no way to specify zero digits or a letters-only ID through `idFormatOptions`. If the user asks for something outside 4 to 8, tell them the supported range rather than writing an out-of-range value.
- **`<prefix>` and `<suffix>` must be alphanumeric only** (letters and digits, no hyphens, spaces, or other punctuation) and **at most 10 characters**. A common mistake is a value like `ENU-` or `-2024`; the hyphen is rejected. Use `ENU` or `2024`.
- **For `<displayMode>table</displayMode>`, `<showColumnsWhenTable>` must be non-empty and must include the `id` column.** A table-view cases dataset whose displayed columns omit `id` is rejected.

## Base columns by discriminator (CASES and ENUMERATORS)

`<fieldNames>` is a free-form, comma-separated list, and the server does not reject a definition for missing columns. But case-management and enumerator datasets each have a standard column set that the SurveyCTO console always creates. When you author these by hand, reproduce the standard set by default so the file behaves like one created in the console, then append any extra columns the user asked for after the standard ones. Column order is not enforced by the server; follow the standard order for readability.

### ENUMERATORS datasets

Standard columns: `id,name,users`.

- `id` (required): unique enumerator ID. Set `<uniqueRecordField>id</uniqueRecordField>`.
- `name` (required): enumerator display name.
- `users` (include by default): comma-separated usernames controlling which users see each enumerator. Include it unless the user explicitly asks for no per-user filtering. It powers filtering the enumerator picker to the logged-in user, auto-selecting that user's own enumerator, and the manager-code prompt when someone picks a different enumerator. The console always creates this column, so omitting it produces a dataset that silently loses those behaviors. A blank value means that enumerator is shown to all users.
- Append any user-requested columns after these. For example, a requested `region` column gives `id,name,users,region`, not `id,name,region`.
- `<idFormatOptions>` is strongly recommended for a new enumerator dataset: if you omit it, the server defaults to 6 digits with no prefix or suffix. Gather the values from the user rather than inventing them. The server enforces: `numberOfDigits` from 4 to 8 (default 6), and `prefix`/`suffix` alphanumeric only (no hyphens or punctuation) and at most 10 characters. Generated IDs are assembled as `prefix` + zero-padded number + `suffix` with no separator (so `prefix=ENU`, `numberOfDigits=6` yields IDs like `ENU000123`). See the value rules above.

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

A field inside a repeat group takes a `*` suffix on its `formField`. Whether the `datasetField` also takes a `*` depends on the publishing format:

- **Wide format** (`dataLinkFormat` 0): the `*` goes on **both sides** (`"formField": "field*"` maps to `"datasetField": "column*"`). The `*` on the dataset side is what expands the repeat into numbered columns (`column_1`, `column_2`, ...); a repeated field mapped to a `datasetField` without the `*` publishes nothing.
- **Long format** (`dataLinkFormat` 1): the `*` goes on the `formField` **only** (`"formField": "field*"` maps to `"datasetField": "column"`, no `*`). Each repeat instance becomes its own row in a single dataset column, so the column name carries no `*`. This is what the server console produces; a `*` on the dataset side is non-canonical here (the publishing engine strips it), so do not emit it.

See [Long format publishing](#long-format-publishing) for the full long-format rules.

### fieldMap gotchas

- **`select_multiple` fields publish the field name directly.** SurveyCTO already stores `select_multiple` submission values as a space-separated string; do *not* invent a pre-joined helper field (e.g. `species_joined`) and point `formField` at it. Use the real `select_multiple` field name.
- **Every name in `fieldMap` must really exist in the form.** The publishing engine maps by literal field name; there is no form-side pre-processing layer. Verify each `formField` against the form's actual `survey` rows before uploading the dataset definition.

## dataLink element order

The children of `<dataLink>` are validated as an ordered sequence by the server schema. They must appear in exactly this order; any optional element you omit is simply skipped, but the ones you include cannot be reordered:

`dataLinkClass`, `dataLinkType`, `dataLinkState`, `dataLinkFormat`, `linkObjectId`, `fieldMap`, `joiningField`, `relevanceField`, `isAutoConfigured`, `publishPartialData`

The common mistake is placing `joiningField` before `fieldMap`. That produces this upload error:

```
cvc-complex-type.2.4.a: Invalid content was found starting with element 'fieldMap'. One of '{relevanceField, isAutoConfigured}' is expected.
```

The fix is ordering only: move `fieldMap` ahead of `joiningField`. The error names `relevanceField` and `isAutoConfigured` because those are what the schema allows after `joiningField`, but neither is required by the schema. `fieldMap`, `joiningField`, `relevanceField`, `isAutoConfigured`, and `publishPartialData` are all optional in the schema; only `dataLinkClass`, `dataLinkType`, and `linkObjectId` are required. One caveat: for a **long-format** link, include the `<relevanceField>` element (empty when unused), as the console does; see [Long format publishing](#long-format-publishing).

## Long format publishing

Set `<dataLinkFormat>1</dataLinkFormat>` to publish each instance of a repeat group as its own dataset row (long format). With the default `0` (wide), each repeat instance becomes a separate set of numbered columns in a single row instead.

Use this when a form has a repeat group and the user wants one dataset row per repeat instance. Worked example for a form with a non-repeated `farmer_id` and a repeat group `plot_measurements` containing `plot_id`, `area_ha`, and `crop_type`, publishing one row per plot:

```xml
<dataset>
  <definition>
    <id>repeat_plots</id>
    <title>Plot Measurements</title>
    <datasetType>SERVER</datasetType>
    <fieldNames>plot_id_key,area_ha,crop_type</fieldNames>
    <formLinks/>
    <dataLinks>
      <dataLink>
        <dataLinkClass>FORM</dataLinkClass>
        <dataLinkType>INCOMING</dataLinkType>
        <dataLinkFormat>1</dataLinkFormat>
        <linkObjectId>plot_measurement_form</linkObjectId>
        <fieldMap>[{"formField":"plot_id*","datasetField":"plot_id_key","updateLogicAction":"REPLACE","updateLogicOptions":null},{"formField":"area_ha*","datasetField":"area_ha","updateLogicAction":"REPLACE","updateLogicOptions":null},{"formField":"crop_type*","datasetField":"crop_type","updateLogicAction":"REPLACE","updateLogicOptions":null}]</fieldMap>
        <joiningField>plot_id*</joiningField>
        <relevanceField></relevanceField>
        <isAutoConfigured>false</isAutoConfigured>
      </dataLink>
    </dataLinks>
    <discriminator>DATA</discriminator>
    <uniqueRecordField>plot_id_key</uniqueRecordField>
    <allowOfflineUpdates>false</allowOfflineUpdates>
  </definition>
  <instance>
    <version>1</version>
  </instance>
</dataset>
```

Naming rules for long format, all of which the example above follows:

- **`joiningField`**: the form field that identifies a unique record, written as the form field name with the `*` suffix (`plot_id*`). It identifies which repeated rows are distinct.
- **`uniqueRecordField`**: the **dataset column** that the joining field publishes into, with no `*` (`plot_id_key`). It must be one of the names in `<fieldNames>`. Do **not** use the bare form-field name (`plot_id`) here: for a new dataset the server rejects a `uniqueRecordField` that is not an existing column with `Sorry, the field "..." doesn't exist in the dataset`. Because the joining field maps `plot_id*` into `plot_id_key`, naming the column `plot_id_key` here also satisfies the rule that the joining field must merge on the unique record column.
- **Repeated fields** carry `*` on the `formField` only. The `datasetField` takes **no** `*` in long format (each repeat instance is its own row in a single column). This is the opposite of wide format, where the `datasetField` also carries the `*` to expand into numbered columns. See [Repeated fields](#repeated-fields).
- **`relevanceField`**: include the `<relevanceField>` element even when there is no filter (leave it empty: `<relevanceField></relevanceField>`). It is a long-standing schema element that the console always writes, so including it imports cleanly on every server. An empty element is stored as a blank filter.
- **Dataset column names are your choice.** The example names the lookup column `plot_id_key`: the `_key` suffix is an indexing convention, not a long-format requirement. Columns whose names end in `_key` are automatically indexed on client (device) datasets to speed up `search()` and `pulldata()` lookups. It does not affect whether publishing succeeds, so do not treat `_key` as a rule the way the joining-field and `*` conventions are.

The server enforces these structural rules; the field selection must satisfy them or the upload is rejected:

1. A `joiningField` is required for long format.
2. The joining field must exist in the form and be inside a repeat group.
3. Every other published field (and the `relevanceField`, if used) must be in the same repeat instance as the joining field, in a parent group, or outside all groups. A field from a different, sibling repeat group does not qualify.

Include the `<relevanceField>` element even when empty. It is a long-standing part of the dataset schema and the console always writes it, so adding it imports cleanly on every server.

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
- **`<dataLink>` children must follow the schema order** (see [dataLink element order](#datalink-element-order)). In particular `fieldMap` comes before `joiningField`.
- **Cannot upload if `<formLinks>` or `<dataLinks>` reference non-existent forms.** Deploy forms first.
- **`<showColumnsWhenTable>` contains multiple `<columnNames>` child elements**, not a single comma-separated string.
- **To modify an existing dataset**: Download XML + CSV, delete dataset, upload modified XML, then upload CSV data using Append mode.
- **`<version>` resets to 1** on each upload; it is managed by the server.

## Dataset types

**Always emit `<datasetType>SERVER</datasetType>`.** SERVER is the only type you author or edit, including read-only lookup tables consumed by `pulldata()` and `search()`. Whether a dataset pre-loads onto devices for offline use is controlled by its `<formLinks>` (the forms that attach it) together with its discriminator, not by the dataset type. To make a lookup available offline, give it `<formLinks>` to the consuming form(s) and leave the type as SERVER.

The other two values are legacy or system-managed. Never generate them; recognize them only if you open an existing definition.

| Type | Status | Notes |
| --- | --- | --- |
| `SERVER` | **Use this** | The only type to author or edit. Pre-loading is driven by `<formLinks>` plus the discriminator. |
| `CLIENT` | Legacy, do not emit | Old pre-loaded-lookup type. The server can no longer attach a CLIENT dataset to a form, so it cannot pre-load. Replace with a SERVER dataset plus `<formLinks>`. |
| `REPORT` | System-managed, do not emit | Auto-generated quality-check warning datasets (titled `<dataset> - QC warnings`). Uploading a REPORT definition is rejected by the server. Leave any you encounter untouched. |

## Discriminator values

| Value | Description |
| --- | --- |
| `DATA` | Standard data dataset |
| `CASES` | Case management dataset |
| `ENUMERATORS` | Enumerator assignment dataset |

The server infers the discriminator from the option blocks present: `<caseManagementOptions>` forces CASES and `<idFormatOptions>` forces ENUMERATORS, overriding a conflicting `<discriminator>`. A dataset is also treated as a cases dataset when its `<id>` is literally `cases`, or (in later console/data-access paths, not at import) when its column set matches the full cases signature.

## Less-obvious server behaviors

These are real behaviors the server applies that are easy to miss when authoring by hand:

- **Publishable fields.** Only data-bearing form fields can be published into a dataset. Notes are not publishable. `select_multiple` publishes as one field (a space-separated value), not one column per choice. A `geopoint` publishes as a single field; its derived `-Latitude`/`-Longitude`/`-Altitude`/`-Accuracy` columns are not separately publishable. `geoshape`, `geotrace`, and `barcode` publish as single string fields. Fields inside a repeat group carry the `*` suffix on the `formField` (and, in wide format only, on the `datasetField`); see [Repeated fields](#repeated-fields).
- **Always-available metadata sources.** `SubmissionDate`, `formdef_version`, `review_quality`, and `KEY` are always available as field-map sources even though they are not survey rows. `formdef_id`, `review_status`, `instanceID`, and `instanceName` are not part of the incoming form-to-dataset feed; do not rely on them as publishing sources.
- **Cases virtual columns.** `scto_saved_count` and `scto_sent_count` are valid entries in `<showColumnsWhenTable>` but must not appear in `<fieldNames>` (the server maintains them).
- **`entryMode` default.** When `<enumeratorDatasetId>` is set on a cases dataset and `<entryMode>` is omitted, the server defaults `entryMode` to `LIST`.
- **Enumerator `name` uniqueness.** The `name` column of an enumerator dataset has a database unique index: two enumerators cannot share a name. This is enforced when data is inserted, not at definition upload, so the validator cannot check it offline.
- **`allowOfflineUpdates` needs a unique record field.** Enabling offline updates requires a unique record field (forced to `id` for cases/enumerator datasets), and a subscription that supports offline publishing.
- **Outgoing and cloud links are console-only.** `OUTGOING` links and the `SPREADSHEET`/`FUSION_TABLE` classes are configured in the console, not created by importing a dataset definition. `WEBHOOK`/`ZAPIER` are not in the import schema at all. Author only incoming `FORM` links in definitions.
- **`isAutoConfigured` is server-generated.** Leave it `false` (or omit it). The auto-configured enumerator-link constraints are applied by the console, not the import path.
- **`publishPartialData` controls real-time (partial) dataset publishing.** Default: OMIT it. Most servers do not support the feature and reject the element on import (`cvc-complex-type.2.4.d`); omitting it equals `false`, so never add it to an ordinary definition. The one exception: when the user explicitly asks to enable real-time or partial publishing AND confirms their server supports it, set `<publishPartialData>true</publishPartialData>` (last in `<dataLink>`, after `isAutoConfigured`). If they ask but have not confirmed server support, do not add it; say it requires a supporting server and ask. In a downloaded definition that already contains it, remove it before re-uploading unless the user confirms the target server supports the feature; a server can export the element but still reject it on import (`cvc-complex-type.2.4.d`), so do not assume a downloaded file re-uploads as-is.
