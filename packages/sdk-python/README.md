# assay — Python SDK

One API, two modes. Application code written against one runs unchanged against the other.

```bash
pip install assay-client   # remote only
pip install "assay[local]" # + embedded engine
```

**Embedded** — reads PromptFiles off disk. No server, no network:

```python
from assay import Client

assay = Client.local("./prompts")
print(assay.run("support/refund-triage", {"message": "refund please"}).text)
```

**Remote** — same calls against a `/v1` server:

```python
assay = Client("https://prompts.acme.internal", api_key="…")
print(assay.run("support/refund-triage", {"message": "refund please"}).text)
```

A prototype reading local files becomes a production deployment by changing one constructor
call.

## API

```python
assay.list(prefix=..., tag=[...], status=...)   # -> list[PromptRef]
assay.get(prompt_id, version=...)               # -> dict
assay.render(prompt_id, variables, model=...)   # no model call
assay.run(prompt_id, variables, model=...)      # -> RunResponse
assay.evaluate(prompt_id, model=..., max_workers=4) # bounded eval report
assay.create(prompt_id, body, **fields)
assay.models(provider=...)
assay.health()
```

Streaming is an async iterator in both embedded and remote modes:

```python
async for event in assay.stream("support/refund-triage", {"message": "refund"}):
    if event["type"] == "delta":
        print(event["delta"], end="", flush=True)
    elif event["type"] == "tool_call_delta":
        print(event["tool_call"])
    else:
        result = event["result"]  # final usage, provenance, controls, and stream evidence
```

Tool-call events carry a stable call index plus name, id, and complete or fragmented
arguments. Output guardrails may deliberately buffer the answer before the first delta.
Inspect `event["buffered"]` and the final `result["streaming"]`; do not infer live token
timing from a buffered stream.

`RunResponse` carries `.text`, `.model`, `.provider`, `.cost_usd`, `.latency_ms` and `.usage`.

## License

MIT
