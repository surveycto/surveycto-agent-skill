<!--
  PRIMER: field-plugins
  STATUS: docs-derived. Condensed from the SurveyCTO field plug-in developer
  documentation (github.com/surveycto/field-plug-in-resources) and the
  associated product docs/support articles. Update when the upstream
  developer docs change.
-->

# SurveyCTO Field Plug-in Reference

Field plug-ins are small HTML/CSS/JS bundles that **take over the rendering
of a single form field** in SurveyCTO Collect (Android), SurveyCTO Collect
for iOS, and web forms. A plug-in renders inside a WebView/iframe and
communicates with the form host through a small JavaScript bridge: the host
exposes the field's properties and a set of utility functions; the plug-in
defines callbacks the host invokes to read or clear the answer.

This primer condenses the upstream developer documentation. The authoritative
source is the [field-plug-in-resources repo on GitHub](https://github.com/surveycto/field-plug-in-resources),
particularly [`docs/developer-docs-home.md`](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/developer-docs-home.md),
[`docs/plug-in-definition.md`](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/plug-in-definition.md),
and [`docs/api-reference.md`](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/api-reference.md).

## Overview

A field plug-in is a zip bundle (`<name>.fieldplugin.zip`) attached to a form.
A field whose `appearance` column starts with `custom-<name>` renders through
the plug-in instead of the default UI. The plug-in is responsible for:

- Displaying the question (label/hint/media).
- Collecting input.
- Reporting the resulting answer back to the form via `setAnswer(value)`.
- Clearing its UI state on demand via `clearAnswer()`.

Plug-ins are supported on these field types only:

- `text`
- `integer`
- `decimal`
- `select_one`
- `select_multiple`

Plug-ins **cannot** be attached to `date`, `time`, `datetime`, `geopoint`,
`geotrace`, `geoshape`, `image`, `audio`, `video`, `barcode`, `calculate`,
`note`, `acknowledge`, `begin group`, `begin repeat`, or any other type.

For ready-made plug-ins, see the [field plug-in catalog](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog).
For an LLM-assisted authoring workflow, see [A non-developer's guide to using GenAI to build field plug-ins](https://www.surveycto.com/data-collection-quality/build-field-plugins-genai/).

## Anatomy and packaging

### Required files (case-sensitive names, all at zip root)

| File | Purpose |
| --- | --- |
| `manifest.json` | Plug-in metadata and capabilities |
| `template.html` | Mustache-templated HTML rendered into the field |
| `style.css` | Stylesheet (loaded after any `externalCss`) |
| `script.js` | Plug-in logic (loaded after any `externalJs`) |

### Optional files

- External libraries listed under `externalCss` / `externalJs` in the manifest (e.g. `jquery.min.js`).
- **Plug-in attachments** — assets shipped inside the zip (images, fonts, JSON data, etc.). Reference them in `template.html`/`style.css`/`script.js` via `{{PLUGINDIR}}/filename.ext`.
- **Form attachments** — files attached to the form (not the plug-in zip). Reference them by bare filename, exactly as in standard form attachments.

### Packaging rules

- Final artifact: `<filenamestem>.fieldplugin.zip`. The `<filenamestem>` is what form designers reference as `custom-<filenamestem>` in the field's `appearance` column. It is **independent of `manifest.name`** (which is a human-readable display name).
- **Subdirectories inside the zip are flattened on upload.** Keep every file at the zip root, and avoid duplicate basenames — duplicates after flattening cause an upload error.
- **Zip filename rules** (case-insensitive at upload; the rules apply to the full filename including `.fieldplugin.zip`): only letters, numbers, `.`, `-`, `_`; must start with a letter; ≤ 100 characters total.
- **Inner filename rules** (case-sensitive at runtime, applied to every file inside the zip): only letters, numbers, `.`, `-`, `_`; must start with a letter; ≤ 100 characters. The four required filenames already satisfy these rules — pay attention when naming external libraries and plug-in attachments.
- Always bump `manifest.json` `version` when re-uploading. The form host caches plug-in assets aggressively; without a version bump, devices may continue serving the previous build.

## `manifest.json` schema

```json
{
  "name": "myplugin",
  "author": "Your Name",
  "version": "1.0.0",
  "supportedFieldTypes": ["text"],
  "externalCss": ["bootstrap.min.css"],
  "externalJs": ["jquery.min.js"],
  "hideDefaultRequiredMessage": false,
  "hideDefaultConstraintMessage": false
}
```

| Key | Required | Notes |
| --- | --- | --- |
| `name` | yes | **Human-readable** display name of the plug-in (max 100 chars). Does **not** drive `custom-<name>` in form `appearance` — that comes from the `.fieldplugin.zip` filename stem. |
| `author` | yes | Author name or organization. |
| `version` | yes | Semver string. **Bump on every re-upload.** |
| `supportedFieldTypes` | yes | Non-empty subset of `text`, `integer`, `decimal`, `select_one`, `select_multiple`. |
| `externalCss` | no | Array of CSS filenames bundled at the zip root, loaded *before* `style.css`. |
| `externalJs` | no | Array of JS filenames bundled at the zip root, loaded *before* `script.js`. |
| `hideDefaultRequiredMessage` | no | If `true`, the host suppresses its default required-field error UI; the plug-in is expected to handle it via `handleRequiredMessage`. |
| `hideDefaultConstraintMessage` | no | Same idea for constraint errors and `handleConstraintMessage`. |

## `template.html`

`template.html` is rendered through Mustache against a `fieldProperties`
object the host supplies. Mustache section/inverted-section/escaping rules
apply.

**Always use triple-brace tags for label and hint text** because SurveyCTO
labels and hints can contain HTML (e.g. line breaks, formatting). Double
braces would HTML-escape the markup:

```html
<label class="default-question-text-size">{{{LABEL}}}</label>
<p class="default-hint-text-size">{{{HINT}}}</p>
```

For values that are guaranteed safe (e.g. numeric `CURRENT_ANSWER`), double
braces are fine.

Reference plug-in attachments via `{{PLUGINDIR}}`, which the host substitutes
to the runtime path of the unpacked zip. The substitution is a plain
search-and-replace and applies in **all three** core files (`template.html`,
`style.css`, and `script.js`):

```html
<img src="{{PLUGINDIR}}/icon.png" alt="">
```

```css
.bg { background-image: url("{{PLUGINDIR}}/bg.png"); }
```

```js
img.src = "{{PLUGINDIR}}/icon.png";
```

Form attachments are referenced by bare filename (no prefix), the same as in
the rest of the form.

## `style.css` and `script.js`

Loading order at runtime:

1. Any files listed in `externalCss`, in order.
2. `style.css`.
3. The rendered `template.html`.
4. Any files listed in `externalJs`, in order.
5. `script.js`.

`script.js` should generally:

- Define a global `clearAnswer()` (and optionally `handleRequiredMessage`, `handleConstraintMessage`, `setFocus`) — see [Called JS functions](#called-js-functions).
- Wire up DOM event listeners that **call** the host-provided `setAnswer(value)` whenever the user changes the answer. `setAnswer` is provided by the host; the plug-in does not define it.
- Read `fieldProperties.*` for parameters/metadata/etc., or use `getPluginParameter()` and `getMetaData()`.

When behavior must differ by platform, branch on the document classes the
host adds (see [CSS classes provided by the runtime](#css-classes-provided-by-the-runtime))
rather than user-agent sniffing.

## Form API: field properties

Inside `template.html`, properties are referenced as Mustache tags
(`{{LABEL}}`, `{{{LABEL}}}`, `{{#CHOICES}}…{{/CHOICES}}`). Inside `script.js`,
the same data is on the global `fieldProperties` object
(`fieldProperties.LABEL`, `fieldProperties.CHOICES`, etc.).

### Common to all field types

| Property | Description |
| --- | --- |
| `FIELDTYPE` | One of `text`, `integer`, `decimal`, `select_one`, `select_multiple`. |
| `LANGUAGE` | Active form language code (matches the `language-<lang>` document class). |
| `LABEL` | Field label, possibly containing HTML — use triple braces. |
| `HINT` | Field hint, possibly containing HTML — use triple braces. |
| `APPEARANCE` | Full `appearance` column value, including `custom-<name>(params)` and any extra appearance tokens. |
| `CONSTRAINTMESSAGE` | The form's constraint-violation message for this field. |
| `REQUIREDMESSAGE` | The form's required-field message. |
| `QUESTION_PLACEHOLDER_LABEL` | Placeholder text used when the field has no `label`. |
| `READONLY` | `true` if the field is read-only (also reflected by the `is-read-only` document class). |
| `MEDIAIMAGE` | Path to the field's `media::image` attachment, if any. |
| `MEDIAAUDIO` | Path to the field's `media::audio` attachment, if any. |
| `MEDIAVIDEO` | Path to the field's `media::video` attachment, if any. |
| `METADATA` | Plug-in metadata previously persisted via `setMetaData` (string, may be empty). |
| `PARAMETERS` | Array of `{ key, value }` parameter pairs from `custom-<name>(...)`. **Prefer `getPluginParameter(key)` over indexing into this array.** |
| `PRECONFIGURED_INTENT` | Boolean. `true` when the field is configured to communicate with an external app via the XLSForm `ex:` appearance prefix; otherwise `false`. Always `false` on web forms and iOS Collect (the underlying intent mechanism is Android-only). |

### Field-specific

`text`, `integer`, `decimal`, `select_one`, `select_multiple`:

| Property | Description |
| --- | --- |
| `CURRENT_ANSWER` | The current answer for the field. For `select_multiple`, a space-separated list of selected `value`s. |

`select_one` and `select_multiple` only — `CHOICES` is an array of objects
iterable in Mustache via `{{#CHOICES}}…{{/CHOICES}}`:

| Choice property | Description |
| --- | --- |
| `CHOICE_VALUE` | The choice's stored value. |
| `CHOICE_INDEX` | 0-based position in the (filtered) list. |
| `CHOICE_LABEL` | The choice's label, possibly containing HTML — use triple braces. |
| `CHOICE_SELECTED` | `true` if currently selected. |
| `CHOICE_IMAGE` | Path to the choice's `image` attachment, if any. |

## CSS classes provided by the runtime

The host adds classes to `<html>`/`<body>` so plug-ins can adapt their UI:

| Class | Meaning |
| --- | --- |
| `android-collect` | Running inside SurveyCTO Collect on Android. |
| `ios-collect` | Running inside SurveyCTO Collect for iOS. |
| `web-collect` | Running inside a SurveyCTO web form. |
| `is-read-only` | Field is read-only (mirrors `fieldProperties.READONLY`). |
| `language-<lang>` | Active form language. The host lowercases the language name, strips diacritics to ASCII where possible (e.g. `español` → `espanol`), and replaces any remaining special characters or spaces with hyphens (e.g. `idioma español` → `language-idioma-espanol`). For single-language forms the class is `language-default`. |

Utility classes (use them so plug-ins honor the user's font-size settings):

| Class | Apply to |
| --- | --- |
| `default-question-text-size` | The element rendering `LABEL`. |
| `default-answer-text-size` | The element(s) rendering or capturing the answer. |
| `default-hint-text-size` | The element rendering `HINT` and similar helper text. |

## Provided JS functions

Defined by the host on the global scope; the plug-in calls them.

### Navigation

| Function | Notes |
| --- | --- |
| `goToNextField([skipValidation])` | Advance to the next field. **Default `skipValidation` is `false`.** |
| `goToPreviousField([skipValidation])` | Move to the previous field. **Default `skipValidation` is `true`.** |

The defaults are inverted by design: the form should validate before
advancing, but going back should always be allowed.

### Soft keyboard (Android only)

| Function | Notes |
| --- | --- |
| `showSoftKeyboard()` | Shows the on-screen keyboard. No-op on iOS and web. |

### Metadata

| Function | Notes |
| --- | --- |
| `setMetaData(string)` | Persists a plug-in-level metadata string with the form data. |
| `getMetaData()` | Returns the most recently saved metadata string for this field. |

Plug-in metadata persists across save/resume/crash and is included in the
raw form XML. Other fields can read it via `plug-in-metadata(${field})` in
expressions.

**Treat metadata exactly like response data for security purposes.** Per the
upstream API reference, metadata is encrypted only when both the form and
the field are encrypted; it is **not** encrypted when the field is
publishable, and it is visible to anyone inspecting the raw submitted XML or
SurveyCTO Desktop's local storage. Do not put secrets, API keys, or PII you
wouldn't put in a response field into metadata.

### Parameters

| Function | Notes |
| --- | --- |
| `getPluginParameter(key)` | Returns the value of the parameter named `key` from the `custom-<name>(...)` appearance, or `undefined`. |

Prefer `getPluginParameter(key)` over `fieldProperties.PARAMETERS[i].value` —
the array is order-sensitive and breaks the moment a form designer reorders
or omits a parameter.

### Intents (Android only)

| Function | Notes |
| --- | --- |
| `launchPreconfiguredIntent(callback(error, result))` | Launch the external app the field is configured for via the `ex:` appearance prefix (i.e. when `PRECONFIGURED_INTENT` is `true`). The field's current value is passed to the external app as a `value` parameter. |
| `launchIntent(intentName, params, callback(error, result))` | Launch an arbitrary [Android intent](https://developer.android.com/reference/android/content/Intent). The `uri_data` key in `params` is mapped to the intent's `data` attribute; all other keys become intent extras. |

In all callbacks, exactly one of `error` and `result` is populated.
On iOS Collect and web forms these functions are not available.

### Phone (Android only)

| Function | Notes |
| --- | --- |
| `makePhoneCall(phoneNumber, phoneNumberLabel?, hidePhoneNumber?, callback(error, result))` | Place a phone call. If Collect is the default phone app it places the call directly; otherwise it dispatches an intent. Set `hidePhoneNumber=1` to keep the number out of Collect's UI; pass `phoneNumberLabel` to display an alternate label. |
| `getPhoneCallStatus(callback(error, result))` | `result` is `-1` when there is no active call, otherwise the integer state value from Android's [`Call.getState()`](https://developer.android.com/reference/android/telecom/Call#getState()). |

## Called JS functions

Functions the host invokes on the plug-in. Define them as global functions in
`script.js`.

### Required

| Function | When called |
| --- | --- |
| `clearAnswer()` | Host wants the plug-in to reset its UI state and clear any internal answer. **Required.** |

**Note:** `setAnswer` is *not* a function the plug-in defines. It is provided
by the host and the plug-in calls it to push a new answer up (see [Field-specific
answer formats](#answer-formats)). The host does not call into the plug-in to
"set the current answer" — instead, on every render it injects the saved value
as `fieldProperties.CURRENT_ANSWER`, which `script.js` should read to restore
the UI state on load.

### Optional

| Function | When called |
| --- | --- |
| `handleRequiredMessage(message)` | Host has a required-field error to display. Implement when `manifest.hideDefaultRequiredMessage` is `true`. |
| `handleConstraintMessage(message)` | Host has a constraint-violation message to display. Implement when `manifest.hideDefaultConstraintMessage` is `true`. |
| `setFocus()` | Host wants the plug-in to take input focus (e.g. user just navigated to this field). |

### Answer formats

When the plug-in calls `setAnswer(value)`, the value type depends on the
field type:

| Field type | Expected `value` |
| --- | --- |
| `text` | String. |
| `integer` | Integer (or numeric string). |
| `decimal` | Number (or numeric string). |
| `select_one` | A single choice `value`. |
| `select_multiple` | **Space-separated** list of choice `value`s, e.g. `"red green"`. Not comma-separated. |

## Parameters from the form

A form designer passes parameters through the field's `appearance` column:

```text
custom-myplugin(min=0, max=100, label='Pick one', target=${other_field}, init=expr())
```

Notes:

- Each parameter is a `key=value` pair, comma-separated.
- Values may be unquoted scalars, single-quoted strings, `${field}` references, or full SurveyCTO expressions; **values are evaluated by the form before the plug-in loads**, so the plug-in sees the *resolved* value.
- The plug-in reads them with `getPluginParameter('key')`. The legacy `fieldProperties.PARAMETERS` array is also available but order-sensitive — avoid it.
- Parameters are not strongly typed. Validate inputs and document defaults.
- Multiple `custom-<name>(...)` appearances on a single field are not supported; use one plug-in per field.

## Metadata round-trip with the form

Plug-in metadata is a per-field string the plug-in fully owns. Use it for
state the plug-in must persist across saves and that other form logic may
need to read.

- `setMetaData(s)` stores the string with the rest of the form data. It survives save/resume and crash recovery and is included in the raw submitted XML; encryption follows the response-data rules — encrypted only when both the form and the field are encrypted, and never encrypted when the field is publishable.
- `getMetaData()` reads the most recently stored value.
- Other fields can read it in expressions via `plug-in-metadata(${field})`.
- On the next render, the host injects the persisted value as `fieldProperties.METADATA`, so `script.js` can restore plug-in state on load.

## Using a plug-in in a form

1. **Attach the zip.** In the Form Designer, open the form's *Attachments*
   section and add the `.fieldplugin.zip`. (When uploading via XLSForm, you
   can also add it as a regular form attachment in the upload UI.)
2. **Set the appearance** on the field that should use the plug-in:

   | type | name | appearance |
   | --- | --- | --- |
   | `text` | `phone_number` | `custom-mypluginname(country='US')` |

3. **Verify field type compatibility** — the plug-in's `manifest.json`
   `supportedFieldTypes` must include the field's `type`.

Behavior caveats:

- Standard appearance support varies — a plug-in may ignore or override appearances like `minimal`, `quick`, etc.
- The form's "Label display behavior" (e.g. label-on-top) is bypassed; the plug-in renders the label itself.
- iOS keyboards may behave differently inside a WKWebView; some plug-ins need explicit `inputmode`/`pattern` attributes to surface the right keyboard.

## Testing workflow

### 1. Local fast loop (this skill ships a harness)

When authoring or editing a plug-in inside an agent session, the local
harness is the default in-agent preview surface — render it as soon as
the four core files are in place, and re-render after every revision.

Use the bundled test harness in `assets/field-plugin-test-harness/`:

- **`validate.mjs`** — a Node script that statically validates the plug-in
  package (file presence, manifest schema, `supportedFieldTypes`, naming
  rules, references to external CSS/JS). Run after every change.
- **`preview.html`** — a single self-contained HTML file that renders the
  plug-in against editable fixtures, stubs the host JS bridge, lets you
  toggle `web-collect` / `android-collect` / `ios-collect` document
  classes, and mirrors the JS console. Open it in any modern browser, or
  let an agent host serve it as an inline HTML artifact.

Both tools are zero-dependency, so they work offline and inside agent
sandboxes. See [`assets/field-plugin-test-harness/README.md`](../assets/field-plugin-test-harness/README.md)
for usage and limits.

### 2. SurveyCTO field plug-in console (final validation, required)

The form designer's test view includes a **field plug-in console** for
previewing live code changes against the real form context.

To open it:

1. In the SurveyCTO form designer, click *Test* — the top-right toggle
   inside the designer, or the *Test* button next to the form on the
   Design tab — to enter test view. *Test* is a form-level action, not
   a per-field action.
2. Navigate to the field that uses the plug-in. An icon button appears
   on the left edge of the form area; click it to expand the console.
   You can drag to resize.

The console shows three things:

- **Plug-in details** — name, version, author, supported field types,
  filename.
- **Current values** — the actual current values of any dynamic
  parameters and metadata, given the live form context.
- **Live code preview** — three editable boxes (HTML, CSS, JS) plus a
  *Reload* button. Edits persist for the test-view session as you
  navigate between fields.

Edits made in the console are session-scoped and **not** saved back to
the zip — use the console to validate behavior, then propagate fixes
to your source files and re-upload the `.fieldplugin.zip` (bumping
`manifest.version`).

For log-level debugging, prefer the local harness or browser devtools
(web forms); the in-product console does not surface a generic JS
console. See [Testing field plug-ins](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/07.testing-field-plug-ins.html).

### 3. Browser devtools and CodePen

For web forms specifically, browser devtools give you `console.log`,
breakpoints, and live DOM inspection. For non-SurveyCTO-dependent UI work,
a quick CodePen/JSFiddle iteration is often the fastest loop.

### 4. Real devices

Before deploying a plug-in widely, test it on each target platform:

- SurveyCTO Collect on a representative Android device (and a recent OS version).
- SurveyCTO Collect for iOS on an iPhone/iPad.
- Web forms in at least one major desktop browser.

Older Android System WebView and iOS WKWebView versions may not support
recent JavaScript features. See SurveyCTO's *Creating compatible field
plug-ins* PDF (linked from the developer docs home) for the supported
feature baseline.

### 5. Advanced: scripted browser tests (described, not shipped)

For agents that have Playwright or Puppeteer available, `preview.html` can
be driven headlessly: navigate to the file URL, populate the textareas via
DOM, snapshot/inspect the rendered output, and assert on the `setAnswer`
log. This skill does not ship such a runner; it is a documented option.

## Recommended starting points

Most SurveyCTO users are not GitHub users — assume no `git` or `gh` CLI
unless the user has clearly chosen a Git workflow. The default path for
acquiring a starting point is downloading a repository as a ZIP from
GitHub's *Code → Download ZIP* button.

Decide in this order:

1. **Use as-is from the catalog.** Always check the
   [field plug-in catalog](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog)
   first — there's a good chance a maintained plug-in already does what
   the user needs, and attaching it requires no authoring at all.
2. **Customize an existing plug-in.** Download the closest catalog plug-in
   or SurveyCTO `baseline-*` repo as a ZIP from GitHub (or clone/fork it if
   the user is comfortable with Git), then edit the four files at the
   bundle root.
3. **Start from the bundled
   [`assets/field-plugin-template/`](../assets/field-plugin-template/)** —
   a clean minimal text-only skeleton, useful when offline or when the user
   wants the smallest possible reading surface. It is original code, not a
   copy of `baseline-text`, and intentionally omits several baseline
   behaviors (see *What the bundled template omits* below). For non-`text`
   field types, prefer a baseline.

SurveyCTO baseline plug-ins, by field type:

| Field type | Repo |
| --- | --- |
| `text` | https://github.com/surveycto/baseline-text |
| `integer` | https://github.com/surveycto/baseline-integer |
| `decimal` | https://github.com/surveycto/baseline-decimal |
| `select_one` | https://github.com/surveycto/baseline-select_one |
| `select_multiple` | https://github.com/surveycto/baseline-select_multiple |

Feature demos:

- Parameters: https://github.com/surveycto/feature-demo-parameters
- Metadata: https://github.com/surveycto/feature-demo-metadata
- Intents (Android): https://github.com/surveycto/feature-demo-intents

### What the bundled template omits

`assets/field-plugin-template/` is intentionally minimal so the entire
skeleton fits in a few dozen lines a reader can scan in one sitting. When
you start from it instead of `baseline-text`, the following baseline-text
behaviors must be added back manually if you need them. The list is
pointer-style; consult `baseline-text`'s
[`source/template.html`](https://github.com/surveycto/baseline-text/blob/master/source/template.html),
[`source/style.css`](https://github.com/surveycto/baseline-text/blob/master/source/style.css),
and [`source/script.js`](https://github.com/surveycto/baseline-text/blob/master/source/script.js)
for the exact code rather than copying through this primer (license
attribution belongs with the source).

- **Field media rendering.** baseline-text's `template.html` renders
  `MEDIAIMAGE`, `MEDIAAUDIO`, and `MEDIAVIDEO` blocks; the bundled template
  does not.
- **HTML-entity unescaping in label/hint.** baseline-text's `script.js`
  defines an `unEntity()` helper and re-injects label/hint as
  `innerHTML` so HTML coming from `${field}` references in the form
  definition renders as markup rather than escaped text.
- **`QUESTION_PLACEHOLDER_LABEL` with default fallback.** baseline-text's
  template binds the placeholder to `QUESTION_PLACEHOLDER_LABEL` and falls
  back to `"Your answer here..."` when none is set; the bundled template
  has no placeholder.
- **Read-only display of empty values.** baseline-text hides the input
  entirely when the field is read-only and `CURRENT_ANSWER` is empty; the
  bundled template renders a disabled empty input regardless.
- **Read-only / response styling beyond `readOnly`.** baseline-text ships
  CSS classes (`.label`, `.hint`, `.response`, `.is-read-only .response`)
  with sensible defaults (margins, italic hint, bordered input, dimmed
  read-only background); the bundled template's CSS is far thinner.
- **Standard appearance handling.** baseline-text's `script.js` honors the
  `numbers`, `numbers_decimal`, and `numbers_phone` standard appearances by
  setting `input.type`/`pattern`/`inputmode` and applying an input filter
  for decimal-only entry.
- **Per-platform `inputmode` overrides.** baseline-text reads the
  `inputmode-android`, `inputmode-ios`, and `inputmode-web` plug-in
  parameters via `getPluginParameter()` and branches on the
  `android-collect` / `ios-collect` / `web-collect` body classes.
- **`setFocus` triggers the soft keyboard.** baseline-text's `setFocus()`
  calls `window.showSoftKeyboard()` on Android in addition to focusing the
  input; the bundled template only focuses the input.
- **`dir="auto"` on label, hint, and input.** baseline-text sets
  `dir="auto"` so RTL labels/answers render correctly; the bundled template
  does not.

baseline-text does **not** plumb `getMetaData`/`setMetaData` or call
`goToNextField()` by default — those are demonstrated in the
`feature-demo-metadata` and other feature-demo repos rather than
baseline-text itself, so they are not gaps in the bundled template.

## Authoring workflow (condensed)

1. **Check the catalog.** Don't rebuild what already exists.
2. **Pick a starting point** in the order above — catalog plug-in or
   `baseline-*` ZIP from GitHub (download or fork), or the bundled template
   for a minimal/offline starter.
3. **Write a short tech spec** before coding:
   - Which baseline or catalog plug-in you're starting from (download or fork).
   - Default behaviors retained vs. removed.
   - Parameters: names, types, defaults, validation rules.
   - Output data shape (what `setAnswer` produces) and what metadata you persist with `setMetaData`.
   - Error handling: how required/constraint messages render, what happens on bad parameters.
   - External libraries (kept minimal — every byte ships with the form).
4. **Implement in milestones.** After each milestone, re-render `preview.html` so the user can see the current state and run `validate.mjs` for static checks. Once the harness looks right, gate deployment on the in-product field plug-in console (final validation), then a real-device pass on each target platform.
5. **Get a code review.** Either a peer or a second LLM session — plug-ins are user-facing UI shipping inside a form, so a fresh pair of eyes catches a lot.
6. **Document.** Include a `README.md` in the source repo (parameters, behaviors, screenshots) and ship a **test form** that exercises the plug-in.

## Sharing/publishing conventions

From the [developer docs home](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/developer-docs-home.md):

- Tag the GitHub repo with the topic `scto-field-plug-in` so it shows up in catalog tooling.
- Keep editable source under `source/` in the repo.
- Keep the up-to-date `<name>.fieldplugin.zip` at the repo root so users can grab it without building.
- Put ancillary files (test forms, screenshots, license addenda) under `extras/`.
- Always include a test form in the repo.

## Common pitfalls

| Pitfall | Symptom | Fix |
| --- | --- | --- |
| Files placed in subdirectories of the zip | Files 404 at runtime, or duplicate-filename upload error | Flatten the zip — every file at the root, no duplicate basenames |
| Double-brace Mustache for `LABEL`/`HINT` | Label HTML is rendered as escaped text | Use triple braces: `{{{LABEL}}}` and `{{{HINT}}}` |
| `setAnswer` for `select_multiple` with comma-separated value | Only the first choice is selected, or none | Use **space**-separated: `setAnswer('red green')` |
| Reading parameters via `fieldProperties.PARAMETERS[i].value` | Plug-in breaks when designer reorders parameters | Use `getPluginParameter('key')` |
| Plug-in attached to unsupported field type | `appearance` ignored or upload error | Plug-ins only support `text`, `integer`, `decimal`, `select_one`, `select_multiple` |
| Confusing the appearance token with `manifest.name` | Field renders with the default UI even though the zip is attached | The `custom-<name>` token must match the `.fieldplugin.zip` filename stem (e.g. `myplugin.fieldplugin.zip` → `custom-myplugin`). `manifest.name` is a separate, human-readable display name. |
| Re-uploading without bumping `manifest.version` | Devices keep serving the old build (cached) | Bump the version on every release |
| Embedding API keys/secrets in plug-in code | Secrets ship to every device and are extractable | Don't. Route through a backend the plug-in calls, or accept the secret as a parameter set per server |
| Forgetting `clearAnswer()` | Host can't reset the field; required-on-revisit logic breaks | Always define `clearAnswer()` |
| Restoring state without reading `CURRENT_ANSWER` | Field shows blank after save/resume even though the answer is stored | Initialize the UI from `fieldProperties.CURRENT_ANSWER` on load |
| Assuming Android intent/phone APIs exist on iOS or web | Plug-in works in Collect, breaks in web forms | Branch on `android-collect` document class; degrade gracefully |
| Calling `goToNextField()` without considering validation | User skips required validation | Pass `skipValidation` explicitly when you mean to skip; the default is `false` |

## Quick-reference links

- Developer docs home: https://github.com/surveycto/field-plug-in-resources/blob/master/docs/developer-docs-home.md
- Plug-in definition (file structure, manifest, packaging): https://github.com/surveycto/field-plug-in-resources/blob/master/docs/plug-in-definition.md
- API reference (properties, classes, JS functions): https://github.com/surveycto/field-plug-in-resources/blob/master/docs/api-reference.md
- Using field plug-ins (product docs): https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html
- Testing field plug-ins (product docs): https://docs.surveycto.com/02-designing-forms/03-advanced-topics/07.testing-field-plug-ins.html
- Field plug-in catalog (Support Center): https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog
- Guide to creating field plug-ins (Support Center): https://support.surveycto.com/hc/en-us/articles/360052426933-Guide-to-creating-field-plug-ins
- Guide to field plug-ins: how to customize fields (Support Center): https://support.surveycto.com/hc/en-us/articles/360045234534-Guide-to-field-plug-ins-how-to-customize-fields
- Non-developer's guide to building field plug-ins with GenAI: https://www.surveycto.com/data-collection-quality/build-field-plugins-genai/
