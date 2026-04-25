<!--
  PRIMER: expressions
  STATUS: V1 — slated for regeneration from docs.surveycto.com via the prompt
  in README.md ("Regenerating primers"). Keep expression-language semantics
  here; XLSForm column placement belongs in xlsform.md.
-->

# SurveyCTO Expressions Reference

This is the bundled reference for all SurveyCTO expression operators and functions. For the most current version, see the live documentation: [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html).

## Referencing current values

`${fieldname}`
Refers to a different field's current value.
Example: `${age}` returns the value entered in the field named `age`.

`.`
Refers to the user's proposed entry for the current field.
Example: `. < 3` checks if the new proposed value for the current field is less than 3.

## Comparison operators

| Operator | Operation | Example | Example answer |
| --- | --- | --- | --- |
| = | Equal | `${fieldname} = 3` | `true` or `false` |
| != | Not equal | `${fieldname} != 3` | `true` or `false` |
| > | Greater-than | `${fieldname} > 3` | `true` or `false` |
| >= | >-or-equal | `${fieldname} >= 3` | `true` or `false` |
| < | Less-than | `${fieldname} < 3` | `true` or `false` |
| <= | <-or-equal | `${fieldname} <= 3` | `true` or `false` |

## Logical operators

`or`
Returns true if either expression evaluates to true.
Example: `${age} = 3 or ${age} = 4` returns true if age is 3 or 4.

`and`
Returns true only if both expressions evaluate to true.
Example: `${age} > 3 and ${age} < 5` returns true if age is between 3 and 5.

`not()`
Returns true if the expression does not evaluate to true.
Example: `not(${age} > 3 and ${age} < 5)` returns true if age is not between 3 and 5.

## Working with strings

Literal strings should be enclosed in single-quotes, except when including single-quotes in the string.
Example: `if(${yesno} = 1, "a string with 'single quotes' in it", "no single quotes here")`

`string(field)`
Converts field to a string.
Example: `string(34.8) = '34.8'`

`string-length(field)`
Returns the length of the string field.
Example: `string-length(.) > 3 and string-length(.) < 10` ensures field is between 3 and 10 characters.

`substr(fieldorstring, startindex, endindex)`
Returns a substring starting at startindex and ending just before endindex.
Example: `substr(${phone}, 0, 3)` returns the first three digits of a phone number.

`concat(a, b, c, ...)`
Concatenates fields and/or strings together.
Example: `concat(${firstname}, ' ', ${lastname})` returns a full name.

`linebreak()`
Returns a linebreak character.
Example: `concat(${field1}, linebreak(), ${field2}, linebreak(), ${field3})` returns a list of three field values with linebreaks between them.

`lower()`
Converts a string to all lowercase characters.
Example: `lower('Street Name')` returns "street name".

`upper()`
Converts a string to all uppercase characters.
Example: `upper('Street Name')` returns "STREET NAME".

## Working with select_one and select_multiple fields

`count-selected(field)`
Returns the number of items selected in a select_multiple field.
Example: `count-selected(.) = 3` ensures exactly three choices are selected.

`selected(field, value)`
Returns true or false depending on whether the value was selected.
Example: `selected(${gender}, 'Male')` shows a group or field if `Male` was selected.

`selected-at(field, number)`
Returns the selected item at the specified index in a select_multiple field.
Example: `selected-at(${fieldname}, 0) = 'Shona'` shows a group or field if the first selected choice is `Shona`.

`choice-label(field, value)`
Returns the label for a select_one or select_multiple field choice.
Example: `choice-label(${selectonefield}, ${selectonefield})` returns the label for the current choice in `selectonefield`.

## Working with repeated data

`join(string, repeatedfield)`
Generates a string-separated list of values from a field within a repeat group.
Example: `join(', ', ${hh_member_name})` generates a comma-separated list from all entered names.

`join-if(string, repeatedfield, expression)`
Like `join()`, but checks each instance with the expression.
Example: `join-if(', ', ${hh_member_name}, ${age} >= 18)` generates a list from names of adults.

`count(repeatgroup)`
Returns the current number of times a repeat group has repeated.
Example: `count(${repeatgroupname})` returns the number of instances of the group.

`count-if(repeatgroup, expression)`
Like `count()`, but checks each instance with the expression.
Example: `count-if(${hhmembers}, ${age} >= 18)` returns the count of adult household members.

`sum(repeatedfield)`
Calculates the sum of all values in a field within a repeat group.
Example: `sum(${loan_size})` returns the total value of all loans.

`sum-if(repeatedfield, expression)`
Like `sum()`, but checks each instance with the expression.
Example: `sum-if(${loan_size}, ${loan_size} > 500)` returns the total value of loans over 500.

