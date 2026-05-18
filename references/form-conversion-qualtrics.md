<!-- PRIMER: form-conversion-qualtrics
  STATUS: drafted 2026-05-16 -->

# Converting a Qualtrics `.qsf` export into a SurveyCTO XLSForm

> **Read [`form-conversion.md`](form-conversion.md) first.** It defines the overall workflow (confirming expectations with the user, reading SurveyCTO-side references, applying edits via MCP, producing the conversion report, the validation checklist, and the universal mapping concerns: field-name sanitization, choice-list deduplication, "Other, please specify", HTML/Markdown handling, multi-language carry-over, expression rewrites, form metadata). This file only adds the Qualtrics-specific details that sit on top of that workflow.

Qualtrics is a different shape from SurveyCTO in almost every dimension: a proprietary JSON file format, a different question-type model, a separate "survey flow" layer for routing, embedded data variables, piped text, and JavaScript per question. Many features have no clean XLSForm equivalent and must be flagged in the conversion report rather than silently approximated. The goal here is a deterministic, auditable mapping for the well-defined subset of Qualtrics that does translate, plus a clear list of everything the user must verify or rebuild by hand.

## The `.qsf` file format

A `.qsf` is a JSON file. Load it with the standard library:

```python
import json
from pathlib import Path

qsf = json.loads(Path(qsf_path).read_text(encoding="utf-8"))
```

The top level has two keys:

- **`SurveyEntry`** — survey metadata (`SurveyName`, `SurveyID`, `SurveyOwnerID`, `SurveyLanguage`, `SurveyStartDate`, `SurveyExpirationDate`, `SurveyCreationDate`, `LastModified`, `SurveyStatus`, etc.). Used for `form_title`, `default_language`, and a few report fields.
- **`SurveyElements`** — a heterogeneous array of typed elements. Each item has `Element` (the type tag), `PrimaryAttribute`, `SecondaryAttribute`, `TertiaryAttribute`, and `Payload`.

The `Element` types you'll encounter:

| `Element` | What it is | What to do with it |
| --- | --- | --- |
| `BL` | Survey Blocks (appears once) | Block → question-export-tag list, ordering, page-break positions. Use to derive `begin group` / `end group` structure. |
| `FL` | Survey Flow (appears once) | Block ordering, branch elements, embedded-data declarations, end-of-survey elements. Drives the order of groups in the output and any cross-block `relevance` expressions. |
| `SO` | Survey Options (appears once) | Back-button, progress-bar, mobile-friendliness; mostly informational, log into the conversion report. |
| `RS` | Response Set | Ignored. |
| `PL` | Project Logic | Ignored (rarely populated). |
| `QC` | Question Count | Use as a sanity-check against your `SQ` count. |
| `SCO` | Scoring | Log into the report; not translated. |
| `STAT` | Statistics | Ignored. |
| `SQ` | Survey Question | **The main payload — one per question.** Most of the conversion work is here. |
| `Notes` | Author notes | Log into the conversion report, not the form. |

### The `SQ` (question) payload

Each `SQ` element has a `PrimaryAttribute` like `"QID5"` and a `Payload` with the fields you actually care about:

