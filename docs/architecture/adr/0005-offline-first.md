# ADR-0005 — Offline-first, and the model catalogue as data

**Status:** Accepted · **Date:** 2026-07-27

## Context

Two recurring problems with prompt tooling:

**You cannot try it without credentials.** A new contributor clones the repo, runs the test
suite, and it fails because there is no `OPENAI_API_KEY`. CI on a fork cannot run because
secrets are not exposed to fork PRs. The barrier to a first contribution is a billing
relationship with a third party.

**Hardcoded model tables are wrong within weeks.** The 0.x codebase pinned model ids, context
windows and prices in Python. Every price change or model release needed a code change, a
review, and a release. The table was therefore usually stale, and cost estimates built on it
were quietly wrong.

## Decision

**1. `echo` is a first-class provider.** Always installed, no key, no network, zero cost.
`echo/echo` returns the rendered prompt; `echo/json` returns the render variables as JSON so
schema assertions are exercisable offline. It is the default model in a fresh workspace.

Consequence: `assay render`, `assay run`, `assay test`, `assay lint`, the MCP server and the whole
`/v1` API are all exercisable end to end with no credentials. Contributors validate templates,
schemas, guardrails, capability gating and every deterministic assertion before they own an
API key.

**2. The model catalogue is data, not code.** Loaded in priority order:

1. `$ASSAY_MODEL_CATALOG`
2. `<workspace>/models.json` — committed, so a team pins one shared view
3. `~/.assay/models.json` — refreshed by `assay models sync`
4. A small bundled seed

Earlier sources win. A malformed override is skipped, not fatal. **An unknown model resolves
to `None` and degrades to zero cost rather than raising** — being unable to price a model must
never mean being unable to run it.

## Consequences

**Good**

- `git clone && assay test` works, immediately, for anyone.
- CI on fork PRs is meaningful without secrets.
- Model prices track reality via `assay models sync`, no release required.
- Deterministic tests: `echo` makes the whole runtime reproducible.

**Costs**

- `echo` output is not model output, so it validates plumbing, not prompt quality. Documented
  plainly; `assay test -m <real-model>` is the quality gate.
- Cost figures are estimates from catalogue prices, not billed amounts. Providers round and
  discount differently. Documented as estimates everywhere they surface.
- A stale local catalogue silently under-reports cost. Mitigation: `assay models sync` and a
  planned staleness warning.

## Alternatives considered

**Mock provider only in tests.** Would leave the CLI unusable without keys — the exact barrier
we are removing. Making it a real, listed provider means the offline path is the one everyone
walks first, so it stays working.

**Bundle a full catalogue.** Large, stale on arrival, and a merge-conflict magnet. A small
seed plus `sync` keeps the repository clean and the data fresh.
