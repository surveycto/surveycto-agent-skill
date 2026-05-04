# Plan: Expand SurveyCTO skill to cover field plug-in development & testing

## Goal

Extend the SurveyCTO Agent Skill so an agent that loads it can competently help a
user **develop, package, and test SurveyCTO field plug-ins** — alongside the
existing XLSForm, dataset XML, and Data Explorer expertise. The skill should
embed enough condensed, authoritative reference material that the agent can
work without internet access, while still linking to the live, more
comprehensive sources.

## Sources researched

Verified against the following authoritative SurveyCTO sources:

1. [Using field plug-ins (product docs)](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/06.using-field-plug-ins.html) — how form designers attach and use plug-ins.
2. [Testing field plug-ins (product docs)](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/07.testing-field-plug-ins.html) — the field plug-in console in the form designer test view.
3. [Field plug-in catalog (Support Center)](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog) — curated catalog of community/SurveyCTO plug-ins.
4. [Guide to creating field plug-ins (Support Center)](https://support.surveycto.com/hc/en-us/articles/360052426933-Guide-to-creating-field-plug-ins) — beginner-oriented authoring guide.
5. [Guide to field plug-ins: how to customize fields](https://support.surveycto.com/hc/en-us/articles/360045234534-Guide-to-field-plug-ins-how-to-customize-fields) — user-facing guide.
6. [A non-developer's guide to using GenAI to build field plug-ins](https://www.surveycto.com/data-collection-quality/build-field-plugins-genai/) — recommended LLM-assisted workflow.
7. **[Developer documentation home (GitHub) — most authoritative](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/developer-docs-home.md)**, plus its two key sub-docs:
   - [`plug-in-definition.md`](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/plug-in-definition.md) — file structure, manifest schema, attachments, naming rules.
   - [`api-reference.md`](https://github.com/surveycto/field-plug-in-resources/blob/master/docs/api-reference.md) — full form API: properties, CSS classes, provided/called JS functions, field-specific APIs.
8. SurveyCTO baseline plug-in repos (template starting points): `baseline-text`, `baseline-integer`, `baseline-decimal`, `baseline-select_one`, `baseline-select_multiple`, plus feature demos `feature-demo-parameters`, `feature-demo-metadata`, `feature-demo-intents`.

## What will change

### 1. New reference primer: `references/field-plugins.md`

A single, self-contained primer (modeled after the existing primers in
`references/`) that condenses the developer documentation. Target length
roughly that of `references/datasets-xml.md` (~250–400 lines). Sections:

1. **Overview**
   - What a field plug-in is: an HTML/CSS/JS web view that "takes over" rendering of a single field.
   - Runtime: Android WebView, iOS WKWebView, or web-form iframe.
   - Supported field types: only `text`, `integer`, `decimal`, `select_one`, `select_multiple`.
   - Typical use cases (link to catalog).

2. **Anatomy & packaging**
   - Required files (case-sensitive names): `manifest.json`, `template.html`, `style.css`, `script.js`.
   - Optional files: external CSS/JS libraries, plug-in attachments (images/data), form attachments.
   - **Subdirectories are flattened on upload** — keep all files in zip root; duplicate filenames cause errors.
   - Filename rules: case-insensitive zip name, only letters/numbers/`.`/`-`/`_`, must start with a letter, ≤100 chars; other files inside are case-sensitive.
   - Final artifact: `name.fieldplugin.zip`.

3. **`manifest.json` schema**
   - Required: `name`, `author`, `version` (semver), `supportedFieldTypes` (subset of the five).
   - Optional: `externalCss`, `externalJs`, `hideDefaultRequiredMessage`, `hideDefaultConstraintMessage`.
   - Annotated example.

4. **`template.html`**
   - Mustache-templated HTML.
   - **Always use `{{{LABEL}}}` and `{{{HINT}}}` (triple braces)** because labels/hints can contain HTML.
   - Reference plug-in attachments via `{{PLUGINDIR}}/file.png`; reference form attachments by bare filename.

5. **`style.css` and `script.js`**
   - Loading order: `externalCss` → `style.css`; `externalJs` → `script.js`.
   - Recommendation: detect platform via the `android-collect`, `ios-collect`, `web-collect` document classes when behavior must differ.

6. **Form API: field properties** (Mustache + `fieldProperties.*`)
   - Full list with one-line semantics: `FIELDTYPE`, `LANGUAGE`, `LABEL`, `HINT`, `APPEARANCE`, `CONSTRAINTMESSAGE`, `REQUIREDMESSAGE`, `QUESTION_PLACEHOLDER_LABEL`, `READONLY`, `MEDIAIMAGE`, `MEDIAAUDIO`, `MEDIAVIDEO`, `METADATA`, `PARAMETERS`, `PRECONFIGURED_INTENT`.
   - Field-specific: `CURRENT_ANSWER` (text/integer/decimal/select), `CHOICES` array on selects with `CHOICE_VALUE`, `CHOICE_INDEX`, `CHOICE_LABEL`, `CHOICE_SELECTED`, `CHOICE_IMAGE`.

7. **CSS classes provided by the runtime**
   - Document-level: `android-collect`, `web-collect`, `ios-collect`, `is-read-only`, `language-<lang>`.
   - Utility: `default-question-text-size`, `default-answer-text-size`, `default-hint-text-size` (use these to honor user font-size settings).

8. **Provided JS functions** (call from your code)
   - Navigation: `goToNextField([skipValidation])`, `goToPreviousField([skipValidation])` (note inverted defaults).
   - Soft keyboard (Android): `showSoftKeyboard()`.
   - Metadata: `setMetaData(string)`, `getMetaData()`.
   - Parameters: `getPluginParameter(key)` (preferred) vs. `fieldProperties.PARAMETERS[i].value` (fragile).
   - Intents (Android only): `launchPreconfiguredIntent(cb)`, `launchIntent(name, params, cb)` (note `uri_data` special parameter).
   - Phone (Android only): `makePhoneCall(...)`, `getPhoneCallStatus(cb)`.

9. **Called JS functions** (you must define / may define)
   - Required: `clearAnswer()`, `setAnswer(value)` (per field type — incl. space-separated list for `select_multiple`).
   - Optional: `handleRequiredMessage(message)`, `handleConstraintMessage(message)`, `setFocus()`.

10. **Parameters from the form**
    - Form-side: `appearance = custom-pluginname(key=value, key='string', key=${field}, key=expr())`.
    - Values are evaluated *before* the plug-in loads, so `${field}` and full expressions work.
    - Parameter retrieval recommendations and pitfalls.

11. **Metadata round-trip with the form**
    - Persistence semantics (survives save/resume/crash, encrypted with the form, present in raw XML).
    - Read by other fields via `plug-in-metadata(${field})` SurveyCTO function.

12. **Using a plug-in in a form**
    - Attaching the `.fieldplugin.zip` (Form Designer Attachments section, or as a regular form attachment when uploading XLSForm).
    - Setting `appearance = custom-<pluginname>` at the field.
    - Behavior caveats: appearance support varies by plug-in; "Label display behavior" is bypassed; iOS keyboard quirk.

13. **Testing workflow**
    - **Field plug-in console** in the form-designer test view: HTML/CSS/JS live-edit boxes + Reload, parameter/metadata inspector, plug-in metadata panel — changes persist for the session only and are not saved.
    - Browser devtools (web forms) for `console.log` debugging.
    - CodePen / standalone HTML for non-SurveyCTO-dependent UI iteration.
    - Test on each target platform (Android Collect, iOS Collect, web forms) before deploying.
    - Compatibility: older Android/iOS WebViews may not support newer JS — link to the "Creating compatible field plug-ins" PDF.

14. **Recommended starting points**
    - Baseline repos for each supported field type (URLs).
    - Feature demos for parameters, metadata, intents.
    - The catalog as a lookup before building from scratch.

15. **Authoring workflow (condensed from the GenAI guide)**
    - Pick the closest baseline plug-in to fork.
    - Write a short tech spec: which baseline, retained vs. removed default behaviors, parameters, output data + metadata, error handling, libraries.
    - Implement in milestones; test each in the field plug-in console.
    - Code review (peer or second LLM) before publishing.
    - Document with a README and include a test form.

16. **Sharing/publishing conventions** (from developer-docs-home.md)
    - Add `scto-field-plug-in` GitHub topic.
    - Keep source under `source/`, the up-to-date `name.fieldplugin.zip` at the repo root, ancillary files under `extras/`.
    - Always include a test form.

17. **Common pitfalls**
    - Subdirectories inside the zip get flattened.
    - Forgetting the triple-brace Mustache for labels/hints.
    - Calling `setAnswer` for select with comma-separated rather than space-separated values.
    - Using `fieldProperties.PARAMETERS[i]` order-based access.
    - Trying to use plug-ins on unsupported field types (date, geopoint, image, etc.).
    - Re-uploading without bumping `version` so caches don't refresh.
    - Including secrets (API keys) inside plug-in code.

18. **Authoritative links** — same set listed under "Sources researched" above, formatted as a quick-reference list at the end.

### 2. `SKILL.md` updates (deliberately minimal — defer to references)

Most users of the skill are doing form/workflow work, not plug-in authoring. The
SKILL.md additions should be the *minimum* needed for an agent to:

1. Recognize a `.fieldplugin.zip` and the `custom-<name>` appearance syntax.
2. Help a user **attach and use** an existing plug-in in their form.
3. Know that authoring/testing exists and where to find the deep reference.

Specifically:

- **Front-matter `description`** — append a short clause mentioning field plug-ins / `.fieldplugin.zip` so routing fires when a user asks about them. One sentence, not a paragraph.
- **"SurveyCTO Form and Dataset Authoring" intro** — extend the file-type list from 3 to 4 (add field-plug-in definitions). One bullet line.
- **"Identifying SurveyCTO files" table** — one new row.
- **New top-level section: "Field plug-ins"** — kept short (~30 lines). Contains:
  - One-paragraph definition.
  - The two-line "use a plug-in" recipe (attach `.fieldplugin.zip` + set `appearance = custom-<name>(params)`).
  - Three bullet lines on authoring (fork a SurveyCTO baseline repo, edit four files, repackage as `name.fieldplugin.zip`) and two lines on testing: (i) the bundled local harness, which the agent can also render as an inline artifact in capable hosts; (ii) the in-product field plug-in console, required for final validation.
  - **Single pointer** to `references/field-plugins.md` for everything else: anatomy, manifest schema, full form API, parameters, metadata, testing, baselines.
  - No validation checklist here — that lives in the primer.
- **"Common patterns" section** — one short sub-pattern, "Use a custom field plug-in", showing the `appearance` syntax with a parameter referencing a field. ~5 lines.
- **"Debugging common issues" table** — 3 plug-in-specific rows (won't appear in dropdown / value not saved / subdirectory files 404). Each one line.
- **References table at the bottom** — one new row for `references/field-plugins.md`.
- **Key documentation links list** — 2 new links (developer-docs-home, "Using field plug-ins"). The primer carries the full link set.

Net effect: ~50–70 added lines in SKILL.md. Everything heavy lives in the primer.

### 3. `README.md` updates

- Update the one-line description in the intro to mention field plug-ins alongside forms/datasets/Data Explorer.
- Add a row to the "What's included" table for `references/field-plugins.md`.
- No structural changes to installation or release sections.

### 4. `assets/field-plugin-test-harness/` — local testing scaffolding (new)

Field plug-ins are pure HTML/CSS/JS in a wrapper that (a) renders `template.html`
through Mustache with a `fieldProperties` object, (b) substitutes `{{PLUGINDIR}}`,
(c) injects `style.css` and `script.js`, (d) provides a fixed set of global
JS functions and document classes, (e) calls `clearAnswer()`/`handleRequiredMessage()`
/etc. on the plug-in. All of that is reproducible outside SurveyCTO, which lets
us give the agent a fast in-the-loop testing harness before the user moves to
the in-product field plug-in console for final validation.

A key design constraint: many target hosts (Claude Code, Claude Cowork,
ChatGPT Canvas, Cursor's webview, etc.) can render HTML/JS artifacts directly
in their UI. The browser harness below is therefore designed as a single
self-contained HTML file that works **both** as a local-file tool **and** as
an inline artifact, so the agent can offer immediate visual previews without
the user leaving the chat.

We will ship two complementary tools, both zero-dependency at runtime:

#### A. `validate.mjs` — static packaging validator (Node, stdlib only)

Single-file Node script that takes a plug-in directory or `.fieldplugin.zip`
and checks:

- All four required files (`manifest.json`, `template.html`, `style.css`, `script.js`) present at the root.
- No subdirectories (or warns that they will be flattened).
- Zip and inner filename character/length rules (zip name case-insensitive, inner files case-sensitive; only letters/numbers/`.`/`-`/`_`; start with letter; ≤100 chars).
- `manifest.json` parses, contains required keys (`name`, `author`, `version`, `supportedFieldTypes`), `supportedFieldTypes` is a non-empty subset of the five allowed values, `version` looks like semver, optional keys (`externalCss`, `externalJs`, `hideDefault*Message`) have valid types.
- `script.js` defines `clearAnswer` and `setAnswer` (cheap regex; warning, not error, if not detected).
- Referenced `externalCss` / `externalJs` files actually exist.
- Suggests bumping `version` if a previous build is detected (optional; based on a sibling `.fieldplugin.zip`).

Output: pass/fail with a machine-friendly JSON mode (`--json`) and a human mode by default. The agent can run this after every edit.

#### B. `preview.html` — single-file test harness (no deps, artifact-renderable)

A **single self-contained HTML file** that doubles as (1) a local-file harness
opened in a browser and (2) an inline artifact rendered in agent UIs that
support HTML/JS artifacts (Claude Code, Claude Cowork, ChatGPT Canvas,
Cursor's webview, etc.). All assets — official `mustache.js` (~600 LOC, MIT),
fixtures, harness JS, harness CSS — are inlined. No network requests at
runtime.

It behaves like a stripped-down field plug-in console:

- **Plug-in source loading — two modes:**
  - **Local-file mode:** "Load from folder" UI using `<input type="file" webkitdirectory>` (or three individual file pickers as a fallback) reads `manifest.json`, `template.html`, `style.css`, `script.js` from the user's machine. Reload button re-reads after edits on disk.
  - **Inline / artifact mode:** three textareas (HTML / CSS / JS) plus a manifest-JSON textarea, all editable in place. The agent can pre-populate them when it serves the harness as an artifact, then update the artifact contents as the plug-in evolves. The user can also edit in the textareas to test small changes — same loop as the SurveyCTO in-product console.
  - Mode is auto-detected and switchable via a toggle.
- **Mustache rendering:** uses the bundled official `mustache.js` so output matches SurveyCTO's runtime on sections, inverted sections, partials, and escaping (including the `{{{LABEL}}}` triple-brace HTML-passthrough pattern).
- **`{{PLUGINDIR}}` substitution:** done before render. In artifact mode the placeholder is replaced with `data:` URIs for any plug-in attachments the user pastes/uploads (or with a configurable string for testing).
- **Fixtures:** built-in fixtures for each supported field type (`text`, `integer`, `decimal`, `select_one`, `select_multiple`) — selectable from a dropdown, editable as JSON in a textarea so the agent or user can tailor `LABEL`, `HINT`, `APPEARANCE`, `PARAMETERS`, `CHOICES`, etc.
- **Stubs for provided global JS functions:**
  - `setAnswer(v)` and `setMetaData(s)` log to a panel and update the displayed "current answer" / "metadata" state.
  - `getMetaData()` reads from that panel.
  - `getPluginParameter(key)` looks up the fixture's `PARAMETERS`.
  - `goToNextField` / `goToPreviousField` log and show a "would navigate" toast.
  - Android-only functions (`launchPreconfiguredIntent`, `launchIntent`, `makePhoneCall`, `getPhoneCallStatus`, `showSoftKeyboard`) are no-ops that log a warning that they only run on Android Collect.
- **Runtime classes:** togglable `web-collect` (default) / `android-collect` / `ios-collect` document class, `is-read-only` toggle, language picker (sets `language-<x>` class).
- **External UI:** buttons to invoke `clearAnswer()`, `handleRequiredMessage('msg')`, `handleConstraintMessage('msg')`, `setFocus()`. The harness calls them on the plug-in if they're defined and shows a clear "not defined" indicator otherwise.
- **Output panels:** "current answer", "metadata", and a JS console mirror so the agent and user can both observe what the plug-in is doing without devtools.

Hosts that *can't* render HTML artifacts inline still get full value: the user
opens `preview.html` from disk and uses local-file mode.

Limits we will explicitly document in the harness's README and in the primer:

- Real WebView/intent/phone APIs are stubbed; final testing on Android/iOS requires the in-product field plug-in console.
- The harness ships the official `mustache.js`. SurveyCTO's runtime should match closely, but if SurveyCTO has private extensions we'll surface any divergence in the README.

#### C. Tier C (Playwright) — described, not shipped

The primer will include a short "advanced" subsection sketching a
Playwright/Puppeteer-driven version of `preview.html` for agents in environments
that have those libraries — this is documentation-only, no code shipped.

### 5. `assets/field-plugin-template/` skeleton (confirmed)

Ship a minimal "hello world" plug-in starter (original code, Apache-2.0 like
the rest of the skill), parallel to the existing `assets/xlsform-template.xlsx`:

```
assets/field-plugin-template/
  manifest.json     # name=template, supportedFieldTypes=["text"], version=0.1.0
  template.html     # uses {{{LABEL}}}, {{{HINT}}}, {{CURRENT_ANSWER}}; default-*-text-size classes
  style.css         # minimal styling, platform-class examples in comments
  script.js         # implements clearAnswer(), wires input -> setAnswer()
  README.md         # how to rename, repackage as <name>.fieldplugin.zip, attach, set appearance
```

`SKILL.md` and `references/field-plugins.md` will both point to this directory
as the recommended starting point when the user wants a clean baseline; for
non-text field types and for richer features, they should fork the official
SurveyCTO `baseline-*` and `feature-demo-*` repos.

The skeleton is intentionally `text`-only and minimal — it is a *starter*, not
a copy of all five baselines. Users wanting `select_one`, `select_multiple`,
`integer`, or `decimal` baselines should fork from SurveyCTO's `baseline-*`
repos as documented.

## Out of scope

- Actually shipping baseline plug-in source code (those live in their own SurveyCTO repos and are MIT-licensed by SurveyCTO; the agent should be told to fork from there rather than copying into this repo).
- Tooling that actually builds/zips the plug-in. The skill describes the steps; if generic shell tools are available the agent can `zip` the directory itself, and that's covered by general agent capabilities.
- Changes to the SurveyCTO MCP server (separate project). The skill should
  note that today there is **no** MCP tool dedicated to field plug-in
  authoring; live `kb_search` is the only related MCP path.

## Implementation order (when execution begins)

1. Write `references/field-plugins.md` end-to-end (the heavy primer; everything authoritative lives here).
2. Build `assets/field-plugin-test-harness/`: `validate.mjs`, `preview.html` (with vendored tiny Mustache), built-in fixtures, and a `README.md` explaining usage and stub limitations.
3. Build `assets/field-plugin-template/` skeleton (4 source files + README, text-only minimal starter).
4. Edit `SKILL.md` minimally — keep it reference-heavy. Point to the primer for everything beyond "what is it / how to use it / where to look".
5. Edit `README.md` (intro line + "What's included" rows for the primer, the skeleton, and the test harness).
6. **Rebuild both zips at the very end:** `surveycto-skill.zip` and `surveycto-skill-dev.zip`. Confirm build command/script with the user during implementation if it's not obvious from the existing zips' structure.
7. No version bump in `SKILL.md` front-matter (per user direction).

## Decisions (resolved)

- **Skeleton:** ship `assets/field-plugin-template/` (text-only minimal starter); link to SurveyCTO's `baseline-*` and `feature-demo-*` repos for everything else.
- **Testing harness:** ship Tier A (Node validator) + Tier B (single-file browser preview harness, designed to work both locally and as an inline artifact in agent UIs that support HTML/JS rendering — Claude Code, Cowork, Canvas, Cursor webview, etc.), both zero-dependency, in `assets/field-plugin-test-harness/`. Tier C (Playwright) is documentation-only in the primer.
- **SKILL.md size:** keep additions minimal (~50–70 lines); push depth into `references/field-plugins.md` and the test-harness README.
- **Slash command:** skip on this pass.
- **Version bump:** none.
- **Zip rebuild:** yes — rebuild both `surveycto-skill.zip` and `surveycto-skill-dev.zip` as the final step.
