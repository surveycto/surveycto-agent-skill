<!-- PRIMER: form-conversion
  STATUS: drafted 2026-05-16 -->

# Converting forms from other platforms into SurveyCTO

This primer covers **converting a form definition exported from another data collection platform into a SurveyCTO XLSForm**. It is platform-agnostic: it describes the overall workflow, the universal mapping concerns that recur across every source platform, the conversion-report contract, and the validation checks that apply on top of the standard XLSForm checklist. Platform-specific details (`.qsf` anatomy, XForms namespaces, Kobo extensions, ODK divergences, etc.) live in dedicated companion references.

**Read this primer first**, then load the matching platform-specific reference for the source format:

| Source platform | Source file | Platform reference |
| --- | --- | --- |
| Qualtrics | `.qsf` (JSON) | [`form-conversion-qualtrics.md`](form-conversion-qualtrics.md) |
| KoboToolbox | `.xlsx` (XLSForm) | [`form-conversion-kobo.md`](form-conversion-kobo.md) |
| ODK Central / ODK Collect | `.xlsx` (XLSForm) | [`form-conversion-odk.md`](form-conversion-odk.md) |
| CommCare | `.xml` (XForms) | [`form-conversion-commcare.md`](form-conversion-commcare.md) |

If the source is from a platform without a dedicated reference — SurveyMonkey, REDCap, Magpi, Open Data Kit forks not covered above, in-house tools, custom CSV/JSON schemas — **the workflow below still applies.** Adapt the universal mapping concerns to the source format and lean on the SurveyCTO references (`xlsform.md`, `expressions.md`, the SurveyCTO docs via `kb_search`) for the target side.

## Set the right expectation with the user up front

Conversions are imperfect by design. Different data-collection platforms have different feature sets, different expression languages, different ways of organizing logic, and different conventions for almost everything. **The output of any conversion is a starting draft the user must review and refine — not a finished form.**

State this explicitly at the start of the conversation, before doing any conversion work, and again when you hand over the result. The conversion report (described below) is the primary mechanism by which the user understands what survived intact, what was approximated, and what needs hand-finishing.

What conversion does cover:

- The form **instrument structure**: questions, choice lists, groups, repeats, basic logic (relevance / skip patterns, constraints, calculations), settings, languages.
- A written **conversion report** that surfaces every approximation, drop, and judgment call with enough detail for the user to find and fix it.

What conversion does **not** cover (out of scope for this primer and every platform reference):

- **Response data migration.** Already-collected submissions from the source platform are a separate, much higher-stakes problem (no schema mismatch is acceptable for response data); this primer handles the *instrument* only.
- **Round-tripping.** Output XLSForms are not guaranteed to be re-importable into the source platform.
- **Platform-side delivery, themes, branding.** SurveyCTO has its own theming and delivery model; source-platform CSS, fonts, and logos are dropped.
- **Server-side integrations** unique to the source platform (Qualtrics XM Directory, CommCare case sharing, Kobo Hub deployments, ODK Central projects). These don't map; flag them in the report.

## Strategic choice: agent-driven, not script-driven

This skill's form-conversion workflows are **agent-driven**. You — the agent — read the source file, plan the mapping with full context, ask the user about ambiguous cases, and apply edits to the SurveyCTO XLSForm template via the standard MCP workflow. There is no per-platform Python converter script that takes a source file and writes an XLSForm; the only bundled helpers are small parsers that normalize source files into a clean shape for you to iterate (currently just [`commcare_xform_loader.py`](../assets/form-conversion/commcare_xform_loader.py) for CommCare XForms XML, where namespace handling is finicky enough to merit abstraction).

This is deliberate. The lossy / approximation surface of cross-platform conversion is large, and the right answer for any given edge case depends on the specific survey, the specific user, and the specific feature set they care about. An agent reasoning about the whole form at once can recognize edge cases, ask clarifying questions, and produce a much more useful conversion than a deterministic script with a frozen mapping table — at the cost of some run-to-run variance, which the conversion report makes auditable.

