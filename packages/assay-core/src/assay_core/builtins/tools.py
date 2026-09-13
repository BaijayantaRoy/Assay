"""Built-in tool providers (``assay.tools``).

The tool interface is one of the four elements of an agent harness. These built-ins
follow the pattern that has repeatedly outperformed large bespoke tool catalogues:
**expose a filesystem and a few general verbs rather than one tool per task.** A model
that can `read`, `grep`, `list` and `write` can accomplish things nobody wrote a tool
for; a model with forty narrow tools can only do the forty things anticipated.

Every tool here is sandboxed to a root directory and returns errors rather than raising,
so the model can see a failure and recover instead of the run aborting.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from ..contracts import CONTRACT_VERSION, ToolCall, ToolResult

MAX_OUTPUT_CHARS = 30_000
MAX_FILE_BYTES = 2_000_000


def _ok(call: ToolCall, content: str, started: float) -> ToolResult:
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + f"\n… [truncated at {MAX_OUTPUT_CHARS} chars]"
    return ToolResult(call=call, content=content,
                      latency_ms=int((time.perf_counter() - started) * 1000))


def _err(call: ToolCall, message: str, started: float) -> ToolResult:
    return ToolResult(call=call, content=message, is_error=True,
                      latency_ms=int((time.perf_counter() - started) * 1000))


class _Sandboxed:
    """Shared path containment. Every filesystem tool resolves through this."""

    def _root(self, context: dict) -> Path:
        return Path(context.get("sandbox_root") or os.getcwd()).resolve()

    def _resolve(self, context: dict, relative: str) -> Path:
        root = self._root(context)
        candidate = (root / relative).resolve()
        # Containment check must happen after resolution so that symlinks and
        # ../ traversal are both caught.
        if root != candidate and root not in candidate.parents:
            raise PermissionError(f"path escapes sandbox root: {relative}")
        return candidate


class FileSystemTools(_Sandboxed):
    """``fs.*`` — read, write, list, grep, glob within a sandbox root."""

    id = "fs"
    contract_version = CONTRACT_VERSION

    def list_tools(self) -> Iterable[dict]:
        return [
            {
                "name": "fs.read",
                "description": "Read a UTF-8 text file. Returns numbered lines.",
                "input_schema": {
                    "type": "object", "required": ["path"],
                    "properties": {
                        "path": {"type": "string", "description": "Path relative to the root."},
                        "start": {"type": "integer", "minimum": 1},
                        "limit": {"type": "integer", "minimum": 1, "default": 500},
                    },
                },
            },
            {
                "name": "fs.write",
                "description": "Write a UTF-8 text file, creating parent directories.",
                "input_schema": {
                    "type": "object", "required": ["path", "content"],
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                },
            },
            {
                "name": "fs.list",
                "description": "List directory entries.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": "."}},
                },
            },
            {
                "name": "fs.glob",
                "description": "Find files matching a glob pattern, e.g. '**/*.py'.",
                "input_schema": {
                    "type": "object", "required": ["pattern"],
                    "properties": {"pattern": {"type": "string"},
                                   "limit": {"type": "integer", "default": 200}},
                },
            },
            {
                "name": "fs.grep",
                "description": "Search file contents with a regular expression.",
                "input_schema": {
                    "type": "object", "required": ["pattern"],
                    "properties": {
                        "pattern": {"type": "string"},
                        "glob": {"type": "string", "default": "**/*"},
                        "limit": {"type": "integer", "default": 100},
                        "ignore_case": {"type": "boolean", "default": False},
                    },
                },
            },
        ]

    def call(self, name: str, arguments: dict, *, context: dict) -> ToolResult:
        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        try:
            handler = {
                "fs.read": self._read, "fs.write": self._write, "fs.list": self._list,
                "fs.glob": self._glob, "fs.grep": self._grep,
            }.get(name)
            if handler is None:
                return _err(call, f"unknown tool {name!r}", started)
            return _ok(call, handler(arguments, context), started)
        except PermissionError as exc:
            return _err(call, f"denied: {exc}", started)
        except FileNotFoundError as exc:
            return _err(call, f"not found: {exc}", started)
        except Exception as exc:
            return _err(call, f"{type(exc).__name__}: {exc}", started)

    # -- handlers ----------------------------------------------------------

    def _read(self, args: dict, context: dict) -> str:
        path = self._resolve(context, args["path"])
        if not path.is_file():
            raise FileNotFoundError(args["path"])
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes; use fs.grep instead")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(args.get("start", 1)))
        limit = int(args.get("limit", 500))
        window = lines[start - 1: start - 1 + limit]
        numbered = "\n".join(f"{start + i:>5}  {line}" for i, line in enumerate(window))
        suffix = "" if start - 1 + limit >= len(lines) else f"\n… {len(lines)} lines total"
        return numbered + suffix

    def _write(self, args: dict, context: dict) -> str:
        path = self._resolve(context, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = args["content"]
        path.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {args['path']}"

    def _list(self, args: dict, context: dict) -> str:
        path = self._resolve(context, args.get("path", "."))
        if not path.is_dir():
            raise FileNotFoundError(args.get("path", "."))
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        return "\n".join(
            f"{'dir ' if e.is_dir() else 'file'}  {e.name}" for e in entries
        ) or "(empty)"

    def _glob(self, args: dict, context: dict) -> str:
        root = self._root(context)
        limit = int(args.get("limit", 200))
        matches = [
            str(p.relative_to(root)) for p in root.glob(args["pattern"])
            if p.is_file() and not any(part.startswith(".") for part in p.parts)
        ][:limit]
        return "\n".join(matches) or "(no matches)"

    def _grep(self, args: dict, context: dict) -> str:
        root = self._root(context)
        flags = re.IGNORECASE if args.get("ignore_case") else 0
        pattern = re.compile(args["pattern"], flags)
        limit = int(args.get("limit", 100))
        glob = args.get("glob", "**/*")
        hits: list[str] = []
        for path in root.glob(glob):
            if not path.is_file() or any(part.startswith(".") for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(root)}:{number}: {line.strip()[:200]}")
                    if len(hits) >= limit:
                        return "\n".join(hits) + f"\n… stopped at {limit} matches"
        return "\n".join(hits) or "(no matches)"


class ShellTools(_Sandboxed):
    """``shell.run`` — execute a command in the sandbox root.

    Deliberately the most dangerous built-in, and therefore the one most worth gating.
    Harness files should list it under ``control.require_approval`` or restrict it with
    ``control.allow_commands``. It refuses to run at all unless the harness opts in via
    ``control.allow_shell: true``.
    """

    id = "shell"
    contract_version = CONTRACT_VERSION

    def list_tools(self) -> Iterable[dict]:
        return [{
            "name": "shell.run",
            "description": "Run a shell command in the workspace root and return its output.",
            "input_schema": {
                "type": "object", "required": ["command"],
                "properties": {
                    "command": {"type": "string"},
                    "timeout_s": {"type": "integer", "default": 60, "maximum": 600},
                },
            },
        }]

    def call(self, name: str, arguments: dict, *, context: dict) -> ToolResult:
        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        if name != "shell.run":
            return _err(call, f"unknown tool {name!r}", started)
        if not context.get("allow_shell"):
            return _err(
                call,
                "shell is disabled for this harness. Set control.allow_shell: true to enable.",
                started,
            )
        command = arguments.get("command", "")
        allow = context.get("allow_commands")
        if allow and not any(fnmatch.fnmatch(command, pattern) for pattern in allow):
            return _err(call, f"command not permitted by control.allow_commands: {command!r}",
                        started)
        try:
            result = subprocess.run(
                command, shell=True, cwd=self._root(context), capture_output=True,
                text=True, timeout=min(int(arguments.get("timeout_s", 60)), 600),
            )
        except subprocess.TimeoutExpired:
            return _err(call, "command timed out", started)
        except Exception as exc:
            return _err(call, f"{type(exc).__name__}: {exc}", started)

        body = f"exit_code: {result.returncode}\n"
        if result.stdout:
            body += f"\nstdout:\n{result.stdout}"
        if result.stderr:
            body += f"\nstderr:\n{result.stderr}"
        outcome = _ok(call, body, started)
        outcome.is_error = result.returncode != 0
        return outcome


class HttpTools:
    """``http.get`` — fetch a URL. Restricted by an allow list, never open by default."""

    id = "http"
    contract_version = CONTRACT_VERSION

    def list_tools(self) -> Iterable[dict]:
        return [{
            "name": "http.get",
            "description": "HTTP GET a URL and return the response body as text.",
            "input_schema": {
                "type": "object", "required": ["url"],
                "properties": {"url": {"type": "string", "format": "uri"}},
            },
        }]

    def call(self, name: str, arguments: dict, *, context: dict) -> ToolResult:
        import httpx

        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        if name != "http.get":
            return _err(call, f"unknown tool {name!r}", started)

        url = arguments.get("url", "")
        allow = context.get("allow_hosts")
        if not allow:
            return _err(
                call,
                "http is disabled. Set control.allow_hosts to a list of permitted hostnames.",
                started,
            )
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        if not any(fnmatch.fnmatch(host, pattern) for pattern in allow):
            return _err(call, f"host {host!r} is not in control.allow_hosts", started)
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                response = client.get(url)
            return _ok(call, f"status: {response.status_code}\n\n{response.text}", started)
        except Exception as exc:
            return _err(call, f"{type(exc).__name__}: {exc}", started)


class PromptTools:
    """``prompt.*`` — let a harness call the prompt library itself.

    This is what makes sub-agent delegation work: a harness can search for a maintained
    prompt and run it as a step, instead of inlining an untested prompt into its own
    reasoning.
    """

    id = "prompt"
    contract_version = CONTRACT_VERSION

    def list_tools(self) -> Iterable[dict]:
        return [
            {
                "name": "prompt.search",
                "description": "Find a maintained prompt in the library by keyword.",
                "input_schema": {
                    "type": "object", "required": ["query"],
                    "properties": {"query": {"type": "string"},
                                   "limit": {"type": "integer", "default": 10}},
                },
            },
            {
                "name": "prompt.run",
                "description": "Execute a library prompt as a sub-task and return its output.",
                "input_schema": {
                    "type": "object", "required": ["id"],
                    "properties": {"id": {"type": "string"},
                                   "variables": {"type": "object", "additionalProperties": True}},
                },
            },
        ]

    def call(self, name: str, arguments: dict, *, context: dict) -> ToolResult:
        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        store = context.get("store")
        runtime = context.get("runtime")
        if store is None or runtime is None:
            return _err(call, "prompt tools require a workspace store and runtime", started)
        try:
            if name == "prompt.search":
                query = (arguments.get("query") or "").lower()
                limit = int(arguments.get("limit", 10))
                hits = []
                for prompt_id in store.list():
                    pf = store.get(prompt_id)
                    haystack = f"{pf.id} {pf.name} {pf.data.get('description','')} {' '.join(pf.tags)}".lower()
                    if not query or query in haystack or all(t in haystack for t in query.split()):
                        hits.append(f"{pf.id} — {pf.data.get('description') or pf.name}")
                return _ok(call, "\n".join(hits[:limit]) or "(no matches)", started)

            if name == "prompt.run":
                pf = store.get(arguments["id"])
                result = runtime.run(pf, arguments.get("variables") or {})
                # Sub-task spend must roll up into the parent trajectory's budget.
                context.setdefault("subtask_cost", 0.0)
                context["subtask_cost"] += result.cost_usd
                return _ok(call, result.text, started)

            return _err(call, f"unknown tool {name!r}", started)
        except Exception as exc:
            return _err(call, f"{type(exc).__name__}: {exc}", started)


class MockTools:
    """``mock.*`` — deterministic tools for testing harnesses offline.

    Responses come from ``control.mock_responses`` in the harness file, so a harness's
    trajectory tests run in CI with no filesystem, no network, and no API key.
    """

    id = "mock"
    contract_version = CONTRACT_VERSION

    def list_tools(self) -> Iterable[dict]:
        return [
            {
                "name": "mock.search",
                "description": "Search a fixed corpus. Deterministic; for tests.",
                "input_schema": {
                    "type": "object", "required": ["query"],
                    "properties": {"query": {"type": "string"}},
                },
            },
            {
                "name": "mock.fetch",
                "description": "Fetch a fixed document by id. Deterministic; for tests.",
                "input_schema": {
                    "type": "object", "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
            },
            {
                "name": "mock.fail",
                "description": "Always returns an error. Exercises recovery paths.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    def call(self, name: str, arguments: dict, *, context: dict) -> ToolResult:
        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        if name == "mock.fail":
            return _err(call, "mock failure, as requested", started)
        responses = context.get("mock_responses") or {}
        if name in responses:
            value = responses[name]
            return _ok(call, value if isinstance(value, str) else json.dumps(value), started)
        key = arguments.get("query") or arguments.get("id") or ""
        return _ok(call, f"[mock:{name}] {key}", started)
