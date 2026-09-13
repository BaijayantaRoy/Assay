# End-to-end suite

These tests drive the product the way a user does: the installed `assay` **binary** through
a subprocess, a real HTTP server on a real port, a real MCP process over stdio.

Nothing here calls `assay_core` to do the work. If a test can pass by importing Python
directly, it belongs in `packages/assay-core/tests` instead.

## Why it exists

Every bug in this project that reached a *user* lived in a seam between components, and
none of them were visible to in-process tests:

| Bug | What in-process tests saw |
|:--|:--|
| Batch file closed with no message | nothing — it isn't Python |
| `.next` cache deleted every start, so the UI never came up | nothing — it's a launcher |
| Red-team reported 0% ASR while every attack errored | a passing unit test |
| MCP `assay_test` evaluated harnesses as plain prompts | CLI tests passed; MCP was never compared |

That last one is why `test_parity_e2e.py` exists. The architecture claims the CLI, REST
API and MCP server are "three faces of one engine". It was false, and only a test that
ran the same artifact through all three could tell.

## Running

```bash
pip install -e packages/assay-core -e packages/assay-cli -e packages/assay-mcp
pip install -r backend/requirements-dev.txt

pytest tests/e2e -v                      # everything
pytest tests/e2e/test_cli_e2e.py -v      # one surface
pytest -m e2e                            # by marker
pytest -m "not e2e"                      # unit tests only, much faster
```

No API key is needed. The offline `echo` provider makes every surface exercisable, so
this runs on a fork with no secrets.

## Layout

| File | Covers |
|:--|:--|
| `conftest.py` | fixtures: throwaway workspace, CLI runner, uvicorn process, MCP client |
| `test_cli_e2e.py` | the real binary, exit-code contract, the full new-user workflow |
| `test_api_e2e.py` | a real uvicorn process on a real port |
| `test_mcp_e2e.py` | real JSON-RPC over stdio, both protocol revisions |
| `test_parity_e2e.py` | the same artifact through all three surfaces |
| `test_ui_contract_e2e.py` | the field names the web workbench reads out of `/v1` |

## Design notes

**The CLI fixture invokes the binary, not `python -m`.** A broken console-script entry
point is a real user failure that importing the module would hide.

**The API fixture starts uvicorn as a subprocess, not `TestClient`.** TestClient skips
startup, the lifespan hook, port binding and teardown — which is where server bugs live.

**`api_server` is session-scoped and shares one workspace.** Starting uvicorn per test
adds seconds each. The trade-off is that tests using `shared_workspace` must be
*additive* — create new ids, never invalidate existing ones. Anything destructive uses
the function-scoped `workspace` fixture instead.

**There is a 120s per-test timeout** (`pytest.ini`). A hung end-to-end test is a failed
end-to-end test; without a timeout a deadlocked subprocess blocks CI until the job limit
and reports nothing useful.

**`test_ui_contract_e2e.py` asserts field names, not just status codes.** The workbench
destructures specific keys out of `/v1` responses. Those keys are declared in
`frontend/lib/v1.ts` as TypeScript types, which are erased at runtime and therefore verify
nothing about what the server actually sends — a backend rename would typecheck cleanly on
both sides and render `undefined` in the browser. Three assertions in that file are
load-bearing rather than routine: `verified` must stay tri-state (`null` means *nothing was
checked*, which is neither a pass nor a fail), `usable` must exist on a red-team report (so
a run where every attack errored cannot display a flattering 0%), and every governance
control must carry a non-empty `gap` (the UI gives evidence and gap equal weight).

## Known limitation

Under tight resource limits — a constrained container, few available PIDs — running all
modules in one process alongside a long-lived uvicorn can stall. Each module passes
independently. CI runs them as separate steps for this reason, which also produces
clearer failure attribution. If you hit it locally, run the modules separately.
