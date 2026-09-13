# Agent harness engineering

> An agent harness is the runtime layer around a model: **an agent loop, a tool
> interface, context management, and control mechanisms.** Most of the engineering work
> in an agent lives in the harness, not in the model.

The practical consequence is uncomfortable and useful: when an agent that demos well
falls over on real work, the model is rarely what changed. The harness is.

---

## The four elements

### 1. The agent loop

Reason, act, observe, repeat. In this project that loop is
[`assay_core/harness.py`](https://github.com/BaijayantaRoy/Assay/blob/main/packages/assay-core/src/assay_core/harness.py), and the
parameters that govern it live in the PromptFile rather than in code:

```yaml
kind: harness
harness:
  loop: react
  max_iterations: 12
  budget: { cost_usd: 0.50, wallclock_s: 120, tool_calls: 30 }
  stop_when:
    - { type: tool_called, value: submit }
```

**Why the file and not the code.** Iteration ceilings, budgets and stop conditions are
the parameters that decide whether an agent is safe and affordable. Buried in application
code they are invisible to review and untestable in CI. In a file they diff in a pull
request, and `assay test` fails the build when a change makes the agent wander.

**Budgets are not optional.** A loop without a ceiling is an unbounded spend, and an
unbounded spend is an incident waiting for a trigger. `assay lint` flags a harness with no
budget for exactly this reason.

### 2. The tool interface

The pattern that has repeatedly outperformed large bespoke catalogues: **expose a
filesystem and a few general verbs rather than one tool per task.** Microsoft's SRE agent
work reported moving from 100+ bespoke tools to a filesystem-based interface — read,
grep, find, shell — and an "Intent Met" score rising from 45% to 75% on novel incidents.
*(Reported, not reproduced here.)*

The reasoning is simple enough to trust: a model that can `read`, `grep`, `list` and
`write` can accomplish things nobody anticipated. A model with forty narrow tools can do
exactly the forty things someone thought of.

Tools here are a plugin contract (`assay.tools`), so exposing an internal system to every
harness in a workspace is one package install, and every harness gets the same audit and
control path.

### 3. Context management

Covered in depth in [context engineering](context-engineering.md). The short version:
this is the element that decides whether a long run stays coherent, and the failure is
characteristic — fine for ten iterations, incoherent at thirty, because a naive
truncation dropped the goal along with the noise.

Every strategy in this project pins the system prompt and the original goal
unconditionally. That single rule prevents the most common long-run failure.

### 4. Control

The element that separates a demo from something you point at a real system. Controllers
are consulted **before every tool call and before every iteration**, so a policy can halt
a run rather than merely reporting on it afterwards.

```yaml
control:
  deny: [shell.run]                 # never, regardless of anything else
  require_approval: [fs.write]      # needs an approver, or it does not run
  allow_shell: false
  max_repeated_calls: 2             # the stuck-agent signature
  max_consecutive_errors: 3
  sandbox_root: ./workspace
```

`max_repeated_calls` deserves a note. An agent calling the same tool with identical
arguments and expecting a different answer is the clearest signal it has lost the plot.
Catching it costs nothing and saves a budget.

All controllers **fail closed**: an error while deciding is a denial, not an allowance.

---

## The output is a trajectory, not an answer

A prompt produces a completion. A harness produces a
[`Trajectory`](https://github.com/BaijayantaRoy/Assay/blob/main/packages/assay-core/src/assay_core/contracts.py) — every model turn,
tool call, observation, guardrail decision and memory operation.

This matters because **most interesting agent failures are invisible in the output**:

- it answered confidently without ever searching;
- it called the same tool eleven times;
- it took thirty iterations to do a two-step job;
- it succeeded, but only by writing somewhere it should never have touched;
- it "finished" without any verification ever passing.

None of those show up in the final string. All of them show up in the trajectory, and all
of them are assertable:

```yaml
evals:
  - id: searches-before-answering
    assert:
      - { type: tool_call_order, value: [fs.grep, fs.read] }
      - { type: iterations_under, value: 8 }
      - { type: no_repeated_tool_call }
      - { type: budget_under, value: 0.10 }
      - { type: no_denied_calls }
```

`assay lint` warns when a `stable` harness asserts only on output, because that is the
review gap through which agent regressions actually arrive.

---

## Failure modes, and what catches them

| Failure | Signature | Catch it with |
|:--|:--|:--|
| Answers without gathering | no tool calls before the answer | `tool_called`, `tool_call_order` |
| Stuck in a rut | same tool, same arguments, repeatedly | `no_repeated_tool_call`, `control.max_repeated_calls` |
| Wanders | correct answer, thirty iterations | `iterations_under` |
| Runs away | cost climbs, no progress | `harness.budget`, `budget_under` |
| Wants forbidden actions | policy blocks it and it retries | `no_denied_calls` |
| Degrades late in a run | coherent early, confused at step 30 | context strategy — see [context engineering](context-engineering.md) |
| Obeys its input | acts on text from a tool result | see [agent security](agent-security.md) |

A passing run that trips `no_denied_calls` is worth reading: the agent *wanted* to do
something it was not permitted to do, and only policy stopped it.

---

## Try it

The repository ships a working harness. No API key needed — the offline `echo/agent`
provider emits scripted tool calls, so the whole loop is exercisable and testable.

```bash
assay ls                                   # find the harnesses
assay agent agents/researcher -g "find the retry bug"
assay test agents/researcher               # its trajectory assertions
assay redteam agents/researcher            # see the security section
```

Over HTTP, `POST /v1/harnesses/{id}/run` returns the full trajectory — every step, tool
call and decision — at `http://localhost:8001/docs`.

---

## Judgement calls

Things I believe from building this, offered as opinion rather than finding:

- **The budget matters more than the prompt.** A mediocre prompt with a hard ceiling is
  operable. An excellent prompt without one is a liability.
- **Fewer, more general tools beat many specific ones**, and the crossover point is
  lower than it feels — somewhere well under twenty.
- **Iteration count is the most useful single health metric.** It moves before quality
  does. An agent that used to finish in six steps and now takes fourteen is telling you
  something before any eval score changes.

---

## Sources

[Agent Harness Engineering (Addy Osmani)](https://addyosmani.com/blog/agent-harness-engineering/) ·
[Code as Agent Harness](https://arxiv.org/pdf/2605.18747) ·
[awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) ·
[Context engineering for AI agents](https://mem0.ai/blog/context-engineering-ai-agents-guide)
