# ADR-0009 — Rename to Assay, and separate the spec from the brand

**Status:** Accepted · **Date:** 2026-07-28 · **Supersedes:** the `MyPromptLibrary` /
`mpl` naming throughout

## Context

The project shipped under the name `MyPromptLibrary`, with `mpl` as the CLI binary, the
package prefix, the environment-variable prefix, the plugin entry-point namespace, the
error-code namespace, the state directory — and, critically, **the required first key of
every PromptFile**:

```yaml
---
mpl: 1
id: agents/researcher
---
```

Four problems, in rising order of cost.

**The name describes a product we no longer ship.** "Library" implies storage; this is a
runtime with an execution engine. "Prompt" covers perhaps a third of the surface — there is
nothing in the name about harnesses, verified loops, agent memory, red-teaming, judge
calibration or governance evidence. "My" reads as a personal scratch project.

**`mpl` is the universal abbreviation for matplotlib.** `import matplotlib as mpl` is the
idiomatic convention, and the `mpl-*` distribution namespace on PyPI is effectively
matplotlib's. `pip install mpl-cli` would read as a plotting tool to most Python developers.

**Several strong alternatives were already occupied by direct neighbours.** `cairn` is a
background agent system, `trellis` an agent workflow layer with five figures of stars, and
`meridian-cli` orchestrates agents "through its native harness." Shipping into any of those
names would have created permanent search collision in exactly our category.

**The format carried the product's name.** This is the expensive one, and it is a design
error independent of what the product is called.

## Decision

### 1. The product is **Assay**

To assay is to test a material to determine its true composition — historically by
touchstone, later by fire. The name states the differentiator rather than the storage
medium, and it keeps stating it every time someone types `assay test` or `assay redteam`.

It also matches an ethic already enforced in the code: a judge is not trusted until it
clears a two-stage gate, an unverified loop reports `not checked` rather than success, and a
red-team run that produced no usable result refuses to display an attack-success rate. The
product's job is determining what something is actually made of. The name should say so.

Renamed accordingly: `assay` binary; `assay-core` / `assay-cli` / `assay-mcp` distributions
and `assay_core` / `assay_cli` / `assay_mcp` modules; `assay` Python SDK package;
`ASSAY_*` environment variables; `assay.yaml` workspace config; `.assay/` state directory;
`assay.*` plugin entry-point groups; `assay.*` error codes; `assay_*` MCP tools;
`assay://` MCP resource URIs; `AssayError`.

### 2. The spec key becomes `promptfile:`, not `assay:`

```yaml
---
promptfile: 1      # was: mpl: 1
id: agents/researcher
---
```

The plugin groups stay `assay.*` — those describe *this runtime's* extension points, and a
different implementation would have its own. But the frontmatter key describes **the format**,
and the format must not carry a vendor's name.

Two reasons, and the second is the one that matters.

**Adoption.** A format is only a standard if tools that compete with us implement it. No
competitor will ship files whose required first key is a rival's brand. `promptfile: 1`
matches the spec's actual published name — PromptFile v1 — and is adoptable by anyone.

**Reversibility.** With the brand out of the format, the product can be renamed again in
five years without touching a single file anyone has written. This ADR is the last one that
ever needs to be expensive.

### 3. No compatibility alias for `mpl:`

The parser does not accept `mpl: 1`. Nothing was ever published — no git remote, no
release, no user outside this repository — so there is no file in the world that needs the
alias. Shipping a deprecation path for a version that never existed would be dead code
pretending to be diligence, and it would appear in the spec as though `mpl:` had once been
legitimate. It hadn't.

Had a single version shipped, this decision would invert: the compatibility policy in
[ADR-0004](0004-compatibility-policy.md) sets a 12-month deprecation floor, and it would
apply.

## Consequences

**Good.** The name now describes the product, and the format is portable and
vendor-neutral. Future renames cost a `sed` in this repository and nothing to anyone else.
The `matplotlib` collision is gone.

**Cost.** 759 token occurrences across 103 files changed in one commit, plus five directory
renames (done with `git mv`, so `git log --follow` still works). Anyone with the repo
checked out must reinstall: `pip install -e packages/assay-core -e packages/assay-cli`.

**Unverified.** Registry availability was checked on PyPI and npm; `assay` and `assay-core`
appeared free at the time of writing. **Trademark clearance in the relevant software classes
was not performed** and should happen before any public announcement. The GitHub
organisation and the `assay.dev` domain referenced in the schema `$id` are likewise
aspirational until registered — the `$id` is an identifier, not a URL that must resolve, but
it should not point somewhere owned by someone else.

**Not changed.** The repository directory on the author's machine is still
`MyPromptLibrary`; renaming it is a local operation with no effect on the published
artifacts.

## Alternatives considered

**Keep `MyPromptLibrary`.** Rejected: the name actively misdescribes the product, and every
day of delay raises the cost of the spec-key fix.

**Rename the product but leave `mpl:` in the spec.** Rejected: this keeps the only part of
the problem that becomes unfixable after publication, in exchange for saving about ten
minutes.

**`Plinth` / `Praxis`.** Both clean on the registries. `Plinth` bets on infrastructure
positioning but is obscure and has no verb form; `Praxis` fits the knowledge-plus-runtime
shape well but reads academic. Both were viable; `Assay` was preferred for stating the
differentiator directly.