## The universal workflow

Follow these steps in order. Don't skip ahead: in particular, do not start patching the template before you've taken a complete inventory of the source.

### 1. Confirm the conversion expectations with the user

Before reading any files:

- **Confirm the source platform and source file.** If the user hasn't said, ask.
- **Set expectations** as described above — imperfect, starting draft, conversion report.
- **Ask the user what they care about most.** Different surveys have different "essential" features. A study that depends heavily on display logic needs a careful relevance translation pass; a simple intake form may not. This shapes where you spend effort and what you ask about as you go.
- **Ask about output naming.** What should the resulting form's `form_id` and `form_title` be? Slugify a reasonable default from the source if the user doesn't have a preference (lowercase, underscores, alphanumeric-only).
- **Ask about translations.** If the source is multi-language, does the user want all languages carried over, or just one? Default: carry all.

### 2. Read the SurveyCTO-side references

- **[`xlsform.md`](xlsform.md) is mandatory.** Column conventions, multi-language structure, group/repeat rules, and expression syntax — these are exactly the targets the conversion writes into, and SurveyCTO's conventions diverge from most other ODK-based platforms in subtle ways.
- **[`expressions.md`](expressions.md)** if the source has any logic (display logic, skip logic, constraints, calculations) — which is almost always.
- **[`translation.md`](translation.md)** if the source is multi-language.
- **[`mcp.md`](mcp.md)** for the MCP tools you'll use to apply edits and export the result.

### 3. Load the platform-specific reference

If a `form-conversion-<platform>.md` exists for the source format, read it fully before reading the source file. The platform reference is where you'll find the mapping table for question types, the expression-rewrite rules, and the platform-specific gotchas.

If no platform reference exists, skim the source format's own documentation (or what the user can tell you about it) and treat this primer's universal mapping concerns as the working guidance.

### 4. Read the source file with your own tooling

**Crucially: do not use the SurveyCTO MCP XLSForm tools on the source file.** Those tools (`start_xlsform_session`, `xls_get_rows`, `xls_apply_patches`, `export_xlsform`) understand SurveyCTO-shaped XLSForms specifically. They will either reject a non-SurveyCTO file outright or, worse, accept it and silently misinterpret columns. The MCP tools are for the *target* side only.

Read the source with:

