# SurveyCTO Agent Skill

An [Agent Skill](https://agentskills.io) that enables AI agents to design, edit, and debug [SurveyCTO](https://www.surveycto.com) forms (XLSForm .xlsx files), server datasets (XML definitions), and Data Explorer workbook definitions.

## What's included

| File | Purpose |
| --- | --- |
| `SKILL.md` | Main skill — overview, conventions, editing workflow, validation, debugging |
| `references/xlsform-reference.md` | Complete XLSForm worksheet, column, and field type reference |
| `references/expressions-reference.md` | All SurveyCTO expression operators and functions |
| `references/dataset-xml-reference.md` | Dataset XML definition structure and usage |
| `references/data-explorer-reference.md` | Data Explorer workbook definition reference |
| `assets/xlsform-template.xlsx` | XLSForm template with headers, formatting, and help worksheets |

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

This skill follows the [Agent Skills](https://agentskills.io) open standard. For tools like Cursor, VS Code Copilot, Gemini CLI, Roo Code, and others, consult their documentation for how to install agent skills. The skill directory can typically be placed in the tool's skills folder.

## Usage

Once installed, the skill activates automatically when you:
- Ask about SurveyCTO, XLSForm, or survey form design
- Work with .xlsx files containing `survey`/`choices`/`settings` worksheets
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

When merging `develop` into `main`, bump this version number first. The release workflow reads it to create the Git tag and GitHub Release name (e.g., version `"1.1"` produces tag `v1.1` and release `v1.1`).

Use [semantic versioning](https://semver.org):
- **Patch** (e.g., 1.0 → 1.0.1): Fix incorrect information, typos, or clarify existing guidance
- **Minor** (e.g., 1.0 → 1.1): Add new content (new reference sections, new patterns, template updates)
- **Major** (e.g., 1.1 → 2.0): Structural changes that may affect how agents use the skill

### Building the zip locally

```bash
zip -r surveycto-skill.zip . -x '.*' -x '.git/*' -x '.github/*' -x 'README.md' -x 'LICENSE' -x '*.zip'
```

### Making changes

1. Create a feature branch from `develop`
2. Make your changes
3. Open a PR to `develop`
4. Once merged and tested, bump the version in `SKILL.md` and merge `develop` into `main` to create a release

## Links

- [SurveyCTO Documentation](https://docs.surveycto.com)
- [SurveyCTO Support Center](https://support.surveycto.com)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Using expressions in your forms](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html)

## License

Apache-2.0
