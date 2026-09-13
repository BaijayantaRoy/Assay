# Mutation testing

> **Coverage tells you which lines ran. It does not tell you whether anything would have
> failed had those lines been wrong.**

A test that calls a function and asserts nothing scores identically to one that checks the
answer. This directory asks the question coverage cannot: *if we shipped this bug, would
anything go red?*

```bash
python tests/mutation/run_mutations.py --check    # anchors valid?  (~1s, CI gate)
python tests/mutation/run_mutations.py --list     # what is measured, and why
python tests/mutation/run_mutations.py            # full run (minutes)
python tests/mutation/run_mutations.py 0 5        # a slice, for time-boxed runs
```

Exit code is 0 only when every mutation was killed **and** every anchor resolved.

## The method

Each mutation breaks one claim this project makes in its README, its docs or its UI, then
runs the suite. If the suite still passes, the claim is undefended — **we could ship that
bug today**.

The mutations are hand-chosen rather than randomly generated. Random operator mutation
mostly turns up equivalent mutants and dead branches, and the survivors take longer to
triage than they are worth on a codebase this size. Deliberately breaking a stated promise
produces a shorter list where every survivor is worth acting on.

Current set (46): fencing tool output as untrusted, the injection scanner, fail-closed
red-team corpus contracts, deny-list
enforcement, tool-result guardrail enforcement, complete tool pinning, red-team usability
gating, unverified loops claiming success, constant-series
correlation, governance gaps, audit hash verification, attributable approvals, determinism
claims, paired A/B winner uncertainty, stall detection, handoff failure, spec
version refusal, unknown-field preservation, memory ranking weights, case-cluster confidence
intervals, ordered golden trajectories, dataset workspace containment, real concurrent
fan-out, explicit handoff-cycle stopping, incremental context items, selective result
clearing, strict optimizer output parsing, real repeated sampling, majority selection,
honest aggregate sampling cost, bounded streaming, fragmented streamed tool-call assembly,
stream-backed harness trajectories, adaptive red-team delivery, registry concurrency, and
rate-limit bounds.

## What this found

Run against the suite as it stood on 2026-07-28, before any of it was written for
mutation testing:

| Mutation | Result |
|:--|:--|
| Harness marks all tool output **TRUSTED** | **survived** |
| `pearson` returns 1.0 for a constant series | **survived** |
| Memory entity weight flattened below keyword | **survived** |
| 6 others | killed |

The first is the one worth dwelling on. `provenance.fence()` had thorough unit tests, so
the fence demonstrably *worked* — but nothing asserted the harness **used** it. You could
have changed one line so every tool result entered the model's context marked as trusted
operator instruction, and all 236 tests stayed green. A unit test of a lock does not tell
you the door is locked.

Fixing the three gaps required `test_harness.py` and `test_stats.py`, neither of which
existed. `harness.py` — the largest and most security-relevant module in the project — had
no dedicated suite at all; it was covered incidentally by tests that happened to run an
agent on their way to testing memory or red-teaming.

Two product bugs surfaced along the way, both found by writing the tests rather than by
the mutations:

- **Denied tool calls were counted as tool errors.** A harness whose deny list correctly
  fired reported errors, failed a `no_tool_errors` assertion for doing its job, and showed
  a warning in the workbench for a successful defence.
- **An unknown tool name silently returned success.** Any unrecognised name fell through
  to the `submit`-style declaration-only path and was handed back its own arguments as
  content — so a model that invented a tool was told the call had worked.

## Two rules this script follows, both learned by getting them wrong

**Never mutate prose.** The first version replaced the first textual match anywhere in the
file and reported a surviving mutant that had edited nothing but a docstring. That is a
false finding — precisely the failure mode this project exists to prevent — so anchors are
now rejected unless `tokenize` confirms they land on real code.

**Stale anchors fail loudly.** They used to print `SKIP` and exit zero, which silently
shrinks the suite every time someone refactors. `--check` is a hard failure, and it is what
CI gates on because it runs in about a second.

## Limits — read before quoting a number

- **The mutation score is not a quality score.** It measures 44 chosen claims, not the
  codebase. A 100% score here says those promises are defended; it says nothing
  about the rest.
- **Hand-chosen mutations reflect their author's blind spots.** Randomised operator
  mutation (`mutmut`, `cosmic-ray`) would find classes of bug this misses. Running one
  periodically is on the roadmap.
- **Only `assay-core` is covered.** The CLI, MCP server, REST API and frontend are not
  mutated; they are covered by `tests/e2e/` instead.
- **A killed mutant does not mean the test is good** — only that *something* failed. It
  could have been an unrelated assertion tripping over the change.

## Adding a mutation

Add a `Mutation` to `M` in `run_mutations.py`:

```python
Mutation(
    "short-kebab-name",
    "The claim this breaks, phrased as the promise a reader would believe.",
    SRC / "module.py",
    "exact source text to replace",     # must be real code, not a docstring
    "replacement that introduces the bug",
    [TESTS + "test_module.py"],         # expected to catch it; suite is the fallback
),
```

Then run `--check` to confirm the anchor resolves, and the mutation itself to confirm it
is killed. **A mutation that is already killed on the day you add it is still worth
adding** — it pins the behaviour against future regression, which is the point.