`min(repeatedfield)`
Calculates the minimum of all values in a field within a repeat group.
Example: `min(${hh_member_age})` returns the age of the youngest household member.

`min-if(repeatedfield, expression)`
Like `min()`, but checks each instance with the expression.
Example: `min-if(${hh_member_age}, ${hh_member_age} >= 18)` returns the age of the youngest adult.

`max(repeatedfield)`
Calculates the maximum of all values in a field within a repeat group.
Example: `max(${hh_member_age})` returns the age of the oldest household member.

`max-if(repeatedfield, expression)`
Like `max()`, but checks each instance with the expression.
Example: `max-if(${hh_member_age}, ${hh_member_age} >= 18)` returns the age of the oldest adult.

`index()`
Returns the index number for the current repeat group instance.
Example: `index()` returns 1 for the first instance, 2 for the second, etc.

`indexed-repeat(repeatedfield, repeatgroup, index)`
References a field or group inside a repeat group from outside that group.
Example: `indexed-repeat(${name}, ${names}, 1)` returns the first name from the `names` repeat group.

`rank-index(index, repeatedfield)`
Calculates the ordinal rank of the specified instance of a repeated field. Rank 1 is assigned to the instance with the highest value, rank 2 to the next-highest, and so on.
Example: `rank-index(1, ${random_draw})` calculates the rank of the first instance based on `random_draw`.

`rank-index-if(index, repeatedfield, expression)`
Like `rank-index()`, but checks each instance with the expression. Instances where the expression is false are omitted from the calculation.
Example: `rank-index-if(1, ${age}, ${age} >= 18)` calculates the age rank of instance 1 within the set of adults.

## Working with lists of items

`count-items(string, field)`
Returns the number of items in a list separated by string.
Example: `count-items(',', ${list_of_addresses})` returns the number of addresses in a comma-separated list.

`item-at(string, field, number)`
Returns the item at index number from a list separated by string.
Example: `item-at(',', ${list_of_addresses}, 0)` returns the first address in a comma-separated list.

`item-index(string, field, value)`
Returns the index of value from a list separated by string.
Example: `item-index(',', ${list_of_names}, ${name})` returns the index of ${name} in a comma-separated list.

`item-present(string, field, value)`
Checks if value is present in a list separated by string.
Example: `item-present(',', ${list_of_addresses}, '')` checks if any items in a comma-separated list are empty.

`de-duplicate(string, field)`
Removes duplicates from a list separated by string.
Example: `de-duplicate(' ', ${fieldname})` removes duplicate values from a space-separated list.

`rank-value(value, list)`
Calculates the ordinal rank of a value relative to a space-separated list.
Example: `rank-value(3, '4 2 1 9 3 7')` calculates the rank of `3` in the list.

## Working with geographical data

`distance-between(point1, point2)`
Returns the distance in meters between two geopoint fields.
Example: `distance-between(${start_gps}, ${end_gps})`

`area(setofgeopoints)`
Returns the area in square-meters enclosed within a series of GPS coordinates.
Example: `area(${gps_reading})` calculates the total area between all points.

`geo-scatter(geopointfield, range)`
Adds error to a GPS coordinate for anonymization.
Example: `geo-scatter(${location}, 20)` moves the GPS point within 20 meters of the original.

`short-geopoint(geopointfield)`
Returns a string with only the longitude and latitude.
Example: `short-geopoint(${location})`

## Working with numbers

| Operator | Operation | Example | Example answer |
| --- | --- | --- | --- |
| + | Addition | `1 + 1` | `2` |
| - | Subtraction | `3 - 2` | `1` |
| * | Multiplication | `3 * 2` | `6` |
| div | Division | `10 div 2` | `5` |
| mod | Modulus | `9 mod 2` | `1` |

`number(field)` — Converts field to a number. Example: `number('34.8') = 34.8`

`int(field)` — Converts field to an integer.

`min(field1, ... , fieldx)` — Returns the minimum of the passed fields. Example: `min(${father_age}, ${mother_age})`

`max(field1, ... , fieldx)` — Returns the maximum of the passed fields. Example: `max(${father_age}, ${mother_age})`

`format-number(field)` — Formats a number according to locale settings. Example: `format-number(${income})` formats "120000" as "120,000".

`round(field, digits)` — Rounds a number to the specified digits after the decimal. Example: `round(${interest_rate}, 2)`

`abs(number)` — Returns the absolute value.

`pow(base, exponent)` — Returns base raised to the power of exponent.

`log10(fieldorvalue)` — Returns the base-ten logarithm.

`sin(fieldorvalue)`, `cos(fieldorvalue)`, `tan(fieldorvalue)` — Trigonometric functions (radians).

