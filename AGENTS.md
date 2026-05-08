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

Edit the version in one place — the frontmatter at the top of
`SKILL.md`:

```yaml
metadata:
  author: Dobility, Inc. (SurveyCTO)
  version: "X.Y.Z"
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
  -x '**/.DS_Store' -x '**/Thumbs.db'
```

The local zip is gitignored. Don't commit it.

### Why an inclusion list

The skill bundle has a fixed structure: `SKILL.md` at the root,
`references/`, and `assets/`. Listing those three things explicitly is
more stable than excluding everything else — a new top-level file
(another doc, a config dir, a tool) won't accidentally get bundled.
The two `**/.DS_Store` / `**/Thumbs.db` exclusions catch OS clutter
that may have crept into `references/` or `assets/`.

If you add a new top-level path that *should* ship in the skill, update
both `.github/workflows/release.yml` and `.github/workflows/build-dev.yml`
(and the local command above) to include it.

## Repo layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | The skill content itself. Loaded by the agent host on activation. |
| `references/` | Deep-dive reference docs the agent loads on demand. See [`README.md` → Maintaining `references/`](README.md#maintaining-references). |
| `assets/` | Bundled templates and tools (XLSForm template, field plug-in template, field plug-in test harness). |
| `surveycto-skill.zip` | Local-only test zip if you build one. Gitignored, not committed. CI builds and publishes the official release zip on push to `main`. |
| `README.md` | End-user-facing install/use/maintenance docs. **Excluded from the skill zip.** |
| `AGENTS.md` | This file. **Excluded from the skill zip.** |
| `LICENSE` | Apache-2.0. **Excluded from the skill zip** (it's at the repo level, not the bundle level). |
| `.kilo/` | Per-project Kilo config, plans, command/agent overrides. **Excluded from the skill zip.** |
| `planning/` | Internal planning notes. **Excluded from the skill zip.** |

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
- **Editing the field plug-in test harness or template** — keep the
  harness zero-dependency and offline-usable. Run `validate.mjs`
  against `assets/field-plugin-template/` after any change.
- **Updating MCP server reference (`references/mcp.md`)** — this is
  derived from the private `scto-assistant-be` repo, not from public
  docs. See [`README.md` → Maintaining the MCP server reference](README.md#maintaining-the-mcp-server-reference).

## Release flow (summary)

1. PR feature branch → `develop`. CI publishes a fresh
   `surveycto-skill-dev.zip` build artifact.
2. When ready to release: bump `metadata.version` if not already done
   on `develop`, then PR `develop` → `main`.
3. Merge to `main`. The release workflow tags `vX.Y.Z` and attaches
   `surveycto-skill.zip` to the GitHub Release.
4. If a primer changed, sync it to the SurveyCTO MCP server's vendored
   copies (see [`README.md` → Syncing primers to the MCP server](README.md#syncing-primers-to-the-mcp-server)).
