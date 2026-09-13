# ADR-0001 — The prompt is a file, and the format is a public specification

**Status:** Accepted · **Date:** 2026-07-27 · **Supersedes:** the 0.x database-only prompt model

## Context

Version 0.x stored prompts as rows in SQLite, with a `PromptVersion` table providing
git-like history. That works, and it is what every hosted competitor does. It also means:

- prompts cannot be reviewed in a pull request;
- CI cannot test a prompt without standing up the application;
- `grep` does not find them;
- moving to another tool requires an export script, and the export is lossy;
- two developers editing the same prompt get last-write-wins instead of a merge.

Meanwhile the ecosystem is converging on file formats: Google's **dotprompt** (`.prompt`,
YAML frontmatter + Handlebars), Microsoft's **POML** (HTML-like component tree). Neither has
won, and neither carries evals, guardrails, capability requirements or lifecycle status.

## Decision

The canonical representation of a prompt is a **plain-text file** — `.prompt.md`,
`.prompt.yaml` or `.prompt.json` — and the format is published as a **standalone
specification** under CC BY 4.0, versioned independently of this implementation.

The document model is an ordered mapping plus a body string. **Unknown keys are preserved
as the same keys and values on round-trip.** A `Store` protocol keeps database, object-storage
and remote backends possible, but the file store is canonical and git is the version history.

## Consequences

**Good**

- Prompts diff, review, merge and blame with the tools people already use.
- `assay test` runs in CI with no service, no database, and (with the `echo` provider) no
  network or API key.
- Exit cost is `git clone`. That is a feature we advertise, because a tool confident enough to
  make leaving easy is a tool worth trusting.
- Publishing the spec invites others to implement it. A format only we read would be a
  proprietary database wearing a text file's clothes.

**Costs**

- The shipped workbench and `/v1` API use the file store as their only source of truth. The
  unversioned 0.x SQLite routes remain available only behind `ASSAY_ENABLE_LEGACY_API=1`
  for controlled migration and can therefore still require maintenance until removal.
- Concurrent editing through the web UI needs conflict handling that a database gave for free.
- Very large libraries (10k+ prompts) will want an index. `FileStore.reindex()` is the seam
  where that lands; it does not change the format.

## Alternatives considered

**Adopt dotprompt as-is.** Closest fit and genuinely good, but it has no eval, guardrail,
capability or lifecycle model, and extending it unilaterally would fragment it. We instead
ship a **lossless bidirectional converter** and stay a superset.

**Adopt POML.** Strong compositional story, but an XML-ish tree is worse to diff than YAML
frontmatter, and it targets prompt *authoring* rather than the full artifact lifecycle. Also
supported via importer/exporter.

**Keep the database and add export.** Rejected. Export is not the same as being the format —
if the round-trip is lossy, and it always is, the database remains the real home.
