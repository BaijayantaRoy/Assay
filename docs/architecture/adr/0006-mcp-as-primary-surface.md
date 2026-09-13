# ADR-0006 — MCP as a primary surface, implemented without an SDK

**Status:** Accepted · **Date:** 2026-07-27

## Context

Most prompt work in 2026 happens *inside* an agent — Claude Code, Cowork, Cursor, Zed, or a
bespoke harness. A prompt library the agent cannot reach is a prompt library the agent will
route around by writing a new prompt inline, which is precisely the sprawl the library exists
to prevent.

MCP is the interoperability layer for that, and it treats prompts as a **first-class primitive**
with standard `prompts/list` and `prompts/get` methods — a near-exact match for what this
project stores.

Two complications:

1. **The protocol is moving.** The `2026-07-28` revision is the largest since launch: the
   `initialize`/`initialized` handshake is removed, `Mcp-Session-Id` is gone, `server/discover`
   replaces handshake-time capability exchange, list results gain `ttlMs`/`cacheScope`, tool
   schemas are lifted to full JSON Schema 2020-12, and `logging` is deprecated in favour of
   stderr and OpenTelemetry. Clients will be spread across revisions for a long time.
2. **SDKs move with it.** Depending on an MCP SDK means an SDK release can break this server.

## Decision

**MCP is a primary surface**, on equal footing with the CLI and the REST API — not a plugin,
not an afterthought.

**Implemented against the wire protocol using only the standard library.** No MCP SDK
dependency. JSON-RPC over stdio and over Streamable HTTP are both a few hundred lines.

**Dual-revision, decided per request rather than per connection:**

- a request carrying `initialize` gets the legacy handshake, with the protocol version echoed
  back from the client's request when we support it;
- `server/discover` is implemented for stateless clients;
- no session id is ever required, so both models coexist without branching state.

Additionally, aligned with the newer revision because these are strictly better and harmless
to older clients: `ttlMs`/`cacheScope` on list and read results; full JSON Schema 2020-12 in
tool schemas; the standard `-32602` for a missing resource; diagnostics to stderr; and no
external `$ref` dereferencing.

**The tool set closes a verification loop.** Alongside `assay_search`/`assay_get`/`assay_render`/
`assay_run` for retrieval and execution, `assay_create`/`assay_update` let an agent author, and
`assay_test`/`assay_lint` let it *check its own work*. An agent that can write but cannot verify
is the failure mode harness engineering warns about; giving it a way to prove a prompt still
passes its evals after an edit is the whole point.

## Consequences

**Good**

- Works today with clients on any revision from `2025-03-26` to `2026-07-28`.
- Cannot be broken by an SDK release; the only dependency is `assay-core`.
- Statelessness means horizontal deployment behind a plain round-robin load balancer — no
  sticky sessions, no shared session store.
- Prompts appear natively in the agent's prompt picker, with typed arguments derived from
  `input.schema`.

**Costs**

- We hand-maintain protocol conformance instead of inheriting it. Mitigated by a request/
  response test matrix across revisions, and the protocol surface we use is small and stable.
- No SSE streaming in the HTTP transport yet. Acceptable: prompt operations are short, and the
  newer revision de-emphasises long-lived streams anyway.
- Server-initiated requests (elicitation) are not implemented. Nothing here needs them.

## Alternatives considered

**Use the official Python MCP SDK.** Less code today, but couples our release cadence and
protocol support to theirs, and during a large protocol transition that coupling is exactly
the wrong dependency to take.

**Expose MCP only over HTTP.** Most desktop clients launch stdio subprocesses. Both are
supported; stdio is the default.
