# ADR-0003 — Capability negotiation, and failing closed

**Status:** Accepted · **Date:** 2026-07-27

## Context

Prompts are not portable in the way "model-agnostic" marketing suggests. A prompt that
depends on structured JSON output, or a 200k context window, or prompt caching, or image
input, will not behave correctly on a model lacking that feature. It will usually *appear* to
work — and return prose where a parser expected JSON, or silently truncate the context.

Silent degradation is the worst available failure mode. It moves the error away from the
cause, so the symptom surfaces in a service three hops downstream, hours later.

There is also a forward-compatibility problem. New modalities arrive continuously — vision,
audio, reasoning tokens, computer use, whatever 2029 brings. A format that enumerates
capabilities in a closed enum needs a spec revision every time.

## Decision

A PromptFile declares what it needs:

```yaml
requires:
  capabilities: [json_mode, cache_control, vision]
  min_context_tokens: 200000
  plugins:
    assay-provider-acme: ">=1.0,<2"
```

The runtime resolves the union of what the provider reports for that model and what the model
catalogue records, and **refuses to execute on any mismatch** — raising `CapabilityError`
before a single token is spent.

Capability strings are an **open vocabulary**. They are not validated against an enum. A
capability nobody has invented yet is just a string that no current provider advertises, so a
prompt requiring it fails closed until a plugin advertises it.

`model.fallbacks` are checked against the same gate, so a fallback cannot be a downgrade that
quietly breaks the contract.

## Consequences

**Good**

- Failures happen at the boundary, with an actionable message naming the missing capability.
- New modalities cost nothing: a new string, a plugin that advertises it. No spec revision.
- `assay lint` can flag capability/model mismatches statically, before deploy.
- Cost control: an incompatible run fails before the API call, not after.

**Costs**

- Capability reporting is only as good as the provider plugin and the catalogue. A provider
  that under-reports causes false refusals. Mitigations: the union of both sources; a
  documented `capabilities:` override in the workspace catalogue.
- A genuine escape hatch is needed for experimentation — `--no-capability-check` is on the
  roadmap, deliberately opt-in and per-invocation rather than a config default, because a
  default that disables a safety gate is a safety gate nobody has.

## Alternatives considered

**Warn and continue.** Rejected. This is the silent-degradation failure we are eliminating.

**Infer requirements from the file.** Tempting — `output.schema` implies `json_mode`. But
inference is guessy, and an explicit declaration is documentation for the next reader. We
infer *nothing*; `assay lint` instead *suggests* requirements you appear to need but have not
declared.
