"""End-to-end fixtures.

These tests drive the product the way a user does: the installed ``assay`` binary through
a subprocess, a real HTTP server on a real port, a real MCP process over stdio. Nothing
here imports ``assay_core`` to do the work — if a test can pass by calling Python directly,
it belongs in ``packages/assay-core/tests`` instead.

That distinction matters. Every bug found in this project so far that reached a *user*
was in the seam between components: a batch file that closed silently, a `.next` cache
deleted on every start, a red-team report showing 0% because nothing ran. In-process
tests cannot see any of those.

No API key is needed anywhere: the offline ``echo`` provider makes the whole surface
exercisable, so this suite runs on a fork with no secrets.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT = 45


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end test using real processes")


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


SAMPLE_PROMPT = """---
promptfile: 1
id: e2e/greet
name: Greet
summary: A minimal prompt used by the end-to-end suite.
description: Greets someone by name.
version: 1
kind: prompt
status: stable
tags: [e2e]
engine: { template: jinja2, strict: true }
input:
  schema:
    type: object
    required: [name]
    properties:
      name: { type: string }
model:
  primary: echo/echo
  params: { temperature: 0 }
evals:
  - id: says-the-name
    input: { name: Ada }
    assert:
      - { type: contains, value: Ada }
      - { type: cost_under, value: 1.0 }
---

Say hello to {{ name }}.
"""

SAMPLE_HARNESS = """---
promptfile: 1
id: e2e/agent
name: E2E Agent
summary: A scripted harness used by the end-to-end suite.
kind: harness
status: stable
model:
  primary: echo/agent
  provider_params:
    echo:
      script:
        - { tool: mock.search, arguments: { query: notes } }
        - { text: "Found the answer in billing/invoice.py." }
harness:
  stream_model_calls: true
  max_iterations: 4
  budget: { cost_usd: 1.0, wallclock_s: 30 }
  control:
    deny: [shell.run, http.get]
    max_repeated_calls: 2
    mock_responses:
      mock.search: "billing/invoice.py:42 has the retry logic"
  memory:
    backend: jsonl
    namespace: e2e
    recall: { limit: 3 }
tools:
  - { ref: mock.search }
evals:
  - id: searches-first
    input: { goal: find the retry logic }
    assert:
      - { type: tool_called, value: mock.search }
      - type: trajectory_accuracy
        value:
          - { tool: mock.search, arguments: { query: notes } }
      - { type: iterations_under, value: 4 }
      - { type: completed }
---

Investigate: {{ goal }}
"""

SAMPLE_LOOP = """---
promptfile: 1
id: e2e/loop
name: E2E Loop
summary: A verified two-step loop used by the end-to-end suite.
kind: loop
status: stable
loop:
  goal: the artifact exists
  max_cycles: 2
  steps:
    - id: build
      command: "echo built > artifact.txt"
      verify:
        command: 'python -c "import pathlib,sys; p=pathlib.Path(sys.argv[1]); raise SystemExit(not (p.is_file() and p.stat().st_size > 0))" artifact.txt'
        success_when: { type: exit_code, value: 0 }
      on_error: stop
  verify:
    command: 'python -c "import pathlib,sys; p=pathlib.Path(sys.argv[1]); raise SystemExit(not (p.is_file() and p.stat().st_size > 0))" artifact.txt'
    success_when: { type: exit_code, value: 0 }
evals:
  - id: converges
    assert:
      - { type: goal_met }
      - { type: steps_verified }
---

