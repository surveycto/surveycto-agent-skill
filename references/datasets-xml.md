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

    <formLinks>                             <!-- Optional: forms that attach/pre-load this dataset -->
      <formLink>
        <formId>form_id</formId>
      </formLink>
    </formLinks>

    <dataLinks>                             <!-- Optional: data publishing rules -->
      <dataLink>                            <!-- Children MUST appear in the order below -->
        <dataLinkClass>FORM</dataLinkClass>         <!-- Required: FORM or SPREADSHEET -->
        <dataLinkType>INCOMING</dataLinkType>        <!-- Required: INCOMING or OUTGOING -->
        <dataLinkState>ENABLED</dataLinkState>       <!-- Optional: ENABLED or DISABLED -->
        <dataLinkFormat>0</dataLinkFormat>           <!-- Optional: 0=wide (default), 1=long -->
        <linkObjectId>form_id</linkObjectId>         <!-- Required: form or file ID -->
        <fieldMap>JSON_MAPPING</fieldMap>             <!-- Optional: field-to-column mapping. Must come BEFORE joiningField -->
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

Fields inside a repeat group use a `*` suffix on **both sides** of the field map entry:
- `"formField": "field*"` maps to `"datasetField": "column*"`

The `*` is required whether you publish in wide format or long format. What differs between the two formats is how those repeated fields land in the dataset; see [Long format publishing](#long-format-publishing).

### fieldMap gotchas

- **`select_multiple` fields publish the field name directly.** SurveyCTO already stores `select_multiple` submission values as a space-separated string; do *not* invent a pre-joined helper field (e.g. `species_joined`) and point `formField` at it. Use the real `select_multiple` field name.
- **Every name in `fieldMap` must really exist in the form.** The publishing engine maps by literal field name; there is no form-side pre-processing layer. Verify each `formField` against the form's actual `survey` rows before uploading the dataset definition.

## dataLink element order

The children of `<dataLink>` are validated as an ordered sequence by the server schema. They must appear in exactly this order; any optional element you omit is simply skipped, but the ones you include cannot be reordered:

`dataLinkClass`, `dataLinkType`, `dataLinkState`, `dataLinkFormat`, `linkObjectId`, `fieldMap`, `joiningField`, `relevanceField`, `isAutoConfigured`

The common mistake is placing `joiningField` before `fieldMap`. That produces this upload error:

```
cvc-complex-type.2.4.a: Invalid content was found starting with element 'fieldMap'. One of '{relevanceField, isAutoConfigured}' is expected.
```

The fix is ordering only: move `fieldMap` ahead of `joiningField`. The error names `relevanceField` and `isAutoConfigured` because those are what the schema allows after `joiningField`, but neither is required. `fieldMap`, `joiningField`, `relevanceField`, and `isAutoConfigured` are all optional; only `dataLinkClass`, `dataLinkType`, and `linkObjectId` are required.

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
        <fieldMap>[{"formField":"plot_id*","datasetField":"plot_id_key*","updateLogicAction":"REPLACE","updateLogicOptions":null},{"formField":"area_ha*","datasetField":"area_ha*","updateLogicAction":"REPLACE","updateLogicOptions":null},{"formField":"crop_type*","datasetField":"crop_type*","updateLogicAction":"REPLACE","updateLogicOptions":null}]</fieldMap>
        <joiningField>plot_id*</joiningField>
        <isAutoConfigured>false</isAutoConfigured>
      </dataLink>
    </dataLinks>
    <discriminator>DATA</discriminator>
    <uniqueRecordField>plot_id</uniqueRecordField>
    <allowOfflineUpdates>false</allowOfflineUpdates>
  </definition>
  <instance>
    <version>1</version>
  </instance>
</dataset>
```

Naming rules for long format, all of which the example above follows:

- **`joiningField`**: the form field that identifies a unique record, written as the form field name with the `*` suffix (`plot_id*`). It identifies which repeated rows are distinct.
- **`uniqueRecordField`**: the same field as the bare form field name, with no `*` (`plot_id`).
- **All repeated fields** carry `*` on both `formField` and `datasetField`, as in wide format.
- **Dataset column names are your choice.** The example names the lookup column `plot_id_key`: the `_key` suffix is an indexing convention, not a long-format requirement. Columns whose names end in `_key` are automatically indexed on client (device) datasets to speed up `search()` and `pulldata()` lookups. It does not affect whether publishing succeeds, so do not treat `_key` as a rule the way the joining-field and `*` conventions are.

The server enforces these structural rules; the field selection must satisfy them or the upload is rejected:

1. A `joiningField` is required for long format.
2. The joining field must exist in the form and be inside a repeat group.
3. Every other published field (and the `relevanceField`, if used) must be in the same repeat instance as the joining field, in a parent group, or outside all groups. A field from a different, sibling repeat group does not qualify.

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
