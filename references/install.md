# Installing the SurveyCTO Agent Skill

This guide covers installing the skill, connecting the SurveyCTO MCP server, enabling the network access the MCP server requires, and troubleshooting common installation issues. For an overview of what the skill is and where to download it, see the project [README](https://github.com/surveycto/surveycto-agent-skill#readme).

This file ships inside `surveycto-skill.zip` so the agent can reference it mid-session when coaching a user through installation or network-egress problems.

## Components

For the best experience, install both:

1. **The skill itself** (`surveycto-skill.zip`) — teaches the agent SurveyCTO domain expertise.
2. **The SurveyCTO MCP server** at `https://assistant-be.surveycto.net/mcp` — provides purpose-built XLSForm tools and live knowledge-base search.

The skill works on its own, but without the MCP server (or without working network access to it) the agent cannot reliably edit XLSForm files. See [Why the MCP server matters](#why-the-mcp-server-matters) below.

## Claude Cowork

1. Open the sidebar and click **Customize**.
2. Click **Create skill… → Upload a skill** and upload `surveycto-skill.zip`.
3. Click into **Connectors** and then **Add custom connector**.
4. Enter `https://assistant-be.surveycto.net/mcp` as the server address and **SurveyCTO tools** as the name.
5. Once the connector is added, click **Always allow** for each of the SurveyCTO tools.
6. **Configure network egress** — see [Network egress (Cowork)](#network-egress-cowork) immediately below. This step is required and is the most common reason the skill appears installed but then fails to upload or download XLSForms.

Tip: in Claude billing settings, enable extra usage so the agent can keep working past your subscription-level usage quota.

### Network egress (Cowork)

Claude Cowork runs skills inside a sandboxed code-execution environment that blocks outbound network access by default. The SurveyCTO MCP server's XLSForm tools rely on `curl` uploads and HTTPS downloads to `assistant-be.surveycto.net`, so you must explicitly allow that traffic before the agent can move XLSForm bytes.

**Configure this once, before your first SurveyCTO chat:**

1. Open **Settings → Capabilities**.
2. Confirm **Cloud code execution and file creation** is on (required for skills in general).
3. Turn on **Allow network egress**.
4. Under **Domain allowlist**, either select **All domains** or keep **Package managers only** and add `*.surveycto.net` to **Additional allowed domains**.
5. **Start a new chat.** Egress changes do not reliably take effect for chats that are already in progress — the sandbox state for an in-flight session is sticky, and the agent can keep hitting network errors for the rest of that chat even after the setting is enabled.

## OpenAI Codex

Codex doesn't (as of this writing) have a UI for managing skills, so install the skill by unzipping into `~/.agents/skills/surveycto`:

```bash
mkdir -p ~/.agents/skills/surveycto
unzip surveycto-skill.zip -d ~/.agents/skills/surveycto
```

Codex does have a UI for MCP servers:

1. Open Codex settings and click **MCP servers**.
2. Click **+ Add server**, then enter `https://assistant-be.surveycto.net/mcp` as the server address and **SurveyCTO tools** as the name.
3. If SurveyCTO capabilities don't appear in new chats, restart Codex.

Codex prompts for permission on every tool call. Select **Always allow** in those prompts to permanently approve each tool. Codex does not sandbox network egress separately from the host machine, so no extra egress configuration is needed once the user has approved the tool.

## Other Agent Skills-compatible hosts

This skill follows the [Agent Skills](https://agentskills.io) open standard. For other hosts (Claude Code, Cursor, VS Code Copilot, Gemini CLI, Roo Code, etc.), consult the host's documentation for skills and MCP servers. In general:

- **Skill**: extract `surveycto-skill.zip` into the host's skills directory (often `~/.<host>/skills/surveycto` or similar).
- **MCP server**: register `https://assistant-be.surveycto.net/mcp` (Streamable HTTP, no auth). For stdio-only clients, wrap with `mcp-remote`:

  ```json
  {
    "surveycto": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://assistant-be.surveycto.net/mcp"]
    }
  }
  ```

- **Network access**: if your host sandboxes skill execution, ensure outbound HTTPS to `*.surveycto.net` (or at minimum `assistant-be.surveycto.net`) is allowed. Hosts that run skills directly on your machine typically just prompt for permission on the first `curl` and need no separate egress configuration.

## Why the MCP server matters

The SurveyCTO MCP server provides session-based XLSForm tools with SurveyCTO-aware parsing, atomic patches, formula recalculation on export, and formatting preservation. Without it — or with it installed but blocked by egress — the agent falls back to generic spreadsheet tooling (commonly Python's `openpyxl`), which in practice round-trips the SurveyCTO XLSForm template poorly: conditional formatting, formula recalculation state, the help worksheets, named styles, and row coloring are frequently lost or corrupted. Users end up fixing formatting by hand in Excel after every export.

Inline base64 transport (`xlsx_base64` on `start_xlsform_session`, `format="base64"` on `export_xlsform`) is also not a viable workaround: a real XLSForm encoded as base64 is too large to round-trip through agent tool-call parameters. The bundled 154 KB template alone becomes ~205 KB of base64 (~195K tokens), which exceeds typical agent read/parameter limits.

If you want a smooth experience, install the MCP server *and* unblock egress before you start working.

## Troubleshooting

### "The agent uploaded fine the first time but now everything is failing"

Most likely a Cowork sandbox state issue. Egress changes don't always apply to in-progress chats. Verify egress is configured (see [Network egress (Cowork)](#network-egress-cowork)), then, if necessary, **start a new chat**.

### "Network egress is on and the domain is allowed, but uploads still fail"

- Double-check you started a new chat *after* enabling egress.
- Confirm the domain entry is `*.surveycto.net` (or `All domains`), not just `surveycto.com`.
- In a fresh chat, ask the agent to run the MCP preflight (start a session, upload the bundled template, end the session). The agent will surface the underlying error message.

### "The MCP tools aren't showing up at all"

- In Cowork: confirm the connector was added under **Connectors** and that each SurveyCTO tool shows **Always allow**.
- In Codex or stdio clients: restart the host after adding the server.
- In any host: ask the agent to call `get_surveycto_mcp_capabilities` — if that fails, the MCP server isn't reachable from the host at all.

### "The agent is editing XLSForms with `openpyxl` instead of MCP tools"

The agent only falls back to generic tooling when MCP isn't connected or upload/download is failing. Run the MCP preflight in a fresh chat to see which.
