# Context engineering

> Managing every piece of information the model sees at inference: instructions, memory,
> retrieved knowledge, tool output, conversation history.

The characteristic failure is late, not early. An agent works for ten iterations and by
thirty it is repeating tool calls or has forgotten the goal — because a naive truncation
dropped the instructions along with the noise.

---

## The rule that prevents most of it

**Pin the system prompt and the original goal unconditionally.** Every context strategy
in this project does this. It costs a few hundred tokens and prevents the single most
common long-run failure.

Everything else — what to drop, what to summarise, what to retrieve — is optimisation on
top of that floor.

---

## Strategies

| Strategy | What it does | Cost | When |
|:--|:--|:--|:--|
| `none` | keeps everything | none | short runs; fails loudly when full |
| `truncate` | drops oldest middle turns, keeps pinned prefix + recent tail | none | simple long runs |
| `selective_clear` | clears only bulky old tool results; keeps surrounding reasoning | none | retrieval-heavy runs |
| `compact` | incrementally maintains a source-labelled itemized digest | none | **the default worth using** |
| `summarize` | asks a model to summarise dropped turns | a model call, and it can fail | high-fidelity long runs |

```yaml
harness:
  context:
    strategy: compact
    max_tokens: 100000
    keep_first: 1      # the goal
    keep_last: 6       # recent working memory
```

`none` failing loudly is deliberate. A hard provider error is more debuggable than an
agent that silently lost its instructions.

`compact` is the recommended default because it is cheap, predictable, and lists exactly
what an agent needs to avoid redoing work. Items are keyed by call signature, so repeated
work updates one bullet rather than growing duplicates. Each item names its tool source,
step and status; injection-shaped previews are withheld. Before whole-turn compaction it
selectively clears eligible old tool bodies, often preserving the assistant's reasoning.
No model call means it cannot fail or cost anything. `summarize` falls back to it when no
summariser is available, so a harness never breaks because summarisation did.

---

## Memory is not a longer prompt

In 2026 memory is treated as a **dedicated architectural component**, separate from the
context window. The split:

- **Short-term** — the current conversation, tool calls and results.
- **Long-term episodic** — concrete past trajectories and failure cases.
- **Long-term semantic** — distilled rules, preferences, project conventions.

```yaml
harness:
  memory:
    backend: jsonl
    namespace: incidents
    recall: { limit: 3 }
    write: { on: [failed] }     # often the higher-value setting
```

**Recall is hybrid**, and the weighting is a deliberate choice: entity match ranks
highest, above keyword overlap and recency. Exact identifiers — `billing/invoice.py`,
`PROJ-412` — are what actually stop an agent redoing work, and they are precisely what
embedding similarity is worst at. The default backend uses no embeddings at all; that
keeps memory offline and dependency-free, and a vector backend is a plugin for the
paraphrase cases.

**`write: { on: [failed] }` is worth considering as the default.** A recorded failure
prevents a repeat. A recorded success rarely changes anything.

**Recalled memory is fenced as `derived`, not as operator instruction.** Without that, a
single injected run poisons memory and becomes a persistence mechanism for its own
injection on every subsequent run. See [agent security](agent-security.md).

### A sceptical note worth carrying

There is a strand of the literature arguing that much of what is marketed as agent memory
is retrieval with extra steps. That reading seems right, and this implementation agrees
with it: memory here is a retrieval-and-persistence problem with a scoring function, not
cognition. Naming it honestly makes it easier to reason about.

---

## The token economy

A prompt library's whole value is having many prompts. But a server that returns full
metadata for every prompt spends the client's context before any work begins.

**Progressive disclosure** is the measured answer: load in tiers, on demand. Names and
one-line descriptions first, full body only when selected, bundled files only when read.

Measured in this repository, at 200 prompts:

```
without tiering   73,392 tokens
tier-1 index       1,924 tokens        97% saved
per prompt          87.5 tokens
```

*(Measured. Run `assay tokens` in your own workspace to reproduce it.)*

Two details that matter as much as the tiering:

- **Ordering must be stable.** A reshuffled prefix invalidates the client's prompt cache
  and silently multiplies cost. Ordering here is content-derived and deterministic.
- **Omission must be informative.** When the budget binds, "180 omitted, use search"
  tells a client nothing. A namespace histogram — `{support: 25, legal: 25, …}` — costs a
  few dozen tokens and makes the follow-up search informed rather than blind. That design
  only appeared after measuring the first version and finding it useless.

---

## Just-in-time retrieval

Rather than pre-loading content, put **handles** in context — file paths, ids, query
strings — and let the agent pull what it needs. `assay://prompt/<id>` and
`attachment_refs` follow this pattern: the identifier is cheap, the content is fetched
only if the agent decides it matters.

---

## Remaining limits

Stated plainly:

- **Cross-source confidence.** Tool provenance is preserved, but facts are not yet assigned
  calibrated confidence when multiple sources disagree.
- **Model-summary provenance.** Mechanical `compact` items retain provenance. Free-form
  `summarize` output still depends on the summarizer following its instruction.

---

## Try it

```bash
assay tokens                          # what your library costs a client
assay memory stats                    # what agents have remembered
assay memory search "billing/invoice.py"
```

---

## Sources

[Context Engineering for AI Agents (mem0)](https://mem0.ai/blog/context-engineering-ai-agents-guide) ·
[Context Engineering: A Practical Guide (Sourcegraph)](https://sourcegraph.com/blog/context-engineering) ·
[State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) ·
[Contextual Agentic Memory is a Memo, Not True Memory](https://arxiv.org/pdf/2604.27707) ·
[Agent Skills: Progressive Disclosure](https://www.newsletter.swirlai.com/p/agent-skills-progressive-disclosure)
