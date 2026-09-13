"""Assay MCP server.

Exposes a prompt workspace to any MCP client — Claude Code, Cowork, Cursor, Zed,
Continue, or your own agent harness.

Protocol strategy
-----------------
This server speaks **both** the session-based revision (``2025-11-25`` and earlier)
and the stateless revision (``2026-07-28``), and it decides which per request rather
than per connection:

* If a request carries ``initialize``, the legacy handshake is honoured.
* If a request carries ``_meta["io.modelcontextprotocol/clientInfo"]`` or the
  ``MCP-Protocol-Version`` header, it is served statelessly — no session required.
* ``server/discover`` is implemented for clients that fetch capabilities up front.

Because the server holds no per-connection state beyond a cached workspace index,
horizontal deployment behind a plain load balancer works without sticky routing.

List results carry ``ttlMs`` and ``cacheScope`` so clients can cache them, and
``tools/list`` schemas are full JSON Schema 2020-12.

Implemented with the standard library only: no MCP SDK dependency, so this server
cannot be broken by an SDK release and runs anywhere Python runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
from typing import Any, Callable

from assay_core import (
    AgentRuntime,
    LoopRuntime,
    AssayError,
    ModelCatalog,
    PromptFile,
    Runtime,
    Workspace,
    __version__,
    disclosure,
)

logger = logging.getLogger("assay.mcp")

SERVER_NAME = "assay"
SERVER_VERSION = "1.0.0"
LATEST_PROTOCOL = "2026-07-28"
SUPPORTED_PROTOCOLS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26")

# JSON-RPC error codes. -32002 was MCP-custom for "resource not found" before
# 2026-07-28 moved it to the standard -32602; we emit the standard code.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND = -32700, -32600, -32601
INVALID_PARAMS, INTERNAL_ERROR = -32602, -32603

LIST_CACHE_MS = 30_000


class MPLServer:
    """Serves one workspace over MCP."""

    def __init__(self, root: str | None = None) -> None:
        self.workspace = Workspace.find(root)
        self.store = self.workspace.store()
        self.runtime = Runtime(workspace=self.workspace)
        self.budget = disclosure.DisclosureBudget.from_config(
            self.workspace.config.get("disclosure")
        )
        self.handlers: dict[str, Callable[[dict], Any]] = {
            "initialize": self.h_initialize,
            "notifications/initialized": lambda p: None,
            "ping": lambda p: {},
            "server/discover": self.h_discover,
            "prompts/list": self.h_prompts_list,
            "prompts/get": self.h_prompts_get,
            "resources/list": self.h_resources_list,
            "resources/read": self.h_resources_read,
            "resources/templates/list": lambda p: {"resourceTemplates": []},
            "tools/list": self.h_tools_list,
            "tools/call": self.h_tools_call,
            "completion/complete": self.h_completion,
        }

    # -- capability description -------------------------------------------

    def _server_info(self, protocol: str) -> dict:
        return {
            "protocolVersion": protocol,
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "Assay",
                "version": SERVER_VERSION,
                "websiteUrl": "https://github.com/BaijayantaRoy/Assay",
            },
            "capabilities": {
                "prompts": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "tools": {"listChanged": False},
                "completions": {},
            },
            "instructions": (
                f"Workspace '{self.workspace.name}' exposes versioned, tested prompts as MCP "
                "prompts. Use prompts/list and prompts/get to pull a maintained prompt instead "
                "of writing one from scratch. Use assay_search to find one by intent, assay_render "
                "to preview it filled in, assay_run to execute it, and assay_test to check it still "
                "passes its evals after an edit."
            ),
        }

    def h_initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion", LATEST_PROTOCOL)
        negotiated = requested if requested in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
        return self._server_info(negotiated)

    def h_discover(self, params: dict) -> dict:
        """``server/discover`` — the stateless replacement for the handshake."""
        return self._server_info(LATEST_PROTOCOL)

    # -- prompts -----------------------------------------------------------

    def _all_prompts(self) -> list:
        loaded = []
        for prompt_id in self.store.list():
            try:
                loaded.append(self.store.get(prompt_id))
            except Exception:
                continue  # a broken file must not break discovery
        return loaded

    def h_prompts_list(self, params: dict) -> dict:
        """Tier-1 only: id, title, one-line summary, typed arguments.

        Full messages, schemas and model bindings arrive at ``prompts/get``. Attachments
        stay at tier 3. This keeps the cost of *having* a large library proportional to
        the number of prompts, not their size — see ``assay_core.disclosure``.

        Ordering is deterministic and content-derived so the prefix stays stable across
        calls; a reshuffled list invalidates the client's prompt cache.
        """
        report = disclosure.build_index(self._all_prompts(), budget=self.budget)

        entries = []
        for entry in report.entries:
            prompt = self.store.get(entry.id)
            entries.append({
                "name": entry.id,
                "title": entry.title,
                # Tier-1 description is the budgeted one-liner, not the full description.
                "description": entry.summary,
                "arguments": _prompt_arguments(prompt),
                "_meta": {
                    "dev.assay/version": entry.version,
                    "dev.assay/status": entry.status,
                    "dev.assay/kind": entry.kind,
                    "dev.assay/tags": entry.tags,
                    "dev.assay/tier": 1,
                },
            })

        meta = {
            "dev.assay/disclosure": {
                "tier": 1,
                "included": report.included,
                "index_tokens": report.index_tokens,
                "naive_tokens": report.full_tokens,
                "saved_tokens": report.saved_tokens,
                "tokens_per_prompt": report.tokens_per_entry,
            }
        }
        meta["dev.assay/namespaces"] = report.namespaces
        if report.omitted:
            # Never truncate silently. The namespace histogram above tells the client the
            # shape of what is not listed, so a follow-up search is informed rather than
            # a guess.
            meta["dev.assay/omitted"] = {
                "count": len(report.omitted),
                "reason": f"tier-1 index budget of {report.budget_tokens} tokens reached",
                "recovery": "call assay_search with a query, or read assay://index, to reach "
                            "prompts not listed here. See namespaces for what exists.",
            }
        return {"prompts": entries, "ttlMs": LIST_CACHE_MS, "cacheScope": "session",
                "_meta": meta}

    def h_prompts_get(self, params: dict) -> dict:
        name = params.get("name")
        if not name:
            raise _rpc(INVALID_PARAMS, "prompts/get requires 'name'")
        try:
            pf = self.store.get(name)
        except AssayError as exc:
            raise _rpc(INVALID_PARAMS, exc.message) from exc

        arguments = params.get("arguments") or {}
        rendered = self.runtime.render(pf, arguments)
        messages = []
        for message in rendered.messages:
            # MCP prompt messages only carry user/assistant; a system message is
            # promoted to a leading user turn so no instruction is silently dropped.
            role = "assistant" if message.role == "assistant" else "user"
            content = message.content if isinstance(message.content, str) else json.dumps(message.content)
            messages.append({"role": role, "content": {"type": "text", "text": content}})

        return {
            "description": _prompt_description(pf),
            "messages": messages,
            "_meta": {
                "dev.assay/version": pf.version,
                "dev.assay/model": pf.model_ref,
            },
        }

    # -- resources ---------------------------------------------------------

    def h_resources_list(self, params: dict) -> dict:
        resources = [{
            "uri": "assay://spec/promptfile-v1",
            "name": "PromptFile v1 specification",
            "description": "The open prompt artifact format this workspace stores.",
            "mimeType": "text/markdown",
        }, {
            "uri": "assay://workspace/config",
            "name": "Workspace configuration",
            "description": "assay.yaml: defaults, providers, plugins, policy.",
            "mimeType": "application/yaml",
        }, {
            "uri": "assay://models",
            "name": "Model catalogue",
            "description": "Known models with context windows, capabilities and pricing.",
            "mimeType": "application/json",
        }, {
            "uri": "assay://index",
            "name": "Prompt index",
            "description": "Compact tier-1 index of every prompt: id, title, one-line "
                           "summary. Read a specific prompt with assay://prompt/<id>.",
            "mimeType": "application/json",
        }]
        # Enumerating every prompt as a resource is the same context leak as an untiered
        # prompts/list. The index resource above is the handle; individual prompt URIs
        # are listed only while the budget allows, and remain readable either way.
        report = disclosure.build_index(self._all_prompts(), budget=self.budget)
        for entry in report.entries:
            resources.append({
                "uri": f"assay://prompt/{entry.id}",
                "name": entry.id,
                "description": entry.summary,
                "mimeType": "text/markdown",
            })
        meta = {}
        if report.omitted:
            meta["dev.assay/omitted"] = {
                "count": len(report.omitted),
                "recovery": "read assay://index for the complete list",
            }
        return {"resources": resources, "ttlMs": LIST_CACHE_MS, "cacheScope": "session",
                "_meta": meta}

    def h_resources_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        if uri == "assay://spec/promptfile-v1":
            from importlib.resources import files

            try:
                document = files("assay_core").joinpath("spec/promptfile-v1.md")
                return _text_resource(uri, document.read_text(encoding="utf-8"),
                                      "text/markdown")
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise RuntimeError("Installed assay-core is missing the PromptFile spec") from exc

        if uri == "assay://index":
            report = disclosure.build_index(self._all_prompts(), budget=self.budget)
            payload = {
                "prompts": [e.to_dict() for e in report.entries],
                "omitted": report.omitted,
                "disclosure": report.to_dict(),
            }
            return _text_resource(uri, json.dumps(payload, indent=2), "application/json")

        if uri == "assay://workspace/config":
            import yaml

            return _text_resource(
                uri, yaml.dump(self.workspace.config, sort_keys=False), "application/yaml"
            )

        if uri == "assay://models":
            catalog = ModelCatalog.autoload(self.workspace.root)
            payload = [
                {"ref": f"{m.provider}/{m.id}", "name": m.display_name,
                 "context_window": m.context_window,
                 "input_cost_per_mtok": m.input_cost_per_mtok,
                 "output_cost_per_mtok": m.output_cost_per_mtok,
                 "capabilities": sorted(m.capabilities)}
                for m in catalog.all()
            ]
            return _text_resource(uri, json.dumps(payload, indent=2), "application/json")

        if uri.startswith("assay://prompt/"):
            prompt_id = uri[len("assay://prompt/"):]
            try:
                pf = self.store.get(prompt_id)
            except AssayError as exc:
                raise _rpc(INVALID_PARAMS, exc.message) from exc
            return _text_resource(uri, pf.to_text(), "text/markdown")

        raise _rpc(INVALID_PARAMS, f"Unknown resource URI: {uri}")

    # -- tools -------------------------------------------------------------

    def h_tools_list(self, params: dict) -> dict:
        return {"tools": TOOLS, "ttlMs": LIST_CACHE_MS, "cacheScope": "session"}

    def h_tools_call(self, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        method = getattr(self, f"tool_{name}", None)
        if method is None:
            raise _rpc(INVALID_PARAMS, f"Unknown tool: {name}")
        try:
            structured = method(args)
        except AssayError as exc:
            return _tool_error(f"{exc.code}: {exc.message}")
        except Exception as exc:
            logger.exception("tool %s failed", name)
            return _tool_error(f"{type(exc).__name__}: {exc}")
        return {
            "content": [{"type": "text", "text": json.dumps(structured, indent=2, default=str)}],
            "structuredContent": structured,
            "isError": False,
        }

    # -- tool implementations ---------------------------------------------

    def tool_assay_search(self, args: dict) -> dict:
        query = (args.get("query") or "").lower()
        tags = set(args.get("tags") or [])
        limit = int(args.get("limit", 20))
        hits = []
        for prompt_id in self.store.list():
            try:
                pf = self.store.get(prompt_id)
            except Exception:
                continue
            if tags and not tags & set(pf.tags):
                continue
            haystack = " ".join([
                pf.id, pf.name, pf.data.get("description") or "",
                " ".join(pf.tags), pf.body[:2000],
            ]).lower()
            if query and query not in haystack:
                # token fallback so multi-word intent still matches
                if not all(token in haystack for token in query.split()):
                    continue
            hits.append({
                "id": pf.id, "name": pf.name,
                "description": pf.data.get("description") or "",
                "version": pf.version, "status": pf.status, "kind": pf.kind,
                "tags": pf.tags, "model": pf.model_ref,
                "variables": sorted(pf.template_variables()),
                "has_evals": bool(pf.evals),
            })
        return {"query": args.get("query", ""), "count": len(hits), "results": hits[:limit]}

    def tool_assay_get(self, args: dict) -> dict:
        pf = self.store.get(args["id"], version=args.get("version"))
        return {"id": pf.id, "version": pf.version, "source": pf.to_text(),
                "variables": sorted(pf.template_variables()),
                "model": pf.model_ref, "status": pf.status}

    def tool_assay_render(self, args: dict) -> dict:
        pf = self.store.get(args["id"])
        rendered = self.runtime.render(pf, args.get("variables") or {}, model=args.get("model"))
        return {"id": pf.id, "version": pf.version, "model": rendered.model,
                "messages": [m.to_dict() for m in rendered.messages],
                "params": rendered.params}

    def _engine_for(self, artifact):
        """Dispatch by kind, exactly as the CLI does.

        Running a harness through the plain prompt runtime produces no trajectory, so
        every trajectory assertion fails for the wrong reason — an agent using this tool
        to check its own edit would be told it broke something it did not. The surfaces
        are meant to be three faces of one engine; this is where that has to be enforced.
        """
        from assay_core import AgentRuntime, LoopRuntime

        if artifact.is_loop:
            return LoopRuntime(self.runtime)
        if artifact.is_harness:
            return AgentRuntime(self.runtime)
        return self.runtime

    def tool_assay_run(self, args: dict) -> dict:
        pf = self.store.get(args["id"])
        variables = args.get("variables") or {}
        model = args.get("model")
        if pf.is_loop:
            return LoopRuntime(self.runtime).run(pf, variables, model=model).to_dict()
        if pf.is_harness:
            return AgentRuntime(self.runtime).run(pf, variables, model=model).to_dict()
        return self.runtime.run(pf, variables, model=model).to_dict()

    def tool_assay_test(self, args: dict) -> dict:
        prompt_id = args.get("id")
        targets = [prompt_id] if prompt_id else list(self.store.list())
        reports = []
        for target in targets:
            pf = self.store.get(target)
            if not pf.evals:
                reports.append({
                    "prompt_id": pf.id, "prompt_version": pf.version,
                    "passed": None, "score": None, "usable": False,
                    "cases": [], "total_assertions": 0, "failed_assertions": 0,
                    "unverified_cases": 0, "total_cost_usd": 0.0,
                    "error": "no eval cases defined",
                })
                continue
            engine = self._engine_for(pf)
            max_workers = int(args.get("max_workers", 1))
            if not 1 <= max_workers <= 32:
                raise ValueError("max_workers must be between 1 and 32")
            if not pf.is_agentic and max_workers > 1:
                reports.append(asyncio.run(engine.aevaluate(
                    pf, model=args.get("model"), max_concurrency=max_workers
                )))
            else:
                reports.append(engine.evaluate(pf, model=args.get("model")))
        failed = sum(1 for report in reports if report["passed"] is False)
        unverified = sum(1 for report in reports if report["passed"] is None)
        passed = False if failed else (None if unverified else True)
        return {
            "passed": passed,
            "prompts_tested": len(reports) - unverified,
            "prompts_unverified": unverified,
            "failed": failed,
            "reports": reports,
        }

    def tool_assay_lint(self, args: dict) -> dict:
        problems = []
        for prompt_id in self.store.list():
            pf = self.store.get(prompt_id)
            for message in pf.validate(strict=True):
                problems.append({"id": pf.id, "message": message})
        return {"clean": not problems, "problems": problems}

    def tool_assay_create(self, args: dict) -> dict:
        data = {
            "promptfile":  1,
            "id": args["id"],
            "name": args.get("name") or args["id"].rsplit("/", 1)[-1],
            "description": args.get("description", ""),
            "version": 1,
            "kind": args.get("kind", "prompt"),
            "status": "draft",
            "tags": args.get("tags") or [],
            "engine": {"template": "jinja2", "strict": True},
        }
        if args.get("model"):
            data["model"] = {"primary": args["model"]}
        pf = PromptFile(data=data, body=args.get("body", ""))
        self.store.put(pf, message=args.get("commit_message"))
        return {"id": pf.id, "path": str(pf.path), "version": pf.version}

    def tool_assay_update(self, args: dict) -> dict:
        pf = self.store.get(args["id"])
        if "body" in args:
            pf.body = args["body"]
        for key in ("name", "description", "status", "tags"):
            if key in args:
                pf.data[key] = args[key]
        if args.get("model"):
            pf.data.setdefault("model", {})["primary"] = args["model"]
        pf.bump(message=args.get("commit_message"))
        self.store.put(pf, message=args.get("commit_message"))
        return {"id": pf.id, "version": pf.version, "path": str(pf.path)}

    def tool_assay_models(self, args: dict) -> dict:
        catalog = ModelCatalog.autoload(self.workspace.root)
        models = catalog.all()
        if args.get("provider"):
            models = [m for m in models if m.provider == args["provider"]]
        return {"count": len(models), "models": [
            {"ref": f"{m.provider}/{m.id}", "name": m.display_name,
             "context_window": m.context_window,
             "input_cost_per_mtok": m.input_cost_per_mtok,
             "output_cost_per_mtok": m.output_cost_per_mtok,
             "capabilities": sorted(m.capabilities)}
            for m in models
        ]}

    # -- completions -------------------------------------------------------

    def h_completion(self, params: dict) -> dict:
        """Argument autocompletion for prompt variables."""
        ref = params.get("ref") or {}
        if ref.get("type") != "ref/prompt":
            return {"completion": {"values": [], "hasMore": False}}
        try:
            pf = self.store.get(ref.get("name", ""))
        except Exception:
            return {"completion": {"values": [], "hasMore": False}}
        typed = (params.get("argument") or {}).get("value", "")
        examples = (pf.data.get("input") or {}).get("examples") or []
        arg_name = (params.get("argument") or {}).get("name", "")
        values = [str(e.get(arg_name)) for e in examples if arg_name in e]
        values = [v for v in values if v.startswith(typed)][:100]
        return {"completion": {"values": values, "hasMore": False}}

    # -- dispatch ----------------------------------------------------------

    def handle(self, request: dict) -> dict | None:
        method = request.get("method")
        request_id = request.get("id")
        if method not in self.handlers:
            if request_id is None:
                return None
            return _error(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}")
        try:
            result = self.handlers[method](request.get("params") or {})
        except _RpcError as exc:
            return _error(request_id, exc.code, exc.message) if request_id is not None else None
        except Exception as exc:
            logger.error("handler %s failed: %s\n%s", method, exc, traceback.format_exc())
            if request_id is None:
                return None
            return _error(request_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result if result is not None else {}}


# ---------------------------------------------------------------------------
# tool schemas — full JSON Schema 2020-12
# ---------------------------------------------------------------------------

_VARIABLES = {"type": "object", "description": "Template variables.", "additionalProperties": True}

TOOLS: list[dict] = [
    {
        "name": "assay_search",
        "title": "Search prompts",
        "description": "Find a maintained prompt by intent, keyword, or tag. Prefer this over "
                       "writing a prompt from scratch — results are versioned and eval-tested.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the prompt should do."},
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "assay_get",
        "title": "Get prompt source",
        "description": "Return the full PromptFile source for one prompt, optionally at a "
                       "specific version from git history.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": ["id"],
            "properties": {"id": {"type": "string"}, "version": {"type": "integer", "minimum": 1}},
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "assay_render",
        "title": "Render prompt",
        "description": "Fill a prompt's variables and return the exact messages that would be "
                       "sent to a model. Does not call any model.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": ["id"],
            "properties": {"id": {"type": "string"}, "variables": _VARIABLES,
                           "model": {"type": "string"}},
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "assay_run",
        "title": "Run prompt",
        "description": "Execute a prompt against a model and return output, tokens, latency "
                       "and cost. Requires provider credentials in the server environment.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": ["id"],
            "properties": {"id": {"type": "string"}, "variables": _VARIABLES,
                           "model": {"type": "string",
                                     "description": "Override, e.g. anthropic/claude-opus-5."}},
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "assay_test",
        "title": "Run prompt evals",
        "description": "Run the embedded eval cases for one prompt or the whole workspace. "
                       "Use after editing a prompt to confirm nothing regressed.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "model": {"type": "string"},
                "max_workers": {
                    "type": "integer", "minimum": 1, "maximum": 32, "default": 1,
                    "description": "Bounded concurrent cases for kind: prompt.",
                },
            },
        },
        "annotations": {"readOnlyHint": False, "openWorldHint": True},
    },
    {
        "name": "assay_lint",
        "title": "Lint workspace",
        "description": "Validate every prompt against the PromptFile schema and style rules.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "properties": {},
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "assay_create",
        "title": "Create prompt",
        "description": "Write a new PromptFile into the workspace and optionally commit it.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": ["id", "body"],
            "properties": {
                "id": {"type": "string", "maxLength": 512,
                       "pattern": "^[a-z0-9]([a-z0-9._-]*[a-z0-9])?(/[a-z0-9]([a-z0-9._-]*[a-z0-9])?)*$"},
                "body": {"type": "string"},
                "name": {"type": "string"}, "description": {"type": "string"},
                "kind": {"type": "string", "default": "prompt"},
                "model": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "commit_message": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    },
    {
        "name": "assay_update",
        "title": "Update prompt",
        "description": "Edit an existing prompt, bump its version, and optionally commit.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": ["id"],
            "properties": {
                "id": {"type": "string"}, "body": {"type": "string"},
                "name": {"type": "string"}, "description": {"type": "string"},
                "status": {"type": "string",
                           "enum": ["draft", "review", "stable", "deprecated", "archived"]},
                "tags": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"}, "commit_message": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "assay_models",
        "title": "List models",
        "description": "Model catalogue with context windows, capabilities and per-token pricing.",
        "inputSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "properties": {"provider": {"type": "string"}},
        },
        "annotations": {"readOnlyHint": True},
    },
]


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _rpc(code: int, message: str) -> _RpcError:
    return _RpcError(code, message)


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _text_resource(uri: str, text: str, mime: str) -> dict:
    return {"contents": [{"uri": uri, "mimeType": mime, "text": text}],
            "ttlMs": LIST_CACHE_MS, "cacheScope": "session"}


def _prompt_description(pf: PromptFile) -> str:
    base = pf.data.get("description") or pf.name
    return f"{base} (v{pf.version}, {pf.status})"


def _prompt_arguments(pf: PromptFile) -> list[dict]:
    schema = pf.input_schema or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if properties:
        return [
            {"name": key, "description": spec.get("description", spec.get("type", "")),
             "required": key in required}
            for key, spec in properties.items()
        ]
    return [{"name": v, "description": "", "required": True}
            for v in sorted(pf.template_variables())]


def serve_stdio(server: MPLServer) -> int:
    """Newline-delimited JSON-RPC over stdin/stdout — the default MCP transport.

    Per the 2026-07-28 deprecation of the ``logging`` capability, diagnostics go to
    stderr rather than travelling over the protocol.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                        format="assay-mcp %(levelname)s %(message)s")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_error(None, PARSE_ERROR, str(exc))) + "\n")
            sys.stdout.flush()
            continue
        batch = request if isinstance(request, list) else [request]
        responses = [r for r in (server.handle(item) for item in batch) if r is not None]
        for response in responses:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
        sys.stdout.flush()
    return 0


