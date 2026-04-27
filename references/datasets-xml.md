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