| Field | Meaning |
| --- | --- |
| `QuestionText` | The prompt shown to respondents. Stored as raw HTML from Qualtrics' rich-text editor. |
| `DataExportTag` | The export column name the researcher actually wants (e.g., `age`, `hh_size`). **This is the right source for the SurveyCTO `name` cell, not `QID`.** Qualtrics may show `QID` in display logic, but `DataExportTag` is the stable, user-visible variable name. |
| `QuestionType` | The question family: `MC`, `TE`, `Matrix`, `Slider`, `RO`, `DB`, `DD`, `SBS`, `CS`, `NPS`, `TB`, `Meta`, `Captcha`, `FileUpload`, `Draw`, `HotSpot`, `HeatMap`, `GraphicSlider`. |
| `Selector` | Visual sub-variant within a `QuestionType` (e.g., `SAVR`, `MAVR`, `DL`, `SB` for `MC`; `Likert`, `Bipolar` for `Matrix`; `HSLIDER`, `STAR` for `Slider`). |
| `SubSelector` | Further refinement, mainly for `Matrix` (`SingleAnswer`, `MultipleAnswer`, `TE`). |
| `Choices` | Choice options keyed by an internal integer ID. **Must be re-ordered via `ChoiceOrder` before iteration** — Python dicts preserve insertion order, which would otherwise scramble the displayed order. |
| `ChoiceOrder` | The integer IDs in display order. |
| `RecodeValues` | Numeric/short label codes typed in the Recode Values dialog. |
| `ChoiceDataExportTags` | Full alphanumeric tags for choices. **When both `RecodeValues` and `ChoiceDataExportTags` are present, `ChoiceDataExportTags` wins** — it's what the researcher actually wants as the stored value. |
| `Answers` | For `Matrix` questions: the column-axis choices (the shared scale). `Choices` holds the row-axis (each row becomes its own SurveyCTO field). |
| `Validation` | `Settings` sub-object describing `ForceResponse`, numeric ranges, custom validators, etc. See *Validation* below. |
| `DisplayLogic` | A tree of conditions describing when this question is shown. See *Display logic* below. |
| `Configuration` | Question-type-specific settings (slider min/max, decimal count, allowed file extensions, etc.). |
| `Language` | Multi-language payload — a dict of language code → translated `QuestionText` / `Choices` / etc. See *Multi-language* below. |
| `QuestionJS` | Per-question JavaScript hook. **Always dropped, always flagged** — SurveyCTO has no equivalent (consider [field plug-ins](field-plugins.md) for similar capability). |

### Recommended pre-processing pass

Before emitting any SurveyCTO rows, walk the `.qsf` once to build:

