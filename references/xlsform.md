<!--
  PRIMER: xlsform
  STATUS: V1 — slated for regeneration from docs.surveycto.com via the prompt
  in README.md ("Regenerating primers"). Keep XLSForm mechanics here; expression
  language details belong in expressions.md.
-->

# XLSForm Reference

A SurveyCTO form definition is an XLSX workbook with three worksheets: `survey`, `choices`, and `settings`. This reference covers all worksheets, columns, and field types.

For full documentation, see [Designing forms: core concepts](https://docs.surveycto.com/02-designing-forms/01-core-concepts/).

## survey worksheet

Every group, question, and calculation is a row. All form logic lives here.

### Core columns

| Column | Purpose |
| --- | --- |
| `type` | Field/group type (see field types below) |
| `name` | Unique variable name (no spaces or punctuation); becomes the export column name |
| `label` | Main prompt text shown to the user |
| `hint` | Help text shown under the label |
| `relevance` | Expression controlling when the row is shown (skip logic) |
| `constraint` | Validation expression (use `.` to refer to the current field's value) |
| `constraint message` | Message shown when the constraint fails |
| `required` | Set to `yes` to force a response |
| `required message` | Message shown when a required field is skipped |
| `calculation` | Expression for `calculate` fields or default values |
| `repeat_count` | Fixed repeat count or expression for repeat groups |
| `choice_filter` | Expression to filter choices for select fields |
| `appearance` | Display options (see appearance options below) |
| `default` | Default value for the field |
| `read only` | Set to `yes` to make field read-only |
| `disabled` | Set to `yes` to disable the field |
| `media:image` | Image filename to display with the field |
| `media:audio` | Audio filename to play with the field |
| `media:video` | Video filename to play with the field |

### Translation columns

Any column that displays text supports localization by appending `:Language` or `::Language` to the column name. Examples:

- `label:English`, `label:French`
- `hint::Español`
- `constraint message:Swahili`
- `media:image:English`, `media:image:French`

The base `label` and `hint` columns provide defaults, controlled by `default_language` in the settings worksheet.

### Field types

| Type | Description |
| --- | --- |
| `text` | Free-text input |
| `integer` | Whole number input |
| `decimal` | Decimal number input |
| `select_one [list_name]` | Single-choice from a choice list |
| `select_multiple [list_name]` | Multi-choice from a choice list |
| `note` | Display-only text (no data collected) |
| `calculate` | Hidden calculated value (use `calculation` column) |
| `date` | Date picker |
| `time` | Time picker |
| `dateTime` | Date and time picker |
| `geopoint` | GPS coordinate capture |
| `geotrace` | GPS trace (line) |
| `geoshape` | GPS shape (polygon) |
| `image` | Photo capture |
| `audio` | Audio recording |
| `video` | Video recording |
| `file` | File upload |
| `barcode` | Barcode/QR code scanner |
| `acknowledge` | Acknowledgement checkbox |
| `start` | Automatically records form start timestamp |
| `end` | Automatically records form end timestamp |
| `deviceid` | Automatically records unique device identifier |
| `phonenumber` | Automatically records device phone number |
| `username` | Automatically records configured username |
| `caseid` | Automatically records case ID (for case management) |
| `comments` | Enables field-level comments |
| `calculate_here` | Like `calculate`, but evaluated at the field's position (not at form start) |
| `speed violations` | Tracks speed violations per field |
| `text audit` | Tracks text entry audit trail |
| `audio audit` | Records background audio during form filling |
| `sensor_statistic` | Captures sensor statistics |
| `sensor_stream` | Captures raw sensor data stream |
| `begin group` | Start of a group |
| `end group` | End of a group |
| `begin repeat` | Start of a repeat group |
| `end repeat` | End of a repeat group |

### Appearance options

| Appearance | Applicable types | Description |
| --- | --- | --- |
| `minimal` | `select_one`, `select_multiple` | Dropdown/autocomplete instead of full list |
| `quick` | `select_one` | Auto-advances after selection |
| `likert` | `select_one` | Likert-scale layout |
| `compact` | `select_one`, `select_multiple` | Compact choice layout |
| `label` | `select_one`, `select_multiple` | Labels only (for table-like appearance in groups with `field-list`) |
| `list-nolabel` | `select_one`, `select_multiple` | Choices without labels (pair with `label` in same group) |
| `field-list` | `begin group` | Show all fields in group on one screen |
| `table-list` | `begin group` | Table layout for multiple select fields |
| `multiline` | `text` | Multi-line text input |
| `numbers` | `text` | Numeric keyboard for text input |
| `hidden` | Any | Hide the field from the user |
| `w1`–`w10` | Any (inside `field-list`) | Width classes for side-by-side layout |
| `signature` | `image` | Signature pad |
| `draw` | `image` | Drawing pad |
| `annotate` | `image` | Annotate an image |
| `search(...)` | `select_one`, `select_multiple` | Load choices dynamically from pre-loaded data (see search patterns below) |

Multiple appearances can be combined with spaces: `minimal quick`.

### search() for dynamic choice lists

To load choices from pre-loaded data, use a `search()` expression in the `appearance` column of a `select_one` or `select_multiple` field. On the `choices` worksheet, include one row where `value` and `label` contain column names from the data source instead of literal values.

Common `search()` patterns:
- `search('datasetid')` — include all distinct rows
- `search('datasetid', 'matches', 'column', ${field})` — include rows where column exactly matches field
- `search('datasetid', 'contains', 'column', ${field})` — include rows where column contains field
- `search('datasetid', 'startswith', 'column', ${field})` — include rows where column starts with field
- `search('source', 'matches', 'col', ${val}, 'filtercol', ${filterval})` — add a secondary filter

See [Loading multiple-choice options from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) for full syntax.

## choices worksheet

Defines choice lists used by `select_one` and `select_multiple` fields.

### Core columns

| Column | Purpose |
| --- | --- |
| `list_name` | Choice list name (matches the list referenced in `select_one [list]` or `select_multiple [list]`) |
| `value` | Internal code stored when chosen (unique within the list) |
| `label` | Display text for the choice |
| `image` | Optional image filename per choice |
| `filter` | Optional value used with `choice_filter` for cascading selects |

### Translation columns

Like the survey worksheet, `label:Language` and `image:Language` variants are supported.

### Dynamic choice lists (pre-loaded data)

For choices loaded from a pre-loaded CSV dataset:
- `value` contains the CSV column name for the stored value
- `label` contains a CSV column name (or comma-separated column names) for the display text

## settings worksheet

Form-wide settings. Only one data row (row 2).

### Core columns

| Column | Purpose |
| --- | --- |
| `form_title` | Human-friendly display name |
| `form_id` | Unique stable ID (letters, numbers, underscores, hyphens; starts with a letter) |
| `version` | Version number; typically a 10-digit timestamp |
| `default_language` | Name of the default content language |
| `public_key` | PEM public key for end-to-end encryption |
| `submission_url` | URL for encrypted submission targets |

## Core mechanics summary

- **Column names use spaces**, not underscores: `constraint message` (not `constraint_message`), `required message`, `read only`, `repeat_count`, `choice_filter`. Match the exact names listed above.
- **Field names** must be unique across the entire form (no spaces or punctuation). They become column names in exported data.
- **Multiple-choice fields** reference a choice list by name: `select_one mylist` or `select_multiple mylist`.
- **Groups**: `begin group` / `end group` enclose a block. A `relevance` expression on the `begin group` row controls visibility for everything inside.
- **Repeats**: `begin repeat` / `end repeat` repeat the enclosed block. Use `repeat_count` for a fixed or calculated number of repetitions.
- **Expressions** use XPath-like syntax. `${fieldname}` references another field's value. `.` refers to the current value in constraints.
- **Translation**: `label:Lang` and `hint:Lang` columns provide per-language texts. The `default_language` setting controls which language displays by default.

## Common patterns

### Cascading selects

Use `choice_filter` to filter choices based on a prior selection:

| type | name | label | choice_filter |
| --- | --- | --- | --- |
| `select_one region` | `region` | Region | |
| `select_one district` | `district` | District | `region = ${region}` |

The `choices` worksheet needs a `filter` column (here named `region`) on the `district` list with matching values.

### Calculated field

| type | name | label | calculation |
| --- | --- | --- | --- |
| `calculate` | `age` | | `int((today() - ${dob}) div 365.25)` |

### Skip logic

| type | name | label | relevance |
| --- | --- | --- | --- |
| `select_one yesno` | `has_phone` | Do you have a phone? | |
| `text` | `phone_number` | What is your phone number? | `${has_phone} = 'yes'` |

### Constraint with message

| type | name | label | constraint | constraint message |
| --- | --- | --- | --- | --- |
| `integer` | `age` | Age | `. >= 0 and . <= 120` | Age must be between 0 and 120 |
