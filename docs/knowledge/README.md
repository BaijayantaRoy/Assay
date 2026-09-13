# Knowledge centre

Reference material for prompt, context and agent engineering — written against the
survey in [RESEARCH.md](../architecture/RESEARCH.md) rather than from folklore.

**Every page is paired with something you can run.** Documentation that cannot be
executed goes stale silently, and a guide whose examples no longer work is worse than
no guide. Where a page shows a technique, there is a PromptFile in
[repository PromptFile](https://github.com/BaijayantaRoy/Assay/tree/main/prompts) that demonstrates it and a test that keeps it honest.

---

## The tracks

| | | Status |
|:--|:--|:--|
| [Agent harness engineering](harness-engineering.md) | The four elements, budgets, control, why the loop lives in a file | written |
| [Loop engineering](loop-engineering.md) | Outer loops, verification, stalling, error compounding | written |
| [Context engineering](context-engineering.md) | Compaction, memory, retrieval, the token economy | written |
| [Evaluating agents](evaluating-agents.md) | Three levels, trajectory assertions, judge calibration | written |
| [Prompt injection & agent security](agent-security.md) | Indirect injection, tool poisoning, what defence is worth | written |
| Prompting techniques | Structured output, reasoning budgets, model-specific notes | planned |
| Optimization | Reflective rewrite, DSPy/GEPA, ACE incremental context | planned |

Planned means not written. It is listed so the shape of the thing is visible, not to
imply it exists.

---

## How to read this

Start with whichever of these describes your problem:

**"My agent works in a demo and falls over on real tasks."**
→ [Agent harness engineering](harness-engineering.md). Most of that gap is the harness,
not the model — budgets, context management and control.

**"My agent finishes and I do not trust the result."**
→ [Loop engineering](loop-engineering.md), specifically the verification section. An
agent reporting success is making a claim; a check that passes is evidence.

**"My agent works for ten steps then loses the plot."**
→ [Context engineering](context-engineering.md). That failure is almost always a naive
truncation dropping the goal along with the noise.

**"My eval scores look fine but production does not."**
→ [Evaluating agents](evaluating-agents.md). End-to-end scores hide trajectory
problems, and an uncalibrated judge is an unknown measurement presented as a number.

**"I am about to give an agent tools and a file system."**
→ [Agent security](agent-security.md). Read it before, not after.

---

## A note on confidence

These pages distinguish three things, and say which is which:

- **Measured** — a number produced by this repository's own tooling, reproducible by you.
- **Reported** — a figure from published research, cited, not independently reproduced here.
- **Judgement** — an opinion formed while building this, offered as such.

Where the field disagrees, that is stated rather than resolved. Where a threshold is a
community convention rather than a physical constant, it says so.
