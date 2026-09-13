# assay-mcp

Serve your prompt library to any MCP client — Claude Code, Cowork, Cursor, Zed, Continue, or
your own agent harness.

```bash
pip install assay-mcp
```

```jsonc
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

## What it exposes

**Prompts** — every PromptFile appears natively in the client's prompt picker via
`prompts/list` and `prompts/get`, with typed arguments derived from `input.schema`.

**Resources** — raw PromptFile sources, the workspace config, the model catalogue, and the
PromptFile specification itself, so an agent can read the format before writing one.

**Tools**

| Tool | Purpose |
|:--|:--|
| `assay_search` | find a tested prompt by intent instead of inventing one |
| `assay_get` | full source, optionally at a historical version |
| `assay_render` | fill variables without calling a model |
| `assay_run` | execute and report cost |
| `assay_test` | **run the evals** — prove an edit didn't regress |
| `assay_lint` | validate the whole workspace |
| `assay_create` / `assay_update` | author and revise, with an optional git commit |
| `assay_models` | catalogue with context windows, capabilities and pricing |

The pairing that matters is `assay_update` + `assay_test`: an agent that can write *and verify* its
own work. Writing without a way to check the result is where agent workflows fail.

## Protocol support

Speaks both the session-based revisions (`2025-11-25` and earlier) and the stateless
`2026-07-28` revision, decided per request:

- legacy `initialize` handshake honoured, protocol version echoed back
- `server/discover` implemented for stateless clients
- no session id ever required, so the HTTP transport scales behind a plain round-robin load
  balancer with no sticky routing
- `ttlMs` / `cacheScope` on list results; full JSON Schema 2020-12 tool schemas; diagnostics to
  stderr rather than the deprecated `logging` capability

**Implemented with the standard library only.** No MCP SDK dependency, so an SDK release
cannot break this server. See
[ADR-0006](../../docs/architecture/adr/0006-mcp-as-primary-surface.md).

## Transports

```bash
assay mcp                                  # stdio (default)
assay mcp --transport http --port 8765     # Streamable HTTP
```

## License

MIT