- **Python + `openpyxl`** (or the agent's xlsx skill) for source XLSForms (Kobo, ODK, and any other XLSForm-based source).
- **Python + stdlib `json`** for Qualtrics `.qsf` files. The `.qsf` is JSON; `json.loads(Path(qsf_path).read_text())` is enough.
- **Python + stdlib `xml.etree.ElementTree` or `lxml`** for XForms `.xml` files. For CommCare specifically, use the bundled [`assets/form-conversion/commcare_xform_loader.py`](../assets/form-conversion/commcare_xform_loader.py) helper — it normalizes the source into a clean dict structure so you can iterate it instead of wrestling with namespaces.
- **Whatever the agent's environment supports** for unusual source formats. CSV, Google Sheets export, REDCap data dictionary, etc.

Take a **complete inventory** before patching anything:

- Every question / field, with its source identifier and source label.
- Every choice list, with values and labels.
- Every expression (display logic, skip logic, constraints, calculations, choice filters).
- Settings and metadata (form ID, title, languages, version, encryption).
- Anything that doesn't map cleanly — note the location and what makes it lossy.

For long source forms, this inventory is most useful as a structured Python object (or scratch notes) that you can iterate over when emitting patches. Don't try to convert in one pass while reading; separate the read pass from the write pass.

### 5. Plan the mapping

Before opening an MCP session:

- Decide the structural mapping (source blocks/sections → SurveyCTO groups; source loops → SurveyCTO repeats; source page breaks → SurveyCTO `field-list` group boundaries).
- Decide the question-type mapping for every field (consult the platform reference's mapping table).
- Decide choice-list deduplication (which lists collapse into one shared `list_name`).
- Translate every expression to SurveyCTO syntax (see "Expression rewrites" below).
- Identify every feature you can't translate — these go in the conversion report.

If you hit an ambiguous case where two mappings are both defensible and the choice depends on the user's intent, **ask the user** rather than guessing. Examples: a custom validator that could be a regex or a numeric range; a constant-sum question where SurveyCTO can only enforce the sum at the end of the group, not in real time; a display-logic expression that references an embedded variable never initialized in the source. The conversion report should mention every question you asked about and the user's answer.

### 6. Apply edits via the standard MCP workflow

Now you're on the SurveyCTO side, and the normal `SKILL.md` rules apply:

1. **Start from the template.** Make a literal file copy of `assets/xlsform-template.xlsx` to the output path. Never construct an `.xlsx` from scratch.
2. **`start_xlsform_session`** on the copy.
3. **Set settings** via `change_setting` — `form_id`, `form_title`, `default_language`. Don't touch `version`.
4. **Apply rows in batched `xls_apply_patches` calls.** Group related edits; use `validate_only=true` on a full batch for risky changes; set `return_form_summary=false` and `include_details=false` for large batches and verify once at the end.
5. **`export_xlsform`** when done. Hand the file or `download_url` to the user.

Read [`mcp.md`](mcp.md) before your first patch call. The patch semantics, concurrency rules, and limits are all documented there; don't guess them.

### 7. Write the conversion report

Always produced. Markdown. Saved as `<form_id>_conversion_report.md` (or similar — adjust to fit the user's naming) **next to the output `.xlsx`**, so the user can find it without digging through chat history. The format is fixed across platforms so reports diff cleanly across reruns; see "The conversion report" below.

### 8. Summarize inline and hand off

In chat, give the user:

- A one-paragraph summary: source file, target file, totals (questions converted / approximated / dropped, expressions translated / flagged).
- The top three or four issues that most need human attention, with line/question references. This is curated, not exhaustive — the report has the full list.
- A link or path to the conversion report file.
- A link or path to the output XLSForm.
- A reminder that the form is a starting draft, not a finished form, and the user should review the report and open the form in SurveyCTO's designer to verify it behaves as expected.
- A reminder to attach any required `.fieldplugin.zip` files in the SurveyCTO console at upload time, if the conversion produced any `custom-<name>` appearances (rare for conversions, but possible if the user asked for plug-in integration).

## Template flexibility

The bundled SurveyCTO XLSForm template at `assets/xlsform-template.xlsx` is a **helpful starting point, not a fixed requirement.** It ships with starter content (a `yesno` choice list, several metadata / audit rows, an auto-updating `version` formula, conditional formatting, help worksheets) that's there as a convenience. Treat different starter content differently: user-facing example content and unused example choice lists are fair game to delete or replace, while the standard metadata / audit rows are generally useful defaults and should usually stay unless the source form or user request gives you a reason to remove them.

In conversion specifically, the most common edits to template starter content are:

- **Drop unused example choice lists or user-facing starter rows** when they are not part of the source instrument. In particular, drop the template `yesno` choice list if the source uses different values or labels and you want to preserve the source's expressions verbatim. The `yesno` list is an example, not mandatory infrastructure — nothing in SurveyCTO breaks if it isn't present.
- **Keep standard metadata / audit rows by default.** They are useful in most SurveyCTO forms and are not user-facing clutter. Remove or replace them only when the source has its own equivalent fields, the user asked for a minimal instrument, or keeping them would create confusing duplicates. The template `caseid` row is more context-dependent: keep it for case-management conversions; otherwise delete it if it would confuse the draft, or leave it only with a report note.
- **Keep the auto-updating `version` formula**, the conditional formatting, and the help worksheets — these are the template content most worth preserving, because they're tooling rather than form content.

Don't leave unused user-facing starter content in a converted form by inertia. If the source's yes/no convention doesn't exactly match the template's `yesno` list, either normalize the source to `yesno` and rewrite every expression that compares against those values, or preserve the source choice values and **delete the unused template `yesno` list**. Standard metadata / audit rows are different: keeping them is usually fine and does not need a special justification unless the conversion report would otherwise imply a source-faithful field inventory.

The rule that does **not** bend: every new XLSForm starts by copying the template (never built from scratch). Once copied, the contents are yours to edit, including deleting starter rows or choice lists that don't apply.

When you change template starter content, be consistent — if you drop a choice list, also drop every reference to it. If you rewrite a choice's `value`, also rewrite every expression that compares against the old value. The silent-breakage risk is rewriting only one side.

## Universal mapping concerns

The patterns below recur across every source platform. The platform-specific reference will tell you when and how each applies for that platform; this section is the canonical statement of the underlying SurveyCTO target rules.

### Field-name sanitization

Source platforms commonly allow characters in question identifiers that XLSForm `name` cells don't. Spaces, hyphens, dots, leading digits, Unicode letters, and platform-specific reserved characters all need to go.

The safe-name rule:

- Match `^[A-Za-z_][A-Za-z0-9_]*$`.
- Strip or replace anything else with `_`. Collapse consecutive `_` into one.
- If the result starts with a digit, prefix `q_`.
- If two source fields sanitize to the same target name, disambiguate with `_2`, `_3`, … suffixes and **flag both** in the conversion report so the user can give them meaningful names.

Once a source identifier has been sanitized, build a `source_id → safe_name` lookup and use it everywhere — in field references inside expressions, in choice-filter expressions, in repeat-count references, in `pulldata()` calls if any.

### Choice-list deduplication

Many surveys repeat the same set of choices across many questions (Yes/No, Likert 1–5, frequency scales). The source platform may store these inline per question — emitting them naively produces one `list_name` per question and a bloated `choices` worksheet.

Deduplicate by **exact string match** on the choice values and labels (in order):

- Same number of choices.
- Same `value` strings in the same order.
- Same `label` strings in the same order (in every language present).

If all three match, share a `list_name`. If any differ — even by case (`"Strongly Agree"` vs `"Strongly agree"`) or whitespace — don't dedupe; the difference may be intentional. Flag near-misses in the report so the user can decide.

Pick `list_name` slugs by question context (`yesno`, `likert_5pt`, `freq_weekly`, `region_codes`) rather than by source identifier. The template already ships with a `yesno` list — reuse it for any source list that matches it exactly.

### "Other, please specify" pattern

Most platforms support a choice that opens a free-text follow-up ("Other, please specify"). The SurveyCTO pattern:

- The parent `select_one` or `select_multiple` stays unchanged, with `other` (or a similar value) as one of the choices.
- A **sibling** `text` field follows immediately after, with `relevance = selected(${parent_name}, 'other')` (for both single- and multi-select; `selected()` works for both and is safer).
- The sibling's `name` is `<parent_name>_other` (or `<parent_name>_text` if the source uses `_text` consistently — match the source convention if reasonable).
- The sibling's `label` carries the source's "please specify" prompt (or a default like "Please specify").

### HTML and Markdown in labels

Source platforms with rich-text editors (Qualtrics, REDCap, some Kobo/ODK forms) embed HTML in labels: `<p>`, `<span style="…">`, `<br>`, `&nbsp;`, named entities. **SurveyCTO supports HTML in labels, notes, constraint messages, and required messages when the form is rendered in web, Android, and iOS clients** — the raw HTML you see in the form designer or the XLSForm file is what enumerators and respondents see formatted at collection time. Carry source HTML over largely intact.

The conversion rule:

- **Preserve HTML in labels, notes, and message text.** `<b>`, `<i>`, `<u>`, `<br>`, `<p>`, `<span>`, `<div>`, `<ul>/<ol>/<li>`, `<a href="…">`, inline `style` attributes, and `&nbsp;`/`&amp;`/`&lt;`/`&gt;`/`&quot;` entities all render in SurveyCTO clients. Don't strip them.
- **Strip JavaScript.** SurveyCTO does **not** execute JavaScript in labels. Remove `<script>…</script>` blocks entirely, and strip JS event-handler attributes (`onclick`, `onload`, `onerror`, `onmouseover`, and any other `on*=` attribute). Strip `javascript:` URIs from `href` attributes. If the source label had behavior that depended on the stripped JavaScript, flag it in the conversion report; the user may want a [field plug-in](field-plugins.md) instead.
- **Strip document-level wrappers.** `<html>`, `<head>`, `<body>` shouldn't appear inside a label cell; if they do, unwrap them and keep the inner content.
- **Hints are the exception**: per [`xlsform.md`](xlsform.md), the `hint` column does **not** render HTML. For hint cells, strip all tags down to plain text and replace named entities (`&nbsp;` → space, `&amp;` → `&`, etc.). Collapse whitespace.
- **Inline images** (`<img src="…">`) need attention. SurveyCTO renders inline images in two ways: (a) the `media:image` column (and an attached image file) shows an image alongside the label, and (b) an `<img>` tag with a same-form attachment filename in `src` can also work in some clients. A remote `src` URL won't be reliable offline. Prefer the `media:image` route — emit the label with the `<img>` stripped, add a `media:image` reference if you can resolve the filename, and flag in the report so the user attaches the image at upload time.
- **Markdown is not rendered.** If the source uses Markdown markers (`**bold**`, `_italic_`, `# heading`), translate to the SurveyCTO HTML equivalents (`<b>`, `<i>`, etc.) rather than preserving the Markdown markers — SurveyCTO will display them literally.

See [Label, Hint, And Message Formatting](xlsform.md#label-hint-and-message-formatting) for the canonical SurveyCTO-side rules.

### Multi-language carry-over

If the source has multiple languages:

- Identify the **default language** (the one corresponding to the source's primary or first-defined language). Set `default_language` in `settings` to that language name.
- Put the default language's labels/hints/messages in the **unsuffixed** column (`label`, `hint`, `constraint message`, `required message`).
- Put every other language's content in suffixed columns (`label:Spanish`, `hint:Spanish`, etc.). Use the language *name* as it should appear in SurveyCTO, not the source's locale code.

This is one of the most commonly broken patterns in XLSForms — see the gotcha in [`xlsform.md`](xlsform.md). Putting the default language only in a suffixed column and leaving the base empty silently breaks the form.

### Required, constraint, and length validation

Most platforms have direct equivalents of `required` and basic numeric/length constraints. Translate them per the platform reference; the SurveyCTO column targets are:

- `required = yes` for required fields. (Add `required message` if the source has a per-field required message.)
- `constraint` for the expression (use `.` to refer to the field's own proposed value).
- `constraint message` for the user-facing failure message.

Numeric range → `. >= MIN and . <= MAX`. Length → `string-length(.) >= MIN and string-length(.) <= MAX`. Combine multiple checks with `and`.

For free-text validators that look like regular expressions, translate to `regex(., '<pattern>')` — but verify the pattern in the source platform's regex flavor matches SurveyCTO's (ODK-flavored, broadly XPath 1.0). Flag any pattern that uses lookaheads, named groups, or other features outside basic regex; ask the user.

### Expression rewrites

Almost every source expression needs at least one rewrite for SurveyCTO. The universal ones:

| Replace | With | Where it appears |
| --- | --- | --- |
| `==` | `=` | Equality comparisons anywhere |
| `position()` | `index()` | Repeat-instance number |
| `jr:choice-name(…)` | `choice-label(…)` | Label lookups |
| `/data/<field>` or `/<root>/<field>` | `${<field>}` | XPath-style field references (XForms-based platforms) |
| `relevant` (column) | `relevance` (column) | Column rename for XLSForm-based sources |
| `selected-at(…)`, `count-selected(…)` | (same names — confirm in [`expressions.md`](expressions.md)) | Multi-select helpers |
| `if(/data/x, …)` with implicit empty checks | `if(string-length(${x}) > 0, …)` | Implicit "truthiness" rewrites |
| `coalesce(a, b)` | `coalesce(a, b)` | Same in SurveyCTO; just confirm |

The platform-specific reference will add its own rewrites for platform idioms (Qualtrics' `q://QID5/SelectableChoice/3` references; CommCare's case-property paths; etc.).

Always verify rewritten expressions against [`expressions.md`](expressions.md). When in doubt, run a quick `kb_search` to confirm a function name and signature before emitting it.

### Form metadata

Set via `change_setting`:

- **`form_id`** — slugified from the source's identifier or title. Lowercase, underscores, alphanumeric-only. Confirm with the user; the form ID can't easily change after deployment.
- **`form_title`** — the source's title, raw (no slugification).
- **`default_language`** — see above.

Don't touch the `version` cell; the template's formula handles it and `export_xlsform` recalculates it.

## Things that rarely translate cleanly

Every source platform has features that don't have a clean SurveyCTO equivalent. The universal handling rule: **flag every one in the conversion report**, with location and a one-line description of what the user must add by hand or replace with native SurveyCTO features. Never silently approximate something the user might be relying on.

Common cross-platform examples:

- **Server-side scripting / JavaScript per question** (Qualtrics `QuestionJS`, custom validators). Drop and flag. Point the user at [`field-plugins.md`](field-plugins.md) for SurveyCTO's equivalent capability.
- **Dynamic piped text** referencing prior questions, random values, or server-context variables. Static-question references translate to `${field}` substitutions; random and server-context pipes do not.
- **Randomization** at question, choice, or block level. SurveyCTO has `appearance=randomized` for choices and group-level randomization patterns; map where possible and flag.
- **Quotas.** No XLSForm equivalent. Flag.
- **End-of-survey customization** (custom messages, redirects, conditional termination). Implement as best-effort `relevance` on remaining groups; flag complex cases.
- **Survey themes, fonts, logos, custom CSS.** SurveyCTO uses its own theming. Drop silently; the report acknowledges this is intentional, not a bug.
- **Real-time validation that XLSForm validates only on submit** (running totals, live regex feedback). Constraints fire at field exit / form submit; running-total UIs are not native. Best-effort with `calculate` rows and end-of-group constraints; flag.
- **Source-platform integrations** (panel services, external dashboards, in-platform analytics). Out of scope; flag.

## The conversion report

Always produced, always Markdown, always with the three sections below. The structure is stable across platforms and across reruns of the same source, so users can diff reports as their source forms evolve.

Save the report as `<form_id>_conversion_report.md` next to the output `.xlsx`. In chat, give the user a short summary and a link/path to the file.

### Section 1 — Summary

One paragraph plus a small stats table. Includes:

- Input filename, source platform, output filename.
- Source survey title and identifier.
- Total counts: questions in source, questions converted, questions converted with warnings, questions dropped.
- Logic counts: branches / display-logic rules / skip-logic rules / embedded-variable references — how many of each were translated vs. flagged.
- Languages carried over.
- A one-sentence overall fidelity statement (e.g., "Conversion is high-fidelity; the main items needing human attention are two custom validators and one constant-sum question.").

### Section 2 — Per-question warnings

One subsection per affected question, headed by the SurveyCTO `name` and the question label excerpt. Each warning has:

- The original source feature (with the source identifier so the user can find it in the source platform).
- What the converter did instead in SurveyCTO.
- A one-line instruction for the user — what to add, where, and a pointer to the relevant skill reference (`expressions.md`, `xlsform.md`, `field-plugins.md`, etc.).

Skip questions that converted cleanly; this section is only for warnings.

### Section 3 — Survey-level issues

Items that aren't pinned to a single question: untranslated flow elements, unresolved cross-references in logic, embedded/global variables referenced but never initialized, theme/CSS dropped, end-of-survey customization, quotas, randomization rules, integration dependencies. Each item with source location (block / flow / module / page) and remediation guidance.

End with a final subsection listing **clarifying questions you asked the user during conversion and the user's answer**, so the report stands alone as a record of the decisions made.

## Conversion-specific validation checklist

Run this in addition to the standard XLSForm validation checklist in [`SKILL.md`](../SKILL.md#validation-checklist):

- [ ] Every dropped or approximated source feature appears in the conversion report with a location.
- [ ] Every emitted expression uses SurveyCTO conventions (`=` not `==`, `index()` not `position()`, `choice-label()` not `jr:choice-name()`, `selected()` for multi-select, `relevance` column not `relevant`).
- [ ] Every sanitized field name matches the same name everywhere it's referenced (in `${field}` substitutions, choice filters, repeat-count expressions, `pulldata()` calls, the source-id-to-safe-name lookup table is consistent).
- [ ] Every `selected()`, `=` or other comparison against a choice uses a `value` that actually exists in the referenced `list_name`.
- [ ] Unused user-facing starter content and unused example choice lists were removed or explicitly justified in the report — especially the template `yesno` choice list when the source uses a different yes/no list. Standard metadata / audit rows may remain by default; the `caseid` row should be kept, removed, or reported based on whether case management is in scope.
- [ ] Multi-language forms have the default language in the unsuffixed column and additional languages in suffixed columns (not vice versa).
- [ ] `form_id` and `form_title` reflect the source survey (or the user's preferred names) and were set via `change_setting`, not by writing into the `settings` worksheet directly.
- [ ] HTML in labels, notes, and message text is carried over (SurveyCTO renders HTML in those at collection time); `<script>` blocks, `on*=` event handlers, and `javascript:` URIs have been stripped; Markdown markers in the source have been translated to HTML equivalents.
- [ ] Hint cells contain plain text only (SurveyCTO does not render HTML in hints).
- [ ] Inline images in source labels are either resolved to `media:image` attachments or flagged in the report as media-attachment TODOs.
- [ ] The conversion report is saved alongside the output `.xlsx` and was linked in the chat hand-off summary.
- [ ] The user has been reminded that the output is a starting draft, not a finished form.

## When to ask the user

Cross-platform conversion has more "could go two ways" decisions than typical XLSForm authoring. The agent should ask the user when:

- The source has a feature with multiple defensible SurveyCTO mappings, and the right choice depends on the user's intent (custom validators, constant-sum quantization, end-of-survey routing, "Other, please specify" naming, choice-list deduplication near-misses).
- A source field's identifier is ambiguous, a collision under sanitization, or otherwise needs a meaningful name in SurveyCTO.
- A required setting (`form_id`, `form_title`, `default_language`) has multiple reasonable values.
- A feature is lossy enough that the user might prefer to handle it manually rather than have the converter emit a best-effort approximation.

Ask one or two questions at a time, not a long batch — the agent should make progress between questions and ask only when truly blocked. Record every question-and-answer pair in the conversion report's Section 3 footer.

## Where to go next

After reading this primer:

1. Load the platform-specific reference if one exists.
2. Read [`xlsform.md`](xlsform.md), [`expressions.md`](expressions.md), and [`mcp.md`](mcp.md) (all mandatory for any non-trivial conversion).
3. If multi-language, read [`translation.md`](translation.md).
4. If the source platform has a SurveyCTO-side feature you're unsure about (case management, datasets, `pulldata()`, search, field plug-ins), use `kb_search` on the live docs before emitting a mapping you're not certain about.
