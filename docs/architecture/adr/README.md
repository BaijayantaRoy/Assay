# Architecture Decision Records

Short documents recording *why* a structural decision was made, what it cost, and what was
rejected. They are append-only: a decision that changes gets a new ADR that supersedes the old
one, rather than an edit that erases the reasoning.

| # | Decision | Status |
|:--|:--|:--|
| [0001](0001-promptfile-as-the-substrate.md) | The prompt is a file, and the format is a public specification | Accepted |
| [0002](0002-plugin-first-core.md) | Plugin-first core; nine original plus four agent-harness extension points | Accepted |
| [0003](0003-capability-negotiation.md) | Capability negotiation, and failing closed | Accepted |
| [0004](0004-compatibility-policy.md) | Compatibility policy for spec, contracts and API | Accepted |
| [0005](0005-offline-first.md) | Offline-first; the model catalogue is data | Accepted |
| [0006](0006-mcp-as-primary-surface.md) | MCP as a primary surface, implemented without an SDK | Accepted |
| [0007](0007-fully-open-source.md) | Fully open source; remove the licensing layer | Accepted |
| [0008](0008-research-driven-prioritization.md) | Prioritize from surveyed evidence, not from recall | Accepted |
| [0009](0009-name-and-spec-brand-separation.md) | Rename to Assay, and separate the spec from the brand | Accepted |

## Writing a new ADR

Copy the shape of an existing one: **Context** (the forces, honestly stated) → **Decision**
(what we are doing) → **Consequences** (good *and* costs) → **Alternatives considered** (and
why they lost).

The Consequences section must name real costs. An ADR listing only benefits is marketing, and
it is useless to the person who has to live with the decision in two years.
