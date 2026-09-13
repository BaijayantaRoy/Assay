# ADR-0002 — Plugin-first core

**Status:** Accepted · **Date:** 2026-07-27

## Context

The 0.x codebase resolved providers with a chain of `if model_id.startswith(...)` branches in
`llm_service.py`. Every new provider meant editing that function. Evaluators, guardrails and
template handling were similarly hardcoded.

That design has a predictable failure mode, and it is not "it stops working" — it is that the
project's usefulness decays at exactly the rate the field moves. In this field that is weekly.
A tool whose core must be edited to accept a new model is a tool that is always behind.

The requirement driving this project is explicit: *anything new in five years should drop in
without touching core.* That is a structural claim, and structural claims need structure.

## Decision

Every concern that could plausibly change becomes a **plugin behind a versioned Protocol**,
resolved at runtime through a registry.

The original decision introduced nine extension points:

| Entry-point group | Selected by | Examples |
|:--|:--|:--|
| `assay.renderers` | `engine.template` | jinja2, handlebars, fstring, none |
| `assay.providers` | `provider/` prefix of a model ref | openai, anthropic, google, ollama, any OpenAI-compatible |
| `assay.evaluators` | assertion `type` | contains, json_schema, llm_judge, cost_under |
| `assay.guardrails` | guardrail `type` | pii, schema, max_length, regex_block |
| `assay.stores` | `store:` in `assay.yaml` | file, memory, sql, s3 |
| `assay.importers` / `assay.exporters` | format detection | dotprompt, POML, Langfuse, PromptLayer |
| `assay.tracers` | always, all registered | OTLP, Langfuse, Datadog, JSONL |
| `assay.optimizers` | explicit invocation | LLM rewrite, DSPy/MIPROv2, GEPA |

The later agent-harness work applied the same decision to four additional groups:
`assay.tools`, `assay.context`, `assay.controllers`, and `assay.memory`. The current contract
surface therefore has 13 groups; this note records the additive application without rewriting
the original decision.

Three registration paths, in increasing precedence: installed **entry points** → **`assay.yaml`
plugins block** → **programmatic** (`Registry.register`).

Two rules make this hold up:

1. **Built-ins are not privileged.** They register through the same entry points third-party
   plugins use. The extension mechanism is therefore exercised on every single run — the only
   reliable way to stop it rotting.
2. **Discovery is failure-isolated.** A plugin that fails to import is recorded as a load
   error against that one name. It never crashes the process or disables unrelated plugins.

Compatibility is enforced at load: a plugin declares `contract_version`; the registry refuses
a major mismatch and structurally verifies the Protocol.

## Consequences

**Good**

- New provider = one class + one entry-point line. Core untouched.
- Organisations ship private evaluators and guardrails without forking.
- `assay plugins` and `GET /v1/plugins` make the whole system introspectable — including which
  plugins failed to load and why.
- Testability: swap in a `MemoryStore` and the `echo` provider and the entire stack runs
  deterministically offline.

**Costs**

- Indirection. Reading the code means following a registry lookup instead of a direct import.
  Mitigated by keeping composition in exactly one file (`runtime.py`).
- Entry-point scanning costs a few milliseconds at first use. Mitigated: scan is lazy, cached,
  and there is a direct-registration fallback for source checkouts.
- `runtime_checkable` Protocols verify method *names*, not signatures. Contract tests in the
  plugin-authoring guide cover the rest.

## Alternatives considered

**Adapter classes with explicit imports.** Simpler to read, but core imports every adapter,
so core is edited for every addition. That is the problem we are solving.

**A configuration-driven provider table.** Handles the easy 80% (OpenAI-shaped endpoints) and
none of the interesting 20% (Anthropic's system-block and cache-control model, Gemini's
`generationConfig`). We ship `openai_compatible` to cover the easy case *and* the plugin
mechanism for the rest.
