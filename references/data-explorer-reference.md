# Data Explorer Workbook Definition Reference

Data Explorer workbooks visualize form data with field summaries, relationship charts, and quality checks. Workbook definitions are Excel files with specific worksheets. For full documentation, see [Advanced use of Data Explorer workbooks](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html).

## Managing definitions

- **Download**: Monitor tab → Form submissions and dataset data → Enable "Advanced mode" → click workbook → Download → Download workbook definition
- **Upload**: Monitor tab → Form submissions and dataset data → Enable "Advanced mode" → click workbook → Upload → Upload workbook definition (or Add new workbook → Upload workbook definition)

## Workbook structure (4 worksheets)

### 1. summaries

Defines all visualizations and grouping.

| Column | Purpose |
| --- | --- |
| `type` | Summary type (see types below) |
| `field` | Field name to summarize; for relationships, the first field |
| `field_2` | Second field name (relationships only) |
| `label` | Override auto-generated label; required for `begin group` |
| `note` | Explanatory text shown at top of summary/group |
| `exclusion` | Exclude data (see exclusion syntax below) |
| `options` | Comma-separated display options (see options below) |
| `bins` | Integer for binning numeric/temporal data |
| `options_2` | Options applied only to `field_2` in relationships |
| `bins_2` | Bins applied only to `field_2` |

#### Summary types

**Field summaries** (single field):

| Type | Description |
| --- | --- |
| `text` | Text field summary |
| `categorical` | Categorical/select field summary |
| `numeric` | Numeric field summary |
| `temporal` | Date/time field summary |
| `geomap` | Geographic point map |
| `binary` | Binary/media field summary |

**Relationship summaries** (two fields):

| Type | Description |
| --- | --- |
| `scatterplot` | Scatter plot of two fields |
| `crosstab` | Cross-tabulation of two fields |
| `trend` | Trend over time |
| `map` | Geographic map with data overlay |

**Grouping:**

| Type | Description |
| --- | --- |
| `begin group` | Start a group (requires `label`) |
| `end group` | End a group (requires matching `label`) |

Every `begin group` must have a matching `end group`.

#### Exclusion syntax

- Exact values: `"value1";"value2"` (semicolon-separated, each in quotes)
- Ranges: `("min","max");("min2","max2")`

#### Common options

| Option | Applicable types | Description |
| --- | --- | --- |
| `count` | Most types | Show counts |
| `percent` | Most types | Show percentages |
| `bar` | `categorical` | Bar chart |
| `pie` | `categorical` | Pie chart |
| `mean` | `numeric` | Show mean |
| `min` | `numeric` | Show minimum |
| `max` | `numeric` | Show maximum |
| `none` | `temporal` | No time aggregation |
| `days` | `temporal` | Aggregate by days |
| `weeks` | `temporal` | Aggregate by weeks |
| `months` | `temporal` | Aggregate by months |
| `best_fit_line` | `scatterplot` | Add best-fit line |
| `heatmap` | `crosstab` | Heatmap display |

Multiple options are comma-separated: `count,bar`.

### 2. global_filters

Focus all summaries on a data subset.

| Column | Purpose |
| --- | --- |
| `field` | Field name containing filter values |
| `filter` | Exact value `"value"` or range `("min","max")` |

### 3. global_exclusions

Omit specific submissions from the entire workbook.

| Column | Purpose |
| --- | --- |
| `field` | Currently only `KEY` is supported |
| `exclusion` | UUID to exclude, in quotes: `"uuid-value"` |

### 4. settings

Workbook properties. One data row.

| Column | Purpose |
| --- | --- |
| `workbook_title` | Display name |
| `workbook_id` | Unique ID (no spaces or punctuation) |
| `default_language` | Optional: default language for multilingual forms |

## Common patterns

### Group related summaries

| type | field | label |
| --- | --- | --- |
| `begin group` | | Demographics |
| `categorical` | `gender` | |
| `numeric` | `age` | |
| `end group` | | Demographics |

### Numeric distribution with bins

| type | field | options | bins |
| --- | --- | --- | --- |
| `numeric` | `income` | `count` | `10` |

### Time aggregation

| type | field | options |
| --- | --- | --- |
| `temporal` | `submission_date` | `count,weeks` |

### Crosstab with options

| type | field | field_2 | options | options_2 |
| --- | --- | --- | --- | --- |
| `crosstab` | `region` | `gender` | `count,mean` | `percent,max` |

### Exclude outliers per summary

| type | field | exclusion |
| --- | --- | --- |
| `numeric` | `income` | `("0","0");("999999","999999")` |
