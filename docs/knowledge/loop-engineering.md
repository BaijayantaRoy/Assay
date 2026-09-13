# Loop engineering

> A **harness** equips one agent run. A **loop** is the outer system that keeps going: it
> discovers work, dispatches it, **verifies the result**, persists state, and decides
> whether to run again.

The shift is from being the person who prompts an agent turn by turn, to designing the
system that keeps poking agents on a schedule or until a goal is met.

---

## The one thing that matters most

**An agent reporting success is making a claim. A verification step that passes is
evidence.**

Loops that skip verification appear to work and quietly accumulate wrong results. The
agent marks its own homework and always gives itself an A.

So verification here defaults to a **separate, non-model check**:

```yaml
verify:
  command: "pytest -q"
  success_when: { type: exit_code, value: 0 }
```

An exit code cannot be talked into agreeing with you. Model-graded verification is
supported — `verify: { run: judges/some-judge }` — but it is opt-in and the linter says
so out loud, because a model grading a model is a weaker signal and the artifact should
admit it.

`assay lint` flags a loop with no `verify` block with exactly this message: *"the agent
marks its own homework."*

---

## Anatomy

```yaml
kind: loop
loop:
  trigger: goal              # goal | schedule | event | manual
  goal: The test suite passes
  max_cycles: 5
  budget: { cost_usd: 2.00, wallclock_s: 900 }
  orchestration: { pattern: sequential }

  steps:
    - id: find-failures
      run: agents/test-scanner       # a harness, a prompt, or a command
      output: failures
      verify:                        # per-step: catch a bad handoff here
        command: "test -s failures.txt"
        success_when: { type: exit_code, value: 0 }
      on_error: stop

    - id: fix
      run: agents/fixer
      with: { failures: "{{ failures }}" }

  verify:
    command: "pytest -q"
    success_when: { type: exit_code, value: 0 }

  on_verify_fail: retry            # retry | stop | escalate
  detect_stalls: true
  state: { path: .assay/state/{{ loop_id }}.json }
```

---

## Loop taxonomy

| Trigger | Runs when | Use for |
|:--|:--|:--|
| `manual` | you say so | development, one-off jobs |
| `goal` | until verification passes or a ceiling is hit | fix-until-green work |
| `schedule` | on a cron expression | digests, drift checks, nightly sweeps |
| `event` | on an external signal | issue opened, build failed, alert fired |

Only `manual` and `goal` execute today. `schedule` and `event` are declared in the spec
and are not wired to a scheduler — stated here rather than left to be discovered.

---

## Error compounding, and per-step verification

The arithmetic is the whole argument:

> A 90%-accurate step feeding another 90%-accurate step does not give you 90%. Errors
> stack. By step 18 of a 20-step chain you have a confident, coherent, completely wrong
> result.

The documented mitigation is **validation at each handoff** — checkpoints where errors
surface instead of snowballing. That is what per-step `verify:` is for.

The failure it prevents is specific and nasty: a *later* step papers over an *earlier*
step's garbage, the final check passes, and the loop reports success. There is a test for
exactly this — [`test_a_final_pass_can_hide_a_broken_intermediate_step`](https://github.com/BaijayantaRoy/Assay/blob/main/packages/assay-core/tests/test_loop.py).
The cycle-level `verified` says fine; `steps_verified` catches it.

```yaml
evals:
  - id: no-silent-corruption
    assert:
      - { type: goal_met }
      - { type: steps_verified }     # every handoff that declared a check, passed it
      - { type: cycles_under, value: 3 }
```

---

## Stalling

A loop that repeats itself is not failing — it is *stuck*, and the distinction matters
because the fixes differ. Verification failing means the work was wrong. Stalling means
there is no work: the agent produced the identical outcome and the check still failed.

The runtime fingerprints each cycle's step outcomes and stops when one repeats:

```
status: stalled
stop_reason: cycle 2 produced exactly the outcome of an earlier cycle and verification
             still failed, so nothing is changing. Stopping rather than burning the
             remaining cycles.
```

Stopping early is the point — the remaining cycles cost money and change nothing.

Set `detect_stalls: false` for loops whose steps legitimately produce identical output
while the world changes underneath them.

---

## Multi-agent patterns

Four are settled in practice:

| Pattern | Shape | Watch for |
|:--|:--|:--|
| **Sequential** | pipeline, each feeds the next | error compounding |
| **Concurrent** | fan out, aggregate | reconciling contradictory results |
| **Hierarchical** | supervisor delegates to workers | supervisor context bloat |
| **Handoff** | control routes to a specialist | A→B→A routing loops |

All four shapes are executable. Sequential remains the default.

Concurrent fan-out is explicit and bounded:

```yaml
orchestration: { pattern: concurrent, max_workers: 4 }
steps:
  - { id: security, run: agents/security-reviewer, output: security_review }
  - { id: quality, run: agents/quality-reviewer, output: quality_review }
```

Every branch receives the same frozen scope snapshot. Results are merged in declaration
order, not completion order. A branch cannot consume another branch's output; definitions
that try are refused with an instruction to use a sequential pipeline. Output variable
names must also be distinct.

A supervisor chooses only among workers declared in the file:

```yaml
orchestration:
  pattern: supervisor
  supervisor: agents/router
  worker_pattern: sequential       # or concurrent
steps:
  - { id: billing, run: agents/billing, description: Billing and invoices }
  - { id: identity, run: agents/identity, description: Login and access }
```

The supervisor receives `available_steps` and must return a JSON array of ids, or
`{"route":[...]}`. Unknown, empty or malformed routes fail closed. Before workers run,
the runtime checks the resolved targets for a repeated non-adjacent handoff such as
`agents/a → agents/b → agents/a`; it returns `status: routing_loop` and records the exact
route in `state.handoff_cycles`.

---

## Try it

```bash
assay loop loops/fix-until-green -g "make the tests pass"
assay test loops/fix-until-green
```

Over HTTP: `POST /v1/loops/{id}/run`. The `verified` field in the response is the one to
read — everything else is narration.

---

## Judgement calls

- **Write the verification first.** If you cannot state a mechanical check for "done",
  you do not have a loop, you have a hope. That is a useful thing to discover before
  building rather than after.
- **A command beats a judge.** Reach for a model-graded check only when no exit code can
  express the goal, and treat the result as weaker when you do.
- **Cycle count is a cost metric, not a quality metric.** A loop that converges in one
  cycle and one that converges in four may be equally correct; the four-cycle one is four
  times the bill.

---

## Sources

[Loop Engineering (Cobus Greyling)](https://cobusgreyling.medium.com/loop-engineering-62926dd6991c) ·
[AI Agent Design Patterns (Microsoft)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) ·
[Handoff orchestration](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/handoff) ·
[Multi-Agent Orchestration: 5 Patterns That Work](https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work)
