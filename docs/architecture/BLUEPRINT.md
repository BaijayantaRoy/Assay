# Assay — Architecture Blueprint

**Status:** active · **Last updated:** 2026-07-27 · **Spec:** PromptFile v1 · **Core contract:** 1.0

This document explains what Assay is, why it is built the way it is, and how it
stays useful as models, protocols and practices change. It is the entry point for anyone
evaluating, extending, or contributing to the project.

---

## 1. The thesis

Prompt tooling in 2026 splits into two camps.

**Observability platforms** (Langfuse, Helicone, Braintrust, Latitude) instrument production
traffic. They are excellent at telling you what happened, and several also manage prompts,
datasets, experiments, and deployment workflows.

**Prompt and context hubs** give teams visual editing, version history, deploy labels, SDKs,
and increasingly full repositories for agent and skill context. They are excellent at
collaboration; the tradeoff is that assurance evidence and lifecycle semantics remain shaped
by that product's control plane.

Both camps solve real problems. Assay therefore does not claim that files, CI, or versioning
are unique. Its structural bet is narrower: **the portable file carries its execution contract,
controls, and test evidence together**, so those claims can be reviewed and run without the
original control plane.

Assay starts from the opposite premise:

> A prompt is source code. It belongs in a plain-text file, in git, in your repository,
> under your license — and every tool that touches it is optional.

Everything else follows from that. The file format is published as a standalone
specification. The engine that reads it is a library. The CLI, the REST API, the MCP server
and the web UI are four faces of that one library, none of them privileged. And every
capability that could plausibly change — a provider, a template dialect, an assertion type,
a storage backend, a tracer, an optimizer — is a plugin discovered at runtime, so the core
never has to be edited to accommodate something that did not exist when it was written.

### What this architecture optimizes for

| | Typical hosted control plane | Assay |
|:--|:--|:--|
| Canonical artifact | Hosted record or synchronized repository | Files in the user's git repository |
| Assurance evidence | Product-side configuration and experiment records | Embedded evals, controls, and lifecycle metadata |
| CI gating | Mature products support it | `assay test` — exit code 4, with an offline path |
| Agent access | SDKs and integrations | Native MCP plus CLI, REST, web, and SDKs |
| Extension path | Product-specific | 13 public versioned Python protocol groups |
| Network boundary | Depends on product and feature | Offline by default; every remote feature is operator-invoked |
| Software cost | Varies by plan/deployment | MIT license; inference and infrastructure are not free |
| Native exit path | Product-specific export or repository sync | Canonical artifacts are already ordinary files |

---

## 2. System shape

```
                        ┌──────────────────────────────────────────┐
                        │            Interaction surfaces          │
                        │                                          │
   agents ──MCP──────►  │  assay-mcp      assay-cli     /v1 REST + UI  │
   humans ──terminal─►  │  (stdio/HTTP) (assay …)     (FastAPI)      │
   apps   ──SDK──────►  │  sdk-python   sdk-typescript             │
                        └────────────────────┬─────────────────────┘
                                             │  every surface is a thin adapter
                        ┌────────────────────▼─────────────────────┐
                        │                assay-core                  │
                        │                                          │
                        │  PromptFile ─► Runtime ─► RunResult      │
                        │   (parse,      (render, guard,           │
                        │    validate,    execute, evaluate,       │
                        │    round-trip)  trace)                   │
                        │                                          │
                        │              Registry                    │
                        │   resolves every pluggable concern       │
                        └────────────────────┬─────────────────────┘
                                             │  entry points: assay.*
        ┌────────────┬───────────┬───────────┼───────────┬───────────┬────────────┐
     renderers    providers   evaluators  guardrails   stores     tracers    optimizers
     jinja2       openai      contains    pii          file       otel       llm-rewrite
     handlebars   anthropic   json_schema schema       memory     langfuse   dspy / gepa
     fstring      google      llm_judge   max_length   sql        datadog    …
     …            ollama      cost_under  …            s3         …
                  any-openai  …
```

Read the diagram bottom-up. The plugins are the interesting part; the core is deliberately
small; the surfaces are deliberately dumb. When someone asks "can it do X?", the answer is
almost always "yes, as a plugin, without forking".

### Package layout

```
packages/
├── assay-core/          the engine — spec, registry, runtime, built-in plugins
├── assay-cli/           `assay` — git-native prompt engineering from the terminal
├── assay-mcp/           MCP server, stdlib-only, dual protocol revision
├── sdk-python/        embedded or remote, same API shape
└── sdk-typescript/    zero-dependency, runs on every JS runtime
spec/                  the published PromptFile specification + JSON Schema
backend/               FastAPI: /v1 stable API; legacy 0.x compatibility is opt-in
frontend/              Next.js web workbench
docs/                  architecture, guides, and the knowledge centre
```

---

## 3. The five design decisions that matter

Each is recorded in the [ADR index](adr/README.md). Summarised here because they are the
reason the project looks the way it does.

### 3.1 The prompt is a file, and the format is a public spec

