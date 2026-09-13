# What you can check in a browser

The Next.js workbench is file-backed on the stable `/v1` API. It covers PromptFiles,
projects derived from namespaces, the curated catalog, embedded evals, paired A/B tests,
harnesses, loops, memory, red-teaming, calibration, governance, integrations, and token
economy. The same endpoints are browsable at **`/docs`**, the interactive OpenAPI page.

## Start it

**Windows** — double-click `start-assay.bat`, or from a terminal:

```bat
start-assay.bat fresh
```

One command stops orphaned servers, clears stale caches, reinstalls, starts, and
health-checks the result. Double-clicking with no argument opens a menu.

**macOS / Linux** — the same command set:

```bash
./start-assay.sh fresh
```

Other commands you will want:

| | |
|:--|:--|
| `fresh` | the everyday restart — caches cleared, your data kept |
| `fresh --no-frontend` | backend only; fastest when the interactive `/docs` surface is enough |
| `stop` / `restart` | stop or bounce everything this project started |
| `status` | what is running, on which ports, which commit |
| `doctor` | full diagnostic written to a file, safe to attach to a bug report |
| `logs` | tail the most recent backend/frontend logs |
| `test` | run the whole test suite |
| `clean` | delete caches only — never touches your data |
| `reset` | delete db, memory and vectors. Asks for `YES`, backs the db up first |
| `nuke` | reset + fresh, from scratch |

Run it with no arguments for an interactive menu.

**If the window closes and nothing started**, the script writes everything it does to
`.assay\logs\bootstrap.log` from its first line, and pauses before closing when
double-clicked. Run `start-assay.bat doctor` and attach the report.

<details>
<summary>Manual start, if you prefer</summary>

```bash
pip install -e packages/assay-core -e packages/assay-cli -e packages/assay-mcp
pip install -r backend/requirements.txt
export ASSAY_WORKSPACE=/path/to/your/prompts
python -m uvicorn backend.main:app --port 8001 --reload
```
</details>

Open **<http://127.0.0.1:8001/docs>**. Everything below is clickable — "Try it out",
fill the body, execute. No API key needed: the default `echo` models run offline.

For the workbench:

```bash
docker compose up      # backend :8001, frontend :3001
```

Deprecated database-backed 0.x routes are not loaded by default. An operator who still
needs them temporarily for migration can set `ASSAY_ENABLE_LEGACY_API=1`; `/health`
reports whether that compatibility surface is active. It is not used by the current UI.

## Worth clicking, in order

| Endpoint | What you'll see |
|:--|:--|
| `GET /v1/plugins` | Live plugin inventory across every entry-point group, including load failures |
| `GET /v1/harnesses` | Your harnesses with their budgets, tools and whether memory is on |
| `POST /v1/harnesses/{id}/run` | **The full trajectory** — every step, tool call, observation, guardrail decision and memory event. Not just the answer |
| `POST /v1/harnesses/{id}/redteam` | Attack success rate, detection rate, false-positive rate, per category |
| `GET /v1/redteam/corpus` | The 52 attacks across 26 local adversarial categories plus 12 benign controls, with what each expects |
| `POST /v1/loops/{id}/run` | Cycles, and the `verified` field that decides whether the goal was actually met |
| `GET /v1/memory/search?q=…` | What agents remembered, with relevance scores |
| `GET /v1/tokens` | Measured context cost — tier-1 index vs. naive, and the saving |
| `GET /v1/index` | The compact index an MCP client sees before loading anything |
| `POST /v1/judge/calibrate` | Two-stage verdict with κ, Spearman and bootstrap intervals |
| `GET /v1/spec` | The PromptFile JSON Schema |

### Two things to try that show the interesting behaviour

**Memory across runs.** Call `POST /v1/harnesses/{id}/run` twice on a harness with a
`memory:` block. The first response has a `memory_recall` event with `recalled: 0`; the
second recalls the first with a relevance score. Memory is a real component, not a longer
prompt.

**Detection is not prevention.** Run the red-team against a harness whose `control.deny`
list is empty. Detection rate stays high while attack success rate climbs — the detector
fires and the agent complies anyway. That gap is the whole argument for control gates.

## What is deliberately not here

- **No approval prompts over HTTP.** Tools under `control.require_approval` are denied
  rather than auto-approved. A gate that opens itself when nobody is watching is not a gate.
- **No live model by default.** Red-team and eval endpoints run against `echo` unless you
  pass a `model`, and every red-team report states which mode produced it.
