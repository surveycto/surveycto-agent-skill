# Field plug-in test harness

A pair of zero-dependency tools that give you a fast local feedback loop
when authoring SurveyCTO field plug-ins. Use them in the loop, then run
final validation in SurveyCTO's in-product field plug-in console (the
form designer's test view).

| Tool | Use when |
| --- | --- |
| [`validate.mjs`](validate.mjs) | After every change. Static checks on the bundle (file presence, manifest schema, naming rules, references). |
| [`preview.html`](preview.html) | While iterating on UI/JS. Renders the plug-in against editable fixtures with a stubbed host bridge. |

Neither tool talks to the network at runtime. Both work offline.

## `validate.mjs`

Node 18+ stdlib only. Accepts either a plug-in directory or a
`.fieldplugin.zip`. For zip input, the script shells out to the system
`unzip` binary (read-only `unzip -Z1` / `unzip -p`); install `unzip` or
unpack the zip first.

```bash
# Validate a plug-in directory
node validate.mjs ./myplugin

# Validate a packaged zip
node validate.mjs ./myplugin.fieldplugin.zip

# Machine-readable output (for agents)
node validate.mjs ./myplugin --json
```

What it checks:

- All four required files (`manifest.json`, `template.html`, `style.css`, `script.js`) at the bundle root.
- No subdirectories (warning — they get flattened on upload).
- No duplicate basenames after flattening (error — the upload would be rejected).
- `manifest.json` parses, has required keys with valid types.
- `manifest.supportedFieldTypes` is a non-empty subset of `text`, `integer`, `decimal`, `select_one`, `select_multiple`.
- `manifest.version` looks like semver (warning if not).
- `manifest.externalCss` and `manifest.externalJs` reference files that exist in the bundle.
- `script.js` defines a global `clearAnswer` and calls `setAnswer` somewhere (warning if either signal is missing — cheap regex, not a parser).
- Zip filename conforms to SurveyCTO's rules (letters/numbers/`.`/`-`/`_`, starts with a letter, ≤ 100 chars, ends in `.fieldplugin.zip`).

Exit code: `0` on success (warnings allowed), `1` on any error.

## `preview.html`

A single self-contained HTML file. Open it in any modern browser (or let an
agent host serve it as an inline HTML artifact — no network access required).

Two source-loading modes, auto-detected:

- **Local-file mode.** Click *Load folder…* and select the plug-in directory.
  The harness reads `manifest.json`, `template.html`, `style.css`, and
  `script.js` from the selection. *Load files…* is a fallback when
  `webkitdirectory` isn't available — pick the four files individually.
- **Inline / artifact mode.** The four source textareas (HTML, CSS, JS,
  manifest) are editable in place. Edits auto-render after a 250 ms
  debounce. Agents serving the harness as an artifact can pre-populate the
  textareas and update them as the plug-in evolves.

The harness:

- Renders `template.html` through the bundled official mustache.js v4.2.0 (MIT, vendored verbatim) so output matches SurveyCTO's runtime — including triple-brace HTML pass-through, `{{#section}}` / `{{^inverted}}`, and standard escaping.
- Replaces `{{PLUGINDIR}}` in HTML, CSS, and JS via plain search-and-replace, mirroring SurveyCTO's behavior. In folder mode (see [Plug-in attachments and external libs](#plug-in-attachments-and-external-libs)) `{{PLUGINDIR}}/<file>` references resolve to data URIs for any non-core files in the loaded folder; otherwise they fall back to a placeholder path.
- Honors `manifest.externalCss` / `manifest.externalJs` load order: those files are concatenated *before* `style.css` / `script.js` exactly as SurveyCTO loads them.
- Loads the rendered HTML, your effective CSS (external + core), and your effective JS (external + core) inside a sandboxed iframe (`sandbox="allow-scripts"`).
- Exposes the host bridge as globals on the iframe: `setAnswer`, `setMetaData`/`getMetaData`, `getPluginParameter`, `goToNextField`/`goToPreviousField`, plus stubbed Android-only functions (`launchPreconfiguredIntent`, `launchIntent`, `makePhoneCall`, `getPhoneCallStatus`, `showSoftKeyboard`). Stubs log a warning and call any provided callback with `(error, result)` matching the upstream contract.
- Mirrors the iframe's `console.*` and `window.onerror` to the harness log so you don't need devtools for basic debugging.
- Toggles the document classes the runtime supplies (`web-collect` / `android-collect` / `ios-collect`, `is-read-only`, `language-<x>`) so you can verify platform branches without leaving the harness. The `language-` class is normalized exactly as SurveyCTO does it (lowercase, diacritics stripped, special characters/spaces collapsed to hyphens; `language-default` for empty input).
- Lets the parent invoke `clearAnswer`, `setFocus`, `handleRequiredMessage`, and `handleConstraintMessage` on the plug-in. The harness clears its displayed "current answer" when invoking `clearAnswer`, matching the host's order of operations. If a function isn't defined, the harness logs a `not defined` notice so you can decide whether the plug-in should implement it.
- Ships built-in fixtures for each supported field type (`text`, `integer`, `decimal`, `select_one`, `select_multiple`). Open the *Edit fieldProperties JSON* drawer to override `LABEL`, `HINT`, `APPEARANCE`, `PARAMETERS`, `CHOICES`, `CURRENT_ANSWER`, etc.