1. **`qid_to_tag`** — a dict mapping `QID5` → `DataExportTag` for every `SQ` element. Display logic references questions by QID, but you want to emit `${data_export_tag}` references; this lookup is the bridge.
2. **`tag_to_safe_name`** — a dict mapping each `DataExportTag` to its sanitized XLSForm `name` (per the safe-name rule in [`form-conversion.md`](form-conversion.md#field-name-sanitization)). Flag any collisions.
3. **A flat list of question payloads in block-then-flow order**, with their resolved tags, sanitized names, normalized choices, and validation. This is what the question handlers iterate over.
4. **A list of choice-list candidates for deduplication** — every distinct set of choices (after `ChoiceOrder` reordering and `ChoiceDataExportTags`/`RecodeValues` resolution).
5. **The survey flow structure** — block order, branches, embedded-data declarations, end-of-survey elements, loop-and-merge blocks.

A single `.qsf` rarely exceeds a few hundred questions; doing this pre-pass eagerly in Python (rather than streaming) is fine and makes the rest of the conversion much cleaner.

## Question-type and selector mapping

This is the core of the conversion. Match on the tuple `(QuestionType, Selector, SubSelector)`; the platform-agnostic field-name and choice-list rules from `form-conversion.md` apply throughout.

| Qualtrics `QuestionType` | `Selector` (and `SubSelector` where relevant) | SurveyCTO target | Fidelity |
| --- | --- | --- | --- |
| `MC` | `SAVR`, `SACOL`, `SAHR` (single answer vertical/column/horizontal) | `select_one <list>` | Full |
| `MC` | `DL` (drop-down list) | `select_one <list>` with `appearance=minimal` | Full |
| `MC` | `SB` (select box, single answer) | `select_one <list>` with `appearance=minimal` | Full |
| `MC` | `MAVR`, `MACOL`, `MAHR` (multiple answer) | `select_multiple <list>` | Full |
| `MC` | `MSB` (multi-select box) | `select_multiple <list>` with `appearance=minimal` | Full |
| `TE` | `SL` (single line) | `text` | Full |
| `TE` | `ML` (multi-line) | `text` with `appearance=multiline` | Full |
| `TE` | `ESTB` (essay) | `text` with `appearance=multiline` | Full |
| `TE` | `FORM` (multi-field form) | One `text` field per form sub-field, inside a `begin group` | Full |
| `TE` | `PW` (password) | `text` — flag in report: SurveyCTO has no password masking | Lossy |
| `Matrix` | `Likert` / `SubSelector=SingleAnswer` | One `select_one <shared_list>` per row choice, inside a `begin group` with `appearance=field-list` | Full |
| `Matrix` | `Likert` / `SubSelector=MultipleAnswer` | One `select_multiple <shared_list>` per row choice, inside a `begin group` with `appearance=field-list` | Full |
| `Matrix` | `TE` (text entry per cell) | One `text` per row, inside a group | Full |
| `Matrix` | `Bipolar` | `select_one` per row with `appearance=likert` and a left/right hint encoding the bipolar labels | Partial — see [§ Bipolar matrix](#bipolar-matrix) |
| `Matrix` | `RO` (rank order in matrix), `CS` (constant sum in matrix) | Emit as a `note` placeholder + report warning; no native equivalent | Lossy |
| `Slider` | `HSLIDER`, `STAR`, `HBAR` | `integer` or `decimal` (depending on `Configuration.NumDecimals`) with `constraint = . >= MIN and . <= MAX` from `Configuration.CSSliderMin`/`Max` | Full |
| `Slider` | `MULTIPLE` (multiple sliders) | One `integer`/`decimal` per slider row, inside a group | Full |
| `RO` | `DND` (drag-and-drop rank), `Col` (column rank) | Emit a `note` with the choice list rendered as text + report warning; no native rank-order field type | Lossy |
| `DB` | (none) | `type=note`, `label = QuestionText` | Full |
| `DD` | (none, "drop-down list" as a standalone) | `select_one <list>` with `appearance=minimal` | Full |
| `SBS` | (side-by-side) | Recurse into `Payload.AdditionalQuestions` and emit each as a separate field inside a `begin group field-list` block | Full |
| `CS` | (constant sum) | Group of `integer` fields plus a `calculate` row enforcing the total via `constraint` on the calculate | Partial — see [§ Constant sum](#constant-sum) |
| `NPS` | (Net Promoter Score) | `integer` with `constraint = . >= 0 and . <= 10` | Full |
| `TB` | `Timing` / hidden | Skip; SurveyCTO has its own audit fields. Log to report. | Drop |
| `Meta` | (Meta info: browser, OS) | Skip; SurveyCTO collects these via its own metadata field types if needed. Log to report. | Drop |
| `Captcha` | (CAPTCHA) | Skip; not applicable to SurveyCTO Collect. | Drop |
| `FileUpload` | (file upload) | `file` field type, with `mediatype` from Qualtrics' allowed extensions list | Full |
| `Draw` | (signature/drawing) | `image` field with `appearance=signature` | Full |
| `HotSpot`, `HeatMap`, `GraphicSlider` | various | Emit a `note` + warning; no equivalent | Lossy |

For any `(QuestionType, Selector, SubSelector)` tuple not in this table, emit a `type=note` placeholder with the original `QuestionText` and flag in the report; do not guess.

### Sub-field naming for expanded questions

Several Qualtrics question types — **Matrix** (every variant), **Slider MULTIPLE**, **CS**, **SBS**, and **TE FORM** — expand one source question into multiple SurveyCTO fields inside a `begin group` / `end group` block. Each expanded field needs a unique XLSForm `name`. The source provides per-row / per-sub-field identifiers in its payload; the parent question's `DataExportTag` provides the prefix.

The convention:

```
<parent_safe_name>_<row_or_subfield_identifier>
```

Concretely:

| Source shape | Where to find the parent prefix | Where to find the row / sub-field suffix | Example |
| --- | --- | --- | --- |
| **Matrix** (any selector / sub-selector) | `Payload.DataExportTag` of the matrix question, sanitized | `Payload.ChoiceDataExportTags[<choice_id>]` for each row, with fallback to `RecodeValues[<choice_id>]`, with final fallback to `row<choice_id>` | matrix `satisfaction` with rows `quality`, `price`, `service` → fields `satisfaction_quality`, `satisfaction_price`, `satisfaction_service` |
| **Slider** (`MULTIPLE`) | `Payload.DataExportTag` | Same lookup as matrix rows | slider `rate` with sub-sliders `dim1`, `dim2` → `rate_dim1`, `rate_dim2` |
| **CS** (constant sum) | `Payload.DataExportTag` | Same | CS `budget` with parts `food`, `rent`, `other` → `budget_food`, `budget_rent`, `budget_other` (plus a `budget_total` `calculate` for the sum constraint) |
| **SBS** (side-by-side) | `Payload.DataExportTag` | The nested `AdditionalQuestions[i].DataExportTag` if present, otherwise `q<i>` | SBS `comparison` with two columns whose own export tags are `before` and `after` → `comparison_before`, `comparison_after` (each column may itself produce multiple fields if it's a matrix; nest naming consistently) |
| **TE FORM** (multi-field text) | `Payload.DataExportTag` | The `Choices[<id>].Display` slugified, with fallback to `field<id>` | TE FORM `address` with sub-fields "Street", "City", "Zip" → `address_street`, `address_city`, `address_zip` |

Apply the safe-name rule from [`form-conversion.md`](form-conversion.md#field-name-sanitization) to both the prefix and the suffix before joining. Sanitize the joined name once more in case the join itself produced something invalid (consecutive underscores, leading digit).

The parent group's own `name` is `<parent_safe_name>` — the same identifier as the prefix. This is fine: the group name and field names are different from XLSForm's perspective (groups and fields share the same namespace, but `satisfaction` as a group name doesn't collide with `satisfaction_quality` as a field name).

**Collision risk: cross-question.** If two Matrix questions happen to have the same `DataExportTag` (rare under Qualtrics' UI but possible after manual export-tag edits), the expanded fields will collide form-wide. The pre-processing pass already builds a `tag_to_safe_name` lookup that disambiguates parent collisions — apply that disambiguation **before** building expanded sub-field names, so the disambiguation cascades into every expansion.

**Cross-references.** Display logic and piped text that reference an expanded question (`q://QID5/SelectableChoice/1`) in Qualtrics refer to a specific matrix row's value. Resolve to the corresponding `${parent_safe_name_row}` field name. The display-logic operator table in [§ Display logic](#display-logic) gives the leaf operator mappings; combine with the sub-field naming convention above when the referenced QID is a matrix.

### Bipolar matrix

A bipolar matrix has, per row, a left-anchor label and a right-anchor label and a 5- or 7-point scale between them. SurveyCTO's `appearance=likert` renders a horizontal radio scale but does not natively support per-row endpoint labels. The mapping:

- Shared scale → the choice list (positions only).
- Each row's `hint` column → `<left> ↔ <right>` so the enumerator/respondent sees the anchors above the radio buttons.

Document as a known approximation in the report.

### Constant sum

Qualtrics' constant-sum question enforces in real time that the sum across N sub-fields equals a target (usually 100). SurveyCTO can't update a running total inside the field, but can enforce the constraint at the end of the group:

- Emit N `integer` fields (one per sub-field).
- Emit a `calculate` field summing them: `calculation = ${sub_1} + ${sub_2} + ... + ${sub_N}`.
- Put `constraint = . = 100` (or whichever target) on the calculate, with a clear `constraint message` explaining ("The values must sum to 100. They currently sum to ${total}.").

Enumerators won't see the running total during entry but the form blocks submission until the sum is right. Document the approximation in the report.

### "Other, please specify"

Choice-level "text entry" is the Qualtrics "Other, please specify" pattern. Detect by inspecting the choice's payload for a `TextEntry: "true"` flag. Apply the universal pattern from [`form-conversion.md`](form-conversion.md#other-please-specify-pattern): parent `select_*` keeps the choice (typically with `value=other`); emit a sibling `text` field with `relevance = selected(${parent}, 'other')` and `name = <parent_name>_other` (matching Qualtrics' `_TEXT` export convention if the user prefers).

## Validation

Map question-level `Validation.Settings` directly. This is the highest-fidelity part of the converter; implement it first after the basic question-type pass.

| Qualtrics `Validation.Settings` | SurveyCTO column | Notes |
| --- | --- | --- |
| `ForceResponse = "ON"` or `ForceResponseType = "ON"` | `required = yes` | Straightforward. Carry the source's force-response message into `required message` if present. |
| `Type = "ValidNumber"` with `ValidNumber.Min`/`Max` | `constraint = . >= MIN and . <= MAX` | If the source question was `TE` with numeric validation, change the SurveyCTO type to `integer` or `decimal` (based on whether decimals are allowed in `ValidNumber`). |
| `Type = "ValidEmail"` | `constraint = regex(., '^[^@\s]+@[^@\s]+\.[^@\s]+$')` | Pragmatic basic email check. Note in the report that SurveyCTO's regex flavor is XPath 1.0, not PCRE. |
| `Type = "ValidPhone"` | `appearance = numbers_phone` plus a generic length constraint like `string-length(.) >= 7 and string-length(.) <= 15` | Phone validation is locale-dependent; flag for the user to refine. |
| `MinChars` / `MaxChars` | `constraint = string-length(.) >= MIN and string-length(.) <= MAX` | Combine into a single AND. |
| `CustomValidation` (free-form) | Best-effort translate to `constraint`; if it contains JavaScript or piped text you can't resolve, emit as `comment` and flag | High failure rate — most surveys use this for cross-field rules. **Ask the user when ambiguous.** |

Carry the source's per-validation error messages into `constraint message` (and language-suffixed columns when multi-language). For combined constraints (e.g., numeric range + required), the `constraint message` describes the constraint failure; the `required message` describes the empty-response case.

## Display logic

A Qualtrics `DisplayLogic` block is a tree of conditions joined by `BooleanOperator` (`And`/`Or`), with each leaf having:

- **`LeftOperand`** — typically `q://QIDn/SelectableChoice/k` (a choice on a question), `q://QIDn/ChoiceTextEntryValue` (the text-entry value on a question), or `ed://<embedded_var>` (an embedded-data variable).
- **`Operator`** — `Selected`, `NotSelected`, `EqualTo`, `NotEqualTo`, `GreaterThan`, `LessThan`, `IsEmpty`, `IsNotEmpty`, `Contains`, `Matches`.
- **`RightOperand`** — a literal value or a piped reference.

Walk the tree and emit a SurveyCTO `relevance` expression. Leaf-level translations:

| Qualtrics operator | `LeftOperand` form | Emit |
| --- | --- | --- |
| `Selected` | `q://QIDn/SelectableChoice/k` | For `select_one`: `${tag} = '<recoded_value_for_k>'`. For `select_multiple`: `selected(${tag}, '<recoded_value_for_k>')`. |
| `NotSelected` | same | `not(selected(${tag}, '<recoded_value_for_k>'))` |
| `EqualTo` | `q://QIDn/ChoiceTextEntryValue` or numeric `SelectableChoice` | `${tag} = <value>` (single quotes for strings, no quotes for numerics) |
| `NotEqualTo` | same | `${tag} != <value>` |
| `GreaterThan` / `LessThan` | numeric question | `${tag} > <value>` / `${tag} < <value>` |
| `IsEmpty` / `IsNotEmpty` | any | `string-length(${tag}) = 0` / `string-length(${tag}) > 0` |
| `Contains` | text | `regex(${tag}, '<pattern>')` — escape regex metacharacters in the pattern |
| `Matches` | text | `regex(${tag}, '^<pattern>$')` |

The `BooleanOperator` joins map to lowercase `and` / `or`. Use parentheses to preserve nesting precedence; SurveyCTO follows XPath operator precedence, but explicit parens are safer and the conversion-report-friendly choice.

QID → `DataExportTag` resolution uses the `qid_to_tag` lookup from the pre-processing pass. If a referenced QID isn't in the lookup (deleted question, malformed `.qsf`), emit the raw expression with a `# UNRESOLVED QID` prefix in the `comment` column and flag in the report.

Display logic that references **embedded data** (`ed://...`) requires the embedded variable to have been initialized as a `calculate` row (see [Survey flow](#survey-flow) below). If the embedded variable is never initialized in the source flow, drop the leaf and flag — the user will need to decide whether to add a `calculate` with a default value or restructure the logic.

### Skip logic vs. display logic

Qualtrics distinguishes "skip logic" (jump to a later question/block from a specific question) from "display logic" (whether to show this question at all). XLSForm only has the equivalent of display logic — `relevance` is "show this if condition" not "jump to that on condition."

Normalize both into `relevance` expressions: a skip-logic rule "if Q5 = yes, skip to Q10" becomes `relevance = not(${q5} = 'yes')` on every question between Q5 and Q10. Document this transformation in the conversion report — the rewritten relevance expressions look different from the source skip-logic UI, and the user should know why.

## Survey flow

Qualtrics organizes a survey as an ordered list of **blocks** (`Element=BL`) with a separate **survey flow** (`Element=FL`) that determines the order in which blocks are presented and may contain branch elements, embedded-data declarations, end-of-survey elements, and loop-and-merge elements.

### Blocks → groups

Each Qualtrics block becomes an XLSForm `begin group` / `end group` pair with `appearance=field-list` (which renders the group as one screen, matching the Qualtrics default for blocks without page breaks). Block titles become the group `label`. Internal page breaks inside a block (a `PageBreak` entry in the block's `BlockElements` array) split the block into multiple sibling groups in the output, each with its own `field-list` appearance.

### Flow → relevance (with fidelity caveats)

Sequential flow (block A, then block B) is the default and needs no special handling — the groups appear in order.

**Branch elements** (`Type=Branch`) contain `BranchLogic` that references question or embedded-data values. These translate to a `relevance` expression on every block downstream of the branch that depends on the branch condition. The translation is mechanical only when the branch condition references questions (which we have export tags for); embedded-data references require synthesized `calculate` rows that initialize the embedded variables, which is only possible if the embedded data is set inside the flow via a literal value.

**Embedded-data initialization via the flow with literal values** (`Type=EmbeddedData` flow elements with a `Value` field) → emit top-of-form `calculate` rows. Everything else (URL-parameter-driven embedded data, JavaScript-driven embedded data, embedded data set by the platform integration layer) → drop and flag, with the affected branches emitted as best-effort `relevance` strings prefixed with `# TODO: verify this expression — depends on uninitialized embedded variable <name>` in a `comment` column.

### Loop & merge → repeat groups

Qualtrics' loop-and-merge (a flow element that re-runs a block N times, piping different values into each iteration) maps to a SurveyCTO repeat group:

- The looped block becomes a `begin repeat` / `end repeat` pair.
- Each pipe replacement `${lm://Field/1}` becomes `${field_name}` referencing the corresponding repeat-context field.
- **Static value lists** (the user typed values into the loop config): set `repeat_count` to the static count; emit a `calculate` row inside the repeat that returns the piped value indexed by `index()`.
- **Dynamic loops driven by prior responses** (where the iteration count comes from a multi-select count): set `repeat_count = count-selected(${prior_field})` and use `indexed-repeat()` or `index()` to pull the right value into each iteration.

Both patterns get documented in the conversion report so the user can verify the loop behavior matches their intent.

### End-of-survey elements → terminate-and-skip pattern

Qualtrics' end-of-survey flow elements (`Type=EndSurvey`) translate to an XLSForm pattern: a `calculate` row earlier in the form holding the end condition, and a downstream `relevance` on every remaining group that is the negation of all the end conditions seen so far. This gets unwieldy with more than one or two end-of-survey branches; **cap at three end-of-survey elements**, and beyond that emit a `note` field labeled "End of survey for this respondent — submit now" and flag in the report so the user can design a different termination pattern.

## Multi-language

Qualtrics stores translations in a `Language` payload field on each question — a dict of language code → translated `QuestionText`, `Choices`, etc. The conversion:

- Each language code in `SurveyEntry.AvailableLanguages` becomes a column suffix (`label:Spanish`, `hint:Spanish`, …). Use SurveyCTO-friendly language **names**, not the raw Qualtrics locale codes. Qualtrics commonly uses codes like `EN`, `ES-ES`, `FR`, `PT-BR`; map to `English`, `Spanish`, `French`, `Portuguese`, etc.
- `SurveyEntry.SurveyLanguage` (the default) goes in the **unsuffixed** column (`label`, `hint`, …). See the universal rule and gotcha in [`form-conversion.md`](form-conversion.md#multi-language-carry-over).
- Apply per-language translations to: `QuestionText` (→ `label:Lang`), choice `Display` values (→ choice-row `label:Lang`), validation messages (→ `constraint message:Lang`, `required message:Lang`).
- If only some questions have translations (rare but possible), leave the missing cells empty — SurveyCTO falls back to the default-language column.

If the user asked to carry over only one language, drop the others entirely and set `default_language` to that one language.

## HTML and Markdown in question text

`QuestionText` and choice `Display` values are stored as raw HTML from Qualtrics' rich-text editor (`<p>`, `<span style="…">`, `<br>`, named entities, etc.). Apply the universal rule from [`form-conversion.md`](form-conversion.md#html-and-markdown-in-labels): carry HTML over largely intact (SurveyCTO renders HTML in labels/notes/messages at collection time), strip JavaScript (`<script>` blocks, `on*=` event handlers, `javascript:` URIs), strip `<html>/<head>/<body>` document wrappers, and reduce hints to plain text.

Qualtrics surveys frequently use `<p>` for paragraphs and `<span style="font-weight: bold">` instead of `<b>`. Both render. If you want to normalize for cleaner XLSForm cells, convert `<span style="font-weight: bold">…</span>` to `<b>…</b>` and unwrap `<p>` (replacing closing `</p>` with `<br><br>`) — but this is cosmetic, not required.

**Inline images** (`<img src="…">`): Qualtrics often references images by URL into the Qualtrics media library. Those URLs won't resolve from a SurveyCTO form. Strip the `<img>` and flag in the conversion report; the user must download the image, attach it to the form, and add a `media:image` cell or an `<img src="filename.png">` with the attached filename.

## Things that don't translate, and how to handle them

Each of the following appears in the conversion report under a clear heading, with the question / block / flow location and a one-line description of what the user must add by hand or replace with native SurveyCTO features:

- **Per-question JavaScript** (`QuestionJS` payload). Always dropped, always flagged. Point the user at [`field-plugins.md`](field-plugins.md) — plug-ins are SurveyCTO's nearest equivalent for custom field UI / behavior.
- **Piped text** in question or choice text:
  - `${q://QIDn/...}` (reference to a prior question's value) → translate to `${data_export_tag}` substitution. The label rendering engine resolves this at runtime.
  - `${e://Field/<var>}` (reference to embedded data) → translate to `${var}` if the embedded variable has a `calculate` initializer; drop and flag otherwise.
  - `${lm://Field/n}` (loop-and-merge piped value) → translate per the loop-and-merge handling above.
  - `${rand://...}` (random pipe) → drop and flag. SurveyCTO has `random()` and `once(random())` patterns; the user may want to add an explicit `calculate` of `once(random())`.
  - `${date://...}` (server date/time pipe) → translate to `format-date-time(now(), '<format>')`. The format string usually needs a manual fix; flag.
- **Embedded data set by URL parameter or external trigger** (rather than a flow `EmbeddedData` element with a literal `Value`). No XLSForm equivalent — `calculate` rows aren't externally seeded. Flag every reference.
- **Randomization** at question, choice, or block level. SurveyCTO supports `appearance=randomized` for choices and group-level randomization patterns; map where possible, flag where not.
- **Quotas.** No XLSForm equivalent. Flag.
- **End-of-survey customization** (custom messages, redirects, "submit and show this URL"). The converter emits a final `note` with the default end-of-survey message; custom redirects are flagged but not implemented.
- **Survey themes, fonts, logos, custom CSS.** SurveyCTO uses its own theming; drop silently. The report acknowledges this is intentional, not a bug.
- **Scoring** (`SCO` element). Qualtrics' scoring engine has no XLSForm parallel. Log to the report with the scoring rules so the user can re-implement them as `calculate` rows if needed.
- **Survey Options** (`SO` element) — back-button enable/disable, progress bar style, mobile-friendliness toggles, anonymous-link settings. SurveyCTO has its own equivalents in `settings` and platform-level form configuration; flag and let the user configure on the SurveyCTO side.

## Qualtrics-specific gotchas

- **`DataExportTag` is the right name source, not `QID`.** Use the export tag (e.g., `age`, `hh_size`) as the source for the SurveyCTO `name` cell. `QID5` is an internal identifier you'll resolve through the `qid_to_tag` lookup whenever display logic references it.
- **`DataExportTag` collisions.** Qualtrics allows duplicate export tags across questions (rare but happens with copy-paste). XLSForm requires unique `name`s — disambiguate with `_2`, `_3` suffixes and flag both in the report so the user can rename them meaningfully.
- **Sub-field name collisions from expansion.** Matrix / Slider MULTIPLE / CS / SBS / TE FORM each expand one parent question into multiple SurveyCTO fields. Always name expanded fields as `<parent>_<row_or_subfield>` so they don't collide with each other (or with top-level fields that happen to share a row name). See [§ Sub-field naming for expanded questions](#sub-field-naming-for-expanded-questions). Apply parent-level disambiguation before building expanded names so the disambiguation cascades.
- **Recoded vs. choice-export-tag values.** When both `RecodeValues` and `ChoiceDataExportTags` are present in a `MC` payload, **`ChoiceDataExportTags` wins** — those are what the researcher actually wants as stored values. If only `RecodeValues` is present, use it. If neither is present, fall back to the internal integer IDs (and warn — these are unstable across re-exports).
- **Choice order.** `Payload.Choices` is keyed by internal integer ID. **Always re-order via `ChoiceOrder` before iteration.** Python dict insertion order otherwise scrambles the displayed order.
- **Matrix `Choices` vs `Answers`.** For `Matrix` questions, `Choices` is the row-axis (each row becomes its own SurveyCTO field) and `Answers` is the column-axis (the shared `select_one` choice list). They're not interchangeable.
- **Question vs. block titles.** The Qualtrics question's `Payload.QuestionText` is the prompt shown to respondents; `Payload.QuestionDescription` is an internal note in the Qualtrics editor and is **not** displayed to respondents. Don't conflate them.
- **`.qsf` version drift.** The `.qsf` format is undocumented by Qualtrics and changes without notice. Log `SurveyEntry.LastModified` and `SurveyEntry.SurveyCreationDate` into the conversion report. If a required field is missing from a payload, emit a clear error in the report rather than letting `KeyError` propagate — users get a useful failure instead of a stack trace when Qualtrics next changes the shape.
- **Inline images with Qualtrics media-library URLs** will not load from a SurveyCTO form. The image must be re-attached.
- **Locale codes.** Qualtrics uses codes like `EN`, `ES-ES`, `FR-CA`, `PT-BR`, `ZH-S`. Map to readable language names for SurveyCTO column suffixes.

## Worked example

A small Qualtrics question and its SurveyCTO equivalent.

**Source (`.qsf` excerpt):**

```json
{
  "Element": "SQ",
  "PrimaryAttribute": "QID5",
  "Payload": {
    "QuestionText": "<p>What is your <b>highest level</b> of education?</p>",
    "DataExportTag": "education",
    "QuestionType": "MC",
    "Selector": "SAVR",
    "Choices": {
      "1": {"Display": "Primary or less"},
      "2": {"Display": "Secondary"},
      "3": {"Display": "Tertiary"},
      "4": {"Display": "Other, please specify", "TextEntry": "true"}
    },
    "ChoiceOrder": [1, 2, 3, 4],
    "ChoiceDataExportTags": {
      "1": "primary",
      "2": "secondary",
      "3": "tertiary",
      "4": "other"
    },
    "Validation": {"Settings": {"ForceResponse": "ON"}}
  }
}
```

**Target (XLSForm rows):**

`survey` worksheet:

| type | name | label | required | relevance |
| --- | --- | --- | --- | --- |
| `select_one education` | `education` | `<p>What is your <b>highest level</b> of education?</p>` | `yes` | |
| `text` | `education_other` | `Please specify` | | `selected(${education}, 'other')` |

`choices` worksheet:

| list_name | value | label |
| --- | --- | --- |
| `education` | `primary` | `Primary or less` |
| `education` | `secondary` | `Secondary` |
| `education` | `tertiary` | `Tertiary` |
| `education` | `other` | `Other, please specify` |

(If the `education` choice list happens to match another question's list exactly, dedupe per [`form-conversion.md`](form-conversion.md#choice-list-deduplication). For Matrix / Slider MULTIPLE / CS / SBS / TE FORM questions, expansion-naming follows [§ Sub-field naming for expanded questions](#sub-field-naming-for-expanded-questions) — e.g., a matrix with `DataExportTag=satisfaction` and rows `quality`/`price`/`service` produces fields `satisfaction_quality`, `satisfaction_price`, `satisfaction_service` inside a `begin group` named `satisfaction`.)

## Attribution

The `.qsf` anatomy and several specific parsing subtleties (the `ChoiceOrder` requirement, the `RecodeValues` / `ChoiceDataExportTags` precedence, the "Other, please specify" → `_TEXT` sibling pattern) are well-known from the community-maintained [`qualtrics-utils`](https://github.com/mkbabb/qualtrics-utils) project (MIT-licensed), specifically `qualtrics_utils/codebook/generate.py`. The undocumented `.qsf` format is also described in the community gist [`ctesta01/qsf_explanation.md`](https://gist.github.com/ctesta01/d4255959dafd1c54a1c0). This primer reuses anatomy knowledge from those references — no code is copied.
