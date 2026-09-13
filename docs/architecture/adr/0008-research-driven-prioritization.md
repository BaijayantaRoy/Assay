# ADR-0008 — Prioritize from surveyed evidence, not from recall

**Status:** Accepted · **Date:** 2026-07-27 · **Amends:** [ROADMAP](../ROADMAP.md)

## Context

The v1.1 roadmap was assembled from what seemed important — curated prompt packs, a docs
site, importers, a UI migration. Agent harness and loop engineering were then added
because they were raised in conversation.

Neither of those is a method. The first is availability bias; the second is
responsiveness mistaken for research. Both produce a plan that looks reasonable and has
no relationship to where the field's difficulty actually is.

A systematic survey of fourteen sub-domains
([RESEARCH.md](../RESEARCH.md)) produced a materially different ordering. Six domains were
absent from the plan entirely. Two of them — **agent security** and **agent memory** — have
larger gaps than anything that was on it.

The survey also found a defect in code written the same day. The harness executor appended
tool output to the conversation as an ordinary message:

```python
messages.append(Message(role="user", content=f"[tool:{call.name}] {result.content}"))
```

That is the indirect prompt injection surface, in one line. Agent Security Bench reports a
top attack success rate of **84.3%** across 16 attack types against 11 defences; a 2026
disclosure exposed up to **200,000** vulnerable MCP instances. The defect was not found by
review or testing. It was found by reading the literature for the domain the code was in.

## Decision

**Roadmap priority is set from surveyed evidence, and the survey is a versioned artifact
in the repository.**

Three consequences bind:

1. **`RESEARCH.md` is maintained, not archived.** It carries a date and per-domain gap
   assessments. A roadmap item that no domain section supports needs a justification in
   the item itself.
2. **Any domain added to the roadmap gets surveyed first.** "We should support X" is a
   hypothesis; the survey decides whether X is where the difficulty is.
3. **Published thresholds are implemented as thresholds.** Where the field states a number
   — Cohen's κ ≥ 0.6 for judge rubrics, Spearman ≥ 0.80 for production judges, ≥ 500 cases
   for trustworthy aggregates — tooling enforces that number rather than inventing a
   friendlier one.

**Re-prioritised, ahead of everything previously in v1.1:**

| Priority | Item | Basis |
|:--|:--|:--|
| 1 | Tool-result provenance fencing, tool metadata pinning | RESEARCH §3.3 — fixes a shipped defect |
| 2 | `assay.memory` contract, episodic + semantic backends | §3.2 — largest wholly absent capability |
| 3 | Progressive disclosure in the MCP surface | §3.4 — prompt packs are harmful without it |
| 4 | `assay judge calibrate` (κ, Spearman) | §3.1 — published thresholds, near-zero adoption |
| 5 | `assay redteam` against an injection corpus | §3.3 — testing claims need substance |

**Re-scoped:**

- "Knowledge centre" moves from documentation to **tooling**. The valuable artifacts are
  `assay judge calibrate` and `assay redteam`, not essays about them.
- "Optimization" narrows from a DSPy adapter to **ACE-style incremental context updates**
  first (§3.5), because it improves a strategy already shipped and is far cheaper.

**Weakened claim:** documentation implied eval scores are comparable across runs. §3.10
shows they are not across infrastructure — batch-size dependence of reduction kernels
produces accuracy swings up to 9%. Every surface reporting a score now carries that caveat.

## Consequences

**Good**

- The plan reflects the field rather than the author's memory of it.
- A defect class was found before release rather than by a user.
- Published thresholds give the project falsifiable quality claims instead of adjectives.
- Contributors can argue with the *survey*, which is a better argument than arguing with a
  roadmap that has no stated basis.

**Costs**

- Surveying is slow, and it delayed shipping v1.1 features that were already scoped.
- `RESEARCH.md` dates quickly. An out-of-date survey presented as current is worse than
  none, so it needs a review cadence — quarterly, or when a domain is next touched.
- Published thresholds are themselves contested. Implementing κ ≥ 0.6 as a gate encodes one
  community's convention; the tooling should report the number and cite its source rather
  than presenting it as physics.

**Accepted limitation**

The survey used secondary sources and abstracts, not full replication of the papers cited.
It is good enough to set priority order and not good enough to settle a technical dispute.
Where a decision turns on a specific result, read the paper.

## Alternatives considered

**Keep the intuitive roadmap and add security later.** Rejected: the defect was already in
`main`, and "later" for an injection surface means "after someone is affected".

**Survey continuously instead of as an artifact.** Attractive, but an unwritten survey
cannot be reviewed, dated, or disagreed with. Writing it down is most of the value.
