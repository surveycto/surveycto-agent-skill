<!-- PRIMER: form-conversion-commcare
  STATUS: drafted 2026-05-16 -->

# Converting a CommCare XForms XML export into a SurveyCTO XLSForm

> **Read [`form-conversion.md`](form-conversion.md) first** for the overall workflow and universal mapping concerns. CommCare is XForms-based — the same XForms lineage that produced ODK and SurveyCTO — so much of [`form-conversion-odk.md`](form-conversion-odk.md) is conceptually relevant for the expression and field-type mapping. This file focuses on what CommCare-specific.

CommCare is the source format with the largest divergence from SurveyCTO of the four first-class platforms — not because the form fields are different (most map cleanly), but because **CommCare exports only `.xml` (raw XForms), not XLSForm**, and CommCare's case-management model is structurally different from SurveyCTO's. Expect the conversion to need more human attention than the others, especially around case management.

## What CommCare exports

CommCare forms are authored in Vellum (CommCare's form builder) and stored / exported as **XForms XML files**. The XML has several namespaces:

| Prefix | URI | What it's for |
| --- | --- | --- |
| `h` | `http://www.w3.org/1999/xhtml` | The outer XHTML envelope (`<h:html>`, `<h:head>`, `<h:body>`) |
| (default) | `http://www.w3.org/2002/xforms` | The XForms elements themselves (`<model>`, `<bind>`, `<input>`, `<select1>`, …) |
| `jr` | `http://openrosa.org/javarosa` | JavaRosa extensions (`jr:itext`, `jr:constraintMsg`, `jr:preload`, `jr:preloadParams`) |
| `orx` | `http://openrosa.org/jr/xforms` | OpenRosa extensions |
| `vellum` | `http://commcarehq.org/xforms/vellum` | Vellum form-builder metadata (ignore — internal to the editor) |
| `cc` / case-transaction xmlns | `http://commcarehq.org/xforms`, `http://commcarehq.org/case/transaction/v2` | CommCare-specific case-management actions |

Top-level structure:

```
<h:html xmlns:h="..." xmlns="..." xmlns:jr="..." ...>
  <h:head>
    <h:title>Form title</h:title>
    <model>
      <instance>              <!-- primary instance: the form's data structure -->
        <data id="form_xmlns" xmlns="form_xmlns">
          <field1/>
          <field2/>
          <group1>
            <subfield/>
          </group1>
          <case xmlns="...case/transaction/v2">...</case>     <!-- case action block -->
        </data>
      </instance>
      <instance id="casedb" src="jr://instance/casedb"/>      <!-- secondary instances -->
      <instance id="commcaresession" src="jr://instance/session"/>
      <itext>                  <!-- translations -->
        <translation lang="en"> <text id="question1-label"> <value>Label</value> ... </text> ... </translation>
        <translation lang="es"> ... </translation>
      </itext>
      <bind nodeset="/data/field1" type="xsd:string" required="true()" relevant="..." constraint="..."/>
      ...
    </model>
  </h:head>
  <h:body>
    <input ref="/data/field1">
      <label ref="jr:itext('field1-label')"/>
      <hint ref="jr:itext('field1-hint')"/>
    </input>
    <select1 ref="/data/field2">
      <label ref="jr:itext('field2-label')"/>
      <item><label ref="jr:itext('field2-item1-label')"/><value>1</value></item>
      ...
    </select1>
    <group ref="/data/group1">
      <label ref="jr:itext('group1-label')"/>
      <input ref="/data/group1/subfield">...</input>
    </group>
    <repeat nodeset="/data/repeat1">...</repeat>
  </h:body>
</h:html>
```

The two halves to understand:

- **`<h:body>`** holds the UI controls (which question, in which order, with what label / hint). Walking the body in document order gives you the form's question sequence.
- **`<model>`** holds the data structure (`<instance>`), the translations (`<itext>`), the per-field metadata (`<bind>` elements with `type`, `required`, `relevant`, `constraint`, `calculate`, `jr:constraintMsg`, `jr:requiredMsg`, `jr:preload`), and any case-action blocks.

The conversion walks the body and, for each control, looks up its `<bind>` (by `ref` matching `nodeset`) and resolves its label/hint through `<itext>`. The bundled parser helper does all of this for you.

## The bundled parser helper

Use [`assets/form-conversion/commcare_xform_loader.py`](../assets/form-conversion/commcare_xform_loader.py). Standard library only.

```python
from commcare_xform_loader import load_xform

form = load_xform("/path/to/case_followup.xml")

print(form["form_title"], form["form_id"])
print("Languages:", form["languages"])

for q in form["questions"]:
    print(q["name"], q["type"], q.get("xforms_type"), q["labels"])
```

The helper returns a dict with:

| Key | Shape | Notes |
| --- | --- | --- |
| `form_title` | `str` | From `<h:title>`. |
| `form_id` | `str` | The primary instance root tag's local name. Often a Vellum-generated slug. Confirm with the user before using as `form_id` in SurveyCTO — they may want to rename. |
| `languages` | `list[str]` | Language codes from `<itext>` translations, in document order. First is the default. |
| `default_language` | `str` | First language listed; use as `default_language` in `settings`. |
| `questions` | `list[dict]` | One dict per UI control, group/repeat marker, and end marker, in document order. See below. |
| `case_actions` | `list[dict]` | Case-create / case-update / case-close blocks — flag-only, not auto-converted. |
| `secondary_instances` | `list[dict]` | Each `<instance id="..." src="...">` declared in the model. The `casedb` and `commcaresession` instances are CommCare-specific; others are usually external lookups. |
| `warnings` | `list[str]` | Parsing warnings (missing bind ref, case database referenced, etc.). |

Each question dict carries:

| Key | Meaning |
| --- | --- |
| `name` | Leaf node name from the `nodeset` (e.g., `/data/group1/age` → `age`). Use as a base for the SurveyCTO `name` cell after applying the safe-name rule from [`form-conversion.md`](form-conversion.md#field-name-sanitization). **See [§ Groups, repeats, and name collisions](#groups-repeats-and-name-collisions) below** — when the same leaf name appears in multiple groups, the helper also populates `suggested_safe_name`. |
| `suggested_safe_name` | Set only when the leaf `name` collides with another question's leaf name elsewhere in the form. Holds a parent-path-disambiguated alternative (e.g., `head_info_age`, `member_age`). |
| `nodeset` | The full XPath to the data node. Useful when resolving cross-field references and disambiguating in collision cases. |
| `type` | The XForms control tag (`input`, `select1`, `select`, `upload`, `trigger`, `range`, `secret`, `begin_group`, `begin_repeat`, `end_group`, `end_repeat`). |
| `xforms_type` | The bind's `type` attribute (`xsd:string`, `xsd:int`, `xsd:decimal`, `xsd:date`, `xsd:dateTime`, `xsd:time`, `geopoint`, `binary`). |
| `appearance` | `appearance` attribute from the body element (CommCare uses appearance hints similar to ODK's). |
| `labels` | `dict[str, str]` — `{lang: text}`. May contain `${field}` placeholders where `<output value="..."/>` substitutions were present in the source. |
| `hints` | `dict[str, str]` — same shape as `labels`. |
| `media` | `dict[str, dict[str, str]]` — `{form: {lang: jr_uri}}` for `image` / `audio` / `video` / `markdown` media attached via itext. |
| `required` | `bool`. |
| `required_message` / `constraint_message` | `dict[str, str] | None` — multi-language message text resolved from `jr:requiredMsg` / `jr:constraintMsg`. |
| `constraint` / `relevant` / `calculate` | Raw XPath strings from the bind. Apply expression rewrites before emitting. For `begin_group` and `begin_repeat` markers, `relevant` is the group/repeat-level relevance (looked up from the group's own `<bind>`). |
| `readonly` | `bool` — from the bind's `readonly` attribute. Set on questions and on `begin_group` / `begin_repeat` markers. |
| `repeat_count` | For `begin_repeat` markers only: the `jr:count` expression (an XPath like `/data/hh_size`) if present. Apply the same expression rewrites and emit into the SurveyCTO `repeat_count` column. |
| `no_add_remove` | For `begin_repeat` markers only: bool from `jr:noAddRemove`. When `true`, the user cannot dynamically add/remove instances — equivalent to providing `repeat_count` (and is sometimes used together). |
| `choices` | For `select` / `select1`: list of `{value, labels: {lang: text}}`. |
| `upload_mediatype` | For `upload`: `image`, `audio`, or `video`. |
| `preload` / `preload_params` | For metadata fields (`jr:preload="property"` etc.) — map to SurveyCTO metadata types per the table below. |
| `parent_path` | List of ancestor group/repeat names — context for nesting. Empty for top-level questions. |

The helper has a CLI for quick inspection: `python commcare_xform_loader.py path/to/form.xml` dumps the normalized dict as JSON to stdout.

## Field-type mapping

Map XForms controls + `xsd:` types to SurveyCTO types:

| XForms control + bind type | SurveyCTO `type` | Notes |
| --- | --- | --- |
| `<input>` + `xsd:string` | `text` | Add `appearance=multiline` if the bind / appearance suggests long-form. |
| `<input>` + `xsd:int` | `integer` | Watch the 9-digit limit; switch to `text` with `appearance=numbers` for large IDs/phones. |
| `<input>` + `xsd:decimal` | `decimal` | |
| `<input>` + `xsd:date` | `date` | |
| `<input>` + `xsd:dateTime` | `datetime` | |
| `<input>` + `xsd:time` | `time` | |
| `<input>` + `geopoint` | `geopoint` | |
| `<select1>` | `select_one <list>` | The choice list is built from inline `<item>` elements; deduplicate per [`form-conversion.md`](form-conversion.md#choice-list-deduplication). |
| `<select>` | `select_multiple <list>` | Same. Confirm every comparison expression uses `selected()`. |
| `<upload mediatype="image">` | `image` | |
| `<upload mediatype="audio">` | `audio` | |
| `<upload mediatype="video">` | `video` | |
| `<trigger>` | `acknowledge` | Renders as a tap-to-acknowledge. |
| `<range>` | `integer` or `decimal` + `constraint = . >= MIN and . <= MAX` | CommCare's `<range>` is rare; the `parameters` attribute carries `start`, `end`, `step`. |
| `<secret>` | `text` with a flag | SurveyCTO has no password masking. Use `text` and note in the report. |
| `<group>` | `begin group` / `end group` | Add `appearance=field-list` if the source uses Vellum's "single-screen group" pattern (heuristic: the group has no internal page breaks and contains simple controls). |
| `<repeat>` | `begin repeat` / `end repeat` | Carry over `nodeset` and `jr:count` attribute → `repeat_count`. |

### Metadata fields (`jr:preload`)

CommCare uses `<bind jr:preload="..." jr:preloadParams="..."/>` to declare metadata fields (start time, end time, device ID, username, case ID, etc.). Map to SurveyCTO metadata field types:

| `jr:preload` / `jr:preloadParams` | SurveyCTO `type` |
| --- | --- |
| `timestamp` / `start` | `start` |
| `timestamp` / `end` | `end` |
| `date` / `today` | `today` |
| `property` / `DeviceID` | `deviceid` |
| `property` / `username`, `meta` / `username` | `username` |
| `property` / `PhoneNum`, `meta` / `PhoneNumber` | `phonenumber` |
| `case` / (any params) | `caseid` *if* the form has case management you've decided to translate via SurveyCTO case management; otherwise drop and flag |

Carry the metadata fields into the SurveyCTO `survey` worksheet at the top (most metadata is conventionally placed before any visible question), matching the template's existing metadata rows.

## Groups, repeats, and name collisions

CommCare's data model is a tree of nested groups and repeats, with nodeset paths like `/data/head_info/age` and `/data/members/member/age` that are unique by path. **XLSForm's data model is flat: `name` values must be globally unique across the entire form, regardless of group context.** This mismatch is the most common source of conversion warnings for CommCare forms with substantive structure.

### How the helper represents nesting

The helper walks the `<h:body>` in document order and emits markers and questions in sequence:

- A `<group>` produces a `begin_group` marker, followed by every question inside it (with `parent_path` set to the group's ancestor names), followed by an `end_group` marker with the same `name`.
- A `<repeat>` produces a `begin_repeat` / `end_repeat` pair the same way.
- Groups and repeats nest naturally — a question inside `head_info > spouse_info > age` has `parent_path = ["head_info", "spouse_info"]`.

You walk this list in order to produce the SurveyCTO `survey` worksheet: emit `begin group` / `end group` / `begin repeat` / `end repeat` rows for the markers, and field rows for the questions, preserving the order.

### Group- and repeat-level metadata

Each `begin_group` / `begin_repeat` marker has:

- `labels` — resolved from the group's `<label ref="jr:itext(...)"/>` element. Becomes the SurveyCTO group's `label`.
- `appearance` — typically `field-list` in CommCare for Vellum's "single-screen group" pattern; carry over.
- `relevant` — looked up from the group's own `<bind nodeset="/data/group">` element. If set, this is the group-level skip-logic expression — emit it into the `relevance` column on the `begin group` / `begin repeat` row. SurveyCTO applies group-level relevance to every field inside the group automatically, matching CommCare's behavior.
- `readonly` — same lookup; emit into `read only` on the marker row.
- `repeat_count` (repeats only) — the `jr:count` expression. Apply expression rewrites (`/data/<path>` → `${field}`) and emit into the `repeat_count` column on the `begin repeat` row.
- `no_add_remove` (repeats only) — when `true`, the user can't add/remove repeat instances dynamically. This usually pairs with `jr:count`; no extra SurveyCTO column is needed, since setting `repeat_count` already prevents user-driven add/remove.

### Name collisions

When the same leaf name appears at multiple paths (e.g., `age` exists in both `/data/head_info/age` and `/data/members/member/age`), the helper:

1. Detects the collision during a post-processing pass.
2. Populates `suggested_safe_name` on **every** affected question with a parent-path-disambiguated alternative (`head_info_age`, `member_age`).
3. Adds a warning to `form["warnings"]` listing the colliding name and its nodeset paths.

The agent's job:

1. **Before emitting any rows**, walk `form["questions"]` and build a `nodeset → final_name` map: use `suggested_safe_name` when present, otherwise `name`. Apply the safe-name rule from [`form-conversion.md`](form-conversion.md#field-name-sanitization) to whichever you pick.
2. **Emit each question with its final (disambiguated) name.**
3. **Rewrite every cross-reference consistently.** Any `${age}` substitution in a label, hint, message, or expression cell from a source that referenced the now-disambiguated field must be rewritten to use the new name. There are two places to look:
   - **Inside expressions** (`relevant`, `constraint`, `calculate`, `repeat_count`, and `jr:constraintMsg`/`jr:requiredMsg` references). These come from the helper as raw XPath strings; you're already rewriting `/data/<path>` → `${field}` during the expression-rewrite pass — apply the disambiguation lookup at the same time. Use the full nodeset to pick the right disambiguated name, not the bare leaf.
   - **Inside labels and hints** (from `<output value="/data/group/field"/>` substitutions). The helper flattens these to `${field}` in the returned `labels`/`hints` text strings, using **just the leaf name**. When the leaf name collides, this bare `${field}` is ambiguous and must be rewritten using the original `<output>`'s nodeset. The cleanest pass: walk every label/hint string, and for each `${name}` substitution, find the source `<output>` it came from (by re-reading the XML or by retaining nodeset context during the flatten step) and rewrite to `${suggested_safe_name}` if that nodeset's question has one.
4. **Surface the collisions in the conversion report.** Even with automatic disambiguation, the user may want more meaningful names than `head_info_age` / `member_age`. List every collision in the report with the auto-chosen name and a suggestion to rename for clarity.

If the source has many collisions and the user wants meaningful names, **ask before applying defaults** — it's faster to disambiguate once with user input than to rename everything later.

### Repeat-context references

Inside a repeat, CommCare expressions can reference siblings within the same repeat instance (`/data/members/member/age` from another field in the same `member` repeat) or fields outside the repeat. SurveyCTO follows the same XLSForm convention: `${age}` inside the repeat refers to the same-instance `age`; an `indexed-repeat(${age}, ${members}, ${index})` reference reaches across instances.

The helper doesn't auto-detect cross-repeat references — if the source uses `indexed-repeat`-style patterns, translate by hand and verify against [`expressions.md`](expressions.md).

## Translations — itext → `label:Lang`

CommCare's `<itext>` is the native multi-language layer. The helper resolves each label/hint into a `{lang: text}` dict; you then emit one `label:Lang` column per non-default language and put the default-language value in the unsuffixed `label`.

- Default language = `form["default_language"]` (the first `<translation>` in the source).
- Each `form["languages"]` entry becomes a column suffix in the converted XLSForm. Use SurveyCTO-friendly language **names** (e.g., `English`, `Spanish`, `Hindi`) — CommCare uses ISO codes like `en`, `es`, `hi`. If the user has a preferred name for a given code, ask.
- Apply this consistently to `label`, `hint`, `constraint message`, `required message`, and choice `label`s.

Itext entries can have multiple `<value form="...">` children — `long` (full label), `short` (abbreviated), `audio` / `image` / `video` (media references), `markdown`. The helper picks `long` first and falls back to `default` for labels; for hints it uses `default`. Media forms (`image`/`audio`/`video`) are collected separately into `q["media"]` — see [§ Multimedia](#multimedia) below.

Inline `<output value="/data/age"/>` substitutions in label text are flattened by the helper into `${age}` references in the returned strings, ready to use in SurveyCTO labels.

## Multimedia

CommCare attaches media to fields via itext: `<value form="image">jr://images/age_diagram.png</value>`. The helper returns these as `q["media"][form][lang] = "jr://images/age_diagram.png"`.

SurveyCTO uses the `media:image`, `media:audio`, `media:video` columns (with optional language suffixes) and expects the **filename only** — the user attaches the file to the form at upload time.

Convert each `jr://` URI by stripping the `jr://images/` (or `audio/`, `video/`) prefix to get the filename. Write the filename into the SurveyCTO `media:image` column (and language-suffixed variants if the source has per-language media). **Flag in the conversion report** that the user must attach the actual media files to the form on the SurveyCTO side at upload time — the converter cannot copy media files across platforms.

If the source uses `<value form="markdown">` for rich-text labels, treat as a Markdown label: SurveyCTO doesn't render Markdown, so translate `**bold**`/`_italic_` to `<b>`/`<i>` per the rule in [`form-conversion.md`](form-conversion.md#html-and-markdown-in-labels).

## Expression rewrites

CommCare's XPath expressions look like ODK's but with `/data/` (or the form xmlns) absolute paths instead of `${field}` references. Apply these rewrites to every `constraint`, `relevant`, `calculate`, and `jr:constraintMsg`/`jr:requiredMsg` reference returned by the helper:

| Replace | With | Notes |
| --- | --- | --- |
| `/data/<path>/<field>`, `/<root>/<path>/<field>` | `${<field>}` | XLSForm uses `${name}` substitutions; CommCare uses full XPath. Build a lookup of `nodeset → safe_name` during the pre-processing pass. Resolve paths under the form's xmlns the same way. |
| `==` | `=` | If the source ever uses `==`. |
| `position(..)` | `index()` | Repeat index. |
| `jr:choice-name(${field}, '${field}')` | `choice-label(${field}, ${field})` | If used; single quotes around the field name are no longer needed. |
| `coalesce(a, b)` | `coalesce(a, b)` | Same. |
| `if(/data/x, …)` with implicit-truthiness | `if(string-length(${x}) > 0, …)` | When the source relies on XPath truthiness for "field has value." |
| `instance('casedb')/casedb/case[@case_id = ...]/...` | (translated case-property lookup) | See [§ Case management](#case-management) below. Don't emit raw `instance('casedb')` references — they don't resolve in SurveyCTO. |

After rewriting, verify each expression against [`expressions.md`](expressions.md). When unsure, run a quick `kb_search` for the function or operator.

## Case management — the big gap

CommCare's case management model is **structurally different from SurveyCTO's** and the conversion isn't mechanical. The relevant concepts:

- **CommCare cases**: long-lived records (a household, a patient, a beneficiary). Each case has properties, a list of forms that act on it, and lifecycle transitions (create / update / close).
- **CommCare's case database** (`instance('casedb')`): a secondary instance the form reads to look up case properties.
- **Case actions in the form**: `<case xmlns="...case/transaction/v2">` blocks inside the primary instance and matching `<bind>` calculates that compute properties to write back on submission. These declare the form's effect on the case (create new case, update properties, close case).
- **Modules and applications**: CommCare wraps forms in a module + app hierarchy that defines case selection, case list display, and form ordering. **The XForms XML does not carry the module/app context** — that lives in the CommCare HQ app builder and is lost on export.

SurveyCTO's analogues:

- **Case management in SurveyCTO** uses a designated server dataset to store the case list, with `caseid` as the key. Forms attach the case dataset, look up properties with `pulldata()`, and publish updates back via `<dataLink>` rules in the dataset XML. See [`overview.md`](overview.md#forms-datasets-and-data-flow) and [`datasets-xml.md`](datasets-xml.md).
- **Module/app structure** doesn't transfer. SurveyCTO has its own form-deployment model.

The conversion approach:

1. **Detect case usage early.** If `form["case_actions"]` is non-empty or `form["secondary_instances"]` includes a `casedb` entry, the form uses case management. Set expectations with the user before going further — this is the hardest part of any CommCare conversion.
2. **Inventory the case interactions**: which case properties does the form read (look for `instance('casedb')/.../@<property>` references in expressions), which does it write (look at `case_actions`), and what's the case-creation / case-close logic.
3. **Decide with the user how to model cases in SurveyCTO.** The common pattern: author a SurveyCTO server dataset (`datasetType=SERVER`) representing the case list, with `caseid` as the `<uniqueRecordField>`. Set up `<formLinks>` for pre-loading and `<dataLinks>` for the form's writes. See [`datasets-xml.md`](datasets-xml.md) for the XML schema.
4. **Translate case reads** — every `instance('casedb')/casedb/case[@case_id = instance('commcaresession')/.../@case_id]/<property>` becomes a `pulldata('<dataset_id>', '<property>', 'caseid', ${caseid})` calculation in the converted form. Drop the raw `instance('casedb')` expression.
5. **Translate case writes** — the form's case-update properties become fields in the SurveyCTO `survey` worksheet (with their existing `calculate` expressions, rewritten per the table above) that the dataset's `<dataLink>` will publish on submission.
6. **Translate case-create / case-close** — these usually translate to dataset publishing logic in the dataset XML's `<dataLink>` element with appropriate `<allowUpsert>`, `<allowDelete>`, or `<closeCondition>` rules; the precise mapping depends on the user's intent. Ask.
7. **Drop the `<case>` blocks and `casedb` instance references** from the converted XLSForm — SurveyCTO doesn't recognize them.
8. **Document everything in the conversion report** — every case property read or written, every case action, the proposed dataset structure, and the SurveyCTO-side steps the user must take (author the dataset XML, upload it, populate the initial case list).

This is the largest source of user-coaching work in a CommCare conversion. Plan to ask the user clarifying questions about case lifecycle, intended SurveyCTO dataset structure, and case selection (in CommCare, the module decides which case opens the form — in SurveyCTO, the user selects from a case-list view, or the form receives the case ID via `pulldata()` lookup).

## Secondary instances (external lookups)

If `form["secondary_instances"]` includes entries other than `casedb` and `commcaresession`, those are external data sources — typically `jr://fixture/item-list:my_fixture` style URIs that CommCare resolves at runtime against attached fixtures.

Use the clean external-data conversion path from [`form-conversion-odk.md`](form-conversion-odk.md#external-data-csvs-and-datasets) — Pattern A (attached CSV + `pulldata()`) for small static lookups, Pattern B (SurveyCTO dataset) for larger or shared data. Translate the runtime references (`instance('my_fixture')/items/item[...]`) into the equivalent `pulldata()` or `select_one … appearance=search('<dataset_id>')` pattern.

## Settings

CommCare's XForms doesn't have a `settings` worksheet — the form-level metadata lives in `<h:title>`, the primary instance's `id`/`xmlns` attributes, and the CommCare HQ app configuration (which isn't in the export). Build the SurveyCTO `settings` row from:

- `form_title` ← `form["form_title"]`.
- `form_id` ← slugify `form["form_id"]` (or ask the user — the Vellum-generated slug is often awkward).
- `default_language` ← `form["default_language"]`, mapped to a readable language name (`en` → `English`, etc.).
- `version` ← leave alone; template formula handles it.

CommCare app settings (autocapture, supervision-mode, multimedia bundling, end-of-form behavior) live in the CommCare HQ app builder, not the XForms XML, and don't transfer. Flag in the conversion report if the user wants equivalent SurveyCTO settings configured server-side.

## Vellum metadata

Anything in the `vellum:` namespace is Vellum form-builder metadata — labels, comments, formatting hints used only by Vellum. **Ignore entirely.** The helper doesn't surface vellum attributes; you don't need to.

## Things that don't translate cleanly

- **Case management** — translatable but not mechanical; see [§ Case management](#case-management).
- **CommCare modules / app structure** — not in the XML export; out of scope.
- **CommCare-specific XPath functions** like `if-not-changed()`, `commcare-version()`, `weeks-since()`, `count-related-cases()` — no SurveyCTO equivalents. Drop and flag.
- **Form-level autocapture / supervision-mode settings** — CommCare HQ-side configuration, not in the XForms.
- **Multimedia bundling preferences** — same.
- **`<secret>` field type** — SurveyCTO has no password-masked field. Convert to `text` and flag.
- **Form lifecycle hooks** (form submission triggers, callouts to external apps) — CommCare-specific; no XForms-level equivalent in SurveyCTO.

## CommCare-specific gotchas

- **`/data/<field>` vs `${field}`.** CommCare uses full XPath paths (relative to the form xmlns); XLSForm uses `${name}` substitutions. Rewrite every expression. The helper gives you both — `nodeset` (the full path) and `name` (the leaf), build a `nodeset → safe_name` lookup during the pre-processing pass and apply. **When the same leaf name appears in multiple groups, use the disambiguated name from `suggested_safe_name`** — see [§ Groups, repeats, and name collisions](#groups-repeats-and-name-collisions).
- **Nested groups and repeats.** CommCare nests groups arbitrarily deep, and repeats can contain groups (and vice versa). The helper preserves nesting via the begin/end markers and `parent_path`; emit the markers in order and the structure carries over. Watch for group-level `relevant` on the `begin_group` marker — emitting it on the marker row applies the relevance to every field inside, matching CommCare's behavior. Don't re-emit the same relevance on every field inside the group.
- **`jr:itext('id')` resolution.** Labels and hints are nearly always indirect via itext. The helper resolves them for you; if you ever read the XML directly, remember to look up the itext entry rather than treating the `ref` attribute as the label text.
- **The case database is invisible from the XForms.** `instance('casedb')` doesn't carry data inside the XML — at runtime CommCare populates it from the case server. The XForms only declares the reference. Don't try to read case data from the XML; that data lives elsewhere.
- **Form xmlns vs form ID.** The primary instance's `xmlns` attribute is a URL (often a `http://openrosa.org/...` or `http://commcarehq.org/...` URL). It's globally unique but rarely what the user wants as a SurveyCTO `form_id`. Use the primary instance root element's local tag name (`<data id="...">` — the `id` attribute is often a better candidate), or just ask the user.
- **Vellum question IDs** are stored as XForms `nodeset` leaf names, which are usually already XLSForm-safe. But Vellum allows characters XLSForm doesn't (hyphens, leading digits in some older forms); apply the safe-name rule per [`form-conversion.md`](form-conversion.md#field-name-sanitization).
- **`<output>` substitutions inside labels** are common in CommCare. The helper flattens them to `${field}` in the returned label text, but the field referenced might be deep inside a group (`/data/group1/age` → `${age}`) — verify the leaf-name approach doesn't collide. If collision, the conversion will fail the safe-name uniqueness check; disambiguate.
- **`acknowledge` rendering.** CommCare's `<trigger>` (and SurveyCTO's `acknowledge`) renders as a tap-to-continue confirmation. Identical semantics; carry over.
- **Multimedia per language.** CommCare can attach different media files per language (e.g., a different audio file for English vs Hindi). SurveyCTO supports this via `media:image:Hindi` style columns. The helper returns the per-language URIs; emit accordingly.
- **Some forms have inline `xml-external` fixtures** referencing CSV / XML files attached to the CommCare app. These don't transfer automatically; use the external-data conversion path.

## Worked example

A small CommCare form snippet — an integer question with a constraint, multi-language labels, and an inline image — and its SurveyCTO equivalent.

**Source XForms XML excerpt:**

```xml
<model>
  <instance>
    <data id="hh_followup" xmlns="http://commcarehq.org/forms/...">
      <consent/>
      <age/>
    </data>
  </instance>
  <itext>
    <translation lang="en">
      <text id="consent-label"><value>Did the respondent consent?</value></text>
      <text id="age-label">
        <value form="long">How old is the respondent?</value>
        <value form="image">jr://images/age_diagram.png</value>
      </text>
      <text id="age-hint"><value>Years</value></text>
      <text id="age-constraint-msg"><value>Age must be between 0 and 120.</value></text>
    </translation>
    <translation lang="hi">
      <text id="consent-label"><value>क्या उत्तरदाता ने सहमति दी?</value></text>
      <text id="age-label">
        <value form="long">उत्तरदाता की उम्र कितनी है?</value>
      </text>
      <text id="age-hint"><value>वर्ष</value></text>
      <text id="age-constraint-msg"><value>उम्र 0 और 120 के बीच होनी चाहिए।</value></text>
    </translation>
  </itext>
  <bind nodeset="/data/consent" type="xsd:string"/>
  <bind nodeset="/data/age" type="xsd:int" required="true()"
        relevant="/data/consent = 'yes'"
        constraint=". &gt;= 0 and . &lt;= 120"
        jr:constraintMsg="jr:itext('age-constraint-msg')"/>
</model>
<h:body>
  <input ref="/data/consent">
    <label ref="jr:itext('consent-label')"/>
  </input>
  <input ref="/data/age">
    <label ref="jr:itext('age-label')"/>
    <hint ref="jr:itext('age-hint')"/>
  </input>
</h:body>
```

**Target SurveyCTO `survey` rows:**

| type | name | label | label:Hindi | hint | hint:Hindi | required | relevance | constraint | constraint message | constraint message:Hindi | media:image |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `text` | `consent` | `Did the respondent consent?` | `क्या उत्तरदाता ने सहमति दी?` | | | | | | | | |
| `integer` | `age` | `How old is the respondent?` | `उत्तरदाता की उम्र कितनी है?` | `Years` | `वर्ष` | `yes` | `${consent} = 'yes'` | `. >= 0 and . <= 120` | `Age must be between 0 and 120.` | `उम्र 0 और 120 के बीच होनी चाहिए।` | `age_diagram.png` |

**Target SurveyCTO `settings` row** (set via `change_setting`):

| form_title | form_id | default_language |
| --- | --- | --- |
| `Household Follow-up` | `hh_followup` | `English` |

Conversion report items:

- itext language `hi` mapped to SurveyCTO language name `Hindi`. Confirm with the user.
- `/data/consent` XPath rewritten to `${consent}` reference.
- `media:image` cell populated from `jr://images/age_diagram.png` (filename only). User must attach `age_diagram.png` to the form at upload time.
- `jr:constraintMsg` resolved through itext to multi-language `constraint message` columns.
- Form ID derived from primary instance root tag (`hh_followup`); confirm with user.
