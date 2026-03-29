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

SurveyCTO is a mobile data collection platform used for surveys, monitoring, and case management. This skill covers authoring and editing the three types of definition files:

1. **XLSForm form definitions** (.xlsx) — survey instruments with questions, logic, and calculations
2. **Dataset definitions** (.xml) — server dataset structure, publishing rules, and case management config
3. **Data Explorer workbook definitions** (.xlsx) — monitoring dashboard configurations

## Identifying SurveyCTO files

| File type | Format | How to recognize |
| --- | --- | --- |
| XLSForm | .xlsx | Has worksheets named `survey`, `choices`, and `settings` |
| Dataset definition | .xml | Root element is `<dataset>` with `<definition>` child |
| Data Explorer workbook | .xlsx | Has worksheets named `summaries`, `settings`, `global_filters`, `global_exclusions` |

## XLSForm overview

An XLSForm is an XLSX workbook with three worksheets:

- **survey** — every question, group, repeat, and calculation is a row
- **choices** — defines choice lists for `select_one` and `select_multiple` fields
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

**Full reference**: See [references/xlsform-reference.md](references/xlsform-reference.md) for all columns, field types, and appearance options.

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

**Skip logic (relevance):**
`${consent} = 'yes'`

**Constraint with range:**
`. >= 0 and . <= 120`

**Calculated age from date of birth:**
`int((today() - ${dob}) div 365.25)`

**Conditional value:**
`if(${gender} = 'female', 'F', 'M')`

**Pull data from attached dataset:**
`pulldata('households', 'head_name', 'hhid', ${household_id})`

**Random assignment (calculate once):**
`once(if(random() < 0.5, 'treatment', 'control'))`

**Full expression reference**: See [references/expressions-reference.md](references/expressions-reference.md) for all operators and functions.
Live documentation: [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html)

## Working with XLSForm .xlsx files

XLSForm definitions are .xlsx files. This SurveyCTO skill provides the *domain knowledge* — what content goes into the form, which columns to use, expression syntax, and validation rules. For the actual .xlsx file operations (reading cells, writing values, formatting), **also use your xlsx/Excel/spreadsheet skill or tool if you have one**. The two skills complement each other: SurveyCTO for *what* to write, xlsx for *how* to write it well.

### CRITICAL: Always start from the template

Every new XLSForm **must** start from the bundled template at [assets/xlsform-template.xlsx](assets/xlsform-template.xlsx).

**How to use the template:**
1. Copy `assets/xlsform-template.xlsx` to the desired output path
2. Open the copied file for editing
3. Edit it in place — add your content into the existing worksheets

**Never do any of the following:**
- Do NOT create a new .xlsx file from scratch
- Do NOT create new worksheets and build the structure yourself
- Do NOT delete and recreate worksheets from the template
- Do NOT "rebuild" the form "properly" — the template IS the proper starting point

**Why the template is mandatory:** It contains conditional formatting rules, help worksheets, column headers, starter metadata fields, formula-based versioning, and pre-formatted rows that cannot be reliably recreated programmatically. Skipping the template produces files that work but are painful for humans to edit in Excel.

The template provides:
- **survey** worksheet with correct column headers and starter metadata fields (`start`, `end`, `deviceid`, `phonenumber`)
- **choices** worksheet with headers and a `yesno` choice list
- **settings** worksheet with headers and an auto-updating `version` formula
- **help-survey**, **help-choices**, **help-settings** worksheets with reference documentation
- Conditional formatting rules that color-code rows by field type

### How to edit the workbook

Edit XLSForms the way a human would edit a spreadsheet: write values into cells in the existing worksheets. The template already has the correct structure; you are just filling in content.

**Workflow:**
1. **Copy** the template (for new forms) or **open** the existing workbook
2. **Read** existing structure to understand what is already there
3. **Write cell values** into the appropriate rows and columns — see common operations below
4. **Validate** the changes (see checklist below)
5. **Save** the workbook

**Important editing rules:**
- **Only write to rows that contain or will contain data.** Do not touch unused rows below your content. Do not write empty strings, None, or blanks to clear rows that are already empty.
- **Preserve all existing worksheets** — including `help-survey`, `help-choices`, `help-settings` and any other worksheets present in the template or existing form.
- **Preserve existing formatting** — do not clear or overwrite conditional formatting, column widths, or cell styles already in the file.
- **Write content starting from the first empty row** after existing data in each worksheet. The template's survey worksheet has starter rows (start, end, deviceid, phonenumber) in rows 2–5; begin adding your fields at row 6.

### Common operations

**Add a field**: Write `type`, `name`, and `label` (at minimum) into the next empty row in the `survey` worksheet. Place it in the correct position relative to groups and other fields.

**Add a choice list**: Write `list_name`, `value`, and `label` into rows in the `choices` worksheet. Ensure `list_name` matches what is referenced in the `select_one` or `select_multiple` type.

**Add a group**: Write a `begin group` row and an `end group` row with matching `name`. Place fields between them.

**Add a repeat**: Write `begin repeat` / `end repeat` rows with matching `name`. Set `repeat_count` if needed.

