"""``/v1/integrations`` — connecting Assay to the tools people already use.

Three things live here, and they answer the same question from different angles: *how does
the rest of my toolchain find out these prompts exist?*

**AGENTS.md** is the broadest answer. It is stewarded by the Agentic AI Foundation under
the Linux Foundation, sits in 60k+ repositories, and is read natively by Codex, Cursor,
Copilot's coding agent, Gemini CLI, Aider, goose, opencode, Zed, Warp, VS Code, Devin,
Windsurf, Junie and Amp. One generated file reaches all of them, which is why it is worth
more than any single bespoke integration.

**MCP configuration** is the deepest. AGENTS.md tells an agent the prompts exist; MCP lets
it search, render, run and test them live. The snippets here are generated with this
workspace's real path, because a config block someone has to hand-edit is a config block
that gets pasted wrong.

**Chatbot export** is the shallowest and the most used. Not everyone is in an IDE. This
renders a prompt with its variables filled and hands back text ready to paste into
ChatGPT, Claude or Gemini, with the model settings noted so the reader knows what the
prompt was designed against.

Everything here is preview-first. Nothing writes to disk without an explicit POST.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from assay_core import AssayError, ModelCatalog, Runtime, Workspace, agentsmd

from .router import _http, get_runtime, get_store, get_workspace

router = APIRouter(prefix="/v1/integrations", tags=["v1 · integrations"])

_PROVIDER_ENVIRONMENT = (
    ("openai", "OpenAI", "OPENAI_API_KEY"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ("google", "Google", "GOOGLE_API_KEY"),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY"),
    ("xai", "xAI", "XAI_API_KEY"),
    ("moonshot", "Moonshot", "MOONSHOT_API_KEY"),
    ("mistral", "Mistral", "MISTRAL_API_KEY"),
    ("ollama", "Ollama", "OLLAMA_BASE_URL"),
)


def _artifacts(store) -> list:
    out = []
    for prompt_id in store.list():
        try:
            out.append(store.get(prompt_id))
        except Exception:
            continue
    return out


@router.get("/provider-status", summary="Report provider configuration without secrets")
def provider_status() -> dict:
    """Return presence only; secret values never cross the server boundary."""
    providers = [
        {
            "id": provider_id,
            "label": label,
            "configured": bool(os.getenv(variable, "").strip()),
            "source": "server environment",
        }
        for provider_id, label, variable in _PROVIDER_ENVIRONMENT
    ]
    configured = sum(provider["configured"] for provider in providers)
    return {
        "configured": configured,
        "total": len(providers),
        "providers": providers,
        "note": "Configure credentials in the backend environment; values are never returned.",
    }


# ---------------------------------------------------------------------------
# AGENTS.md
# ---------------------------------------------------------------------------


class AgentsMdRequest(BaseModel):
    targets: list[str] = Field(
        default_factory=lambda: ["agents"],
        description="Which files to write. 'agents' → AGENTS.md, 'claude' → CLAUDE.md.",
    )


@router.get("/agents-md", summary="Preview the AGENTS.md block without writing it")
def preview_agents_md(
    workspace: Workspace = Depends(get_workspace),
    store=Depends(get_store),
) -> dict:
    artifacts = _artifacts(store)
    content = agentsmd.generate(
        artifacts,
        workspace_name=workspace.config.get("name") or workspace.root.name,
        prompts_dir=str(workspace.config.get("prompts") or "prompts").lstrip("./"),
    )

    existing = {}
    for key, filename in agentsmd.TARGETS.items():
        path = workspace.root / filename
        existing[key] = {
            "file": filename,
            "exists": path.exists(),
            # Whether a previous generated block is present tells the UI whether this is
            # a create or a refresh — a meaningful difference to anyone with a
            # hand-written file they do not want touched.
            "has_generated_block": path.exists()
            and agentsmd.BEGIN in path.read_text(encoding="utf-8", errors="replace"),
        }

    return {
        "content": content,
        "artifacts": len(artifacts),
        "targets": existing,
        "reaches": [
            "Codex", "Cursor", "GitHub Copilot", "Gemini CLI", "Aider", "goose",
            "opencode", "Zed", "Warp", "VS Code", "Devin", "Windsurf", "Junie", "Amp",
        ],
        "note": (
            "Only the region between the assay:begin and assay:end markers is replaced. "
            "Anything you wrote around it survives regeneration."
        ),
    }


@router.post("/agents-md", summary="Write AGENTS.md into the workspace")
def write_agents_md(
    payload: AgentsMdRequest,
    workspace: Workspace = Depends(get_workspace),
    store=Depends(get_store),
) -> dict:
    unknown = [t for t in payload.targets if t not in agentsmd.TARGETS]
    if unknown:
        raise HTTPException(400, {
            "code": "assay.unknown_target",
            "message": f"unknown target(s) {unknown}; expected any of {sorted(agentsmd.TARGETS)}",
        })

    written = agentsmd.write(
        workspace.root,
        _artifacts(store),
        targets=payload.targets,
        workspace_name=workspace.config.get("name") or workspace.root.name,
        prompts_dir=str(workspace.config.get("prompts") or "prompts").lstrip("./"),
    )
    return {"written": written, "count": len(written)}


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


def _bundles_root() -> Path:
    return Path(__file__).resolve().parents[3] / "integrations"


@router.get("/bundles", summary="Installable bundles for specific clients")
def list_bundles() -> dict:
    """Client-specific packages that ship in the repository.

    Kept as plain directories of text files rather than build artifacts, so anyone can
    read what they are installing before they install it — which for something that
    changes how an agent behaves in your repository seems like the minimum.
    """
    root = _bundles_root()
    bundles = []

    claude = root / "claude-code"
    if claude.is_dir():
        skills = sorted(p.name for p in (claude / "skills").glob("*") if p.is_dir())
        bundles.append({
            "id": "claude-code",
            "name": "Claude Code / Cowork",
            "kind": "skill + MCP",
            "summary": (
                "A skill that teaches Claude Code how an Assay workspace works, plus the "
                "MCP server config. The skill triggers on its own when it sees an "
                "assay.yaml or a prompts/ directory."
            ),
            "skills": skills,
            "path": "integrations/claude-code",
            "readme": (claude / "README.md").read_text(encoding="utf-8")
            if (claude / "README.md").exists() else "",
            "install": [
                "pip install assay-cli",
                "mkdir -p .claude/skills",
                "cp -r integrations/claude-code/skills/assay-prompts .claude/skills/",
                "cp integrations/claude-code/mcp.sample.json .mcp.json",
            ],
            "why": (
                "AGENTS.md is the inventory — what exists and how to run it. The skill is "
                "the method: when to reuse rather than write, why an artifact without "
                "evals is not tested, and what verified: null means."
            ),
        })

    return {"bundles": bundles, "count": len(bundles)}


@router.get("/mcp", summary="Ready-to-paste MCP config for each client")
def mcp_config(workspace: Workspace = Depends(get_workspace)) -> dict:
    """Generated with this workspace's real path.

    A config block a user has to hand-edit is a config block that gets pasted wrong, and
    the failure mode — an MCP server that silently exposes the wrong directory — is
    annoying to diagnose.
    """
    root = str(workspace.root)

    server = {
        "command": "assay",
        "args": ["mcp"],
        "env": {"ASSAY_WORKSPACE": root},
    }

    return {
        "workspace_root": root,
        "clients": [
            {
                "id": "claude-code",
                "name": "Claude Code / Cowork",
                "file": ".mcp.json (project) or ~/.claude.json (global)",
                "config": json.dumps({"mcpServers": {"assay": server}}, indent=2),
                "docs": "https://docs.claude.com",
            },
            {
                "id": "cursor",
                "name": "Cursor",
                "file": ".cursor/mcp.json",
                "config": json.dumps({"mcpServers": {"assay": server}}, indent=2),
                "docs": "https://cursor.com",
            },
            {
                "id": "vscode",
                "name": "VS Code",
                "file": ".vscode/mcp.json",
                "config": json.dumps({"servers": {"assay": {**server, "type": "stdio"}}}, indent=2),
                "docs": "https://code.visualstudio.com",
            },
            {
                "id": "zed",
                "name": "Zed",
                "file": "settings.json",
                "config": json.dumps(
                    {"context_servers": {"assay": {"command": server["command"],
                                                   "args": server["args"],
                                                   "env": server["env"]}}},
                    indent=2,
                ),
                "docs": "https://zed.dev",
            },
        ],
        "tools": [
            {"name": "assay_search", "does": "find a prompt by text or tag"},
            {"name": "assay_get", "does": "read one artifact in full"},
            {"name": "assay_render", "does": "fill the template without calling a model"},
            {"name": "assay_run", "does": "execute it"},
            {"name": "assay_test", "does": "prove an edit did not regress anything"},
            {"name": "assay_create", "does": "write a new artifact"},
            {"name": "assay_lint", "does": "validate against the spec"},
        ],
        "note": (
            "MCP is the deeper integration: AGENTS.md tells an agent your prompts exist, "
            "MCP lets it search, run and test them live."
        ),
    }


# ---------------------------------------------------------------------------
# Chatbot export
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    include_settings: bool = Field(
        True, description="Append the model and parameters the prompt was designed against."
    )


@router.post("/export/{prompt_id:path}", summary="Render a prompt as text to paste into a chatbot")
def export_for_chat(
    prompt_id: str,
    payload: ExportRequest,
    runtime: Runtime = Depends(get_runtime),
    store=Depends(get_store),
) -> dict:
    """Produce copy-ready text for ChatGPT, Claude or Gemini.

    No model is called and nothing is spent — this only renders. The model binding is
    appended as a note rather than silently dropped, because a prompt tuned at
    temperature 0 against a specific model behaves differently pasted into a chat window,
    and the reader should know that before wondering why the output differs.
    """
    try:
        artifact = store.get(prompt_id)
        rendered = runtime.render(artifact, payload.variables)
    except AssayError as exc:
        raise _http(exc) from exc

    system = "\n\n".join(
        str(m.content) for m in rendered.messages if m.role == "system"
    ).strip()
    user = "\n\n".join(
        str(m.content) for m in rendered.messages if m.role != "system"
    ).strip()

    blocks = []
    if system:
        blocks.append(system)
    if user:
        blocks.append(user)
    plain = "\n\n".join(blocks)

    settings = []
    if payload.include_settings:
        if artifact.model_ref:
            settings.append(f"Designed against: {artifact.model_ref}")
        params = artifact.params or {}
        if params:
            settings.append(
                "Parameters: " + ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
            )
        missing = sorted(set(artifact.template_variables()) - set(payload.variables))
        if missing:
            settings.append(f"Unfilled variables left as placeholders: {', '.join(missing)}")

    return {
        "id": artifact.id,
        "system": system,
        "user": user,
        "plain": plain,
        "with_settings": (plain + "\n\n---\n" + "\n".join(settings)) if settings else plain,
        "settings": settings,
        "variables_used": payload.variables,
        "targets": [
            {"id": "chatgpt", "name": "ChatGPT", "url": "https://chat.openai.com/"},
            {"id": "claude", "name": "Claude", "url": "https://claude.ai/new"},
            {"id": "gemini", "name": "Gemini", "url": "https://gemini.google.com/app"},
        ],
        "note": (
            "This is the rendered text only. Guardrails, evals and the model binding are "
            "part of the PromptFile and do not travel with a paste — run it through Assay "
            "if those matter."
        ),
    }


# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------


#: Preference order. models.dev is purpose-built for this — MIT-licensed, 75+ providers,
#: reviewable TOML contributed by pull request. OpenRouter is the fallback because it
#: knows what is actually servable today, which is a different and complementary view.
MODEL_SOURCES = {
    "models.dev": "https://models.dev/api.json",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


class SyncRequest(BaseModel):
    source: str | None = Field(None, description="Override URL. Shape is auto-detected.")


@router.get("/models", summary="The model catalogue, and how fresh it is")
def model_catalogue(workspace: Workspace = Depends(get_workspace)) -> dict:
    catalog = ModelCatalog.autoload(workspace.root)
    models = [
        {
            "ref": f"{m.provider}/{m.id}",
            "provider": m.provider,
            "id": m.id,
            "name": m.display_name,
            "context_window": m.context_window,
            "max_output_tokens": m.max_output_tokens,
            "input_cost_per_mtok": m.input_cost_per_mtok,
            "output_cost_per_mtok": m.output_cost_per_mtok,
            "capabilities": sorted(m.capabilities),
            "deprecated": bool(m.deprecated),
        }
        for m in catalog.all()
    ]
    models.sort(key=lambda m: m["ref"])

    cache = Path(os.getenv("ASSAY_HOME") or (Path.home() / ".assay")) / "models.json"
    synced_at, source = None, None
    if cache.exists():
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            synced_at, source = payload.get("synced_at"), payload.get("source")
        except Exception:
            pass

    return {
        "count": len(models),
        "providers": sorted({m["provider"] for m in models}),
        "models": models,
        "synced_at": synced_at,
        "source": source,
        # A catalogue that has never been synced is running on the small bundled seed.
        # Saying so is the difference between "we support 10 models" and "you have not
        # refreshed yet".
        "is_seed": synced_at is None,
        "sources": MODEL_SOURCES,
    }


@router.post("/models/sync", summary="Refresh the catalogue from a public database")
def sync_models(payload: SyncRequest) -> dict:
    """Try models.dev, fall back to OpenRouter, and report which one answered."""
    import httpx

    from assay_cli.__main__ import _parse_models_dev, _parse_openrouter  # shared parsers

    attempts = (
        [("custom", payload.source)] if payload.source else list(MODEL_SOURCES.items())
    )
    entries: list[dict] = []
    used: str | None = None
    problems: list[str] = []

    for name, url in attempts:
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                body = client.get(url).json()
        except Exception as exc:
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        parsed = (
            _parse_openrouter(body, url)
            if isinstance(body, dict) and "data" in body
            else _parse_models_dev(body, url)
        )
        if parsed:
            entries, used = parsed, url
            break
        problems.append(f"{name}: responded, but no models could be read")

    if not entries:
        raise HTTPException(502, {
            "code": "assay.sync_failed",
            "message": "Could not refresh the catalogue. " + " · ".join(problems),
            "problems": problems,
        })

    from datetime import datetime, timezone

    target = Path(os.getenv("ASSAY_HOME") or (Path.home() / ".assay")) / "models.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "models": entries,
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "source": used,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ModelCatalog.reset()

    return {
        "synced": len(entries),
        "providers": len({e["provider"] for e in entries}),
        "source": used,
        "path": str(target),
        "problems": problems,
    }
