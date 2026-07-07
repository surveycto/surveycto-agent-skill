# Working on this repo

This file orients an AI agent (or a human) making changes to the
**SurveyCTO Agent Skill** itself. It is not part of the skill bundle —
it is excluded from `surveycto-skill.zip` / `surveycto-skill-dev.zip`.

For end-user-facing documentation see [`README.md`](README.md). For the
skill content itself see [`SKILL.md`](SKILL.md).

## What this repo is

An [Agent Skills](https://agentskills.io) package that gives AI agents
SurveyCTO domain expertise. The deliverable is a zip
(`surveycto-skill.zip`) that hosts (Claude Cowork, Codex, etc.) extract
into their skills directory. **The zip is not committed** — it's built
and published by GitHub Actions:

- Push to `develop` → `.github/workflows/build-dev.yml` builds
  `surveycto-skill-dev.zip` as a workflow artifact (downloadable from
  the run page) for smoke-testing pre-release changes.
- Push to `main` → `.github/workflows/release.yml` builds
  `surveycto-skill.zip` and attaches it to a new GitHub Release whose
  tag/name comes from `metadata.version` in `SKILL.md`.

For local smoke-testing, you can build a zip yourself (see
[*When to rebuild the local zip*](#when-to-rebuild-the-local-zip)). It
stays in your working tree and is gitignored.

## Branching

- **`develop`** — active development. Pushes here trigger the dev-build
  workflow.
- **`main`** — stable releases. Pushes here trigger the release
  workflow.

Default working branch for new work is `develop` (or a feature branch
off `develop`). PRs target `develop` first; `develop → main` is reserved
for release.

## When to bump the version

The release workflow takes its tag from `metadata.version` in
`SKILL.md`. If `develop` is merged into `main` without a bump since the
last release, the workflow will try to re-tag the same version and the
release will fail (or, worse, silently overwrite, depending on settings).

**Procedure** before making non-trivial changes to skill content
(`SKILL.md`, `references/`, `assets/`):

1. Compare the current branch's `metadata.version` in `SKILL.md`
   against `main`'s:
   ```bash
   git show origin/main:SKILL.md | sed -n '/^metadata:/,/^---/p' | grep version
   ```
2. If the two match, the current branch hasn't been bumped since the
   last release — bump it as part of this change. If they already
   differ (current is ahead of `main`), no further bump is needed
   unless the new change crosses a different semver boundary than the
   bump that's already there.
3. If you're unsure (e.g. the change is small, or the user hasn't
   asked), ask or offer rather than skipping. A missed bump blocks
   release; an unnecessary bump is harmless.
4. When bumping, update **both** places the version appears in
   `SKILL.md` (see below). They must stay in sync — the frontmatter
   drives the release tag and the body line is what the agent reports
   at runtime, since agents don't see frontmatter.

Use [semantic versioning](https://semver.org), per the rules in
[`README.md` → Versioning](README.md#versioning):

- **Pre-release** (`1.0.0-beta`, `1.0.0-beta.N`, `1.0.0-rc.N`) — public
  beta and release-candidate builds. Increment the trailing
  `-beta.N` / `-rc.N` for each pre-release ship.
- **Patch** (`1.0.0` → `1.0.1`) — fix incorrect information, typos,
  clarify existing guidance.
- **Minor** (`1.0.0` → `1.1.0`) — add new content (new reference
  sections, new patterns, template updates, new behavior rules in the
  skill).
- **Major** (`1.x` → `2.0.0`) — structural changes that may affect how
  agents use the skill (file moves, removed sections, MCP-contract
  changes the skill depends on).

The version lives in **two** places inside `SKILL.md` that must be
kept in sync (see [`README.md` → Versioning](README.md#versioning) for
the rationale):

1. The `metadata.version` field in the frontmatter — read by the
   release workflow and by skill hosts.
2. A "Skill version" line near the top of `SKILL.md`'s body — visible
   to the agent at runtime, since agents do not see frontmatter.

```yaml
metadata:
  author: Dobility, Inc. (SurveyCTO)
  version: "X.Y.Z"
```

```markdown
**Skill version: X.Y.Z.** ...
```

## When to update the version policy

Skills do not auto-update and there is no separate update channel, so
the SurveyCTO MCP server announces the current skill-version policy to
connected agents (it serves the recommended and deprecated versions, and
agents prompt users to update when they're behind). The editorial half
of that policy lives in **`version-policy.source.json`**. Bumping
`metadata.version` in `SKILL.md` alone does **not** update what the
server broadcasts — that file is separate and must be maintained
deliberately. See [`README.md` → Broadcasting versions through the MCP
server](README.md#broadcasting-versions-through-the-mcp-server) for the
end-user-facing rationale.

Edit `version-policy.source.json` in the **same PR that bumps the
version** whenever the deprecation floor or the update summary should
change. Its fields:

- **`latest_updates`** — a newest-first, human-readable list of
  per-version summaries shown to agents. When you bump the version for a
  content change worth surfacing to users, prepend a new
  `"X.Y.Z: <one-line summary>"` entry. This is the field you'll touch
  most often.
- **`deprecated_below_version`** — the deliberate floor; versions below
  it are announced as deprecated. Raise it only when an older release
  becomes genuinely problematic (e.g. it produces broken forms), not on
  every bump.
- **`recommended_min_version`** (optional) — defaults to the released
  version, so each release recommends itself. Set it only to pin an
  older recommended floor than the latest.

Do **not** set `latest_version` here. The release workflow derives it
from the released tag (`metadata.version` in `SKILL.md`), and
`scripts/build_version_policy.py` merges it with these overrides to
produce the `version-policy.json` release asset. Underscore-prefixed
keys (like `_comment`) are treated as comments and dropped from the
asset.

The generator validates, and the release **fails**, if the versions
aren't internally ordered
(`deprecated_below <= recommended_min <= latest`) or if any value isn't a
real semantic version — so keep `deprecated_below_version` at or below
the version you're releasing. `tests/test_version_policy.py` runs in the
release workflow (and locally) to guard this; run it after editing
either the source file or the generator:

```bash
python3 tests/test_version_policy.py
```

## When to rebuild the local zip

The official zips are produced by GitHub Actions, not committed.
Locally, you may want to build a zip to smoke-test installation in an
agent host (Claude Cowork, Codex, etc.) before opening a PR. One zip
is enough; both workflows build the same content from the same paths,
so the local artifact represents both the dev and release builds.

```bash
rm -f surveycto-skill.zip
zip -r surveycto-skill.zip SKILL.md references assets \
  -x '**/.DS_Store' -x '**/Thumbs.db' \
  -x '**/__pycache__/*' -x '**/*.pyc' -x '**/*.pyo'
```

The local zip is gitignored. Don't commit it.

### Why an inclusion list

The skill bundle has a fixed structure: `SKILL.md` at the root,
`references/`, and `assets/`. Listing those three things explicitly is
more stable than excluding everything else — a new top-level file
(another doc, a config dir, a tool) won't accidentally get bundled.
The `**/.DS_Store`, `**/Thumbs.db`, `**/__pycache__/*`, `**/*.pyc`,
and `**/*.pyo` exclusions catch OS and Python cache clutter that may
have crept into `references/` or `assets/`.

If you add a new top-level path that *should* ship in the skill, update
both `.github/workflows/release.yml` and `.github/workflows/build-dev.yml`
(and the local command above) to include it.

## When editing XLSX assets

The XLSForm template and any other public `.xlsx` assets may be edited in
Excel, but Excel can add machine-local metadata to the zip package (for
example `docProps/core.xml` author fields and `x15ac:absPath` absolute
local paths in `xl/workbook.xml`). After every edit to
`assets/xlsform-template.xlsx` or another public XLSX asset, run the
sanitizer and validator before committing:

```bash
python3 scripts/sanitize_xlsx_assets.py
python3 tests/validate_xlsx_assets.py
```

The sanitizer is stdlib-only and removes local author/path metadata. The
validator uses `openpyxl` and checks both metadata hygiene and the
template invariants that Excel can silently break: exact sheet structure,
expected `survey` / `choices` / `settings` headers, survey conditional
formatting coverage across all headered columns, and the `settings!C2`
version formula. CI installs `openpyxl==3.1.5` and runs the same
validator before building the dev or release zip.

## Repo layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | The skill content itself. Loaded by the agent host on activation. |
| `references/` | Deep-dive reference docs the agent loads on demand. See [`README.md` → Maintaining `references/`](README.md#maintaining-references). |
| `assets/` | Bundled templates and tools (XLSForm template, field plug-in template, field plug-in test harness, dataset validator). |
| `surveycto-skill.zip` | Local-only test zip if you build one. Gitignored, not committed. CI builds and publishes the official release zip on push to `main`. |
| `version-policy.source.json` | Editorial overrides for the skill-version policy the MCP server broadcasts (deprecation floor, update summaries). Merged with the release tag at release time. **Excluded from the skill zip.** |
| `README.md` | End-user-facing install/use/maintenance docs. **Excluded from the skill zip.** |
| `AGENTS.md` | This file. **Excluded from the skill zip.** |
| `LICENSE` | Apache-2.0. **Excluded from the skill zip** (it's at the repo level, not the bundle level). |
| `.kilo/` | Per-project Kilo config, plans, command/agent overrides. **Excluded from the skill zip.** |
| `planning/` | Internal planning notes. **Excluded from the skill zip.** |
| `scripts/` | Repo maintenance scripts, including XLSX asset sanitization. **Excluded from the skill zip.** |
| `tests/` | Test fixtures and validation assets. **Excluded from the skill zip.** |

## Quality bar

- Treat skill content as production. The skill ships into desktop AI
  agents that real SurveyCTO users rely on for production form work;
  factual mistakes can break live data collection.
- Prefer accuracy over coverage. Verify product-behavior claims
  against `docs.surveycto.com` (or, for field plug-ins, the
  `surveycto/field-plug-in-resources` GitHub developer docs) before
  asserting them.
- Keep `SKILL.md` lean — it's loaded into every relevant context.
  Detailed reference content goes in `references/`.
- ASCII unless an upstream identifier or existing file requires
  otherwise.

## Common tasks and where to read first

- **Refreshing a primer** (`overview.md`, `xlsform.md`,
  `expressions.md`, `field-plugins.md`) — see the regeneration prompts
  in [`README.md` → Maintaining `references/`](README.md#maintaining-references).
  The field plug-in prompt in particular has an *Invariants to
  preserve* block; read it before regenerating.
- **Editing the dataset XML or Data Explorer primers** — these are
  source-code-derived (not docs-derived). See [`README.md`
  → Source-code-derived primers](README.md#source-code-derived-primers-bespoke-occasional).
- **Editing the dataset validator** (`assets/dataset-validation/validate_dataset.py`
  and `references/dataset-validation.md`) — these are source-code-derived from
  the SurveyCTO server's dataset create/edit rules. The script header lists the
  source files behind each rule. Keep the two in sync, and run
  `python3 tests/test_dataset_validation.py` after any change.
- **Editing the field plug-in test harness or template** — keep the
  harness zero-dependency and offline-usable. Run `validate.mjs`
  against `assets/field-plugin-template/` after any change.
- **Editing `assets/xlsform-template.xlsx` or another public XLSX asset** —
  run `python3 scripts/sanitize_xlsx_assets.py`, then
  `python3 tests/validate_xlsx_assets.py` before committing.
- **Updating what the MCP server broadcasts about skill versions**
  (`version-policy.source.json`, `scripts/build_version_policy.py`) —
  see [*When to update the version policy*](#when-to-update-the-version-policy).
  Run `python3 tests/test_version_policy.py` after any change.
- **Updating MCP server reference (`references/mcp.md`)** — this is
  derived from the private `scto-assistant-be` repo, not from public
  docs. See [`README.md` → Maintaining the MCP server reference](README.md#maintaining-the-mcp-server-reference).

## Release flow (summary)

1. PR feature branch → `develop`. CI publishes a fresh
   `surveycto-skill-dev.zip` build artifact.
2. When ready to release: bump `metadata.version` if not already done
   on `develop` (and update `version-policy.source.json` in the same PR
   if the policy should change — see [*When to update the version
   policy*](#when-to-update-the-version-policy)), then PR `develop` →
   `main`.
3. Merge to `main`. The release workflow tags `vX.Y.Z`, builds
   `version-policy.json` from the tag plus `version-policy.source.json`,
   and attaches both `surveycto-skill.zip` and `version-policy.json` to
   the GitHub Release.
4. If a primer changed, sync it to the SurveyCTO MCP server's vendored
   copies (see [`README.md` → Syncing primers to the MCP server](README.md#syncing-primers-to-the-mcp-server)).