**Add skip logic**: Write the expression into the `relevance` column on the target field or group row.

**Add a constraint**: Write the expression into the `constraint` column (use `.` for current value) and optionally write the message into `constraint message`.

**Add a calculation**: Write a row with `type` = `calculate`, a unique `name`, and the expression in the `calculation` column.

**Update settings**: Write `form_title` and `form_id` values into row 2 of the `settings` worksheet. Do not overwrite the `version` cell — it contains a formula that auto-updates.

### Validation checklist

After editing, verify:

- [ ] All `name` values are unique across the entire form
- [ ] No `name` contains spaces or special punctuation
- [ ] Every `begin group` has a matching `end group` (same `name`)
- [ ] Every `begin repeat` has a matching `end repeat` (same `name`)
- [ ] Groups and repeats are properly nested (no overlapping)
- [ ] Every `select_one [list]` and `select_multiple [list]` references a list that exists in the `choices` worksheet
- [ ] Every choice list has at least one row with a `value` and `label`
- [ ] `${fieldname}` references in expressions point to fields that exist
- [ ] Expressions use SurveyCTO conventions (`=` not `==`, `index()` not `position()`, etc.)
- [ ] The `settings` worksheet has `form_title` and `form_id`

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

- Element names are **case-sensitive** (e.g., `otherUserCode` not `otherUsercode`).
- Forms in `<formLinks>` and `<dataLinks>` must be deployed before uploading the definition.
- `<showColumnsWhenTable>` contains multiple `<columnNames>` child elements, not a comma-separated string.

**Full reference**: See [references/dataset-xml-reference.md](references/dataset-xml-reference.md) for complete XML structure and field map format.

## Data Explorer workbook definitions

Data Explorer workbooks are XLSX files with four worksheets: `summaries`, `settings`, `global_filters`, and `global_exclusions`.

The `summaries` worksheet defines visualizations. Each row is a summary with a `type` (e.g., `text`, `categorical`, `numeric`, `temporal`, `scatterplot`, `crosstab`) and a `field` reference. Groups use `begin group` / `end group` with matching `label` values.

**Full reference**: See [references/data-explorer-reference.md](references/data-explorer-reference.md) for all worksheet structures and options.

## Common patterns

### Cascading selects

Filter choices in one field based on the selection in another:

1. In `choices`, add a `filter` column (e.g., `region`) to the child list
2. In `survey`, set `choice_filter` on the child field: `region = ${region}`

### Pre-loaded data lookup with pulldata()

Use `pulldata()` to look up a single value from an attached dataset:

1. Create a `CLIENT` dataset with the lookup data
2. Attach it to the form via `<formLinks>` in the dataset definition
3. Use `pulldata('dataset_id', 'column_to_return', 'lookup_column', ${key_field})` in a `calculation`

### Dynamic select list from pre-loaded data

Use a regular `select_one` or `select_multiple` field with a `search()` expression in the `appearance` column:

1. Create a `CLIENT` dataset and attach it to the form
2. In `survey`, set `type` to `select_one listname` and `appearance` to `search('dataset_id')` (or a more specific search expression)
3. In `choices`, add one row for `listname` where `value` and `label` contain column names from the dataset (not literal values)

See [references/xlsform-reference.md](references/xlsform-reference.md) for `search()` syntax patterns.

### Random sampling from repeat group

1. Add a `calculate` field inside the repeat with `calculation`: `once(random())`
2. Use `rank-index()` outside the repeat to get the instance with rank 1:
   `rank-index(1, ${random_calc})` returns the index of the randomly-selected instance

### Publishing form data to a dataset

In the dataset XML, add a `<dataLink>` with:
- `<dataLinkClass>FORM</dataLinkClass>`
- `<dataLinkType>INCOMING</dataLinkType>`
- `<linkObjectId>form_id</linkObjectId>`
- `<fieldMap>` with JSON mapping form fields to dataset columns

## Debugging common issues

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Form won't upload | Duplicate `name` values | Search for duplicate names in the `name` column |
| Form won't upload | Unbalanced groups/repeats | Check that every `begin group`/`begin repeat` has a matching `end group`/`end repeat` |
| Field never appears | Incorrect `relevance` expression | Check expression syntax; verify referenced fields exist and have expected values |
| Constraint never passes | Wrong use of `.` or `${fieldname}` | In constraints, `.` is the current field's value; `${fieldname}` is another field |
| Choices missing | `list_name` mismatch | Ensure `select_one [list]` matches exactly a `list_name` in the `choices` worksheet |
| `select_multiple` logic fails | Using `=` instead of `selected()` | Always use `selected(${field}, 'value')` for `select_multiple` fields |
| Date comparison fails | Comparing string to date | Wrap date strings with `date()`: `${field} > date('2024-01-01')` |
| Dataset won't upload | Referenced form not deployed | Deploy all forms referenced in `<formLinks>` and `<dataLinks>` before uploading |
| Dataset element ignored | Case-sensitivity error | Check exact casing of XML element names (e.g., `otherUserCode` not `otherUsercode`) |

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
