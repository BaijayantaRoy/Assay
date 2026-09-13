# Evaluating agents

The distance between "we have evals" and "we have evidence" is mostly rigour, not
features.

---

## Three levels, not one

| Level | Question | Catches |
|:--|:--|:--|
| **End-to-end** | did the task succeed? | nothing about *how* |
| **Trajectory** | was the path sound and efficient? | wandering, loops, skipped steps, blown budgets |
| **Component** | which tool, retriever or sub-agent broke? | attribution |

Most teams have the first. It is the least informative of the three for agents, because
an agent can produce a correct answer through a process you would never ship.

This project implements all three levels. Component attribution is evidence from the evaluator,
not causal inference: it identifies the smallest component directly implicated by a failed
assertion, but does not claim that replacing that component alone will repair the outcome.

---

## Trajectory assertions

For a frozen reference path, use the deterministic `trajectory_accuracy` evaluator:

```yaml
assert:
  - type: trajectory_accuracy
    threshold: 0.8
    value:
      - { tool: fs.search, arguments: { query: retry } }
      - fs.read
      - shell.run
```

It computes an order-aware longest-common-subsequence match, then reports tool-call precision,
recall and F1. Extra calls lower precision; missing or reordered calls lower recall; expected
arguments are required subsets. This is reference-path agreement, not proof that the reference is
the only valid solution. Use looser thresholds or separate golden paths when the task legitimately
admits several methods.

Evaluation reports also group failures by the smallest identified component (tool, sub-agent,
step, verifier, evaluator, runtime, or final output) and provide a seeded 95% case-cluster
bootstrap interval. Bounds are withheld for fewer than three usable cases; unverified cases never
enter the denominator silently.

Ordinary assertions score the final string. These score how the agent got there:

```yaml
evals:
  - id: researches-before-answering
    input: { question: "why did the retry logic change?" }
    assert:
      - { type: tool_call_order, value: [fs.grep, fs.read] }
      - { type: tool_called, value: fs.grep }
      - { type: tool_not_called, value: shell.run }
      - { type: no_repeated_tool_call }
      - { type: iterations_under, value: 8 }
      - { type: budget_under, value: 0.10 }
      - { type: no_denied_calls }
      - { type: completed }
```

Full set: `tool_called`, `tool_not_called`, `tool_call_order`, `trajectory_accuracy`,
`no_repeated_tool_call`,
`iterations_under`, `tool_calls_under`, `budget_under`, `no_tool_errors`,
`no_denied_calls`, `completed`, `verified`, `steps_verified`, `cycles_under`, `goal_met`,
`memory_recalled`, `memory_written`, `injection_detected`, `no_injection_compliance`.

Attached to a plain prompt rather than a harness, a trajectory assertion **fails loudly**
rather than silently passing. An assertion that cannot fail is decoration.

---

## Judge calibration

An LLM judge produces a number between 0 and 1. That number looks like a measurement,
gets averaged, plotted, and used to gate deploys. Nothing in that pipeline ever checks
whether it tracks what a human would say.

**An uncalibrated judge is not a weak measurement. It is an unknown one**, and an unknown
measurement presented as a score is worse than no score, because it gets acted on.

### The two-stage gate

The stages diagnose different faults, which is why collapsing them into one number loses
the diagnosis.

**Stage 1 — is the rubric usable?** Measure agreement *between human raters* (Cohen's κ).
If humans cannot agree with each other, the rubric is ambiguous, and calibrating a judge
against an ambiguous rubric measures nothing. The cited action below κ 0.6 is to fix the
**rubric**, not the judge.

**Stage 2 — does the judge track humans?** Measure the judge against human consensus
(Spearman ρ). The cited bar for production alignment is ρ ≥ 0.80.

```bash
assay judge calibrate --labels reviews.labels.jsonl --write
```

This is not hypothetical. Running it on a deliberately ambiguous label set:

```
Stage 1  inter-rater κ  0.013   →  rubric FAILS
Stage 2  Spearman ρ     0.657   →  judge FAILS
```

The judge looks broken. It is not — it was calibrated against noise. A single-stage tool
would have sent someone to fix the wrong thing.

### The published thresholds

| Threshold | Value | What it gates |
|:--|:--|:--|
| Inter-rater Cohen's κ | ≥ 0.60 | the rubric is usable at all |
| Judge–human Spearman ρ | ≥ 0.80 | the judge may gate production |
| Sample size | ≥ 500 cases | aggregates are trustworthy |
| Human raters | ≥ 2, independent | agreement is measurable |

These are **conventions from one research community, not physical constants.** They are
configurable under `judge.thresholds` and always reported next to the raw numbers so you
can disagree with them.

### Guards worth knowing about

- **Degenerate judges are rejected.** Near-zero score variance correlates with nothing,
  however confident it looks.
- **Bias is reported separately.** Rank correlation can be perfect while absolute scores
  are systematically shifted a full point.
- **Bootstrap intervals on everything.** A 40-case sample shows as a wide interval, not a
  confident point.
- **Certificates expire** (180 days by default). Agreement measured against last
  quarter's distribution is not evidence about this quarter's.

### Chain-of-thought judging

Forcing the judge to articulate reasoning *before* scoring measurably improves alignment
with human judgement (the G-Eval result) and mitigates several known biases. It costs
more tokens. This project makes it the default template, on the view that an unreliable
cheap score is not a saving.

---

## What eval scores cannot tell you

**They are not reproducible across infrastructure.** Temperature 0 plus a fixed seed does
*not* give determinism. The dominant cause is batch-size dependence of reduction kernels —
batch composition varies with concurrent load — not floating-point non-associativity. The
reported consequences are large: accuracy swings up to 9%, and response lengths differing
by thousands of tokens, from changing GPU count or hardware alone.

Practically: **compare scores within one environment only.** A 2% improvement measured on
different infrastructure is not an improvement, it is noise. Assay records a privacy-safe
environment fingerprint on every run and exposes a `comparison_warning` when fingerprints
or inference conditions differ; matching fingerprints still do not eliminate model noise.

### Test-time compute

`model.params.samples` makes bounded, real calls rather than passing a hopeful vendor
parameter. Majority selection covers normalized text and tool calls. A declared verifier
can instead return strict JSON scores. Eval reports pair accuracy with total cost, the
single-sample cost reference and incremental sampling spend. That is one operating point,
not proof that the extra calls caused the score; rerun the same cases at another sample
count for that comparison.

---

## Try it

```bash
assay test                              # everything, exit code 4 on failure
assay test agents/researcher            # one harness, with its trajectory
assay judge calibrate -l labels.jsonl   # the two-stage gate
assay judge check judges/quality        # is the certificate valid and current?
```

In CI, `assay test` is the whole gate — exit code 4 fails the build.

---

## Sources

[LLM-as-Judge Patterns for Agent Evaluation](https://zylos.ai/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/) ·
[LLM Agent Evaluation Metrics 2026](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide) ·
[Agent Evaluation Framework (Galileo)](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks) ·
[Numerical Sources of Nondeterminism in LLM Inference](https://arxiv.org/pdf/2506.09501) ·
[vLLM reproducibility](https://docs.vllm.ai/en/latest/usage/reproducibility/)