### Plug-in attachments and external libs

When you load a plug-in via *Load folder…* or *Load files…*, the harness:

- Reads the four core files into the editors.
- Reads each file listed in `manifest.externalCss` / `manifest.externalJs` as text and prepends it to the effective CSS / JS in declared order.
- Reads every other file as a data URL keyed by basename, then substitutes `{{PLUGINDIR}}/<basename>` references in HTML, CSS, and JS with the corresponding data URL.

References to `{{PLUGINDIR}}/<basename>` for files the harness didn't load (or in inline / artifact mode) fall back to a placeholder path, so the plug-in still loads but the asset URLs won't resolve.

**Inline / artifact mode limitation.** When the harness is served as a single inline artifact, only the four core files are editable; external libraries listed in `manifest.externalCss` / `manifest.externalJs` and plug-in attachments are not loaded. Workarounds:

1. **Inline the libraries** by pasting their CSS into `style.css` and their JS into `script.js` (or use their CDN-hosted UMD builds via `<script>` tags inside `template.html` if your plug-in's runtime allows network access).
2. **Switch to local-file mode** by saving `preview.html` to disk and using *Load folder…*; that exercises the full external-files + attachments path.
3. **Validate end-to-end in the in-product field plug-in console** — the local harness is a fast inner loop, not a substitute.

### Limits to keep in mind

- **Real WebView/intent/phone APIs are stubbed.** Final validation must happen in SurveyCTO Collect (Android), Collect for iOS, and at least one web-form browser.
- **Mustache parity:** the harness uses the upstream `mustache.js`. SurveyCTO's runtime should match closely on standard Mustache features. If you observe a divergence in your plug-in's output between the harness and the in-product field plug-in console, treat the in-product behavior as authoritative and adjust your template accordingly.
- **Form attachments aren't simulated.** The harness substitutes `{{PLUGINDIR}}` to a placeholder string; references to form attachments by bare filename will not resolve.
- **No XLSForm parsing.** The harness doesn't read your form; it renders the plug-in against fixtures you supply.

### Advanced: scripted browser tests (optional)

For agents with Playwright or Puppeteer available, the harness can be
driven headlessly:

1. Serve `preview.html` from a local web server.
2. Navigate to it.
3. Populate `#src-html`, `#src-css`, `#src-js`, `#src-manifest`, and
   `#fixture-json` via DOM (or use the *Load files…* picker).
4. Wait for the *Plug-in script loaded.* log line.
5. Type into the iframe via `page.frameLocator('#preview').locator(...)`,
   click control buttons, and assert on `#out-answer`, `#out-metadata`,
   and `#out-log` text.

This skill does not ship a Playwright runner; the architecture is
described here so an agent can build one ad-hoc when the environment
supports it.

## Reference

- Plug-in primer: [`../../references/field-plugins.md`](../../references/field-plugins.md)
- Skeleton starter: [`../field-plugin-template/`](../field-plugin-template/)
- Upstream developer docs: https://github.com/surveycto/field-plug-in-resources
