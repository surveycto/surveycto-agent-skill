<!-- PRIMER: xlsform
  STATUS: regenerated 2026-04-26 from docs.surveycto.com -->

# SurveyCTO XLSForm Mechanics

This primer covers the structure of SurveyCTO XLSForm workbooks: worksheets, columns, field types, choices, groups, repeats, appearances, and form settings. Expression syntax belongs in [`expressions.md`](expressions.md); dataset attachment and dataset XML belong in [`datasets-xml.md`](datasets-xml.md).

Canonical docs: [Designing forms: core concepts](https://docs.surveycto.com/02-designing-forms/01-core-concepts/), [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html), [Grouping and repeating questions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [Constraints](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html), and [Relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html).

## Worksheets

SurveyCTO spreadsheet form definitions are workbooks with three functional worksheets. The bundled skill template also includes help worksheets, discussed at the end.

| Worksheet | Role | Key rules | Canonical docs |
| --- | --- | --- | --- |
| `survey` | One row per field, group marker, repeat marker, calculation, audit, or metadata field. This is where form order, logic, labels, validation, repeats, and appearances live. | Rows run in form order. `type` and `name` are the core identifiers. Field names must be unique and cannot contain spaces or punctuation. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html) |
| `choices` | Choice lists for `select_one` and `select_multiple` fields. | `list_name` matches the list name in `survey.type`; `value` is stored in data; `label` is shown to users. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html), [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `settings` | Form-level metadata and settings. | Put settings in row 2. `form_id` must be unique and stable for the life of the form. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [Updating an existing form](https://docs.surveycto.com/02-designing-forms/01-core-concepts/10.updating.html) |

## Survey Columns

Columns are exact. Use spaces where documented, for example `constraint message`, `required message`, and `read only`; use underscores where documented, for example `repeat_count` and `choice_filter`.

| Column | Applies to | What it does | How to use it | Canonical docs |
| --- | --- | --- | --- | --- |
| `type` | Every row | Defines the row's field type or structural marker. | Use `text`, `integer`, `select_one yesno`, `begin group`, `begin repeat`, etc. Conditional formatting in the SurveyCTO template highlights recognized types. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [field type pages](https://docs.surveycto.com/02-designing-forms/01-core-concepts/) |
| `name` | Every field, group, repeat | Internal identifier; exported variable name for data fields. | Must be unique; use only letters, digits, underscores, and conservative ASCII names. End rows often repeat the name for readability, though only `type=end group` or `type=end repeat` is required. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `label` | Visible fields, groups, choices via `choices.label` | Primary prompt or display text. | Prefer concise plain text. SurveyCTO does not render Markdown; do not use `**bold**`, `# headings`, or Markdown list syntax expecting formatting. Labels can include line breaks, simple inline HTML fragments such as `<b>text</b>` or `<br>`, and `${field}` references to prior fields or groups. Group references display group labels; repeat-group references display labels for all instances. | [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html) |
| `label:Language` | Visible fields and groups | Translation of `label`. | Add one column per non-default language, such as `label:Spanish`. Keep the base `label` column for the default language. | [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `hint` | Visible fields | Italic helper text below the label. | Use for enumerator guidance. SurveyCTO docs state hints do not support HTML formatting. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html) |
| `hint:Language` | Visible fields | Translation of `hint`. | Add per-language variants such as `hint:Tamil`. | [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `default` | Editable visible fields | Fixed default value. | Put the literal stored value to prefill the field. For dynamic defaults, use `calculation` instead. | [Defaults](https://docs.surveycto.com/02-designing-forms/02-additional-topics/01.defaults.html), [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html) |
| `appearance` | Many field types, groups, repeats, audits, plug-ins | Controls presentation or special behavior. | Use documented options such as `minimal`, `quick`, `field-list`, `table`, `randomized`, `search(...)`, `custom-plugin(...)`. Some options combine with spaces; audit parameters use semicolons. | Field-type pages, [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html) |
| `constraint` | Editable fields | Validation expression for non-blank responses. | Expression must evaluate true before the user can proceed. Use `.` for the proposed current value. See [`expressions.md`](expressions.md). | [Constraints](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html), [support guide](https://support.surveycto.com/hc/en-us/articles/360015295234) |
| `constraint message` | Editable fields with `constraint` | Custom message when constraint fails. | Put user-facing correction text. Add language variants for translated forms. | [Constraints](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html), [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `constraint message:Language` | Editable fields with `constraint` | Translation of `constraint message`. | Add per-language variants such as `constraint message:French`. | [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `relevance` | Fields, groups, repeats | Skip logic. Hidden rows have empty responses. | Put an expression that evaluates true when the row should appear. Relevance on a `begin group` applies to the whole group. Relevance is evaluated when a screen is first displayed, so fields on the same `field-list` screen cannot dynamically appear/disappear based on answers above them on that same screen. | [Relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html) |
| `disabled` | Survey rows | Temporarily disables a field. | Put `yes`. If you need old data to remain exportable, prefer `relevance` set to `0` rather than deleting or disabling the row. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html), [Updating forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/10.updating.html) |
| `required` | Editable visible fields | Requires a non-blank response. | Put `yes`. A constraint does not force a blank optional field to be answered; use `required` for that. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html), [Constraints](https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html) |
| `required message` | Required fields | Custom message when a required response is blank. | Put user-facing text. Add language variants for translated forms. | Template help worksheet, [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `required message:Language` | Required fields | Translation of `required message`. | Add per-language variants such as `required message:Hindi`. | [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `read only` | Visible fields | Shows a field without allowing edits. | Put `yes`. Note fields are inherently read-only. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html) |
| `calculation` | `calculate`, `calculate_here`, and dynamic defaults | Expression to compute a hidden value or editable field default. | For `calculate`, this is the stored value. For visible fields, it computes the default the first time the field is displayed. Configure relevance so dynamic defaults do not calculate too early. See [`expressions.md`](expressions.md). | [calculate](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zb.field-types-calculate.html), [Defaults](https://docs.surveycto.com/02-designing-forms/02-additional-topics/01.defaults.html) |
| `repeat_count` | `begin repeat` rows | Fixed or calculated number of repeat instances. | Use a number such as `3`, or an expression/reference such as `${num_hh_members}`. Without it, the user controls when to add/stop instances. | [Groups and repeats](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [Repeating fields](https://docs.surveycto.com/02-designing-forms/02-additional-topics/02.repeats.html) |
| `media:image` | Visible fields | Image displayed with a field. | Put the exact filename and upload the file with the form. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html), [Images sample](https://docs.surveycto.com/02-designing-forms/04-sample-forms/04.images.html) |
| `media:audio` | Visible fields | Audio clip played with a field. | Put the exact filename and upload the file with the form. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html) |
| `media:video` | Visible fields | Video clip displayed with a field. | Put the exact filename and upload the file with the form. | [Other field properties](https://docs.surveycto.com/02-designing-forms/01-core-concepts/05.other-columns.html) |
| `media:image:Language`, `media:audio:Language`, `media:video:Language` | Visible fields | Language-specific media. | Add one translated media column per language. Upload every referenced file. | [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html) |
| `choice_filter` | `select_one`, `select_multiple` | Filters static choices using columns on `choices`. | Typical pattern: put `filter=${prior_select}` and add a `filter` column on the relevant choice list. More complex expressions and multiple filter columns are allowed. See [`expressions.md`](expressions.md). | [Cascading selects](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/02.cascading-selects.html) |
| `mediatype` | `file` | Restricts accepted file MIME types. | Leave blank for SurveyCTO's default accepted categories, or provide a comma-separated MIME list. | [file](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03o2.field-types-file.html) |
| `accuracy_threshold` | `geopoint` | Mobile GPS accuracy target in meters. | Put `1`, `5`, `10`, etc. Applies on mobile devices; default target is 5m. | [geopoint](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j.field-types-geopoint.html) |
| `publishable` | Encrypted forms | SurveyCTO-specific. Leaves a field unencrypted so it can be published/downloaded conveniently. | Put `yes` only for non-sensitive fields. File attachments remain encrypted even if marked publishable. Ignored for unencrypted forms. | [Encryption](https://docs.surveycto.com/02-designing-forms/02-additional-topics/06.encrypting.html) |
| `minimum_seconds` | Visible fields | SurveyCTO-specific speed-limit metadata. | Put the minimum seconds expected on first view. Collect for Android can enforce this, and speed-violation fields can count, list, or audit violations. | [speed violations](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zc.field-types-speed-violations.html), [quality docs](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/01.collecting-high-quality-data.html) |
| `note` | Printable form output | SurveyCTO template column for print-only explanatory notes. | Use to explain relevance, constraints, or instructions in printable copies; not a runtime prompt. | Template help worksheet, [printable forms](https://docs.surveycto.com/02-designing-forms/02-additional-topics/04.printable-copies.html) |
| `response_note` | Printable form output | SurveyCTO template column for print-only response-area text/symbols. | Use to show response boxes or symbols in printable versions. | Template help worksheet, [printable forms](https://docs.surveycto.com/02-designing-forms/02-additional-topics/04.printable-copies.html) |

### Label, Hint, And Message Formatting

SurveyCTO labels, choice labels, notes, hints, constraint messages, required messages, and group labels are not Markdown-rendered. Do not use Markdown markers such as `**bold**`, `_italic_`, `# heading`, or Markdown bullet syntax expecting formatted output. Use plain text by default.

SurveyCTO can render simple inline HTML fragments in labels/notes and similar display text, such as `<b>important</b>`, `<i>emphasis</i>`, `<u>underline</u>`, and `<br>` for line breaks. Do not write full HTML documents with `<html>`, `<head>`, or `<body>`. Use HTML sparingly because field types, appearances, hints, and plug-ins already provide most visual structure.

Hints are already styled as helper text by the client; SurveyCTO docs state hints do not support HTML formatting, so keep hints plain and concise.

## Field Types

SurveyCTO's current core field-type index documents the types below. Rows marked "SurveyCTO-specific" are SurveyCTO extensions or SurveyCTO-specific field families, not generic XLSForm basics.

| `type` value | Visible? | What it stores/does | Key columns and notes | Canonical docs |
| --- | --- | --- | --- | --- |
| `text` | Yes | Text string. | `appearance` can be `numbers`, `numbers_decimal`, or `numbers_phone` to show numeric keyboards while still storing text; useful for values longer than integer limits. Supports field plug-ins. | [text](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03a.field-types-text.html) |
| `integer` | Yes | Whole number, no decimals. | Integers are limited to nine digits or fewer. `appearance=show_formatted` displays locale-formatted grouping while typing. Supports field plug-ins. | [integer](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03f.field-types-integer.html) |
| `decimal` | Yes | Number with decimals allowed. | `appearance=show_formatted` displays locale-formatted grouping while typing. Supports field plug-ins. | [decimal](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03g.field-types-decimal.html) |
| `select_one listname` | Yes | One stored choice value from `choices.list_name=listname`. | Use `choice_filter` for cascading selects. Supports many appearances and field plug-ins. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `select_multiple listname` | Yes | Space-separated stored choice values. | Use `selected()` in relevance/constraints. Exports can include dummy 1/0 columns unless disabled in Desktop. Supports appearances and field plug-ins. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `enumerator` | Yes | SurveyCTO-specific. Enumerator name and ID in one value, selected/entered/scanned from an attached enumerator dataset. | `appearance` can include `default-to-entry`, `default-to-scan`, `add-new-code(xyz)`, `other-user-code(xyz)`. Requires Collect v2.72+ for proper mobile support. | [enumerator](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i2.field-types-enumerator.html), [managing enumerators](https://docs.surveycto.com/04-monitoring-and-management/01-the-basics/06.managing-enumerators.html) |
| `geopoint` | Yes | Single GPS position. | `appearance=maps`, `placement-map`, or `background`; `accuracy_threshold` sets mobile target accuracy. Web does not support `background`. | [geopoint](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j.field-types-geopoint.html), [GPS data](https://docs.surveycto.com/02-designing-forms/02-additional-topics/04b.collecting-gps-data.html) |
| `geoshape` | Yes | GPS polygon enclosing an area. | Android Collect only; web falls back to a single GPS position. | [geoshape](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j2.field-types-geoshape.html) |
| `geotrace` | Yes | GPS open polyline or closed polygon. | Android Collect only; supports manual and automatic point collection in the user interface. | [geotrace](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j3.field-types-geotrace.html) |
| `barcode` | Yes | Barcode or QR-code value. | Android requires a QR/barcode reader app; iOS needs no extra app; web not supported. | [barcode](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03k.field-types-barcode.html) |
| `datetime` | Yes | Date and time. | `appearance=no-calendar`, `month`, or `month-year`. | [datetime/date/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html) |
| `date` | Yes | Date. | `appearance=no-calendar`, `month`, or `month-year`. | [datetime/date/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html) |
| `time` | Yes | Time. | Use constraints/calculations for validation; see [`expressions.md`](expressions.md) for time functions. | [datetime/date/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html), [support time constraints](https://support.surveycto.com/hc/en-us/articles/360045912114) |
| `image` | Yes | Image attachment. | Blank appearance lets users take or select an image. `new` requires a new photo; `annotate`, `draw`, and `signature` are Collect-only, not web. | [image](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03m.field-types-image.html), [signatures](https://docs.surveycto.com/02-designing-forms/02-additional-topics/05.signatures.html) |
| `audio` | Yes | Audio attachment. | `appearance=new` requires recording a new clip. | [audio](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03n.field-types-audio.html) |
| `video` | Yes | Video attachment. | `appearance=new` requires recording a new clip. | [video](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03o.field-types-video.html) |
| `file` | Yes | File attachment. | Use `mediatype` for comma-separated MIME types. Defaults allow text, image, video, audio, PDF, ZIP, Word, and Excel files. | [file](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03o2.field-types-file.html) |
| `note` | Yes | Display-only text; no data response. | Full note text goes in `label`. `appearance=intro` shows before first visible field; `thankyou` shows after finalization/save. | [note](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03p.field-types-note.html) |
| `start` | Hidden | Start date/time. | Usually named `starttime`; enabled from form settings in the designer. | [start](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03q.field-types-start.html) |
| `end` | Hidden | End date/time. | Usually named `endtime`; enabled from form settings in the designer. | [end](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03r.field-types-end.html) |
| `deviceid` | Hidden | Device ID. | Web forms store `(web)`. Android 10+ uses `ANDROID_ID`; older Android versions use IMEI. | [deviceid](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03s.field-types-deviceid.html) |
| `subscriberid` | Hidden | SIM subscriber ID, if available. | Unsupported on web/iOS; Android 10+ leaves blank. | [subscriberid](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03u.field-types-subscriberid.html) |
| `simserial` | Hidden | SIM serial number, if available. | Unsupported on web/iOS; Android 10+ leaves blank. | [simserial](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03v.field-types-simserial.html) |
| `phonenumber` | Hidden | Device SIM phone number, if available. | Android Collect only; not supported on iOS or web. | [phonenumber](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03w.field-types-phonenumber.html) |
| `username` | Hidden | Username of the user filling the form. | Set when the form starts and does not update. Web may store login username or `anonymousUser`. For current username later in the form, use `username()` in a calculate. | [username](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03x.field-types-username.html) |
| `caseid` | Hidden | Selected case ID, if any. | Blank unless opened via Manage Cases or a link with a `caseid` parameter. | [caseid](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03y.field-types-caseid.html), [case management](https://docs.surveycto.com/03-collecting-data/03-data-collection-workflow/02.case-management.html) |
| `comments` | Hidden | Enables field-level comments. | Exports a URL/path to a submission-specific comments CSV attachment. | [comments](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03za.field-types-comments.html) |
| `calculate` | Hidden | Automatically calculated value. | Expression goes in `calculation`; recalculates when forms load/save and dependencies change. Used for `pulldata()` into hidden fields. | [calculate](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zb.field-types-calculate.html), [preloading](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html) |
| `calculate_here` | Hidden | SurveyCTO-specific fixed-location calculation. | Calculates only when the user reaches that row. Rarely appropriate; use mainly for point-in-time values such as `once(duration())`. | [calculate](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zb.field-types-calculate.html) |
| `speed violations audit` | Hidden | SurveyCTO-specific invisible audio audit triggered by speed violations. | `appearance` uses `v=#; d=#`, where `v` is violation count threshold and `d` is recording duration. Collect only, not web. | [speed violations](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zc.field-types-speed-violations.html) |
| `speed violations count` | Hidden | SurveyCTO-specific count of speed violations. | Works with `minimum_seconds`. | [speed violations](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zc.field-types-speed-violations.html) |
| `speed violations list` | Hidden | SurveyCTO-specific comma-separated list of fields with speed violations. | Works with `minimum_seconds`; useful in Data Explorer. | [speed violations](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zc.field-types-speed-violations.html) |
| `text audit` | Hidden | SurveyCTO-specific CSV attachment with timing/event metadata. | `appearance` can include `p=#`, `eventlog`, and/or `choices`. | [text audit](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zd.field-types-text-audit.html) |
| `audio audit` | Hidden | SurveyCTO-specific invisible audio recording of survey administration. | `appearance` parameters include `p=#`, `s=#`, `s=#-#`, `s=field`, `d=#`, and `d=field`; separate parameters with semicolons. Collect only, not web. | [audio audit](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03ze.field-types-audio-audit.html) |
| `sensor_statistic ...` | Hidden | SurveyCTO-specific Android sensor summary statistic. | Type includes statistic name, such as `sensor_statistic mean_sound_level` or `sensor_statistic pct_quiet`; some use `appearance=min=#;max=#`. Android Collect only. | [sensor_statistic](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zf.field-types-sensor-statistic.html), [support sensor metadata](https://support.surveycto.com/hc/en-us/articles/360009552713) |
| `sensor_stream ...` | Hidden | SurveyCTO-specific sensor stream CSV attachment. | Type includes stream name: `light_level`, `movement`, `sound_level`, `sound_pitch`, or `conversation`; `appearance=period=#`. Android Collect only. | [sensor_stream](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zg.field-types-sensor-stream.html) |
| `begin group` / `end group` | Structural | Starts/ends a non-repeating group. | Put group name and label on `begin group`; `relevance` and group appearances go there. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `begin repeat` / `end repeat` | Structural | Starts/ends a repeat group. | Put repeat name and label on `begin repeat`; `repeat_count`, relevance, and repeat appearances go there. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [repeats](https://docs.surveycto.com/02-designing-forms/02-additional-topics/02.repeats.html) |
| `today`, `email`, `acknowledge` | Varies | Standard XLSForm/ODK types sometimes seen in inherited forms. | These are not listed in SurveyCTO's current core field-type index. Do not introduce them into new SurveyCTO forms unless you have validated the target server accepts them; use documented SurveyCTO types or functions instead, such as `today()` in a calculation. | [core field-type index](https://docs.surveycto.com/02-designing-forms/01-core-concepts/) |

## Choices Worksheet

Canonical docs: [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html), [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html), [cascading selects](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/02.cascading-selects.html), and [dynamic choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html).

| Column | What it does | How to use it |
| --- | --- | --- |
| `list_name` | Names the choice list. | Match the list name in `survey.type`, for example `select_one yesno` uses rows where `list_name=yesno`. |
| `value` | Stored value for a static choice, or source-column name for a dynamic choice row. | Static choices store this value in submissions. For dynamic `search()` lists, put the pre-loaded data column containing unique selected values, commonly an ID/key column. |
| `label` | Display label for a static choice, or source-column name(s) for a dynamic choice row. | Static choices show this text. For dynamic `search()` lists, put the source column name, or comma-separated source column names, used to build labels. |
| `label:Language` | Translated choice label. | Add one per language, such as `label:Spanish`. Keep base `label` for the default language. |
| `image` | Choice image filename, or source-column name for dynamic choice images. | Upload referenced files with the form. Dynamic choice image values are pulled from the named source column. |
| `image:Language` | Language-specific choice image. | Add one per language as needed. |
| `filter` | Conventional filter value for cascading selects. | Use with `survey.choice_filter`, for example `filter=${region}`. Values match stored choice values, not labels. |
| Other filter columns | Additional cascade dimensions. | You can create columns such as `filter_region` and `filter_country`, then use expressions like `filter_region=${region} and filter_country=${country}`. The online designer supports a single filter column, but spreadsheet definitions can be more complex. |

Ordering rules:

- Static choices appear in the order of rows on the `choices` sheet unless the select field uses `randomized` in `appearance`.
- `select_one` and `select_multiple` can randomize choices with `randomized`, `randomized(x, y)`, or seeded forms such as `randomized(329)` or `randomized(${hhid})`.
- Dynamic `search()` choices appear in source order by default. If the attached dataset or CSV includes a numeric `sortby` column, SurveyCTO orders dynamic choices numerically by that column.
- Dynamic `search()` lists may mix static choices before/after the dynamic row. When doing this, the static `value` entries must be numeric.

## Groups And Repeats

Canonical docs: [Grouping and repeating questions](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [Repeating fields](https://docs.surveycto.com/02-designing-forms/02-additional-topics/02.repeats.html), [Updating existing forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/10.updating.html), and [`expressions.md`](expressions.md) for repeat functions.

| Mechanic | Rule |
| --- | --- |
| Group syntax | `begin group` starts a group; `end group` closes it. The begin row should have `name` and usually `label`. |
| Repeat syntax | `begin repeat` starts a repeat group; `end repeat` closes it. Use this when a block can occur multiple times per submission. |
| Nesting | Groups can be nested inside groups. Repeats can be combined with groups, but changing group/repeat nesting after deployment can affect export behavior and should be avoided. |
| Relevance scope | A `relevance` expression on a `begin group` or `begin repeat` controls the whole enclosed block. This is the preferred way to apply one skip condition to many rows. |
| User-controlled repeats | With no `repeat_count`, the user can add repeat instances until done. This is flexible but can be confusing for rosters. |
| Fixed repeats | Put a literal number such as `3` in `repeat_count` on the `begin repeat` row. The block repeats exactly that many times. |
| Dynamic repeats | Put a prior field reference/expression such as `${num_hh_members}` in `repeat_count`. The docs recommend this with a required integer field. |
| Referencing inside a repeat | From within the same repeat instance, `${field}` refers to that instance's field. Use `index()` for the current repeat instance number. |
| Referencing from outside a repeat | Use repeat functions such as `indexed-repeat()`, `join()`, `count()`, `sum()`, and their `-if` variants. Details are in [`expressions.md`](expressions.md). |
| Export shape | Repeated fields can have multiple values per submission. SurveyCTO exports repeat data differently and supports long/wide formats; do not assume every repeated field becomes a single column in the main export. |
| Updating deployed forms | SurveyCTO internally tracks a field by its full path including enclosing groups. Avoid renaming groups, moving fields across groups, or changing repeat-group enclosure after data collection starts. |

## Choice Filters And Cascading Selects

Canonical docs: [Dynamically filtering lists of multiple-choice options](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/02.cascading-selects.html) and sample form [Cascading selects](https://docs.surveycto.com/02-designing-forms/04-sample-forms/06.cascading-selects.html). Expression syntax details belong in [`expressions.md`](expressions.md).

Basic pattern:

| Sheet | Column | Example |
| --- | --- | --- |
| `survey` | `type` | `select_one region`, then `select_one country`, then `select_one city` |
| `survey` | `choice_filter` | On country: `filter=${region}`. On city: `filter=${country}`. |
| `choices` | `filter` | For each country choice, store the region value that should show it. For each city choice, store the country value that should show it. |

Notes:

- Filter by stored `value`, not by the choice label.
- A single `filter` column is enough for most cascades.
- Spreadsheet definitions can use multiple filter columns and richer expressions, for example `filter_region=${region} and filter_country=${country}`.
- `choice_filter` works on static `choices` rows. Dynamic choice lists from attached data use `search()` in `appearance`.

## Appearance Options

There is no single current SurveyCTO "all appearances" page; appearances are documented under their field-type pages and related topics. The table below groups the options documented in the core field-type pages, groups page, navigation page, and field plug-in page.

### Text And Numeric Inputs

| Appearance | Applies to | Effect | Canonical docs |
| --- | --- | --- | --- |
| `numbers` | `text` | Prompts numeric keyboard; still stores text. | [text](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03a.field-types-text.html) |
| `numbers_decimal` | `text` | Prompts numeric/decimal keyboard; still stores text. | [text](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03a.field-types-text.html) |
| `numbers_phone` | `text` | Prompts phone-style numeric keyboard; still stores text. | [text](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03a.field-types-text.html) |
| `show_formatted` | `integer`, `decimal` | Shows locale-formatted number while entering. | [integer](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03f.field-types-integer.html), [decimal](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03g.field-types-decimal.html) |
| `custom-plugin`, `custom-plugin(params)` | `text`, `integer`, `decimal`, `select_one`, `select_multiple` | Uses an attached field plug-in. The plug-in completely controls display and behavior. | [field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html), [support guide](https://support.surveycto.com/hc/en-us/articles/360045234534) |

### Select One

| Appearance | Effect | Canonical docs |
| --- | --- | --- |
| blank | Radio buttons. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `quick` | Advances immediately after selection. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `minimal` | Single drop-down selector. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `compact`, `compact-#` | Compact table; optional forced column count. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `quickcompact`, `quickcompact-#` | Compact display plus auto-advance. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `likert`, `likert-min`, `likert-mid` | Horizontal Likert-style scale; min/mid variants reduce labels. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html) |
| `randomized`, `randomized(x, y)`, `randomized(seed)`, `randomized(seed, x, y)` | Randomizes choice order, optionally excluding top/bottom choices or using a seed. | [select_one](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03h.field-types-select-one.html), [randomization](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/01.randomizing.html) |
| `label` | In a `field-list` group, makes the first select field provide table column headers. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `list-nolabel` | In a `field-list` group, displays later select fields as additional rows without repeated labels. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `search(...)` | Pulls choices from attached CSV/server dataset. Can follow another appearance, for example `quick search(...)`. | [search choices](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |

### Select Multiple

| Appearance | Effect | Canonical docs |
| --- | --- | --- |
| blank | Checkboxes. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `minimal` | Single pop-up selector. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `compact`, `compact-#` | Compact table; optional forced column count. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `randomized`, `randomized(x, y)`, `randomized(seed)`, `randomized(seed, x, y)` | Randomizes choice order, optionally excluding top/bottom choices or using a seed. | [select_multiple](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html) |
| `label`, `list-nolabel` | Same field-list table pattern as `select_one`. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `search(...)` | Pulls choices from attached CSV/server dataset. | [search choices](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html) |

### Date, Time, Location, Media, Notes

| Appearance | Applies to | Effect | Canonical docs |
| --- | --- | --- | --- |
| `no-calendar` | `date`, `datetime` | Smaller UI for smaller screens. | [date/datetime/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html) |
| `month` | `date`, `datetime` | Ask only for month in the date part. | [date/datetime/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html) |
| `month-year` | `date`, `datetime` | Ask only for month and year in the date part. | [date/datetime/time](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03l.field-types-datetime.html) |
| `maps` | `geopoint` | Shows captured point on a map. | [geopoint](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j.field-types-geopoint.html) |
| `placement-map` | `geopoint` | Shows point on a map and lets the user adjust with a pin. | [geopoint](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j.field-types-geopoint.html) |
| `background` | `geopoint` | Captures location invisibly in background. Not supported on web. | [geopoint](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03j.field-types-geopoint.html) |
| `new` | `image`, `audio`, `video` | Requires new capture/recording instead of selecting an existing file. | [image](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03m.field-types-image.html), [audio](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03n.field-types-audio.html), [video](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03o.field-types-video.html) |
| `annotate` | `image` | Allows annotating a taken/selected picture. Collect only, not web. | [image](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03m.field-types-image.html) |
| `draw` | `image` | Free-form drawing input. Collect only, not web. | [image](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03m.field-types-image.html) |
| `signature` | `image` | Signature input. Collect only, not web. | [image](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03m.field-types-image.html), [signatures](https://docs.surveycto.com/02-designing-forms/02-additional-topics/05.signatures.html) |
| `intro` | `note` | Shows note on the opening screen before the first visible field. | [note](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03p.field-types-note.html) |
| `thankyou` | `note` | Shows note at the end after finalization/save. | [note](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03p.field-types-note.html) |

### Groups, Repeats, Enumerator, Audits, Sensors

| Appearance | Applies to | Effect | Canonical docs |
| --- | --- | --- | --- |
| `organized` | `begin group` | Organizes the group under its label in navigation lists. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [navigation](https://docs.surveycto.com/02-designing-forms/02-additional-topics/03.designing-for-nav.html) |
| `organized-closed` | `begin group` | SurveyCTO navigation appearance: organized group starts collapsed in Go To Prompt. | [navigation](https://docs.surveycto.com/02-designing-forms/02-additional-topics/03.designing-for-nav.html) |
| `field-list` | `begin group` | Displays all fields in the group on one screen. Relevance for rows on that screen is evaluated when the screen first displays. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html) |
| `organized field-list` | `begin group` | Combines navigation organization and one-screen display. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html) |
| `table`, `table-labeled` | `begin repeat` | Adds a review/navigation table under repeated questions; `table-labeled` includes the repeat label in row labels. | [groups](https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html), [navigation](https://docs.surveycto.com/02-designing-forms/02-additional-topics/03.designing-for-nav.html) |
| `default-to-entry`, `default-to-scan` | `enumerator` | Defaults enumerator identity prompt to entry or scan mode instead of list mode. | [enumerator](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i2.field-types-enumerator.html) |
| `other-user-code(xyz)` | `enumerator` | Requires code before showing enumerators outside the user's filtered list. | [enumerator](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i2.field-types-enumerator.html) |
| `add-new-code(xyz)` | `enumerator` | Requires code before adding a new enumerator. | [enumerator](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i2.field-types-enumerator.html) |
| `p=#`, `eventlog`, `choices` | `text audit` | Samples text audits, records event-level logs, and/or records shown choice values/labels. Combine with semicolons. | [text audit](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zd.field-types-text-audit.html) |
| `p=#;s=#;d=#`, `p=#;s=#-#;d=#`, `p=#;s=startfield;d=endfield` | `audio audit` | Samples and bounds invisible audio audits by time or field. | [audio audit](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03ze.field-types-audio-audit.html) |
| `v=#; d=#` | `speed violations audit` | Triggers invisible audio after a number of speed violations for a duration in seconds. | [speed violations](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zc.field-types-speed-violations.html) |
| `min=#;max=#` | Some `sensor_statistic ..._between` fields | Defines range for percentage-between sensor statistics. | [sensor_statistic](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zf.field-types-sensor-statistic.html) |
| `period=#`, `period=0` | `sensor_stream ...` | Sets observation period in seconds; `0` records as fast as underlying sensors provide data, subject to documented limits. | [sensor_stream](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03zg.field-types-sensor-stream.html) |

## Settings Worksheet

Canonical docs: [Introduction](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html), [Updating existing forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/10.updating.html), [Encryption](https://docs.surveycto.com/02-designing-forms/02-additional-topics/06.encrypting.html), [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html), [Hiding test forms](https://docs.surveycto.com/02-designing-forms/02-additional-topics/08.hiding-test-forms.html), and [Dynamically naming filled-in forms](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/05.naming-forms.html).

Put settings in row 2.

| Column | What it does | How to use it |
| --- | --- | --- |
| `form_title` | Human-readable form title shown to users. | Can be revised across versions. Titles beginning with `TEST - ` are hidden by default in Collect/Desktop unless users enable showing test forms. |
| `form_id` | Stable unique form identifier. | Must start with a letter and contain only letters, numbers, underscores, and hyphens. Do not change during normal updates; changing it creates a different form. |
| `version` | Form definition version number. | Increase on every spreadsheet-definition update. It must be a single whole number whose digit count stays fixed across versions. SurveyCTO templates use an auto-incrementing timestamp formula. |
| `public_key` | Public encryption key for end-to-end encrypted forms. | Add the public key to encrypt submissions. Encryption settings cannot be changed for an existing `form_id`; use a new `form_id` to change encryption status/key. |
| `submission_url` | Submission URL for encrypted forms. | Included in SurveyCTO templates/help for encryption workflows. Keep aligned with the generated encrypted-form settings. |
| `default_language` | Name of the base/default language. | New forms default to `english`; set this when base `label`, `hint`, `image`, and message columns are in another language. For workflow guidance on *translating* labels (adding a language, updating after source changes, verifying existing translations), see [`translation.md`](translation.md). |
| `instance_name` | Dynamic name for filled-in form instances. | Row 2 is an expression that evaluates to a string, such as `concat('HH SURVEY - ', ${hhid})`. With MCP, set it via `change_setting` (it is one of the patch-addressable keys); without MCP, add the column manually and write the expression into row 2. See [Naming forms](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/05.naming-forms.html). |

## `pulldata()`, `search()`, And Attached Data

Canonical docs: [Pre-loading data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html), [Loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html), [`expressions.md`](expressions.md), and [`datasets-xml.md`](datasets-xml.md).

Structural placement:

| Function | Where it goes | What workbook structure it needs |
| --- | --- | --- |
| `pulldata()` | Usually in `survey.calculation` on a `calculate` row. It can also go in `survey.calculation` for an editable visible field as a dynamic default. | Attached CSV or attached server dataset. Pre-loaded data should have headers, comma-separated columns, and at least one unique lookup column, commonly ending in `_key` for indexing. See [`datasets-xml.md`](datasets-xml.md) for server dataset attachment structure. |
| `search()` | In `survey.appearance` on `select_one` or `select_multiple`; if combined with another appearance, put the normal appearance first, then `search(...)`. | A matching `choices` row whose `list_name` is the select list; its `value`, `label`, and optionally `image` cells name columns in the attached data source. A numeric `sortby` source column controls dynamic choice order if present. |

Defer exact syntax, operators, conversions, and examples to [`expressions.md`](expressions.md). Remember that values pulled from CSV/datasets are treated as text strings; convert with expression functions when numeric behavior is needed.

## Field Plug-Ins

Canonical docs: [Using field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html), [Testing field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/07.testing-field-plug-ins.html), and the Support Center [Guide to field plug-ins](https://support.surveycto.com/hc/en-us/articles/360045234534).

**When to use one.** Default to native field types and appearances; plug-ins add attachment management, version bumping, caching, and cross-platform testing overhead. If a plug-in is warranted, check the [field plug-in catalog](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog) first for one that meets the need as-is, then customize a catalog plug-in or matching SurveyCTO `baseline-*` repo, and only fall back to the bundled minimal template when starting completely fresh. See [`field-plugins.md`](field-plugins.md) for the decision order in detail.

| Piece | Rule |
| --- | --- |
| Supported base types | `text`, `integer`, `decimal`, `select_one`, and `select_multiple`. |
| Attachment | Attach `[name].fieldplugin.zip` to the form, the same way as other form attachments. |
| Selection in spreadsheet | Put `custom-[plug-in name]` in `survey.appearance`, for example `custom-myplugin`. |
| Parameters | Put parameters inside parentheses after the plug-in name, for example `custom-slider(min=0, max=10)`; parameter values can use expressions and field references. |
| Behavior | A field plug-in completely takes over field appearance. Other appearance options may not be supported unless the plug-in documents them. Test carefully on target platforms. |

**After editing.** Forms that reference a `custom-<name>` appearance require the user to attach the matching `<name>.fieldplugin.zip` in the SurveyCTO console at upload time. This skill and the MCP server only edit local files; they do not upload or attach plug-ins. Remind the user explicitly when handing back a form that references a plug-in.

## The Bundled XLSForm Template

The skill ships with [`assets/xlsform-template.xlsx`](../assets/xlsform-template.xlsx). Use it as the required starting point for generated workbooks.

| Template part | What's in it | Why it matters |
| --- | --- | --- |
| `survey` | Standard headers: `type`, `name`, `label`, `hint`, `default`, `appearance`, `constraint`, `constraint message`, `relevance`, `disabled`, `required`, `required message`, `read only`, `calculation`, `repeat_count`, `media:image`, `media:audio`, `media:video`, `choice_filter`, `note`, `response_note`, `publishable`, `minimum_seconds`. It also includes default metadata and calculation rows (including hidden audit calculations and a `caseid` row). | Gives agents and humans the exact SurveyCTO column spellings, useful metadata defaults, formatting, and validation cues. |
| `choices` | Standard headers `list_name`, `value`, `label`, `image`, `filter`, plus a default `yesno` list. | Provides a safe first choice-list pattern and the cascade `filter` convention. |
| `settings` | `form_title`, `form_id`, `version`, `public_key`, `submission_url`, `default_language`, with an auto-incrementing version formula and `default_language=english`. | Avoids missing required form metadata and handles versioning correctly during iteration. |
| `help-survey`, `help-choices`, `help-settings` | Human-readable column help, translation column examples, links to relevant docs, and SurveyCTO-specific columns like `publishable`, `minimum_seconds`, `note`, and `response_note`. | SurveyCTO ignores extra help worksheets, but they preserve institutional knowledge and reduce column-name mistakes. |

**Template starter content is a helpful starting point, not a fixed requirement.** The starter rows (default metadata fields, `caseid`, hidden audit calculations) and the `yesno` choice list are conveniences for common cases, not infrastructure SurveyCTO depends on. Keep the standard metadata and audit rows by default because they are generally useful and not user-facing clutter; remove or replace them only when the source form or user request gives you a reason. Treat `caseid` as context-dependent: keep it for case-management work, but delete it when it would confuse a non-case draft. The `yesno` choice list is just an example choice list — drop or replace it freely when the form uses a different yes/no convention or no row references it. What's worth preserving across every edit is the *tooling*: the auto-updating `version` formula, the conditional formatting, the help worksheets, and the column-header structure. When you change starter content (e.g., rewrite a choice's `value`), be consistent — also update everything that references it, or you'll create silent breakage.

What breaks when building from scratch:

- Missing or misspelled worksheets (`survey`, `choices`, `settings`) make the workbook invalid.
- Misspelled columns silently break behavior or cause upload errors, especially `constraint message`, `required message`, `read only`, `repeat_count`, and `choice_filter`.
- Missing `settings.form_id` or invalid IDs prevent correct deployment or version tracking.
- Missing/inadequate `version` handling causes update failures or confusing deployed-form behavior.
- Omitting template metadata fields can remove useful default audit/export fields.
- Omitting help worksheets makes future maintenance more error-prone, even though SurveyCTO can ignore extra worksheets.

## Accuracy Checklist For Agents

Before editing or generating a SurveyCTO XLSForm:

- Start from the bundled template unless the user supplied an existing workbook.
- Preserve exact worksheet and column names.
- Keep `form_id` stable for updates; increment `version`.
- Do not delete deployed fields if old data must remain exportable; set `relevance` to `0` instead.
- For `select_multiple`, use `selected()` in logic; do not compare the whole value with `=`.
- Put expression syntax details in [`expressions.md`](expressions.md), and dataset attachment details in [`datasets-xml.md`](datasets-xml.md).
- Upload every referenced media, CSV, dataset attachment, and field plug-in with the form.
- Treat SurveyCTO-specific field types and appearances as platform-dependent; check target platform limitations before relying on them.
