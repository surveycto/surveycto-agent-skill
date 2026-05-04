# Field plug-in template (text)

A minimal SurveyCTO field plug-in skeleton for `text` fields. This is
**original minimal code, not a copy of `baseline-text`**, and it
intentionally omits several default behaviors that `baseline-text`
demonstrates — see *What the bundled template omits* in
`references/field-plugins.md` in the SurveyCTO Agent Skill
(https://github.com/surveycto/surveycto-agent-skill) for the full list.

This template is a **minimal/offline starter**, not the first
recommendation. The recommended order for picking a starting point is:

1. **The [field plug-in catalog](https://support.surveycto.com/hc/en-us/articles/360045235134-Field-plug-in-catalog).**
   If a maintained catalog plug-in already does what you need, attach it
   as-is and stop.
2. **A catalog plug-in or SurveyCTO `baseline-*` repo, downloaded as a ZIP**
   from GitHub's *Code → Download ZIP* button (or cloned/forked if you use
   Git). This gives you working defaults to customize.
3. **This template** — when you want the smallest possible reading surface,
   are working offline, or none of the existing plug-ins is a closer fit
   than starting fresh.

## What's here

| File | Purpose |
| --- | --- |
| `manifest.json` | Plug-in metadata (`name`, `author`, `version`, `supportedFieldTypes`) |
| `template.html` | Mustache-templated HTML for the field UI |
| `style.css` | Stylesheet (loaded after any `externalCss`) |
| `script.js` | Wires `<input>` to `setAnswer`, defines `clearAnswer` and `setFocus`, restores `CURRENT_ANSWER` on load |

For non-`text` field types, prefer downloading the matching SurveyCTO
baseline (Git clone/fork also works):

- `select_one`: https://github.com/surveycto/baseline-select_one
- `select_multiple`: https://github.com/surveycto/baseline-select_multiple
- `integer`: https://github.com/surveycto/baseline-integer
- `decimal`: https://github.com/surveycto/baseline-decimal

## How to use it

The packaged **filename stem** (the part before `.fieldplugin.zip`) is what
form designers reference as `custom-<stem>` in the field's `appearance`
column. The `name` field inside `manifest.json` is a separate, human-readable
display name. Pick a clean stem first; it's the one identifier you'll use in
forms.

1. **Copy** this directory to a working folder, e.g. `myplugin/`. The folder
   name doesn't have to match anything; only the final zip filename matters.
2. **Edit `manifest.json`:**
   - Set `name` to a human-readable display name (max 100 characters). This
     is shown to users in tooling; it does **not** drive `custom-<name>` in
     form appearance.
   - Set `author`.
   - Bump `version` on every re-upload (caches are aggressive).
   - Adjust `supportedFieldTypes` if you're targeting more than `text`.
3. **Customize** `template.html`, `style.css`, and `script.js` for your field.
4. **Iterate fast** with the field plug-in test harness shipped in the
   SurveyCTO Agent Skill (`assets/field-plugin-test-harness/` — see
   https://github.com/surveycto/surveycto-agent-skill):
   - Run `node validate.mjs ./myplugin` after each change.
   - Open `preview.html` to render the plug-in against editable fixtures.
5. **Final validation** in SurveyCTO's in-product field plug-in console
   (form designer → test view) before deploying.
6. **Package** when ready. The zip filename is the identifier form designers
   will use, so pick it carefully — it must start with a letter, contain only
   letters/numbers/`.`/`-`/`_`, and not exceed 100 characters total
   (including `.fieldplugin.zip`). Include **every** runtime file at the
   root of the zip:

   - The four core files: `manifest.json`, `template.html`, `style.css`, `script.js`.
   - **Every file listed in `manifest.externalCss` and `manifest.externalJs`** — the upload will fail or the plug-in will break at runtime if any are missing.
   - **All plug-in attachments** referenced via `{{PLUGINDIR}}/<filename>` from your HTML, CSS, or JS (images, fonts, JSON data, etc.).

   From inside the plug-in directory:

   ```bash
   # Include core files + any external libs and attachments you reference.
   zip -j ../myplugin.fieldplugin.zip \
       manifest.json template.html style.css script.js \
       jquery.min.js icon.png    # ← whatever extras your plug-in uses
   ```

   `zip -j` flattens any directory structure — required because subdirectories
   inside the zip get flattened on upload anyway, and duplicate basenames
   cause an error. Inner filenames must follow the same character rules as
   the zip filename (only letters/numbers/`.`/`-`/`_`, start with a letter,
   ≤ 100 chars) and are **case-sensitive** at runtime.

7. **Attach** `myplugin.fieldplugin.zip` to your form (Form Designer →
   Attachments, or as a regular form attachment in the upload UI).
8. **Use** it on a field by setting the appearance to
   `custom-<filenamestem>` — for `myplugin.fieldplugin.zip` that's:

   ```
   appearance: custom-myplugin
   ```

   or with parameters:

   ```
   appearance: custom-myplugin(placeholder='Enter name')
   ```

   In `script.js`, read parameters with `getPluginParameter('placeholder')`
   rather than indexing into `fieldProperties.PARAMETERS`.

## Reference

See `references/field-plugins.md` in the SurveyCTO Agent Skill
(https://github.com/surveycto/surveycto-agent-skill) for the full manifest
schema, form API, parameters/metadata model, runtime CSS classes, testing
workflow, and common pitfalls.
