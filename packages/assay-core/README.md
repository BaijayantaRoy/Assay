# assay-core

The engine behind [Assay](https://github.com/BaijayantaRoy/Assay): a
plugin-first implementation of the [PromptFile v1](../../spec/promptfile-v1.md) specification.

```bash
pip install assay-core
```

```python
from assay_core import PromptFile, Runtime

prompt = PromptFile.load("prompts/support/refund-triage.prompt.md")
result = Runtime().run(prompt, {"message": "I want my money back"})

print(result.text, result.cost_usd, result.completion.usage.total_tokens)
```

Async applications use the same evidence path. Built-in network providers use native
`httpx.AsyncClient` calls; contract-1.0 sync-only plugins are isolated in a worker thread:

```python
result = await Runtime().arun(prompt, {"message": "I want my money back"})
report = await Runtime().aevaluate(prompt, max_concurrency=4)

async for event in Runtime().astream(prompt):
    if event.type == "delta":
        print(event.delta, end="", flush=True)
    else:
        auditable_result = event.result
```

`aevaluate` bounds active cases to 1–32, keeps test-time samples within each case serial,
and returns case evidence in declaration order. Its report names the actual concurrency
ceiling and measured wall time.

Explicit provider rate limits receive bounded sync/async retries (two by default), respect
`Retry-After` within a 30-second total wait ceiling, and leave retry evidence on the
completion. Other provider failures are not retried. Configure the bounds with
`rate_limit_retries`, `rate_limit_backoff_s`, and `rate_limit_max_wait_s` in `model.params`.

`astream` yields provider-neutral text deltas and one final event containing the normal
`RunResult`. If an output guardrail is declared, the runtime buffers the provider stream,
validates or transforms the complete answer, and only then releases text. Sync-only
providers produce one explicitly labelled buffered delta. Sampling and streamed tool calls
are rejected rather than given ambiguous merge semantics.

## What's in here

| Module | Responsibility |
|:--|:--|
| `promptfile` | Parse, validate and serialize PromptFiles with **lossless round-tripping** |
| `contracts` | The 13 plugin Protocols and their contract version |
| `registry` | Entry-point discovery, contract-version enforcement, failure isolation |
| `runtime` | The only place plugins are composed: render → guard → execute → guard → trace |
| `catalog` | Model metadata as data, not code |
| `workspace` | `assay.yaml` configuration |
| `builtins` | Renderers, providers, evaluators, guardrails and stores — registered through the same public entry points third parties use |

## Nothing is hardcoded

No provider, template dialect, evaluator, guardrail or storage backend is imported by core.
All 13 extension points resolve through the registry at runtime:

```toml
[project.entry-points."assay.providers"]
acme = "acme_assay:AcmeProvider"
```

That's the entire integration. See
[ADR-0002](../../docs/architecture/adr/0002-plugin-first-core.md).

## Works with no API key

The `echo` provider is a first-class offline backend, so the whole runtime — rendering,
guardrails, capability gating, evaluation — is exercisable with no credentials and no network.

```python
Runtime(default_model="echo/echo").run(prompt, {"name": "World"})
```

## License

MIT. The specification it implements is CC BY 4.0.
