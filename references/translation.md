<!-- PRIMER: translation
  STATUS: drafted 2026-05-16 -->

# Translating XLSForm labels

This primer covers **adding, updating, and verifying translations of XLSForm labels** — the natural-language content shown to enumerators and respondents during data collection. It assumes you have already read [`xlsform.md`](xlsform.md) for the column conventions and [`mcp.md`](mcp.md) for the tool mechanics (including language rename, column add/delete, and `default_language` changes — the MCP tools fully cover the mechanics, so this primer focuses on the *translation* itself).

Canonical SurveyCTO doc: [Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html).

## When to use this primer

Read this when the user wants to:

- **Add** a new language to an existing form (or build a multi-language form from a single-language draft).
- **Update** translations after the source language has changed — incremental re-translation of just the rows that moved.
- **Verify** existing translations (often produced by someone else) for structural integrity, terminology consistency, and likely quality issues.

Out of scope for this primer:

- Translating data in *submissions* (response text, enumerator comments). That involves much larger volumes, sensitive respondent content, and an external translation API; it is a separate workflow.
- Translating server dataset XML files, Data Explorer workbooks, or field plug-in UI strings — handled (when needed) in their own primers.
- Generating translated audio/image media. The agent cannot produce these; the user provides them.

## Translate using your own capabilities, not an external API

For form labels, the agent should translate directly. Form labels are:

- **Low-volume.** A typical XLSForm has 50–500 labels; the whole form fits in your context.
- **Non-sensitive.** No PII, no respondent data, no third-party data transfer concerns.
- **Quality-sensitive in ways that benefit from contextual reasoning** — terminology consistency, register, idiomatic phrasing, cultural adaptation. A per-cell translation API cannot see the whole form at once.
- **Free of credential setup.** No reason to push users into a Google Cloud Console workflow they shouldn't need.

This is different from translating *response data*, where volume can be large, content can be sensitive, and per-cell determinism is an asset. Don't confuse the two.

## What gets translated, and what doesn't

### Translate

In the `survey` worksheet:

- `label` and any existing `label:Lang` columns
- `hint` and `hint:Lang`
- `constraint message` and `constraint message:Lang`
- `required message` and `required message:Lang`
- Group and repeat `label` cells (these appear as section headers)

In the `choices` worksheet:

- `label` and `label:Lang` for each choice

In `settings`:

- `form_title` only if the user wants the title localized (often yes). Some teams keep `form_title` in the working language for ops reasons — ask if unsure.

### Preserve verbatim — never translate

A confident-looking translation that quietly mangles one of these will break the form silently.

- **Field references**: `${field_name}` and the field names inside. Translate the surrounding sentence; leave the token untouched.
- **Expression syntax in any cell that contains an expression**: `if(...)`, `selected(...)`, `choice-label(...)`, `pulldata(...)`, `indexed-repeat(...)`, `date(...)`, `concat(...)`, `regex(...)`, comparison and arithmetic operators, `and`/`or`/`not()`. Most cells you translate won't contain these, but labels and messages occasionally embed `${field}` substitutions or escaped quoting that you must preserve.
- **Markdown/inline HTML** that appears in a label: `<b>`, `<i>`, `<u>`, `<br>`, `**bold**` (rendered as literal by SurveyCTO, but if the source used it, preserve the markers). Translate the text *inside* the tags.
- **Choice `value` cells** and `list_name` cells in `choices`. These are stored codes, not display text. Same rule for field/group `name` cells in `survey`.
- **`form_id`** in settings. Identifier, not display text.
- **Appearance keywords** (`minimal`, `quick`, `field-list`, `search(...)`, `custom-<name>`, etc.) and any cell where they appear.
- **Numeric literals, dates, currency codes, units written as literals** (`"USD"`, `"kg"`, `"2024-01-01"`). Translate the natural-language surroundings, not the literal.
- **Trailing whitespace and explicit line breaks** in source cells — sometimes load-bearing for display.

When in doubt, leave the token alone and translate around it.