[ADR-0001](adr/0001-promptfile-as-the-substrate.md) · [Spec](https://github.com/BaijayantaRoy/Assay/blob/main/spec/promptfile-v1.md)

`.prompt.md` is YAML frontmatter plus a markdown body. It carries the template, the input
and output JSON Schemas, the model binding, tool declarations, guardrails, eval cases,
provenance and lifecycle status. One prompt, one file, everything needed to run and test it.

The format is published under CC BY 4.0 as a standalone specification so competing tools can
implement it. That is not altruism — a format only one tool reads is a proprietary database
with extra steps.

### 3.2 Everything pluggable, discovered at runtime

[ADR-0002](adr/0002-plugin-first-core.md)

Thirteen extension points: renderers, providers, evaluators, guardrails, stores, importers,
exporters, tracers, optimizers, tools, context strategies, controllers, and memory. Each is a
Python `Protocol` with a declared contract version. Plugins arrive through standard entry
points, through `assay.yaml`, or programmatically.

The built-in plugins use the same path as third-party ones. There is no privileged registration,
which means the extension mechanism is exercised by the project itself on every single run —
the most reliable way to keep it from rotting.

Adding Anthropic's next API, a company-internal evaluator, or a storage backend nobody has
thought of yet is: write a class, add one line, `pip install`. Core is untouched.

### 3.3 Capability negotiation, and failing closed

[ADR-0003](adr/0003-capability-negotiation.md)

A prompt declares what it needs:

```yaml
requires:
  capabilities: [json_mode, cache_control]
  min_context_tokens: 200000
```

A runtime that cannot satisfy that **refuses to execute**. It does not quietly drop the JSON
constraint and return prose that breaks a parser three services downstream.

This is the mechanism that makes future modalities free. Video, computer use, whatever 2029
brings — they are new capability strings. The vocabulary is open. The format does not change.

### 3.4 An explicit compatibility contract

[ADR-0004](adr/0004-compatibility-policy.md)

Three independently versioned things, each with a written policy:

| Surface | Version | Rule |
|:--|:--|:--|
| PromptFile spec | `promptfile: 1` | Every v1 file readable by every future v1 tool. Unknown fields preserved on round-trip. Removal requires 12 months' deprecation and a major bump. |
| Plugin contracts | `1.0` | Additive changes bump minor. Breaking changes bump major, and the previous major is supported alongside for ≥ 12 months. |
| REST API | `/v1` | Additive only. Deprecations advertised via RFC 8594 `Deprecation`/`Sunset` headers. Breaking changes ship as `/v2` with `/v1` still running. |

The `x-` namespace in PromptFile is reserved for vendors and experiments, and conforming
writers **must** preserve it. That is what lets an ecosystem try things without forking the
format — and it is why "add anything in five years" is a structural property here rather than
a marketing line.

### 3.5 Offline by default

[ADR-0005](adr/0005-offline-first.md)

The `echo` provider is a first-class, always-installed backend. Every command in the
toolchain — render, run, test, lint, the MCP server, the REST API — is exercisable end to end
with no API key and no network. `assay test` in CI on a fork with no secrets still validates
templates, schemas, guardrails and deterministic assertions.

This is also why the model catalogue is *data* (`assay models sync`) rather than a hardcoded
table: prices and model ids change weekly, and a project that requires a code release to
track them is a project that is always slightly wrong.

---

## 4. Execution model

```
PromptFile
   │
   ├─ resolve renderer, provider, model, params      registry + catalog
   ├─ check requires.capabilities                    fail closed on mismatch
   ├─ render each message                            renderer plugin
   ├─ input guardrails                               block / warn / redact
   ├─ provider call  ──── on failure ──► fallbacks   ordered, capability-checked
   ├─ tool-result guardrails                         block / warn / whole-result redact
   ├─ output guardrails                              block / warn / redact / retry-with-repair
   ├─ evaluate (when testing)                        evaluator plugins, weighted roll-up
   └─ trace                                          every registered tracer; never fatal
                                                     │
                                                     ▼
                                                 RunResult
                          output · usage · latency · cost · guardrail events · eval results
```

Two properties worth calling out:

**Tracing can never break execution.** Tracer exceptions are swallowed and logged. An
observability backend having a bad day must not take production prompts down with it.

**Guardrail `retry` is a real repair loop.** On a schema violation the runtime re-runs once
with the violation appended as a repair instruction, then re-checks. Bounded at one retry so
a pathological prompt cannot spend money in a loop.

---

## 5. Observability

Traces follow the OpenTelemetry **GenAI semantic conventions** (`gen_ai.*`). Two deliberate
choices, both matching current OTel guidance:

- Prompt and completion **content goes in span events, not span attributes.** Attributes are
  always indexed, size-limited, and a PII hazard in the backend. Events can be dropped at the
  collector without touching application code.
- The conventions are still marked Development upstream, so the tracer is a plugin. When they
  stabilise, or if they change, that is a plugin release — not a core release.

Any tracer that implements the `Tracer` protocol works: OTLP, Langfuse, Datadog, a JSONL file,
your own.

---

## 6. Agent integration — where this project is unusual

Most prompt tools bolt an MCP server on as an afterthought. Here it is a primary surface, and
it is the reason the project is worth using inside a coding agent.

`assay-mcp` exposes:

- **`prompts/list` / `prompts/get`** — your maintained prompts appear natively in the agent's
  prompt picker, with typed arguments derived from `input.schema`.
- **`resources/*`** — raw PromptFile sources, the workspace config, the model catalogue, and
  the specification itself, so an agent can read the format before writing one.
- **`tools/*`** — `assay_search`, `assay_get`, `assay_render`, `assay_run`, `assay_test`, `assay_lint`,
  `assay_create`, `assay_update`, `assay_models`.

The combination that matters: an agent can **search for an existing tested prompt instead of
inventing one**, edit it, and then run `assay_test` to prove it did not regress — a closed
verification loop, which is exactly what harness and loop engineering practice says agents
need. Writing without a way to check the result is where agent workflows fail.

Implementation notes:

- **Stdlib only.** No MCP SDK dependency, so an SDK release cannot break the server.
- **Dual protocol revision.** Speaks the session-based revisions (`2025-11-25` and earlier)
  *and* the stateless `2026-07-28` revision, decided per request: legacy `initialize` is
  honoured; `server/discover` is implemented; no session id is ever required. List results
  carry `ttlMs`/`cacheScope`; tool schemas are full JSON Schema 2020-12; diagnostics go to
  stderr rather than the deprecated `logging` capability.
- **Stateless ⇒ horizontally scalable.** The HTTP transport holds no per-connection state, so
  it runs behind a plain round-robin load balancer with no sticky routing or session store.

---

## 7. Knowledge centre

The second half of the "one-stop" goal: the repository is also the reference, not just the
tool. Five tracks are written in the [knowledge centre](../knowledge/README.md); two are planned and
labelled as such rather than implied:

| Track | Contents |
|:--|:--|
| **Prompting** | Technique catalogue, model-specific guides, anti-patterns, structured output |
| **Context engineering** | Context window budgeting, retrieval shaping, compaction, filesystem-as-context |
| **Agent harness** | The four elements — agent loop, tool interface, context management, control — and how to build each |
| **Loop engineering** | Turn-based, goal-based, scheduled and proactive loops; verification design; sub-agent delegation |
| **Evaluation** | Building golden sets, LLM-as-judge calibration, regression gating, statistical significance |
| **Optimization** | Manual iteration, automatic prompt optimization, DSPy/MIPROv2/GEPA-style search |
| **Operations** | Cost control, caching, fallback strategy, guardrails, incident response |

Each page will be paired with runnable PromptFiles in the [repository prompts directory](https://github.com/BaijayantaRoy/Assay/tree/main/prompts) so the
guidance is executable rather than only readable. Documentation that cannot be run is
documentation that silently goes stale.

---

## 8. Security posture

- **No secrets in the repository.** Provider keys come from the environment or the workspace
  config's `api_key_env` indirection — never from a PromptFile, and never committed.
- **Sandboxed templating.** Jinja2 runs in `SandboxedEnvironment`; a prompt cannot reach
  dunder attributes or execute arbitrary Python.
- **Fail-closed guardrails.** A guardrail that errors is a violation, not a pass.
- **No `$ref` dereferencing.** External JSON Schema references are never fetched, per MCP
  2026-07-28 guidance, so a schema cannot become an SSRF vector.
- **Plugin isolation.** A plugin that fails to import is recorded as a load error against that
  one name; it never crashes the process or disables unrelated plugins.
- **Regex PII detection is documented as a first line of defence, not a compliance control.**
  Overstating that would be worse than omitting it.

---

## 9. What is deliberately not here

Being honest about scope is part of being trustworthy.

- **No hosted service.** Self-host or run locally. No account, no telemetry, no phone-home.
- **No auth/RBAC in core.** Multi-tenant identity belongs in front of the API (reverse proxy,
  gateway), not inside a library. A team plugin can add it; core stays simple.
- **No prompt marketplace.** Curated packs ship in-repo and install by copying files.
- **No claim of full observability parity with Langfuse.** They are excellent at production
  tracing. The tracer plugin *exports to* them rather than competing with them.

---

## 10. Reading order for contributors

1. [`spec/promptfile-v1.md`](https://github.com/BaijayantaRoy/Assay/blob/main/spec/promptfile-v1.md) — the format everything is about
2. [`packages/assay-core/src/assay_core/contracts.py`](https://github.com/BaijayantaRoy/Assay/blob/main/packages/assay-core/src/assay_core/contracts.py) — the 13 plugin contracts
3. [`packages/assay-core/src/assay_core/runtime.py`](https://github.com/BaijayantaRoy/Assay/blob/main/packages/assay-core/src/assay_core/runtime.py) — the only place plugins are composed
4. [ADR index](adr/README.md) — why, not what
5. [`ROADMAP.md`](ROADMAP.md) — where it is going and what is not done yet
