# assay — the Assay CLI

Git-native prompt engineering from the terminal.

```bash
pip install assay-cli
assay init my-prompts && cd my-prompts
assay test
```

No API key required — the offline `echo` provider is the default.

## Commands

| | |
|:--|:--|
| `assay init [path]` | create a workspace; `--from URL --dry-run` previews a remote PromptFile or v1 export |
| `assay new <id>` | scaffold a prompt |
| `assay import <source> --dry-run` | migrate Promptfoo, dotprompt, POML, Langfuse, PromptLayer, or raw messages |
| `assay ls` | list prompts, filter by `--tag` / `--status` |
| `assay show <id>` | inspect one prompt (`--raw` for the file) |
| `assay render <id> -v k=v` | fill variables, no model call |
| `assay run <id> -v k=v` | execute; reports tokens, latency and cost |
| `assay test [id]` | run embedded evals — **the CI gate** |
| `assay lint` | validate schema, style and workspace policy |
| `assay diff <a> [b]` | diff two prompts or two versions |
| `assay history <id>` | git history for a prompt |
| `assay models [ls\|sync]` | model catalogue; `sync` refreshes prices |
| `assay plugins` | inventory installed plugins, including load failures |
| `assay spec validate <path>` | schema-only validation |
| `assay mcp` | run the MCP server |
| `assay serve --proxy` | run the bounded OpenAI-compatible PromptFile proxy |

## Exit codes are a contract

| Code | Meaning |
|:--|:--|
| 0 | success |
| 1 | generic failure |
| 2 | usage error |
| 3 | validation / lint failure |
| 4 | **eval failure** |
| 5 | policy violation |
| 6 | provider or network failure |

Which makes CI a one-liner:

```yaml
- run: pip install assay-cli && assay test    # exit 4 fails the build
```

## Variables

```bash
assay run support/triage -v tier=pro -v count=3        # JSON-typed when parseable
assay run support/triage -v body=@./message.txt        # @ loads a file
assay run support/triage -f vars.yaml                  # or a whole file
```

Every command accepts `--json` for scripting, before or after the subcommand.

## OpenAI-compatible PromptFile proxy

Install the HTTP extra and expose reviewed prompt artifacts to clients that already use
Chat Completions:

```bash
pip install 'assay-cli[serve]'
assay serve --proxy                         # 127.0.0.1:8787
```

```bash
curl http://127.0.0.1:8787/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"assay:support/refund-triage","variables":{"customer_tier":"pro","message":"refund please"}}'
```

Add `"stream": true` for OpenAI-shaped SSE chunks and a final chunk carrying usage plus
Assay run evidence. `assay run <id> --stream` exposes the same contract in a terminal;
combine it with `--json` for newline-delimited delta/completed events.

The adapter accepts `model: assay:<prompt-id>` or a pinned
`assay:<prompt-id>@<version>`, validates `variables` against the artifact input schema,
and returns standard `choices` and `usage` fields plus provenance under `assay`. Exactly
one user text message may be mapped to the conventional `input` variable. Structured
artifacts should use `variables` explicitly.

This is intentionally not an arbitrary chat relay: conversation history, client tools,
streamed tool calls, sampled selection, multiple choices, and unrecognised behavioral
fields fail explicitly. A bind
outside loopback is refused unless `ASSAY_PROXY_TOKEN` is set; clients then send it as a
bearer token. The full workbench REST API remains the source-checkout server
(`python -m uvicorn backend.main:app`).

## License

MIT