## Translation principles

Survey translation is its own discipline. The dominant modern frameworks — [TRAPD](https://pmc.ncbi.nlm.nih.gov/articles/PMC10309006/) (Translation, Review, Adjudication, Pretesting, Documentation), the [Cross-Cultural Survey Guidelines](https://ccsg.isr.umich.edu/chapters/translation/overview/), and the [World Bank DIME guidance](https://dimewiki.worldbank.org/Questionnaire_Translation) — converge on the principles below. Apply them as a working translator, not a transliteration engine.

- **Functional equivalence over literal accuracy.** Preserve what the question *asks* and what it *would mean to a respondent*, not the surface form. A literally-correct translation that no native speaker would ever write is a worse translation.
- **Cross-label context matters.** Labels reference one another ("the food groups listed above"). Read the whole form before translating any of it, and translate with the full instrument visible so cross-references stay coherent.
- **Terminology consistency.** Build and *write down* a glossary as you go (see *Glossary handling* below). Reuse your chosen term for each recurring domain concept (household, member, respondent, enumerator, head, plot, consumption, etc.) throughout the form.
- **Register and voice consistency.** If the source uses formal "you" (Spanish *usted*, French *vous*, Hindi *आप*), keep that throughout. If the source mixes respondent-directed phrasing ("How old are you?") and enumerator-directed phrasing ("Ask the respondent's age"), mirror the same split — don't collapse them.
- **Idiomatic targets.** The output should read like text a competent native speaker would have written from scratch. Stilted "translation-ese" is a quality failure even when individual words are correct.
- **Cultural adaptation flags.** Some questions or choices don't map cleanly across cultures (relationship categories, household structures, food groups, currencies, units, common occupations). When you spot one, surface it to the user rather than silently approximating. Note it in the glossary file.
- **CAPI considerations.** If the form is administered orally (CAPI), enumerators read the label aloud. Favor speakable, natural-cadence phrasings; long parenthetical clauses that read fine on paper sound awkward when spoken.

## Glossary handling

Maintain a per-form glossary of domain terms and their chosen target-language renderings. The glossary serves three purposes: in-pass consistency, future verify/update passes, and reviewer transparency.

Write the glossary to a **Markdown file alongside the XLSForm** — for example, `<form_id>-translations-glossary.md` next to the workbook. The user keeps it with their form and can hand it back to you (or another agent) in a future session to anchor follow-up translation work. Do not try to keep the glossary inside the workbook itself: the XLSForm tools operate only on the `survey`, `choices`, and `settings` worksheets, and juggling local edits to an extra worksheet against MCP-driven edits to the main sheets is more trouble than it's worth.

A minimal structure:

```markdown
# Translations glossary — <form_id>

Source language: English
Target language: Spanish

| Source term | Spanish | Notes |
| --- | --- | --- |
| household | hogar | "hogar" not "casa" — economic unit, not dwelling |
| head of household | jefe/jefa del hogar | gendered; match respondent |
| plot | parcela | agricultural; "lote" if user prefers |
```

Build the glossary as you go. When you encounter a recurring term you've already handled, look up your prior choice rather than re-deciding. On update/verify passes, ask the user for the glossary file if you don't already have it — it is the authoritative reference for what *should* be used. If no glossary exists yet, offer to write one as part of the current pass.

When you hand the form back, hand the glossary file back at the same time, and remind the user to keep them together.

## Workflow: add a new language

1. **Inventory current languages.** Read the `form_summary` and the `survey` and `choices` worksheets. Note which `label:Lang` columns already exist, and which is the default language (the content in the unsuffixed `label` column; the `default_language` setting names it).
2. **Confirm with the user** if not already specified:
   - Source language to translate *from* (default to the form's default language if obvious).
   - Target language to add.
   - Exact column-header suffix to use (`label:Spanish` vs. `label:Español` vs. `label:es` — SurveyCTO accepts any string; consistency with the user's other forms is what matters).
3. **Read all source content in one pass.** Pull every `label`, `hint`, `constraint message`, `required message` from `survey` (plus `form_title` if translating), and every `label` from `choices`. Hold them in context together. This is what makes cross-label terminology consistency possible.
4. **Translate, building the glossary as you go.** Apply the translation principles above. For each label, take a moment to consider register, idiomatic phrasing, and any cultural-adaptation flags before committing.
5. **Self-review pass (recommended; do this routinely).** After the first-pass translation is complete, re-read your translations alongside the source with explicit attention to:
   - Register and voice consistency across the whole form
   - Glossary adherence — same source term → same target term every time
   - Idiomatic phrasing — anywhere it reads like a translation rather than original native text
   - Items you flagged as ambiguous on the first pass
   This second pass costs little and meaningfully improves quality. It is the agent's analog of the TRAPD "Review" stage.
6. **Back-translation spot check (routine; sample 5–10% of labels, plus anything you flagged).** Translate a sample of your target-language labels back to the source language *without looking at the original source*, then compare. Surface any meaningful discrepancies to the user — they're often the most revealing quality signal you can give. For very small forms (<50 labels) you can back-translate everything; for large forms, prioritize complex labels, constraint/required messages, and any item you weren't fully confident about.
7. **Apply translations via the MCP tools.** Batch all related edits into one `xls_apply_patches` call. Add the new `label:Lang` column to `survey` and `choices`; add `hint:Lang`, `constraint message:Lang`, `required message:Lang` columns only where the corresponding base columns have content. Leave the new cell blank when the source cell is blank — don't fabricate text. Write the glossary Markdown file to disk alongside the workbook at the same time. See [`mcp.md`](mcp.md) for the relevant ops and language/column handling.
8. **Run the verification checklist** (below).
9. **Export and hand back**, with the hand-off notes described in *Hand-off to the user*.

## Workflow: update translations after source changes

When the user has edited labels in the source language and wants the translation refreshed:

1. **Identify what changed.** Read the form and find rows where either (a) the source-language column has content but the target-language column is empty, or (b) the user has flagged specific rows as updated. If you can't tell from the file alone which rows were edited, ask the user.
2. **Ask before re-translating already-translated rows.** The user may have manually edited some target-language cells; do not silently overwrite them. By default, translate only rows that are clearly new or that the user has explicitly asked you to revisit.
3. **Use the existing target-language content as a glossary anchor.** Before translating new rows, read the existing translations and ask the user for the glossary Markdown file if you don't already have it. Match the established terminology. If you encounter a term whose existing translations are *inconsistent*, surface that to the user rather than picking one silently.
4. **Translate the changed/new rows only**, applying the same principles as the add workflow.
5. **Self-review pass and a smaller back-translation spot check** focused on the changed rows.
6. **Apply via `xls_apply_patches`, run the checklist, export, hand back.**

## Workflow: verify existing translations

When the user has translations (their own, a colleague's, or a contractor's) and wants the agent to check them. **By default, verify means verify** — produce a report, don't edit. Only auto-fix if the user explicitly opts in.

Check for:

- **Structural integrity:**
  - Every `label:Lang` cell has a corresponding non-empty `label` (or vice versa, if the language has content but the source doesn't — likely a row deletion drift).
  - Counts of populated cells match across languages within each column (`label`, `hint`, `constraint message`, `required message`).
  - No `${...}` references altered, dropped, or wrapped in translated punctuation.
  - No choice `value` or field `name` cells modified.
  - Default language content lives in the *unsuffixed* base columns, not in a suffixed `:DefaultLanguage` column. This is the single most common structural mistake.
  - If any field has language-specific media variants (`media:image:Lang` etc.), all languages with `label:Lang` content have matching media coverage where the user expects it.
- **Terminology consistency:**
  - Recurring source terms map to a consistent target term throughout. Surface every term where you see inconsistent renderings.
  - If the user has a glossary file, check translations against it; if they don't, offer to produce one from the form's actual usage.
- **Likely quality issues** (heuristic — flag, don't "fix"):
  - Register/voice drift mid-form.
  - Labels that look like literal word-for-word translations with awkward target-language grammar.
  - Messages that have been over-translated (translating placeholder text that should have stayed verbatim) or under-translated (left in the source language entirely).
  - Choice labels that don't match the form's question phrasing (e.g., choice labels in formal register while questions are informal).
- **Optional back-translation spot check** on a sample of the existing translations, with results shown to the user.

Return a structured report: structural issues first (with row numbers), then terminology issues (with the conflicting renderings), then quality flags. If the user then asks for fixes, switch into edit mode and apply them via `xls_apply_patches`.

## Very large forms

Most XLSForms fit comfortably in context. For instruments with hundreds of consumption-module items or several thousand choice labels, chunk in this order so the glossary carries forward:

1. **Settings and survey labels** first (just the `label` column on `survey`, plus `form_title` if translating it). Build the glossary as you go.
2. **Hints and messages** on `survey` (`hint`, `constraint message`, `required message`), referencing the glossary from step 1.
3. **Choice labels** in `choices`, referencing the same glossary.

Write the glossary Markdown file as you finish each chunk so each subsequent chunk has a stable reference. If you're about to translate a term you've already handled, look it up rather than re-deciding.

## Verification checklist

Run before exporting:

- [ ] Source and target columns have matching counts of populated cells, per column (`label`, `hint`, `constraint message`, `required message`) on `survey`, and `label` on `choices`.
- [ ] All `${...}` references in translated cells point to fields that exist and are spelled exactly as in the source.
- [ ] No choice `value` or field/group `name` cells were modified.
- [ ] Default-language content is in the **unsuffixed** base columns; the new language is in `:Lang`-suffixed columns. No `:English` (or other default-language) suffix has been introduced.
- [ ] Markdown/HTML tags in source cells are present and unchanged in target cells.
- [ ] Trailing whitespace and explicit line breaks in source cells are preserved where they look intentional.
- [ ] Glossary terms used consistently across all translated cells.
- [ ] No source-language fragments left untranslated inside target cells (unless deliberately preserved, e.g., proper nouns).
- [ ] For any field with language-specific media variants (`media:image:Lang`, `media:audio:Lang`, `media:video:Lang`) in another language, the user has been told that the new language would need its own media files.
- [ ] `form_id` unchanged.

## Hand-off to the user

When you hand back the translated workbook, tell the user — directly and concisely:

1. **What you did.** Languages added or updated, rows touched, glossary Markdown file written (and where) — remind the user to keep it alongside the workbook.
2. **Glossary highlights.** Name the 5–10 most important domain-term choices you made, so the user can correct any they'd render differently.
3. **Back-translation findings** (if you ran the spot check). Any discrepancies, with the user's original source for comparison.
4. **Cultural-adaptation flags** you raised, with row numbers.
5. **Media reminder.** If any language has language-specific media variants, the new language probably needs its own media files; the user will have to provide them.
6. **Native-speaker review recommendation.** Survey translation literature is consistent that a single translator — human or model — is not the ideal final pipeline. Before fielding the form in production, a native speaker of the target language with domain knowledge should review the translations, and enumerator training should include explicit translation pretesting. This is a clear recommendation, not a gate: the user is a professional and decides what's appropriate for their context.

## Further reading

- [SurveyCTO — Form languages](https://docs.surveycto.com/02-designing-forms/02-additional-topics/07.translating.html)
- [World Bank DIME Wiki — Questionnaire Translation](https://dimewiki.worldbank.org/Questionnaire_Translation)
- [Cross-Cultural Survey Guidelines — Translation](https://ccsg.isr.umich.edu/chapters/translation/overview/)
- [TRAPD: Translation, Review, Adjudication, Pretesting, Documentation](https://pmc.ncbi.nlm.nih.gov/articles/PMC10309006/)
- [Pew Research Center — How we translate survey questions](https://www.pewresearch.org/decoded/2022/04/22/how-we-translate-survey-questions-to-be-fielded-around-the-world/)
