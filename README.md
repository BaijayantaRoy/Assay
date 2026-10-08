<div align="center">

<img src="assets/brand/hero-v2.png" alt="Assay — assurance as code. Test prompts, verify agents, and ship evidence." width="100%">

<br/><br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Spec: PromptFile v1](https://img.shields.io/badge/spec-PromptFile%20v1-6f42c1.svg)](spec/promptfile-v1.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28%20%2F%202025--11--25-000000.svg)](docs/architecture/adr/0006-mcp-as-primary-surface.md)
[![Works offline](https://img.shields.io/badge/works-offline-brightgreen.svg)](docs/architecture/adr/0005-offline-first.md)

[Get running](#quick-start) · [See the product](#the-web-workbench) · [Why Assay](#what-sets-assay-apart) ·
[PromptFile v1](spec/promptfile-v1.md) · [Architecture](docs/architecture/BLUEPRINT.md) · [Roadmap](docs/architecture/ROADMAP.md)

</div>

## Turn prompts into software you can prove

Assay gives every prompt and agent the things ordinary source code already has: a portable
file format, executable tests, CI-friendly exit codes, version history, security regression
suites, and evidence a reviewer can inspect. The repository is the source of truth—not a
hosted dashboard you must trust or export from later.

<p align="center">
  <img src="assets/brand/architecture-map.png" alt="High-level map: PromptFiles flow through the Assay engine's evaluations, trajectories, red-team and governance checks into portable proof, exposed through CLI, MCP, REST, SDKs and the workbench" width="100%">
</p>

<table>
<tr>
<td width="33%"><strong>1 · Keep it in Git</strong><br><code>.prompt.md</code> files carry the template, schemas, model binding, guardrails, and eval cases together.</td>
<td width="33%"><strong>2 · Test behavior</strong><br>Score prompt output, agent trajectories, tool-call order, budgets, denials, and verified handoffs.</td>
<td width="33%"><strong>3 · Ship evidence</strong><br>Run the same engine through CLI, MCP, REST, Python, TypeScript, or the visual workbench.</td>
</tr>
</table>

<p align="center">
  <img src="assets/screenshots/web-dashboard.png" alt="Assay workbench showing artifact coverage, agent harnesses, verified loops, context savings, judge calibration, injection defence, plugins, and parsing health" width="92%">
</p>

<p align="center"><em>One engine, every surface. Unmeasured states stay visibly unmeasured.</em></p>

### The 30-second proof

```bash
pip install assay-cli
assay init my-prompts && cd my-prompts
assay test
```

No API key is required. The built-in deterministic provider lets the starter workspace run
offline immediately; connect a live model only when you choose to.

---

## Why this exists

Many prompt platforms center a hosted control plane. Some now version complete agent and
skill repositories, and several support CI, self-hosting, or export. The remaining problem is
not simply where a prompt is stored; it is whether the artifact carries portable, reviewable
evidence that survives outside any one product.

And once a prompt becomes an *agent*, the harder question isn't where it's stored — it's
whether you can show it works. Most tooling will happily report a number. Assay is built so
the number has to be earned: an unverified loop reports **not checked** rather than passing,
a red-team run where every attack errored **refuses to show an attack-success rate**, and
every governance control states its gap beside its evidence.

Assay starts somewhere else:

```
prompts/support/refund-triage.prompt.md
```

One file. YAML frontmatter plus a markdown body. It carries the template, the input and output
schemas, the model binding, the guardrails, **and its own test cases**. It diffs in a PR. It
runs in CI. It works with no API key. Your exit cost is `git clone`.

Everything else — the CLI, the REST API, the MCP server, the web UI, the SDKs — is a thin
adapter over one engine that reads that file. And every part of that engine that could
plausibly change is a plugin.

### How it actually works

1. **You write a `.prompt.md` file.** Template, schemas, model binding, guardrails and eval
   cases all live in one text file, next to your application code, in your own repository.
2. **`assay-core` parses and runs it.** The same runtime backs the CLI, the REST API, the MCP
   server and both SDKs — there is exactly one place behavior can drift, and parity tests
   catch it if it does.
3. **The engine measures instead of asserting.** Every run produces a trajectory (for agents)
   or a structured result (for prompts). Assertions run against that record, not the model's
   prose, and a result with too little evidence to trust is reported as **withheld**, not
   rounded up.
4. **Evidence travels with the artifact.** Evals, red-team results and governance mappings are
   files in your git history — reviewable in the same pull request as the prompt change that
   produced them, and exercisable again by anyone who clones the repository.

---

## See it run

This is real output from this repository — `assay test` against the example prompts shipped
in `prompts/`, no mocking, no live model, no API key:

<img src="assets/screenshots/cli-test.png" alt="assay test — five prompts and harnesses passing, with score intervals honestly withheld where too few cases were usable" width="820">

Notice the second line under most passes: *"score interval withheld: fewer than three usable
cases."* That line is the point of the product. A tool that rounds a two-sample average up to
a confident percentage is lying by omission — Assay would rather tell you it doesn't know yet.

---

## Quick start

```bash
pip install assay-cli          # the CLI + engine
assay init my-prompts && cd my-prompts
```

You now have a working workspace. **No API key needed** — the offline `echo` provider is the
default, so every command below runs immediately:

```bash
assay ls                                  # list prompts
assay render demo/hello -v name=World     # fill variables, no model call
assay run    demo/hello -v name=World     # execute
assay test                                # run embedded evals — exit code 4 on failure
assay lint                                # validate against the spec
```

Point it at a real model when you're ready:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
assay run demo/hello -v name=World -m anthropic/claude-opus-5-5
```

### Expose it to your coding agent

```bash
pip install assay-mcp
```

```jsonc
// Claude Code / Cowork / Cursor MCP config
{
  "mcpServers": {
    "prompts": {
      "command": "assay",
      "args": ["mcp"],
      "env": { "ASSAY_WORKSPACE": "/path/to/my-prompts" }
    }
  }
}
```

Your agent can now search your prompts, render them, run them, create new ones — and call
`assay_test` to prove an edit didn't regress anything.

---

## What a prompt looks like

```markdown
---
promptfile: 1
id: support/refund-triage
name: Refund Triage
version: 7
status: stable
tags: [support, classification]

requires:
  capabilities: [json_mode]          # runtime refuses to run without it

input:
  schema:
    type: object
    required: [message]
    properties:
      message: { type: string }

output:
  format: json_schema
  schema:
    type: object
    properties:
      category: { type: string, enum: [REFUND, BILLING, OTHER] }

model:
  primary: anthropic/claude-opus-5-5
  fallbacks: [openai/gpt-6.1-sol]
  params: { temperature: 0 }

evals:                                # the prompt tests itself
  - id: obvious-refund
    input: { message: "I want my money back" }
    assert:
      - { type: json_schema }
      - { type: contains, value: REFUND }
      - { type: cost_under, value: 0.01 }

guardrails:
  - { type: pii,    stage: input,  action: redact }
  - { type: schema, stage: output, action: retry }
---

Classify the customer message. Respond with JSON only.

Message: {{ message }}
```

That file is the whole thing. [Full specification →](spec/promptfile-v1.md)

---

## What sets Assay apart

Not a features list — a list of things you can go check yourself, because every one of them
is a claim the engine has to earn on every run, not copy on a slide.

- **Tri-state `verified`, not a boolean.** An outer loop's goal check reports `true`, `false`,
  or `null` — never coerced to a pass. `null` means *not checked*, and it stays visible in
  every report that reads it, including the CLI exit code.
- **Score intervals withheld below a usable-sample floor.** Fewer than three usable cases and
  `assay test` prints *"withheld"* instead of a confidence interval built on statistics that
  don't support one. See the screenshot above — it isn't staged copy, it's what the command
  actually prints.
- **Assertions score the trajectory, not just the final text.** `tool_call_order`,
  `no_repeated_tool_call`, `budget_under`, `no_denied_calls` — an agent that reaches the right
  answer the wrong way (skips the search, ignores a control gate, loops twice on the same
  tool) fails the eval even though the output looks fine.
- **The red-team corpus states its own limits.** 52 attacks and 12 benign controls across 26
  categories, and the verdict line says outright: *"scripted... this measures the DEFENCES...
  not model susceptibility"* and *"published attack success rates against current defences
  exceed 80% — treat this as a regression gate, not a safety guarantee."* No tool that wants
  your trust should be quieter than its own worst number.
- **Detection is measured separately from prevention.** The workbench and CLI both report a
  detection rate distinct from attack-success rate, because a detector that fires *and* an
  agent that still complies is a real, common failure mode most red-team reports collapse
  into one green checkmark.
- **Governance controls report their gap, not just their evidence.** Every control mapped to
  EU AI Act / ISO 42001 / NIST AI RMF articles states, in the same breath, what the tool
  cannot do for you — "aggregation is read-only," "operator must finish the job." A mapping
  that lists only strengths tells an assessor nothing except that you were selling.
- **Mutation-tested assertions.** `assay test`'s own suite is checked against deliberately
  broken implementations — an assertion that can't fail is worse than no assertion, because it
  looks like coverage.
- **Thirteen public plugin surfaces, no privileged core.** Providers, evaluators, guardrails,
  tools, context strategies, memory backends, importers and more are discovered through
  standard Python entry points — the built-ins register through the exact same mechanism a
  third-party plugin does.
- **The format outlives the product.** `promptfile: 1` — not `assay: 1` — is the required key.
  A conforming reader must preserve fields it doesn't understand. That's deliberate: a
  PromptFile should still parse if this project is forked, renamed, or replaced outright.

---

## Product interfaces, one engine

|  | Use it for | |
|:--|:--|:--|
| **CLI** | authoring, CI gating, git workflows | `assay test` |
| **MCP server** | coding agents — Claude Code, Cowork, Cursor, Zed | `assay mcp` |
| **REST API** | applications, other languages | `POST /v1/prompts/{id}/run` |
| **SDKs** | Python and TypeScript runtime clients, plus independent `@assay/promptfile` file reader | `assay.run("support/refund-triage", {...})` |

They are adapters over the same `assay-core` runtime, with real-boundary parity tests to catch
behavioral drift.

```python
from assay import Client

client = Client.local("./prompts")            # reads files, no server, no network
print(client.run("support/refund-triage", {"message": "refund please"}).text)

client = Client("https://prompts.internal")   # same API, remote server
```

---

## Everything is a plugin

Thirteen extension points, discovered through standard Python entry points. The built-ins use the
same mechanism third-party plugins do — there's no privileged path, which is why it keeps
working.

| Extension point | Ships with | Add your own |
|:--|:--|:--|
| `assay.renderers` | jinja2, fstring, none | any template dialect |
| `assay.providers` | openai, anthropic, google, ollama, any OpenAI-compatible, echo | any API |
| `assay.evaluators` | contains, regex, json_schema, llm_judge, cost_under, latency_under, … | any assertion |
| `assay.guardrails` | pii, schema, max_length, regex_block | any policy |
| `assay.stores` | file (git) | SQL, S3, remote registry |
| `assay.importers` | Promptfoo, dotprompt, POML, Langfuse, PromptLayer and raw message imports | Braintrust, Latitude |
| `assay.exporters` | contract only | any foreign format; `/v1/export` separately emits native PromptFiles |
| `assay.tracers` | OpenTelemetry GenAI spans | Langfuse, Datadog |
| `assay.optimizers` | measured reflective rewrite | DSPy, GEPA, your own search |
| `assay.tools` / `assay.context` | filesystem, shell, HTTP, prompt; truncate, compact, summarize | custom tools and context policies |
| `assay.controllers` / `assay.memory` | policy, read-only; JSONL, memory, null | approval systems and memory backends |

A new provider is one class and one line:

```toml
[project.entry-points."assay.providers"]
acme = "acme_assay:AcmeProvider"
```

Core is never edited. See [ADR-0002](docs/architecture/adr/0002-plugin-first-core.md).

---

## Built to still work in five years

This is the part most prompt tools don't write down.

- **Open vocabularies, not enums.** Capabilities, artifact kinds and assertion types are open
  strings. A modality invented in 2029 is a new string — not a spec revision.
- **Unknown fields survive.** A conforming writer *must* preserve keys it doesn't understand,
  including the reserved `x-` namespace. Independent Python and TypeScript readers execute
  one shared corpus, and Python property tests generate nested JSON-compatible future values.
  The promise is semantic preservation, not byte-identical YAML styling or comments.
- **Fail closed, never degrade.** A prompt requiring `json_mode` on a model that lacks it
  raises before spending a token — instead of returning prose that breaks a parser downstream.
- **A written compatibility policy.** Spec, plugin contracts and REST API version
  independently, each with a 12-month deprecation floor.
  [ADR-0004 →](docs/architecture/adr/0004-compatibility-policy.md)
- **Model data is data.** `assay models sync` refreshes prices and context windows. No code
  release needed when a vendor changes pricing.

---

## The web workbench

A Next.js UI for browsing, editing, comparing models and inspecting evaluations — file-backed
on the same stable `/v1` API the CLI and MCP server drive. Every screenshot below is the actual
app, running against this repository's own example prompts.

<img src="assets/screenshots/web-dashboard.png" alt="Assay workbench dashboard — artifacts, harnesses, loops, context saving, and trust panels for test coverage, judge calibration and injection defence" width="820">

*The dashboard doesn't just show green numbers — "Judge calibration" and "Injection defence"
report themselves as unmeasured until you actually run them, and "Run log and spend" says
plainly that auditing is off by default.*

<details>
<summary><b>Red team</b> — attack corpus, scored against a versioned suite</summary>
<br>
<img src="assets/screenshots/web-redteam.png" alt="Assay Red Team page listing scored prompt-injection attacks arriving through tool output, each labeled with severity and what counts as compromise" width="820">

Every entry states which tool call would count as compromise *before* the attack runs — the
corpus doesn't grade itself after the fact.
</details>

<details>
<summary><b>Governance</b> — controls mapped to evidence, and to what's still missing</summary>
<br>
<img src="assets/screenshots/web-governance.png" alt="Assay Governance page mapping EU AI Act, ISO 42001 and NIST AI RMF controls to supported evidence and stated gaps" width="820">

"This report lists evidence this repository can produce and the gaps it cannot fill. It is
not a compliance assessment." That line is on the page, not just in this README.
</details>

<details>
<summary><b>Harnesses</b> — run an agent, read the whole trajectory</summary>
<br>
<img src="assets/screenshots/web-harnesses.png" alt="Assay Harnesses page showing a Researcher agent with its tools, memory, budget, and a goal input ready to run" width="820">
</details>

```bat
start-assay.bat fresh      :: Windows — stop, clean, reinstall, start, verify
```
```bash
./start-assay.sh fresh     # macOS / Linux — identical commands and exit codes
docker compose up          # or containers: backend :8001, frontend :3001
```

Double-clicking `start-assay.bat` on Windows opens a menu; it never closes without saying
why. Also `stop`, `restart`, `status`, `doctor`, `logs`, `test`, `clean`, `reset`, `nuke`.
See [docs/local-ui.md](docs/local-ui.md).

> **Upgrading from before the rename?** Your virtualenv still has the old `mpl-*` packages
> installed, pointing at directories that no longer exist. `fresh` detects and removes
> them automatically. If anything still looks wrong, delete `venv/` and run it again.

The deprecated database-backed 0.x routes are disabled by default and can be enabled only as
an explicit migration aid with `ASSAY_ENABLE_LEGACY_API=1`:

| Page | What it shows |
|---|---|
| Agents → Harnesses | Run an agent; read the full trajectory, denials and budget spend |
| Agents → Loops | Per-step verification, stall detection, broken-handoff warnings |
| Agents → Memory | What carried between runs, and how hybrid recall ranked it |
| Agents → Token Economy | Measured progressive-disclosure saving, shown beside its denominator |
| Assurance → Red Team | Attack-success rate, with a run that produced nothing refusing to report a score |
| Assurance → Judge Calibration | The two-stage gate, with bootstrap intervals drawn against the threshold |
| Assurance → Governance | Control mapping where every gap is as visible as its evidence |
| Ops → Spec & Plugins | PromptFile v1 served live from the API, plus the installed plugin inventory |

Raw endpoints remain browsable at **`http://localhost:8001/docs`**.

---

## The red team, from the terminal

The same corpus the workbench page above renders is one command from a CI job:

<img src="assets/screenshots/cli-redteam.png" alt="assay redteam terminal output — 52 attacks defended, 0% attack success rate, with the tool's own caveat about what a clean scripted run does and doesn't prove" width="900">

Read the last two lines. That caveat prints on every run, clean or not — it is not something
you have to go find in the docs.

---

## How it compares

| | Typical hosted control plane | Assay |
|:--|:--|:--|
| Artifact ownership | hosted record or synchronized repository | canonical text files in the user's repository |
| Review workflow | product UI and/or source integration | ordinary pull requests plus embedded evidence |
| CI gating | supported by mature products | `assay test`, including a fully offline path |
| Agent access | SDKs and integrations | MCP plus CLI, REST, web, and two SDKs |
| Extension path | product-specific API/plugin surface | 13 public Python protocol groups |
| Network behavior | varies by feature and deployment | offline by default; provider, remote import, sync, and telemetry calls are explicit |
| Software fee | free, usage, seat, or enterprise tiers vary | MIT-licensed software; provider and infrastructure costs still apply |
| Native exit path | product-specific export or repository sync | the canonical artifact is already in git |

Promptfoo remains materially ahead in red-team breadth and attack strategies; Assay now has a
small deterministic sequence/adaptive regression corpus, not parity. LangSmith now
versions and promotes whole agent/skill contexts. Langfuse and Braintrust are materially
ahead in production tracing, online evaluation, and team operations. Assay's narrower wedge
is **portable assurance-as-code**: evals and governance travel with the artifact, unverified
states and unusable denominators remain visible, handoffs retain evidence, and mutation tests
prove critical checks can fail. See the dated [competitive benchmark](docs/architecture/BENCHMARK.md).

---

## Documentation

| | |
|:--|:--|
| [**Knowledge centre**](docs/knowledge/) | Harness, loop, context, evaluation and security engineering — each paired with runnable artifacts |
| [PromptFile v1 specification](spec/promptfile-v1.md) | The format, conformance rules, interop matrix |
| [Domain research](docs/architecture/RESEARCH.md) | A 14-domain survey with per-domain gap assessment |
| [Architecture blueprint](docs/architecture/BLUEPRINT.md) | How it's built and why |
| [Decision records](docs/architecture/adr/) | The decisions that shaped it, with their costs |
| [Roadmap & known limitations](docs/architecture/ROADMAP.md) | What's shipped, what isn't, what's rough |
| [User guide](docs/user_guide.md) | Day-to-day usage |
| [Contributing](docs/CONTRIBUTING.md) | How to help |
| [Support](SUPPORT.md) | Where to ask, and what to try first |
| [Security policy](SECURITY.md) | How to report a vulnerability privately |
| [Governance](GOVERNANCE.md) | Who decides, and the invariants that are not up for a vote |
| [Changelog](docs/CHANGELOG.md) | What changed in each release |
| [End-to-end suite](tests/e2e/) | Tests driving the installed binary, real servers, MCP stdio, and the prompt proxy |

---

## Project status

**The v1.0 foundation is shipped and tested**: the spec, plugin core, CLI, MCP server,
`/v1` API, both SDKs, and a file-backed workbench spanning authoring, evaluation, agents,
assurance, governance, integrations, and the curated catalog.

Known limitations are listed honestly in the
[roadmap](docs/architecture/ROADMAP.md#known-limitations) — including the lack of hosted
throughput evidence, sampled-stream merging, and cost figures being estimates rather than
billed amounts.

---

## Contributing

The highest-leverage things you can do:

1. **Write a plugin** — it proves the extension points work for someone who didn't design them.
2. **Contribute prompts with eval cases** — a prompt without evals is a suggestion.
3. **Implement the spec in another language** — that's what turns a format into a standard.
4. **Break the round-trip guarantee** — find a file that doesn't survive parse → write → parse.
   That's the bug we most want to hear about.

## License

MIT for the code. The [specification](spec/promptfile-v1.md) is CC BY 4.0 — implement it
anywhere, including in products that compete with this one.

If you use Assay or implement PromptFile in your own work, [CITATION.cff](CITATION.cff) has
the citation details.

---

<p align="center">Built and maintained by <a href="https://github.com/BaijayantaRoy">Baijayanta Roy</a>.</p>
