<!-- PRIMER: expressions
  STATUS: regenerated 2026-04-26 from docs.surveycto.com -->

# SurveyCTO Expression Language

This primer covers the language used in SurveyCTO expressions: field references, operators, functions, scoping, quoting, common idioms, and failure modes. For XLSForm column mechanics, see [`xlsform.md`](xlsform.md). For attached dataset XML and data-link mechanics, see [`datasets-xml.md`](datasets-xml.md).

Canonical source: [Using expressions in your forms: a reference for all operators and functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html).

## Mental Model

SurveyCTO expressions are XPath-derived/XLSForm-style expressions evaluated against the current form instance. Most form logic should be written in SurveyCTO's documented syntax, not generic XPath or generic ODK snippets copied from elsewhere.

| Expression item | Meaning | Example | Docs |
| --- | --- | --- | --- |
| `${fieldname}` | The current value stored in another form field. In labels, calculations, relevance, constraints, and most expressions, this returns the value exactly as it will appear in submitted data. | `${age}` | [Referencing current values](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#referencing-current-values) |
| `.` | In a `constraint`, the user's proposed entry or selection for the current field. SurveyCTO documents `.` for constraints; prefer explicit `${field}` references elsewhere unless a documented example uses `.`. | `. < 130` | [Constraints](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html) |
| Choice-sheet column names in `choice_filter` | A bare name such as `filter` refers to the value in that column for the candidate choice row being tested. `${field}` still refers to a form field. | `filter=${region}`; `selected(${crops}, filter)` | [Cascading selects](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/02.cascading-selects.html) |
| Repeated field reference inside its own repeat | A plain `${field}` reference resolves to the value in the current repeat instance when the referring expression is inside the same repeat group. | Label in same repeat: `Age of ${name}` | [Repeated data support guide](https://support.surveycto.com/hc/en-us/articles/18523141990035-Guide-to-repeated-data-part-2-Using-and-referencing-repeated-data) |
| Repeated field reference outside its repeat | You must specify how to collapse or select instances, using `sum()`, `join()`, `count()`, `indexed-repeat()`, etc. A bare reference commonly triggers an indexed-repeat error. | `indexed-repeat(${name}, ${members}, 1)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |

Expression context matters:

| Context | What is being evaluated | How to think about references |
| --- | --- | --- |
| `constraint` | The candidate value for the current response; it must evaluate true for a non-blank response to pass. | Use `.` for the proposed current value; use `${field}` for prior/current form values. Constraints do not make optional fields required. |
| `calculation` on `calculate` | A hidden value recalculated as dependencies change and when forms load/save. | Use `${field}` references and functions. Use `once()` only as the outermost expression when a value should be stable. |
| `calculation` on visible field | A dynamic default evaluated the first time the field is displayed. | Make the field/group not relevant until prerequisite values exist, or the default can calculate too early. See [`xlsform.md`](xlsform.md#survey-columns). |
| `relevance` | Whether a field/group/repeat is shown. Hidden fields have empty responses. | Usually depends on prior fields. Relevance is evaluated when a screen is first displayed, so fields on the same `field-list` screen cannot dynamically appear/disappear based on earlier answers on that same screen. |
| `choice_filter` | Whether each static choice row is shown. | Bare choice-column names refer to the candidate choice. `${field}` refers to form values. For dynamic pre-loaded choices, use `search()` in `appearance`, not `choice_filter`. |
| `appearance` with `search()` or `randomized(...)` | Special appearance expressions/options interpreted by select fields. | These are expression-like but tied to XLSForm appearance behavior; see [`xlsform.md`](xlsform.md#appearance-options). |
| `default` | A fixed literal default, not an expression. | Use the `calculation` column for dynamic defaults. |

## Quoting and Literals

| Rule | Use | Avoid |
| --- | --- | --- |
| Use straight single quotes for string literals. | `${sex} = 'female'` | `${sex} = female` |
| Use double quotes only when the literal itself contains a single quote/apostrophe. | `if(${ok} = 1, "respondent's answer", 'none')` | `'respondent's answer'` |
| Do not rely on escaping inside single-quoted strings. SurveyCTO's docs show switching to double quotes, not backslash escaping. | `"a string with 'single quotes' in it"` | `'a string with \'single quotes\''` |
| Avoid smart/curly quotes. | `'yes'`, `"don't"` | `&lsquo;yes&rsquo;`, `&ldquo;don&rsquo;t&rdquo;` |
| Choice values are values, not labels. Quote them when used as strings, even if they look numeric. | `selected(${consent}, '1')` | `selected(${consent}, 'Yes')` |

Sources: [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings), [SurveyCTO form design style guide](https://support.surveycto.com/hc/en-us/articles/20723226621075-SurveyCTO-form-design-style-guide).

## Operators

SurveyCTO diverges from many examples of generic ODK/XPath syntax: equality is `=`, not `==`, and division is `div`, not `/`.

| Category | Operator | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| Arithmetic | `+` | number/date-dependent | Addition; also useful for date arithmetic by adding days. | `today() + 30` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Arithmetic | `-` | number/date-dependent | Subtraction; subtracting dates returns days. | `today() - ${dob}` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Arithmetic | `*` | number | Multiplication. | `${qty} * ${price}` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Arithmetic | `div` | number | Division. SurveyCTO docs use `div`, not `/`. | `10 div 2` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Arithmetic | `mod` | number | Remainder after division. | `${year} mod 4` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Comparison | `=` | boolean | Equal. SurveyCTO equality is `=`, not `==`. | `${age} = 18` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Comparison | `!=` | boolean | Not equal. | `${status} != 'refused'` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Comparison | `>` | boolean | Greater than. | `${age} > 17` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Comparison | `>=` | boolean | Greater than or equal. | `. >= 0` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Comparison | `<` | boolean | Less than. | `${age} < 130` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Comparison | `<=` | boolean | Less than or equal. | `. <= today()` | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Boolean | `and` | boolean | True only if both sides are true. | `. >= 0 and . <= 120` | [Logical operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#logical-operators) |
| Boolean | `or` | boolean | True if either side is true. | `${age} = 3 or ${age} = 4` | [Logical operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#logical-operators) |
| Boolean | `not()` | boolean | Negates the expression inside parentheses. | `not(selected(${crops}, '97'))` | [Logical operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#logical-operators) |
| String concatenation | `concat()` | string | SurveyCTO documents concatenation as a function, not an infix string operator. | `concat(${first}, ' ', ${last})` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |

## Function Reference

Return types are practical form-authoring types: `boolean`, `number`, `string`, `date`, `date-time`, `geopoint string`, or "same type as selected value" where SurveyCTO stores the result as the underlying field value.

### Strings

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `string()` | `string(field)` | string | Converts a value to a string. | `string(34.8) = '34.8'` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `string-length()` | `string-length(field)` | number | Length of the string value. | `string-length(.) >= 3` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `substr()` | `substr(fieldorstring, startindex, endindex)` | string | Substring from zero-based `startindex` up to but not including `endindex`. | `substr(${phone}, 0, 3)` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `concat()` | `concat(a, b, c, ...)` | string | Concatenates fields and/or strings. | `concat(${first}, ' ', ${last})` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `linebreak()` | `linebreak()` | string | Returns a line-break character. | `concat(${a}, linebreak(), ${b})` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `lower()` | `lower(fieldorstring)` | string | Converts text to lowercase. | `lower('Street Name')` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| `upper()` | `upper(fieldorstring)` | string | Converts text to uppercase. | `upper('Street Name')` | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |

### Select Fields and Choices

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `count-selected()` | `count-selected(field)` | number | Number of selected items in a `select_multiple` field. | `count-selected(.) = 3` | [Working with select_one and select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields) |
| `selected()` | `selected(field, value)` | boolean | True when `value` was selected in a `select_one` or `select_multiple`. Required for testing `select_multiple` membership. | `selected(${gender}, '1')` | [Working with select_one and select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields) |
| `selected-at()` | `selected-at(field, number)` | string | Returns the zero-based selected value from a `select_multiple`; returns the choice value, not label. | `selected-at(${crops}, 0)` | [Working with select_one and select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields) |
| `choice-label()` | `choice-label(field, value)` | string | Returns the label for a static choice-sheet option. Does not work for dynamically-loaded choices from pre-loaded data; use `pulldata()` to pull those labels. | `choice-label(${crop}, ${crop})` | [Working with select_one and select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields) |
| `jr:choice-name()` | old ODK-compatible choice-label function | string | Older equivalent to `choice-label()`. SurveyCTO documents `choice-label()` as similar but improved; its parameter order is different and single quotes around the field name are no longer needed. Prefer `choice-label()` in new SurveyCTO work. | Prefer `choice-label(${selectone}, ${selectone})` | [Expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields), [2.70 support note](https://support.surveycto.com/hc/en-us/articles/360045920593-New-functions-in-2-70) |

### Repeats and Aggregates

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `join()` | `join(string, repeatedfield)` | string | Joins all values of a repeated field using the delimiter in the first parameter. | `join(', ', ${hh_member_name})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `join-if()` | `join-if(string, repeatedfield, expression)` | string | Joins repeated values only for instances where `expression` is true. | `join-if(', ', ${name}, ${age} >= 18)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `count()` | `count(repeatgroup)` | number | Current number of instances in a repeat group. | `count(${members})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `count-if()` | `count-if(repeatgroup, expression)` | number | Count of repeat instances where `expression` is true. | `count-if(${members}, ${age} >= 18)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `sum()` | `sum(repeatedfield)` | number | Sum of all values in a repeated field. | `sum(${loan_size})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `sum-if()` | `sum-if(repeatedfield, expression)` | number | Sum of repeated values only where `expression` is true. | `sum-if(${loan_size}, ${loan_size} > 500)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `min()` | `min(repeatedfield)` | number/string/date-dependent | Minimum over a repeated field. | `min(${hh_member_age})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `min-if()` | `min-if(repeatedfield, expression)` | number/string/date-dependent | Minimum repeated value where `expression` is true. | `min-if(${age}, ${age} >= 18)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `max()` | `max(repeatedfield)` | number/string/date-dependent | Maximum over a repeated field. | `max(${hh_member_age})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `max-if()` | `max-if(repeatedfield, expression)` | number/string/date-dependent | Maximum repeated value where `expression` is true. | `max-if(${age}, ${age} >= 18)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `index()` | `index()` | number | Current repeat instance number, starting at 1. Use this instead of ODK `position(..)`. | `index()` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `indexed-repeat()` | `indexed-repeat(repeatedfield, repeatgroup, index[, repeatgroup2, index2, ...])` | same type as selected value | References a specific repeated field/group instance from outside that repeat. Additional parameters handle nested repeats. Invalid instance numbers fall back to instance 1. | `indexed-repeat(${name}, ${members}, 1)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `rank-index()` | `rank-index(index, repeatedfield)` | number | Rank of a specific repeated-field instance, highest value ranked 1. Ties are ordered arbitrarily; invalid/non-numeric instances return 999. | `rank-index(1, ${random_draw})` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| `rank-index-if()` | `rank-index-if(index, repeatedfield, expression)` | number | Like `rank-index()`, but ranks only instances where `expression` is true; the `index` still refers to the full unfiltered set. | `rank-index-if(1, ${age}, ${age} >= 18)` | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |

### Lists of Items

These operate on delimited string lists, not repeat groups directly. Empty items are counted.

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `count-items()` | `count-items(string, field)` | number | Number of items in a delimiter-separated list. | `count-items(',', ${addresses})` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |
| `item-at()` | `item-at(string, field, number)` | string | Zero-based item from a delimiter-separated list. | `item-at(',', ${addresses}, 0)` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |
| `item-index()` | `item-index(string, field, value)` | number | Index of the first matching list item; returns `-1` if not found. | `item-index(',', ${names}, ${name})` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |
| `item-present()` | `item-present(string, field, value)` | boolean | True if a delimiter-separated list contains `value`. | `item-present(',', ${addresses}, '')` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |
| `de-duplicate()` | `de-duplicate(string, field)` | string | Removes duplicates from a delimiter-separated list. | `de-duplicate(' ', join(' ', ${crops}))` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |
| `rank-value()` | `rank-value(value, list)` | number | Rank of a numeric value relative to a space-separated numeric list, highest value ranked 1. | `rank-value(3, '4 2 1 9 3 7')` | [Working with lists of items](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-lists-of-items) |

### Geography

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `distance-between()` | `distance-between(point1, point2)` | number | Distance in meters between two geopoints. Errors if non-GPS values are passed; guard relevance/calculation accordingly. | `distance-between(${start_gps}, ${end_gps})` | [Working with geographical data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-geographical-data) |
| `area()` | `area(setofgeopoints)` | number | Area in square meters enclosed by a geoshape, geotrace, or repeated geopoints. | `area(${gps_reading})` | [Working with geographical data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-geographical-data) |
| `geo-scatter()` | `geo-scatter(geopointfield, range)` | geopoint string | Adds random error up to `range` meters for anonymizing GPS locations. | `geo-scatter(${location}, 20)` | [Working with geographical data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-geographical-data) |
| `short-geopoint()` | `short-geopoint(geopointfield)` | string | Returns longitude and latitude only, with no altitude or accuracy. | `short-geopoint(${location})` | [Working with geographical data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-geographical-data) |

### Math and Numbers

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `number()` | `number(field)` | number | Converts a value to a number. Useful for numeric pre-loaded data, which is pulled as text. | `number('34.8') = 34.8` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `int()` | `int(field)` | number | Converts to an integer by dropping digits after the decimal. | `int('39.2') = 39` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `min()` | `min(field1, ..., fieldx)` | number/string/date-dependent | With multiple non-repeating arguments, returns the minimum argument. | `min(${father_age}, ${mother_age})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `max()` | `max(field1, ..., fieldx)` | number/string/date-dependent | With multiple non-repeating arguments, returns the maximum argument. | `max(${father_age}, ${mother_age})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `format-number()` | `format-number(field)` | string | Formats an integer or decimal using the user's locale settings. | `format-number(${income})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `round()` | `round(field, digits)` | number | Rounds to the specified number of digits after the decimal. | `round(${interest_rate}, 2)` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `abs()` | `abs(number)` | number | Absolute value. | `abs(${balance})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `pow()` | `pow(base, exponent)` | number | `base` raised to `exponent`. | `pow(${x}, 2)` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `log10()` | `log10(fieldorvalue)` | number | Base-ten logarithm. | `log10(${value})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `sin()` | `sin(fieldorvalue)` | number | Sine in radians. | `sin(${angle})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `cos()` | `cos(fieldorvalue)` | number | Cosine in radians. | `cos(${angle})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `tan()` | `tan(fieldorvalue)` | number | Tangent in radians. | `tan(${angle})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `asin()` | `asin(fieldorvalue)` | number | Arcsine in radians. | `asin(${ratio})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `acos()` | `acos(fieldorvalue)` | number | Arccosine in radians. | `acos(${ratio})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `atan()` | `atan(fieldorvalue)` | number | Arctangent in radians. | `atan(${slope})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `atan2()` | `atan2(x, y)` | number | Angle in radians subtended at the origin by `(x, y)` and the positive x-axis, in the range `-pi()` to `pi()`. | `atan2(${x}, ${y})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `sqrt()` | `sqrt(fieldorvalue)` | number | Non-negative square root. | `sqrt(${area})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `exp()` | `exp(x)` | number | `e^x`. | `exp(${x})` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| `pi()` | `pi()` | number | Value of pi. | `2 * pi()` | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |

### Dates and Times

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `duration()` | `duration()` | number | Seconds spent filling or editing the current submission. In `calculate_here`, `once(duration())` captures time first reaching that point. | `once(duration())` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `today()` | `today()` | date | Current date in `YYYY-MM-DD` format. | `. <= today()` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `now()` | `now()` | date-time/date when stored alone | Current date and time. SurveyCTO notes that `now()` by itself stores only the date; use with `format-date-time()` to store time. | `once(format-date-time(now(), '%Y-%b-%e %H:%M:%S'))` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `date()` | `date(string)` | date | Converts a string to a date without preserving time. Invalid/partial dates can throw errors. | `${birthday} > date('2013-01-31')` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `date-time()` | `date-time(string)` | date-time | Converts a string to a date-time for formatting. SurveyCTO says not to use it for comparisons when time matters; use `decimal-date-time()`. | `format-date-time(date-time('2013-01-31T16:42:00'), '%H:%M')` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `decimal-date-time()` | `decimal-date-time(string)` | number | Fractional days since January 1, 1970; use for date-time comparisons that include time. | `decimal-date-time(now()) < decimal-date-time('2013-01-31T16:42:00')` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |
| `decimal-time()` | `decimal-time(string)` | number | Fractional day: midnight `0`, noon `0.5`, 18:00 `0.75`. Useful for time constraints, including web forms. | `decimal-time(.) >= 0.5` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times), [time constraints support article](https://support.surveycto.com/hc/en-us/articles/360045912114-Constraining-time-fields-in-form-designs) |
| `format-date-time()` | `format-date-time(field, format)` | string | Formats date/time values as strings. Products are strings; convert again if numeric/date operations are needed later. | `format-date-time(today(), '%Y-%b-%e')` | [Working with dates and times](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-dates-and-times) |

Common `format-date-time()` tokens:

| Token | Meaning |
| --- | --- |
| `%Y` | Four-digit year |
| `%y` | Two-digit year |
| `%m` | Two-digit month |
| `%n` | One-or-two-digit month |
| `%b` | Three-letter month |
| `%d` | Two-digit day |
| `%e` | One-or-two-digit day |
| `%a` | Three-letter day of week |
| `%H` | Two-digit hour |
| `%h` | One-or-two-digit hour |
| `%M` | Two-digit minute |
| `%S` | Two-digit seconds |
| `%3` | Three-digit milliseconds |

### Enumerators and Device/Session Metadata

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `enumerator-name()` | `enumerator-name()` | string | Name of the currently selected enumerator from an `enumerator` field. | `enumerator-name()` | [Working with enumerators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-enumerators) |
| `enumerator-id()` | `enumerator-id()` | string | ID of the currently selected enumerator from an `enumerator` field. | `enumerator-id()` | [Working with enumerators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-enumerators) |
| `username()` | `username()` | string | Currently configured username of the user filling the form. | `username()` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `version()` | `version()` | string/number | Version number of the current form. | `version()` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `device-info()` | `device-info()` | string | Device/browser and SurveyCTO client details; format differs by platform. | `device-info()` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |

### Phone Calls

Android-only; not supported on iOS or web forms per SurveyCTO docs.

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `phone-call-log()` | `phone-call-log()` | string | Event log of call activity while filling the form, one event per line. More detailed when Collect is the default phone app. | `phone-call-log()` | [Working with phone calls](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-phone-calls) |
| `phone-call-duration()` | `phone-call-duration()` | number | Total seconds spent on a phone call during the form. | `if(phone-call-duration() div duration() > 0.5, 'yes', 'no')` | [Working with phone calls](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-phone-calls) |
| `collect-is-phone-app()` | `collect-is-phone-app()` | boolean | True when Collect is currently the default phone app. | `collect-is-phone-app()` | [Working with phone calls](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-phone-calls) |

### Conditional, Empty, Identity, Randomization, Regex, and Plug-ins

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `relevant()` | `relevant(field)` | boolean | True if a field is currently relevant; false if its relevance expression currently evaluates false. | `relevant(${followup_question})` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `empty()` | `empty(field)` | boolean | True if a field has no value, including because it is not relevant. | `empty(${consent})` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `if()` | `if(expression, valueiftrue, valueiffalse)` | same type as selected branch | Returns one of two values depending on whether `expression` is true. | `if(${age} >= 18, 'adult', 'minor')` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `coalesce()` | `coalesce(field1, field2, ...)` | same type as first non-empty arg | Returns the first non-empty non-repeated argument. | `coalesce(${id}, ${id2})` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `regex()` | `regex(field, expression)` | boolean | True if `field` matches the regular expression. SurveyCTO uses a Java engine; JavaScript regex tools are useful for many cases but not authoritative. | `regex(., '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}')` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `hash()` | `hash(fieldorvalue, ...)` | string | Hash representing one or more parameters. Useful for match verification without storing plain PII. | `hash(${name}, ${birthday})` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `uuid()` | `uuid()` | string | Unique random ID. Use `once(uuid())` when storing one stable ID. | `once(uuid())` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `once()` | `once(expression)` | same type as expression | For `calculate` or `calculate_here` only; calculates the enclosed expression only once per form. Use only as the outside of an expression. | `once(format-date-time(now(), '%Y-%b-%e %H:%M:%S'))` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `random()` | `random()` | number | Random draw between 0 inclusive and 1 exclusive. SurveyCTO warns to call it inside `once()` and never directly in relevance. | `once(random())` | [Randomizing survey elements](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/01.randomizing.html), [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions) |
| `plug-in-metadata()` | `plug-in-metadata(field)` | string | Metadata saved by a field plug-in, or empty string if none. | `item-at(' ', plug-in-metadata(${counter}), 0)` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions), [field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html) |

### Pre-loading and Dynamic Choices

| Function | Signature | Return type | Description | Example | Docs |
| --- | --- | --- | --- | --- | --- |
| `pulldata()` | `pulldata(source, colname, lookupcolname, lookupval)` | string | Pulls a value from an attached `.csv` file or server dataset. Even numeric-looking pulled data is text until converted with `number()` or `int()`. | `pulldata('hhplotdata', 'plot1size', 'hhid_key', ${hhid})` | [Other functions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#other-functions), [pre-loading](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html) |
| `search()` | `search(source)` | choice-list query | In `appearance`, loads all distinct dynamic choices from attached pre-loaded data. | `search('households')` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |
| `search()` | `search(source, 'contains', columnsToSearch, searchText)` | choice-list query | Includes distinct rows where any listed column contains `searchText`. | `search('hh', 'contains', 'name', ${name_text})` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |
| `search()` | `search(source, 'startswith', columnsToSearch, searchText)` | choice-list query | Includes rows where any listed column starts with `searchText`. | `search('hh', 'startswith', 'name', ${prefix})` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |
| `search()` | `search(source, 'endswith', columnsToSearch, searchText)` | choice-list query | Includes rows where any listed column ends with `searchText`. | `search('hh', 'endswith', 'name', ${suffix})` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |
| `search()` | `search(source, 'matches', columnsToSearch, searchText)` | choice-list query | Includes rows where any listed column exactly matches `searchText`. | `search('hh', 'matches', 'hhid_key', ${hhid})` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |
| `search()` | `search(source, searchType, columnsToSearch, searchText, columnToFilter, filterText)` | choice-list query | Further filters any search type to rows whose `columnToFilter` exactly contains `filterText`. | `search('hh', 'contains', 'name', ${q}, 'villageid', ${villageid})` | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |

`search()` belongs in `appearance`, not in `calculation`; dynamic choice-list setup also requires a matching row on the `choices` sheet. See [`xlsform.md`](xlsform.md#choice-filters-and-cascading-selects) for the worksheet pattern.

## SurveyCTO vs ODK/XPath Divergences

| Topic | SurveyCTO | Generic ODK/XPath pattern to avoid or translate | Why it matters | Source |
| --- | --- | --- | --- | --- |
| Equality | Use `=`. | `==` | SurveyCTO's documented comparison operator is `=`. | [Comparison operators](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#comparison-operators) |
| Division | Use `div`. | `/` | SurveyCTO's documented numeric division operator is `div`. | [Working with numbers](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers) |
| Skip-logic column | Use `relevance`. | `relevant` | SurveyCTO's spreadsheet column is `relevance`. | [Relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html), [Kobo conversion guide](https://support.surveycto.com/hc/en-us/articles/34654186431763-Converting-forms-from-KoboToolbox) |
| Current repeat index | Use `index()`. | `position(..)` | SurveyCTO says `position(..)` can fail in a non-repeating group inside a repeat group. | [Working with repeated data](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data) |
| Choice labels | Prefer `choice-label(field, value)`. | `jr:choice-name()` | `choice-label()` has a clearer name and different parameter order; single quotes around the field name are no longer needed. | [Expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields), [Kobo conversion guide](https://support.surveycto.com/hc/en-us/articles/34654186431763-Converting-forms-from-KoboToolbox) |
| Pre-loaded lookup | Use `pulldata()` and `search()`. | `instance('list')/root/item[...]` | SurveyCTO documents `pulldata()` for attached data and `search()` for dynamic choices. | [Pre-loading](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html), [Kobo conversion guide](https://support.surveycto.com/hc/en-us/articles/34654186431763-Converting-forms-from-KoboToolbox) |
| `select_multiple` checks | Use `selected(${field}, 'value')`. | `${field} = 'value'` | `select_multiple` stores a space-separated list; `=` tests exact equality, not list membership. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html), [choice-filter support article](https://support.surveycto.com/hc/en-us/articles/16472059641747-How-to-create-a-choice-filter) |
| String literals | Use straight single quotes; switch to double quotes only when the literal contains a single quote. | Smart quotes; backslash escaping; unquoted strings | SurveyCTO warns smart quotes break expressions and demonstrates double quotes for embedded single quotes. | [Working with strings](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-strings) |
| Dynamic defaults | Put expressions in `calculation`, not `default`. | Treating `default` as an expression column | SurveyCTO documents `default` as fixed and `calculation` as dynamic default for visible fields. | [Defaults](https://docs.surveycto.com/02-designing-forms/02-additional-topics/01.defaults.html) |
| Dynamic choice lists | Use `search()` in `appearance`. | `choice_filter` against pre-loaded choices | `choice_filter` filters static choices; pre-loaded dynamic choices use `search()` parameters or a plug-in. | [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html), [choice-filter support article](https://support.surveycto.com/hc/en-us/articles/16472059641747-How-to-create-a-choice-filter) |
| Unsupported/raw XLSForm columns | Translate or omit unsupported `instance::`, `bind::`, `body::`, etc. | Copying them from Kobo/ODK forms | SurveyCTO's conversion guide lists unsupported or renamed columns. | [Kobo conversion guide](https://support.surveycto.com/hc/en-us/articles/34654186431763-Converting-forms-from-KoboToolbox) |

## Worked Patterns

### Skip Logic

| Goal | Expression | Notes |
| --- | --- | --- |
| Show only after consent | `${consent} = '1'` | In the `relevance` column on a field/group. Style guide recommends `selected(${consent}, '1')` for select fields for future-proofing. |
| Show when any of several countries selected | `selected(${country}, 'South Africa') or selected(${country}, 'Zimbabwe')` | `selected()` works for `select_one` and `select_multiple`. |
| Hide until prerequisite exists | `not(empty(${household_id}))` | Useful before `pulldata()` defaults calculate. |

### Constraints

| Goal | Expression | Notes |
| --- | --- | --- |
| Age range | `. >= 0 and . <= 120` | `.` is the proposed current entry. Add a clear `constraint message`. |
| Not older than respondent's age | `. >= 0 and . <= ${age}` | Compare current field with prior numeric field. |
| Birthdate cannot be future | `. <= today()` | Date fields can be compared to `today()`. |
| Static date window | `. >= date('2020-01-01') and . <= today()` | Use `date()` for literal date strings. |
| Time between noon and 5pm | `decimal-time(.) >= 0.5 and decimal-time(.) <= 0.7083333` | `decimal-time()` avoids some web-form UTC issues noted in support docs. |

### Age From Date of Birth

| Scenario | Expression | Notes |
| --- | --- | --- |
| Integer age from date field | `int((today() - ${dob}) div 365.25)` | Approximate year age; support docs warn exact cutoffs for young children may need day-based logic. |
| Decimal age | `round((today() - ${dob}) div 365.25, 2)` | Uses `round()`. |
| Age from pre-loaded Y/M/D fields | `int((today() - date(${dob_pl})) div 365.25)` | Build `${dob_pl}` with `concat(${year_pl}, '-', ${month_pl}, '-', ${day_pl})`; guard against invalid/partial dates before calling `date()`. |

Source: [Basic time calculations](https://support.surveycto.com/hc/en-us/articles/360024601133-Basic-time-calculations-including-how-to-calculate-age-from-a-birthdate).

### Conditional Values

| Goal | Expression | Notes |
| --- | --- | --- |
| Categorize adult/minor | `if(${age} >= 18, 'adult', 'minor')` | Branch values should have compatible intended storage. |
| First available ID | `coalesce(${national_id}, ${project_id}, ${manual_id})` | `coalesce()` accepts non-repeated arguments. |
| Optional date conversion | `if(not(empty(${concat_date})), date(${concat_date}), '')` | Avoid passing blank/invalid dates to `date()`. |

### Pre-loaded Data With `pulldata()`

| Goal | Expression | Notes |
| --- | --- | --- |
| Pull plot size | `pulldata('hhplotdata', 'plot1size', 'hhid_key', ${hhid})` | Source can be attached `hhplotdata.csv` or server dataset ID `hhplotdata`. |
| Use pulled number in math | `number(${interest_rate_pl}) * 100` | Pulled values are text even when they look numeric. |
| Pull dynamic choice label | `pulldata('households', 'hh_name', 'hhid_key', ${selected_hhid})` | Use this for dynamically-loaded choices; `choice-label()` only retrieves static choice-sheet labels. |

### Dynamic Lists With `search()`

| Goal | `appearance` expression | Notes |
| --- | --- | --- |
| Load all distinct rows | `search('households')` | Choices sheet row names the source columns for `value` and `label`. |
| Search names by typed text | `search('households', 'contains', 'name', ${name_text})` | Third parameter can be a comma-separated list of columns. |
| Search within village | `search('households', 'contains', 'name', ${name_text}, 'villageid', ${villageid})` | Extra filter is exact match in the filter column. |

Dynamic choices are ordered by source order unless the attached data has a numeric `sortby` column. See [loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html).

### Stable Randomization and Treatment Assignment

| Goal | Expression | Notes |
| --- | --- | --- |
| Stable random draw | `once(random())` | Put this alone in a `calculate` field such as `rand`. |
| Two-arm assignment | `if(${rand} < 0.5, 'treatment', 'control')` | Never put `random()` directly in relevance. |
| Three-arm assignment | `if(${rand} < 0.333333, 'A', if(${rand} < 0.666667, 'B', 'C'))` | Keep the random draw separate for auditability. |
| Stable UUID | `once(uuid())` | Use for a generated ID once per form. |

Source: [Randomizing survey elements](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/01.randomizing.html).

### Regex Validation

| Goal | Expression | Notes |
| --- | --- | --- |
| Email-like text | `regex(., '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}')` | Java regex engine; test carefully on target platforms. |
| Digits only | `regex(., '^[0-9]+$')` | Use a `text` field with numeric appearance if leading zeros or long IDs matter. |

### Repeated Data

| Goal | Expression | Notes |
| --- | --- | --- |
| Current repeat number | `index()` | Use in a calculate field inside the repeat. |
| Same repeat instance label | `How old is ${hh_name}?` | Works when label is in the same repeat group as `${hh_name}`. |
| First repeated name outside repeat | `indexed-repeat(${hh_name}, ${hh_rep}, 1)` | Use `indexed-repeat()` for a specific instance. |
| Matching instance in a later repeat | `indexed-repeat(${crop_rev}, ${crop_rep}, index())` | Common when two repeats have the same `repeat_count`. |
| Sum all repeated values | `sum(${crop_rev})` | Use aggregate functions for all instances. |
| List adult names | `join-if(', ', ${hh_name}, ${hh_age} >= 18)` | Expression is evaluated per repeat instance. |

## Common Pitfalls and How to Recognize Them

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Upload says a field cannot be found. | Typo in `${field}` reference or renamed field. | Search the workbook for the missing name; fix every reference. |
| `==` expression fails or behaves unexpectedly. | Generic ODK/JavaScript equality copied in. | Use `=`. |
| Division expression fails. | Used `/` instead of `div`. | Use `div`. |
| `select_multiple` choice filter misses selected items. | Used `${multi} = filter`; the field stores a space-separated list. | Use `selected(${multi}, filter)`. |
| Labels show `1` instead of `Yes`. | Directly referenced a select field; stored value is not the label. | Use `choice-label()` for static choices, or `pulldata()` for dynamic choices. |
| Dynamic choice labels do not work with `choice-label()`. | Choices came from pre-loaded data via `search()`. | Pull the display label from the source data with `pulldata()`. |
| Relevance on same `field-list` screen does not update after an answer. | Relevance is evaluated when the screen first displays. | Put dependent fields on later screens or restructure groups. |
| Form throws indexed-repeat error. | Repeated field referenced outside its repeat without specifying instance/aggregate. | Use `indexed-repeat()`, `sum()`, `join()`, `count()`, etc. |
| Random assignment changes after editing/saving. | Used `random()` directly or nested incorrectly. | Store `once(random())` in its own calculate field and reference that field. |
| Dynamic default is blank or stale. | Visible field's calculation ran before prerequisites existed. | Add `relevance` so the field/group appears only after prerequisites are filled. |
| `date()` causes errors before all components are filled. | Partial or invalid constructed date string. | Guard with `if()`/`empty()` and validate year/month/day before calling `date()`. |
| Time constraints work on mobile but not web. | `format-date-time()` and web-form UTC conversion mismatch. | Consider `decimal-time()` for local-time comparisons. |
| Smart quotes break expressions. | Rich text editor converted straight quotes. | Replace with straight `'` or `"`. |
| Pre-loaded numeric math gives wrong result or fails. | `pulldata()` returns text. | Wrap pulled fields in `number()` or `int()` before math. |
| Choice-filter values do nothing. | Filter values were placed on choices but no `choice_filter` expression uses them, or values were dynamic formulas. | Add a `choice_filter` on the select field; keep choices-sheet filter values static. |

## Debugging Checklist

1. Read the first line of the SurveyCTO error and identify the field or expression type named there.
2. Search the workbook for every field reference in the expression; fix typos and renamed fields first.
3. Confirm SurveyCTO syntax: `=`, `div`, `relevance`, `index()`, `choice-label()`, and `selected()` for `select_multiple`.
4. If a repeated field is involved, decide whether you need all instances (`sum()`, `join()`, `count()`) or one instance (`indexed-repeat()`).
5. Temporarily remove or simplify the suspected expression and re-upload/test; if the form uploads, rebuild the expression in smaller calculate fields.
6. Use the server tools where available: Test constraint, Build constraint, Build relevance, and Build calculation.

Source: [Debugging form errors](https://docs.surveycto.com/02-designing-forms/05-performance-and-debugging/01.debugging.html).