Build and verify.
"""


@pytest.fixture(scope="session")
def assay_bin() -> str:
    """Path to the installed CLI. Skips the suite if it is not on PATH.

    Deliberately the *binary*, not ``python -m``: a broken entry point is a real user
    failure that importing the module would hide.
    """
    configured = os.getenv("ASSAY_BIN")
    sibling = Path(sys.executable).with_name(
        "assay.exe" if os.name == "nt" else "assay"
    )
    found = (
        configured if configured and Path(configured).is_file()
        else str(sibling) if sibling.is_file()
        else shutil.which("assay")
    )
    if not found:
        pytest.skip("assay CLI not installed; run: pip install -e packages/assay-cli")
    return found


def _build_workspace(root: Path) -> Path:
    """Populate a directory with one prompt, one harness and one loop."""
    (root / "prompts").mkdir(exist_ok=True)
    (root / "assay.yaml").write_text(
        "promptfile: 1\nname: e2e\nprompts: ./prompts\ndefaults:\n  model: echo/echo\n",
        encoding="utf-8",
    )
    (root / "prompts" / "greet.prompt.md").write_text(SAMPLE_PROMPT, encoding="utf-8")
    (root / "prompts" / "agent.prompt.md").write_text(SAMPLE_HARNESS, encoding="utf-8")
    (root / "prompts" / "loop.prompt.md").write_text(SAMPLE_LOOP, encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def shared_workspace(tmp_path_factory) -> Path:
    """One workspace for the whole session.

    Starting uvicorn per test would add several seconds each; a shared workspace lets the
    server start once. Tests using it must therefore be additive — create new ids, never
    invalidate existing ones — which is also how a real workspace behaves.
    """
    return _build_workspace(tmp_path_factory.mktemp("e2e-shared"))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A throwaway workspace per test, for anything destructive."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "assay.yaml").write_text(
        "promptfile: 1\nname: e2e\nprompts: ./prompts\ndefaults:\n  model: echo/echo\n",
        encoding="utf-8",
    )
    (tmp_path / "prompts" / "greet.prompt.md").write_text(SAMPLE_PROMPT, encoding="utf-8")
    (tmp_path / "prompts" / "agent.prompt.md").write_text(SAMPLE_HARNESS, encoding="utf-8")
    (tmp_path / "prompts" / "loop.prompt.md").write_text(SAMPLE_LOOP, encoding="utf-8")
    return tmp_path


@pytest.fixture
def run_assay(assay_bin, workspace):
    """Invoke the real CLI in the workspace and return (returncode, stdout, stderr)."""

    def _run(*args: str, timeout: int = 120, cwd: Path | None = None, **env_extra):
        env = {
            **os.environ,
            "ASSAY_MEMORY_ROOT": str(workspace / ".assay" / "memory"),
            "NO_COLOR": "1",
            **{k: str(v) for k, v in env_extra.items()},
        }
        proc = subprocess.run(
            [assay_bin, *args],
            cwd=str(cwd or workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr

    return _run


def run_json(run_assay, *args: str):
    """Run the CLI with ``--json`` and parse. Fails loudly on unparseable output."""
    code, out, err = run_assay(*args, "--json")
    try:
        return code, json.loads(out)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"`assay {' '.join(args)} --json` did not emit JSON "
            f"(exit {code})\nstdout:\n{out[:2000]}\nstderr:\n{err[:2000]}"
        ) from exc


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: int = STARTUP_TIMEOUT) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def _spawn_api_server(workspace_root: Path):
    """Start uvicorn against ``workspace_root`` as a subprocess; yield the base URL.

    Shared by every fixture that needs a live server, so startup, the lifespan hook,
    port binding and process teardown are all covered the same way everywhere — the
    parts a TestClient quietly skips.
    """
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    # No chromadb check: the app now degrades semantic search rather than refusing to
    # import, so /v1 runs with a small dependency set.

    port = _free_port()
    env = {
        **os.environ,
        "ASSAY_WORKSPACE": str(workspace_root),
        "ASSAY_MEMORY_ROOT": str(workspace_root / ".assay" / "memory"),
        "PYTHONUNBUFFERED": "1",
    }
    log = workspace_root / "api.log"
    with log.open("wb") as handle:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(REPO_ROOT), env=env, stdout=handle, stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_http(f"{base}/health"):
            proc.terminate()
            pytest.fail(
                f"API did not start within {STARTUP_TIMEOUT}s.\n"
                f"{log.read_text(errors='replace')[-3000:]}"
            )
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


@pytest.fixture(scope="session")
def api_server(shared_workspace):
    """A real uvicorn process serving the API against the throwaway workspace."""
    yield from _spawn_api_server(shared_workspace)


@pytest.fixture
def audited_workspace(workspace: Path) -> Path:
    """The throwaway per-test workspace, with ``governance.audit`` turned on.

    A separate fixture rather than flipping it on ``shared_workspace``: that workspace
    is reused for the whole session, and auditing is off by default specifically so
    tests against the default configuration keep exercising the default. Only the one
    test that needs to prove auditing actually records something asks for this.
    """
    (workspace / "assay.yaml").write_text(
        "promptfile: 1\nname: e2e\nprompts: ./prompts\ndefaults:\n  model: echo/echo\n"
        "governance:\n  audit: true\n",
        encoding="utf-8",
    )
    return workspace


@pytest.fixture
def audited_api_server(audited_workspace):
    """A short-lived server for the one test that needs auditing turned on."""
    yield from _spawn_api_server(audited_workspace)


@pytest.fixture
def http():
    """Minimal HTTP helper. stdlib only, so the suite has no extra dependency."""
    import urllib.error
    import urllib.request

    def _request(method: str, url: str, payload=None, timeout: int = 60):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        def _decode(status, body):
            # /docs serves HTML. Returning the raw text beats exploding on it.
            if not body:
                return status, None
            try:
                return status, json.loads(body)
            except json.JSONDecodeError:
                return status, body

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return _decode(response.status, response.read().decode())
            except urllib.error.HTTPError as exc:
                return _decode(exc.code, exc.read().decode())
            except (ConnectionResetError, TimeoutError, urllib.error.URLError):
                # Windows can reset a fresh loopback connection after Uvicorn has already
                # completed a large response (notably OpenAPI). Retry only idempotent reads;
                # a mutating request must never be replayed implicitly.
                if method != "GET" or attempt == 2:
                    raise
                time.sleep(0.1 * (attempt + 1))
        raise AssertionError("unreachable HTTP retry state")

    return _request


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_call(workspace):
    """Send JSON-RPC requests to a real MCP server subprocess over stdio."""

    def _call(*requests: dict, timeout: int = 60) -> dict:
        env = {
            **os.environ,
            "ASSAY_WORKSPACE": str(workspace),
            "ASSAY_MEMORY_ROOT": str(workspace / ".assay" / "memory"),
        }
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, "-m", "assay_mcp.server"],
            input=payload, capture_output=True, text=True,
            cwd=str(workspace), env=env, timeout=timeout,
        )
        responses = {}
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:  # pragma: no cover
                continue
            if "id" in message:
                responses[message["id"]] = message
        if not responses:
            raise AssertionError(
                f"MCP server returned nothing.\nstdout:\n{proc.stdout[:2000]}\n"
                f"stderr:\n{proc.stderr[:2000]}"
            )
        return responses

    return _call


# ---------------------------------------------------------------------------
# Shared-workspace variants, so parity tests compare surfaces over one directory
# ---------------------------------------------------------------------------


@pytest.fixture
def run_assay_shared(assay_bin, shared_workspace):
    """The CLI, pointed at the same workspace the API server serves."""

    def _run(*args: str, timeout: int = 120, **env_extra):
        env = {
            **os.environ,
            "ASSAY_MEMORY_ROOT": str(shared_workspace / ".assay" / "memory"),
            "NO_COLOR": "1",
            **{k: str(v) for k, v in env_extra.items()},
        }
        proc = subprocess.run(
            [assay_bin, *args], cwd=str(shared_workspace),
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr

    return _run


@pytest.fixture
def mcp_call_shared(shared_workspace):
    """The MCP server, pointed at the same workspace the API server serves."""

    def _call(*requests: dict, timeout: int = 60) -> dict:
        env = {
            **os.environ,
            "ASSAY_WORKSPACE": str(shared_workspace),
            "ASSAY_MEMORY_ROOT": str(shared_workspace / ".assay" / "memory"),
        }
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, "-m", "assay_mcp.server"],
            input=payload, capture_output=True, text=True,
            cwd=str(shared_workspace), env=env, timeout=timeout,
        )
        responses = {}
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in message:
                responses[message["id"]] = message
        if not responses:
            raise AssertionError(
                f"MCP server returned nothing.\nstdout:\n{proc.stdout[:2000]}\n"
                f"stderr:\n{proc.stderr[:2000]}"
            )
        return responses

    return _call
