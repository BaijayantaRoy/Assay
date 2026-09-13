# Assay for Claude Code

Two pieces, useful separately:

- **A skill** (`skills/assay-prompts/`) that teaches Claude Code how an Assay workspace
  works — reuse before writing, every artifact needs an eval, run `assay test` after
  editing, and the handful of things that trip people up.
- **An MCP server config** (`mcp.sample.json`) that gives Claude Code live tools:
  search, render, run, test, create and lint against your actual prompts.

The skill alone is useful without MCP; MCP alone is useful without the skill. Together the
skill tells Claude *how to think about* the workspace and MCP lets it *act on* it.

## Install

**Prerequisite** — the CLI must be on PATH:

```bash
pip install assay-cli
```

### The skill

Copy the skill directory into your project or your user skills directory:

```bash
# project-scoped
mkdir -p .claude/skills
cp -r integrations/claude-code/skills/assay-prompts .claude/skills/

# or user-wide
cp -r integrations/claude-code/skills/assay-prompts ~/.claude/skills/
```

It triggers on its own when Claude Code notices an `assay.yaml` or a `prompts/` directory
of `.prompt.md` files — no invocation needed.

### The MCP server

```bash
cp integrations/claude-code/mcp.sample.json .mcp.json
```

Then remove the `_comment` line. `${CLAUDE_PROJECT_DIR}` is substituted by Claude Code; for
any other MCP client, replace it with an absolute path.

The workbench generates this for you with your real path already filled in —
**Connect → Integrations → MCP** — along with equivalent snippets for Cursor, VS Code and
Zed.

## What Claude Code gets

| Tool | Does |
|:--|:--|
| `assay_search` | find a prompt by text or tag |
| `assay_get` | read one artifact in full |
| `assay_render` | fill the template without calling a model |
| `assay_run` | execute it |
| `assay_test` | prove an edit did not regress anything |
| `assay_create` | write a new artifact |
| `assay_update` | modify an existing one |
| `assay_lint` | validate against the spec |
| `assay_models` | the model catalogue |

Plus resources under `assay://` — the spec, the workspace config, the model list, and a
token-cheap index of every artifact.

## Why a skill and not just AGENTS.md

`assay agents init` writes an AGENTS.md that lists what exists and how to run it. That is
the *inventory*. This skill is the *method* — when to reuse rather than write, why an
artifact without evals is not tested, what `verified: null` means, and why relaxing an
assertion until it passes is not a fix.

Both are worth having, and Claude Code reads `CLAUDE.md` rather than `AGENTS.md`, which is
why `assay agents init --target claude` exists.

## A note on scope

This directory is a convenience, not a dependency. Everything here is a text file you can
read, edit or ignore. Assay itself has no idea Claude Code exists — the CLI, the MCP
server and the REST API are the same engine, and this is one client's way of reaching it.