def serve_http(server: MPLServer, host: str, port: int) -> int:
    """Streamable-HTTP transport, stateless: any request can hit any instance.

    Honours ``Mcp-Method``/``Mcp-Name`` routing headers when present and rejects
    requests where the headers disagree with the body, as the spec requires.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._send(400, _error(None, PARSE_ERROR, str(exc)))

            declared = self.headers.get("Mcp-Method")
            if declared and isinstance(payload, dict) and payload.get("method") != declared:
                return self._send(
                    400, _error(payload.get("id"), INVALID_REQUEST,
                                "Mcp-Method header disagrees with request body"),
                )
            batch = payload if isinstance(payload, list) else [payload]
            responses = [r for r in (server.handle(item) for item in batch) if r is not None]
            if not responses:
                return self._send(202, None)
            return self._send(200, responses if isinstance(payload, list) else responses[0])

        def do_GET(self):  # noqa: N802
            self._send(200, {"server": SERVER_NAME, "version": SERVER_VERSION,
                             "protocols": list(SUPPORTED_PROTOCOLS)})

        def _send(self, status: int, body):
            data = b"" if body is None else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("MCP-Protocol-Version", LATEST_PROTOCOL)
            self.end_headers()
            if data:
                self.wfile.write(data)

    print(f"assay-mcp listening on http://{host}:{port}", file=sys.stderr)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
    return 0


def main(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765,
         root: str | None = None) -> int:
    server = MPLServer(root)
    if transport == "http":
        return serve_http(server, host, port)
    return serve_stdio(server)


if __name__ == "__main__":
    raise SystemExit(main())
