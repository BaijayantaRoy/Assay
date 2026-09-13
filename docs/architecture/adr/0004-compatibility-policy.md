# ADR-0004 — Compatibility policy

**Status:** Accepted · **Date:** 2026-07-27

## Context

The project's stated goal is that a prompt written today still works in five years, and that
something invented in five years drops in without a rewrite. That is a promise about *change
management*, and promises about change management have to be written down and mechanically
enforceable, or they are just optimism.

The MCP specification is a useful precedent here. Its `2026-07-28` revision shipped breaking
changes *and simultaneously* introduced a formal feature lifecycle — Active → Deprecated →
Removed, with a minimum twelve months between deprecation and earliest removal — plus an
extensions framework so new capabilities can ship and stabilise outside the core spec. That
combination is the right shape, and this ADR adopts it.

## Decision

Three surfaces version independently, each with an explicit rule.

### 1. PromptFile spec — `promptfile: <integer>`

| Change | Impact |
|:--|:--|
| New optional field | none — additive within v1 |
| New member of an open vocabulary (`kind`, capabilities, assertion `type`) | none |
| New `x-` extension | none |
| Field becomes required, or semantics change | major bump |
| Field removal | deprecate ≥ 12 months, then major bump |

Enforced by three conformance rules:

1. A reader **must refuse** a major version it does not implement. No best-effort parsing.
2. A reader **must ignore** unknown fields.
3. A writer **must preserve** unknown fields, including all `x-` keys, on round-trip.

Rule 3 is the load-bearing one, and it is covered by a test that asserts byte-stability across
parse → write → parse. It is what lets a newer tool add fields that an older tool neither
understands nor destroys.

### 2. Plugin contracts — `CONTRACT_VERSION`

Additive change (new optional method, new optional keyword argument) bumps **minor** and is
backward compatible. Anything else bumps **major**, and the previous major is supported
alongside the new one for **at least twelve months**.

The registry refuses to load a plugin whose contract major differs from core's, with an error
naming both versions. A plugin ecosystem where version mismatch produces a confusing
`AttributeError` at call time is a plugin ecosystem nobody contributes to twice.

Contract 1.1 is the first exercised minor evolution: it adds optional `AsyncProvider` and
`StreamingProvider` protocols. A 1.0 provider still loads; `Runtime.arun` executes its sync
method in a worker thread and `Runtime.astream` emits labelled buffered text and complete
tool-call deltas. Native 1.1 streams may emit fragmented tool arguments keyed by a stable call
index; core assembles them and fails closed unless they decode to JSON objects. No plugin is
required to pretend it supports native async I/O or incremental streaming.

### 3. REST API — `/v1`

Additive only within a major version. Deprecations are advertised with RFC 8594 `Deprecation`
and `Sunset` headers for ≥ 12 months. Breaking changes ship as `/v2` while `/v1` keeps
running. Clients may pin with `X-Assay-Api-Version`, and a mismatch fails fast rather than
drifting.

### Migration is a plugin, not a rewrite

No automated major-version migration command ships in v1. When one is introduced, upgrading
will be a command, not a project.

## Consequences

**Good**

- Contributors and downstream users know exactly what stability they are getting.
- The twelve-month floor means "we deprecated it" can never be a same-week surprise.
- Round-trip preservation makes the ecosystem additive: experiments do not require forks.

**Costs**

- Carrying two plugin contract majors for a year is real maintenance work.
- Additive-only forces some awkward field names rather than renames. That is the correct
  trade: a slightly ugly stable name beats a pretty breaking one.
- Round-trip preservation means we cannot normalise away fields we consider junk.

## Alternatives considered

**SemVer on the whole repo.** Too coarse. The spec, the plugin contracts and the HTTP API
change at genuinely different rates; coupling them forces false major bumps and makes the
version number meaningless.

**"We're pre-1.0, anything can change."** Honest, and fatal for a project asking people to
store their prompts in its format. Stability is the product.
