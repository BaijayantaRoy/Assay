# Testing

Seven layers, each answering a question the others cannot.

| Layer | Location | Question it answers | Runtime |
|:--|:--|:--|:--|
| **Unit** | `packages/assay-core/tests/` | Does the engine behave? | ~5s |
| **End-to-end** | `tests/e2e/` | Does the *product* behave — real binary, real port, real stdio? | ~90s |
| **Mutation** | `tests/mutation/` | Would a bug in a documented claim be caught? | minutes |
| **Backend** | `backend/tests/` | Do backend security, measurement, observability, and opt-in compatibility paths behave? | ~2s |
| **Browser** | `frontend/tests/browser/` | Does the live workbench remain accessible, responsive, and secret-free at key journeys? | ~15s |
| **Performance** | `tests/performance/` | Does bounded eval execution preserve evidence while materially reducing synthetic wait time? | ~2s |
| **Cross-language conformance** | `spec/conformance/`, `packages/promptfile-typescript/` | Do independent Python and TypeScript readers agree on acceptance and unknown-field preservation? | ~5s |

```bash
pytest packages/assay-core/tests            # fastest signal, run this constantly
pytest tests/e2e                            # before pushing
cd frontend && npm run test:browser         # live Chrome, backend and frontend
python tests/mutation/run_mutations.py      # when changing the engine or the tests
python tests/performance/run_eval_throughput.py --check
cd packages/promptfile-typescript && npm test
assay test                                  # the product testing its own prompts
```

No API key is needed anywhere. The offline `echo` provider makes the whole surface
exercisable, so the suite runs on a fork with no secrets and CI never bills anyone.

## Why these layers

**Unit tests catch logic errors.** They are fast enough to run on every save, so they are
where most assertions live.

**End-to-end tests catch seam errors**, which is where every bug that reached a *user* in
this project has actually lived: a batch file that closed silently, a `.next` cache deleted
on every start, an MCP tool that stopped answering to its own name, a red-team report
showing 0% because nothing ran. In-process tests cannot see any of those, which is why
`tests/e2e/` drives the installed binary through a subprocess, a real uvicorn on a real
port, and a real MCP process over stdio.

**Mutation tests catch missing assertions** — tests that run code without checking it.
Coverage cannot distinguish those from real tests. See
[`tests/mutation/README.md`](mutation/README.md); it found three undefended claims on its
first run, including one where the harness could have marked every tool result as trusted
with the whole suite still green.

**`assay test`** is the product applied to itself: the example prompts, harnesses and loops
in `prompts/` carry their own eval cases, and CI runs them. If the tool cannot test its own
artifacts, it should not be asking anyone else to trust it with theirs.

## Conventions

**Test names are sentences.** `test_a_failed_handoff_stops_the_chain_at_the_step_that_broke`
tells a reader what broke without opening the file. A failure report should be readable by
someone who has never seen the code.

**Docstrings say *why the test exists*, not what the code does.** Several record the bug
that motivated them. That is the context most likely to be missing in two years, and the
thing most likely to stop someone deleting a test they think is redundant.

**Assertion messages name the consequence.** `"a denied call was counted as a tool error,
conflating a working security control with a broken tool"` beats `assert x == y`.

**A test that cannot fail is worse than no test**, because it reads like coverage. Two
memory tests in this repo asserted an ordering that held regardless of the weights they
claimed to be testing; mutation testing caught both. If you are not sure a test can fail,
break the code on purpose and check that it does.

## What is not tested, honestly

- **The frontend has no component tests.** Eight `/v1` pages, typechecked and gated by
  `tests/e2e/test_ui_contract_e2e.py` at the API boundary, but no rendering tests. The
  contract tests catch a backend field rename; they would not catch a broken chart.
- **Property scope is narrow.** Hypothesis now generates nested JSON-compatible unknown fields
  across Markdown, YAML, and JSON round-trips. Other state machines and parser boundaries
  still rely on examples and mutation tests.
- **Performance scope is narrow.** A structural regression proves `discover()` prunes
  dependency trees, and a deterministic benchmark gates bounded eval scheduling at ≤50% of
  serial median time with identical evidence. Large real repositories and hosted models do
  not yet have cross-platform latency budgets.
- **Live providers are never called.** Built-in async parsing is tested without credentials,
  but real provider behavior—streaming, rate limits, malformed responses, and regional
  latency—remains unexercised.
- **Cross-language scope is intentionally small.** The shared corpus has three valid and
  three invalid files. Python adds generated nested JSON values; TypeScript does not yet run
  an equivalent property generator, and neither reader promises comment or quoting retention.
- **Only `assay-core` is mutated.** The CLI, MCP server and REST API rely on `tests/e2e/`.

Coverage sits around 80% on `assay-core`. That number is reported because it is easy to
measure, not because it means much on its own — the mutation suite is the more honest
signal, and its own limits are documented alongside it.

## Known limitation

Under tight resource limits — a constrained container, few available PIDs — running all
`tests/e2e` modules in one process alongside a long-lived uvicorn can stall. Each module
passes independently, and CI runs them as separate steps for this reason, which also
produces clearer failure attribution. If you hit it locally, run the modules separately.