`asin(fieldorvalue)`, `acos(fieldorvalue)`, `atan(fieldorvalue)` — Inverse trigonometric functions (radians).

`atan2(x, y)` — Returns the angle in radians subtended at the origin by the point (x, y).

`sqrt(fieldorvalue)` — Returns the non-negative square root.

`exp(x)` — Returns `e^x`.

`pi()` — Returns the value of pi.

## Working with dates and times

`duration()` — Returns the total amount of time spent, in seconds, filling or editing the current form submission.
Example: `duration()` in a `calculate` field captures total time spent on the form.
Example: `once(duration())` in a `calculate_here` field captures the time to first reach that point.

`today()` — Returns the current date in YYYY-MM-DD format.
Example: `format-date-time(today(), '%Y-%b-%e')`

`now()` — Returns the current date and time.
Example: `once(format-date-time(now(), '%Y-%b-%e %H:%M:%S'))`

`date(string)` — Converts string into a date without preserving time.
Example: `${birthday} > date('2013-01-31')`

`date-time(string)` — Converts a string into a date-time.
Example: `format-date-time(date-time('2013-01-31T16:42:00'), 'at %H:%M:%S on %e %b, %Y')`

`decimal-date-time(string)` — Converts a string to the number of days since January 1, 1970.
Example: `decimal-date-time(now()) < decimal-date-time('2013-01-31T16:42:00')`

`decimal-time(string)` — Converts a string to a number representing a fractional day.
Example: `decimal-time('2013-01-31T18:00:00')` returns 0.75.

`format-date-time(field, format)` — Converts date and/or time into a string.
Example: `format-date-time(${fieldname}, '%Y-%b-%e %H:%M:%S')`

**Format string values:**

| Value | Description |
| --- | --- |
| %Y | four-digit year |
| %y | two-digit year |
| %m | two-digit month |
| %n | one-or-two digit month |
| %b | three-letter month |
| %d | two-digit day |
| %e | one-or-two-digit day |
| %a | three-letter day of week |
| %H | two-digit hour |
| %h | one-or-two-digit hour |
| %M | two-digit minute |
| %S | two-digit seconds |
| %3 | three-digit milliseconds |

## Working with enumerators

`enumerator-name()` — Returns the name of the selected enumerator.

`enumerator-id()` — Returns the ID of the selected enumerator.

## Working with phone calls

`phone-call-log()` — Records an event log of call activity during form filling.
Example: returns a log like "Call started|5555555555|12".

`phone-call-duration()` — Returns the total seconds spent on a phone call during the form.
Example: `if(phone-call-duration() div duration() > 0.5, 'yes', 'no')`

`collect-is-phone-app()` — Returns true if Collect is the default phone app.

## Other functions

`relevant(field)` — Checks if a field is currently relevant. Example: `relevant(${followup_question})`

`empty(field)` — Checks if a field is currently empty. Example: `empty(${consent})`

`if(expression, valueiftrue, valueiffalse)` — Returns one of two values depending on the expression.
Example: `if(selected(${country}, 'South Africa'), 'SADC', 'Non-SADC')`

`pulldata(source, colname, lookupcolname, lookupval)` — Pulls data from an attached dataset or .csv file.
Example: `pulldata('hhplotdata', 'plot1size', 'hhid_key', ${hhid})`

`once()` — Indicates that the enclosed expression should be calculated only once per form.
Example: `once(format-date-time(now(), '%Y-%b-%e %H:%M:%S'))`

`once(random())` — Returns a random number between 0 and 1.
Example: Create a calculate field with `once(random())`, then refer to that field in other expressions.

`coalesce(field1, field2, ...)` — Returns the first non-empty field.
Example: `coalesce(${id}, ${id2})`

`regex(field, expression)` — Returns true if the field matches the regular expression.
Example: `regex(., '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}')`

`hash(fieldorvalue, ...)` — Returns a hash value representing the parameters passed.
Example: `hash(${name}, ${birthday})`

`uuid()` — Calculates a unique random ID.

`username()` — Returns the currently-configured username.

`version()` — Returns the version number of the current form.

`device-info()` — Returns information about the device used to fill out the form.
Examples:
Android: `google|Pixel 3|10|SurveyCTO Collect 2.70.1 (26c7d74)`
iOS: `Apple|My iPhone|13.1.2|SurveyCTO Collect 2.70.1 (52.18)`
Web Forms: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.83 Safari/537.36|SurveyCTO web forms 2.70.2`

`plug-in-metadata(field)` — Returns the metadata saved by a field plug-in for the specified field (or an empty string if there is none).
Example: `plug-in-metadata(${counter})` returns the plug-in metadata saved in the `counter` field.
