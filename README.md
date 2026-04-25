# SurveyCTO Agent Skill

An [Agent Skill](https://agentskills.io) that gives AI agents SurveyCTO domain expertise: designing, editing, and debugging [SurveyCTO](https://www.surveycto.com) forms (XLSForm `.xlsx` files), server datasets (XML definitions), and Data Explorer workbook definitions.

The skill is fully usable on its own. Pair it with the **SurveyCTO MCP server** for built-for-purpose XLSForm file operations and live knowledge-base search; without those tools the skill still imparts the expertise the agent needs, falling back to generic xlsx tooling, web fetches of the live docs, or conversational guidance.

## What's included

| File | Purpose |
| --- | --- |
| `SKILL.md` | Main skill — file types, conventions, available tooling, editing workflow, validation, debugging |
| `references/overview.md` | High-level orientation primer (read first) |
| `references/xlsform.md` | Full XLSForm worksheet, column, and field-type reference |
| `references/expressions.md` | SurveyCTO expression operators, functions, and conventions |
| `references/datasets-xml.md` | Server dataset XML definition reference |
| `references/data-explorer.md` | Data Explorer workbook definition reference |
| `assets/xlsform-template.xlsx` | XLSForm template with headers, formatting, and help worksheets |

The five primers in `references/` are the canonical bundled knowledge set. They are also vendored by the [SurveyCTO MCP server](#surveycto-mcp-server) and served via its `get_surveycto_primer` tool, so callers without the skill installed can still retrieve them.

## SurveyCTO MCP server

The skill recommends the **SurveyCTO MCP server** (public, no auth, Streamable HTTP) when it's available. It provides:

- **XLSForm file tools** — `start_xlsform_session`, `get_xlsform_summary`, `xls_get_rows`, `xls_get_row`, `xls_apply_patches`, `export_xlsform`, `end_xlsform_session`. SurveyCTO-aware parsing, atomic patches with conflict detection, formula recalculation on export, and formatting preservation.
- **Knowledge-base tools** — `kb_search` over indexed SurveyCTO docs/support content; `get_surveycto_primer` for these primers.
- **Discovery** — `get_surveycto_mcp_capabilities` for the canonical tool list, recommended workflows, concurrency contract, and primer topic inventory.

Endpoint: `https://assistant-be.surveycto.net/mcp`

stdio-only clients can wrap with `mcp-remote`:

```json
{
  "surveycto": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://assistant-be.surveycto.net/mcp"]
  }
}
```

The full integration reference (tool surface, recommended workflow, concurrency contract, error codes, limits) lives in `SKILL.md` under *Tools you may have available → SurveyCTO MCP server*.

## Download

**Latest stable release (always up to date):**

[surveycto-skill.zip](https://github.com/surveycto/surveycto-agent-skill/releases/latest/download/surveycto-skill.zip)

This URL always points to the most recent release. You can also browse all releases on the [releases page](../../releases).

## Installation

### Claude.ai / Claude Cowork

1. Download [surveycto-skill.zip](https://github.com/surveycto/surveycto-agent-skill/releases/latest/download/surveycto-skill.zip)
2. Open **Settings** > **Features** (or the **Customize** page)
3. Upload the zip file

### Claude Code

Install as a plugin:

```bash
# If this repo is registered as a plugin marketplace:
/plugin install surveycto-agent-skill

# Or install directly from GitHub:
/plugin install surveycto/surveycto-agent-skill
```

Or install manually as a personal skill:

```bash
git clone https://github.com/surveycto/surveycto-agent-skill.git
cp -r surveycto-agent-skill ~/.claude/skills/surveycto
```

### Other Agent Skills-compatible tools

This skill follows the [Agent Skills](https://agentskills.io) open standard. For tools like Cursor, VS Code Copilot, Gemini CLI, Roo Code, and others, consult their documentation for installing agent skills. The skill directory can typically be placed in the tool's skills folder.

## Usage

Once installed, the skill activates automatically when you:

- Ask about SurveyCTO, XLSForm, or survey form design
- Work with `.xlsx` files containing `survey`/`choices`/`settings` worksheets
- Work with XML files containing `<dataset>` elements
- Mention data collection forms, skip logic, constraints, or choice lists

## Development

This repo uses a `develop` → `main` branching model:

- **`develop`** — active development; pushes here produce a `surveycto-skill-dev.zip` build artifact
- **`main`** — stable releases; pushes here create a GitHub Release with `surveycto-skill.zip` attached

### Versioning

The skill version is stored in the `metadata.version` field in `SKILL.md` frontmatter:

```yaml
metadata:
  author: SurveyCTO
  version: "1.0"
```

When merging `develop` into `main`, bump this version number first. The release workflow reads it to create the Git tag and GitHub Release name (e.g., `"1.1"` → tag `v1.1`, release `v1.1`).

Use [semantic versioning](https://semver.org):

- **Patch** (1.0 → 1.0.1): Fix incorrect information, typos, or clarify existing guidance
- **Minor** (1.0 → 1.1): Add new content (new reference sections, new patterns, template updates)
- **Major** (1.1 → 2.0): Structural changes that may affect how agents use the skill

### Building the zip locally

```bash
zip -r surveycto-skill.zip . -x '.*' -x '.git/*' -x '.github/*' -x 'README.md' -x 'LICENSE' -x '*.zip'
```

### Making changes

1. Create a feature branch from `develop`
2. Make your changes
3. Open a PR to `develop`
4. Once merged and tested, bump the version in `SKILL.md` and merge `develop` into `main` to create a release

## Maintaining the primers

The five primers in `references/` have two different maintenance models, depending on whether the public documentation actually covers the topic.

### Docs-derived primers (regenerated periodically)

`overview.md`, `xlsform.md`, and `expressions.md` cover material that `docs.surveycto.com` documents thoroughly. They are intended to be regenerated periodically from a careful, top-down read of the live docs as the underlying product changes and as more capable AI agents become available. The prompts below are designed for [Claude Cowork](https://claude.ai/) (or any agent with web-fetch and file-write capabilities) — paste one into a fresh session, let it run, and replace the corresponding file with the result.

**Order matters.** Generate them top-down so each lower-level primer can rely on the higher-level ones:

1. `overview.md` (highest-level — generate first)
2. `xlsform.md`
3. `expressions.md`

Each primer should be self-contained enough to be served standalone via the MCP `get_surveycto_primer` tool, but should cross-link to the others where helpful. Use Markdown, prefer tables for column/option/function reference content, and link back to canonical pages on `docs.surveycto.com` and `support.surveycto.com` so a reader can always go deeper.

### Source-code-derived primers (bespoke, occasional)

`datasets-xml.md` and `data-explorer.md` cover material that the public documentation does not adequately describe:

- The Data Explorer docs page explicitly tells readers to "export a workbook and take a look, consulting the four help worksheets as needed" — there is no public column-by-column reference for summary types, options, or exclusion syntax.
- The dataset XML support article is fairly thorough but is missing elements (e.g. `<dataLinkState>`) and contains at least one apparent inconsistency with how the format is actually used in the field.

These primers were originally derived by inspecting the SurveyCTO server source code (and validating against real exported files), not by reading documentation. There is no Cowork prompt for regenerating them, because no agent reading public docs can produce something as accurate as what's already in the repo. When they need to change — because the underlying schema changes, or because a missing element comes to light — update them by re-deriving from the source code in a bespoke pass, then sync the result here.

### Prompt 1 — `overview.md`

```text
You are writing the highest-level primer for an AI agent (and the humans
reading the same content as a skill reference) on SurveyCTO. Target audience:
a capable LLM agent that has just been told it needs to help a user with
SurveyCTO, knows nothing specific about the product, and needs orientation
before diving into details.

Read the following SurveyCTO documentation and produce a single Markdown file
to save as `references/overview.md` in the surveycto-agent-skill repo:

Primary sources to read carefully:
- https://docs.surveycto.com/ (the docs home; survey the top-level table of contents)
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/ (forms intro)
- https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/01.datasets-intro.html (datasets intro)
- https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html (Data Explorer intro)
- https://www.surveycto.com/ (high-level product positioning)

The primer must cover, at a high level only:
- What SurveyCTO is and what problem it solves.
- Its relationship to XLSForm and ODK, and the most important ways SurveyCTO
  has diverged from generic ODK behavior (list the highest-impact gotchas
  briefly; full coverage belongs in expressions.md and xlsform.md).
- The three definition file types an agent will encounter: XLSForm form
  definitions (.xlsx with survey/choices/settings sheets), server dataset
  definitions (.xml with <dataset> root), and Data Explorer workbook
  definitions (.xlsx with summaries/settings/global_filters/global_exclusions
  sheets). For each: what it is, how to recognize it, what it's for.
- How forms and datasets relate: forms publish to datasets via dataLinks;
  datasets pre-load into forms via formLinks; pulldata() and search() consume
  pre-loaded data; case management is a special dataset configuration.
- The authoritative sources hierarchy: docs.surveycto.com, then
  support.surveycto.com, then www.surveycto.com.
- A "where to go next" section pointing to the four lower-level primers
  (xlsform.md, expressions.md, datasets-xml.md, data-explorer.md) with one
  sentence each describing when to read it.

Constraints:
- This is a high-level primer. Do NOT include exhaustive column lists, field
  type catalogs, expression function reference, or XML element reference —
  those belong in the lower-level primers.
- Keep it readable in roughly 2–3 minutes (~600–900 words plus tables).
- Open with an HTML comment block: `<!-- PRIMER: overview\n  STATUS: regenerated YYYY-MM-DD from docs.surveycto.com -->`.
- Use Markdown headings starting at H1 ("# SurveyCTO Overview").
- Use tables for the file-type recognition matrix.
- Cross-link to the other primers using relative links: [`xlsform.md`](xlsform.md), etc.
- Link back to canonical docs URLs whenever you assert a product fact.
- Do NOT invent product behavior. If a source is ambiguous, say so or omit.

Produce only the file contents, ready to save.
```

### Prompt 2 — `xlsform.md`

```text
You are writing the XLSForm mechanics primer for the SurveyCTO agent skill.
The reader has already read overview.md and knows what an XLSForm is at a high
level. They now need to be able to read, edit, and reason about every part of
a SurveyCTO XLSForm.

Read the following SurveyCTO documentation thoroughly. Walk every subsection
under "Designing forms: core concepts" and pull in any other pages linked
from there that describe XLSForm structure or columns:

Primary sources:
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/ (entire section)
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.design-tab.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/02.field-types.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/03.fields.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/04.choices.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/06.groups.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/07.constraints.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/10.appearances.html
  (and any sibling pages on appearances, languages, settings)
- Any pages describing the `settings` worksheet, encryption, languages, and
  form-level metadata.
- Pages describing pulldata(), search(), and field plug-ins as they relate to
  XLSForm columns/appearances (link them to expressions.md for syntax detail).

Also consult support.surveycto.com for any clarifications on edge cases.

The primer must cover, comprehensively:
- The three worksheets (`survey`, `choices`, `settings`) and their roles.
- The `survey` worksheet: every standard column (type, name, label, hint,
  relevance, constraint, constraint message, required, required message,
  calculation, default, repeat_count, choice_filter, appearance, read only,
  disabled, label/hint:Language variants, media columns, etc.) — what each
  one does and how to use it. Use a table.
- All XLSForm field types SurveyCTO supports — text, integer, decimal,
  select_one, select_multiple, date/time/datetime, geopoint/geotrace/geoshape,
  image/audio/video/file, barcode, calculate, note, acknowledge, deviceid,
  start/end/today, begin group / end group, begin repeat / end repeat,
  username/email, and any SurveyCTO-specific types. Use a table.
- The `choices` worksheet: list_name, value, label, label:Language, filter
  columns, image/media columns, ordering rules.
- Group and repeat semantics: nesting, scoping of relevance, repeat_count
  and repeat_count expressions, fixed vs. dynamic repeats, references into
  and out of repeats.
- Choice filter and cascading select patterns.
- Appearance options — list every appearance SurveyCTO documents, grouped by
  the field type(s) they apply to (text, select_one, select_multiple, date,
  group, repeat). Use tables.
- The `settings` worksheet: form_title, form_id, version, default_language,
  encryption keys (public_key), and any other documented settings.
- Field plug-ins and search() / pulldata() at a structural level (where they
  go, what columns they affect) — defer expression syntax to expressions.md
  with a cross-link.
- The XLSForm template that ships with the skill: what's in it, why it's the
  required starting point, what would break if someone built a workbook from
  scratch.

Constraints:
- Open with an HTML comment block: `<!-- PRIMER: xlsform\n  STATUS: regenerated YYYY-MM-DD from docs.surveycto.com -->`.
- Use Markdown, lots of tables.
- Cross-link to expressions.md for any expression-syntax details.
- Cross-link to datasets-xml.md when discussing pulldata/search and dataset
  attachment.
- Length: as long as needed for completeness, but tight. Aim for accuracy
  and structure over prose.
- Link to the canonical docs page for every section.
- If a column or field type is SurveyCTO-specific (not standard XLSForm),
  call it out explicitly.

Save as `references/xlsform.md`. Produce only the file contents.
```

### Prompt 3 — `expressions.md`

```text
You are writing the expression-language primer for the SurveyCTO agent skill.
The reader knows what an XLSForm is and where expressions go (relevance,
constraint, calculation, choice_filter, appearance, default). They now need
to be able to read, write, and debug any SurveyCTO expression.

Read the following SurveyCTO documentation thoroughly:

Primary sources:
- https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html (the canonical expressions page — read every section)
- Any sibling/linked pages on operators, functions, dates, strings, repeats,
  randomization, and references between fields.
- https://support.surveycto.com — search for expression-related articles for
  edge cases and worked examples.

The primer must cover:
- The expression model: XPath-derived, evaluated against the form instance,
  what `${field}` and `.` resolve to in different columns (constraint,
  calculation, relevance, choice_filter), and scoping inside groups/repeats.
- All operators SurveyCTO supports — arithmetic (`+ - * div mod`), comparison
  (`= != < > <= >=`), boolean (`and or not()`), string concatenation, and
  any platform-specific operators. Note `=` (not `==`), `div` (not `/`).
- Every documented function, grouped by category: math, string, date/time,
  selection (selected, selected-at, count-selected), choice (choice-label,
  jr:choice-name where it differs), repeat (index, count, sum, etc.),
  randomization (random, once), pulldata, search, regex, conditional (if,
  coalesce), node-set/aggregate (count, sum, min, max), and any others.
  Use tables with: name, signature, return type, brief description, link to
  the docs section that defines it, and a one-line example.
- The SurveyCTO-vs-ODK divergence list, in full: at minimum `=` vs `==`,
  `index()` vs `position()`, `choice-label()` vs `jr:choice-name()`,
  `relevance` column vs `relevant`, `div` vs `/`, `selected()` requirement
  for `select_multiple`, string-quoting rules, anything else the docs call
  out.
- String-literal quoting rules and escaping (single quotes preferred,
  double quotes when the literal contains a single quote, no character
  escaping inside single-quoted strings).
- Common patterns with worked examples: skip logic, range constraints,
  age from DOB, conditional values, pulldata lookups, search() for dynamic
  lists, once() for stable randomization, treatment assignment, regex
  validation, date comparisons (with date()), repeat-instance referencing.
- Common pitfalls and how to recognize them.

Constraints:
- Open with an HTML comment block: `<!-- PRIMER: expressions\n  STATUS: regenerated YYYY-MM-DD from docs.surveycto.com -->`.
- This primer is about *language*, not *placement*. If a function relates to
  a specific XLSForm column or feature, link to xlsform.md or
  datasets-xml.md rather than re-explaining it.
- Use heavy tables for the function reference.
- Link to the canonical docs anchor for every function/operator.
- If SurveyCTO behavior diverges from generic ODK/XPath, call it out inline
  AND in the divergence summary.
- Do NOT invent functions. If you can't find docs for a function, omit it.

Save as `references/expressions.md`. Produce only the file contents.
```

### Syncing primers to the MCP server

The [SurveyCTO MCP server](https://github.com/SurveyCTO/scto-assistant-be) vendors these primers under `src/mcp_server/primers/` and serves them via its `get_surveycto_primer` tool. After updating any primer here — whether by regenerating from docs or by re-deriving from source — sync the change to the MCP server repo (manual until automated) so callers without the skill installed get the updated content.

## Links

- [SurveyCTO Documentation](https://docs.surveycto.com)
- [SurveyCTO Support Center](https://support.surveycto.com)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html)

## License

Apache-2.0
