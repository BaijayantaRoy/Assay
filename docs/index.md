# Assurance for AI artifacts, carried with the artifact

Assay keeps prompts, agents, and verified loops as portable **PromptFiles**: readable
files containing the template, model binding, controls, and their own eval cases.

The core idea is simple: assurance should travel with the thing being assured. A score
without its denominator, environment, and evidence is not a result Assay will claim.

## Start in three commands

```bash
pip install assay-cli
assay init my-prompts
cd my-prompts && assay test
```

The offline `echo` provider makes the complete starter workflow deterministic, free, and
usable without credentials.

## What makes Assay different

- **One artifact, every surface.** CLI, MCP, REST, and the workbench use the same engine
  and file store.
- **Trajectory evidence.** Agent tests can assert tools, arguments, order, budgets,
  denials, handoffs, and verification—not only the final sentence.
- **Honest measurement.** Unverified is distinct from failed; zero usable cases produce
  no rate; uncertainty and actual test-time cost are reported together.
- **Fail-closed controls.** Tool-result injection boundaries, capability negotiation,
  approval gates, tool pins, and guardrail failures stop at the side-effect boundary.
- **Portable governance evidence.** Privacy-safe hash-chained audit logs, attributable
  approvals, and an Annex IV evidence index stay inspectable without a vendor service.
- **Mutation-proven claims.** Targeted mutants deliberately break product promises and
  must make the suite go red.

## Choose your path

| Goal | Read next |
|:--|:--|
| Create and run your first PromptFile | [User guide](user_guide.md) |
| Test prompts and agents rigorously | [Evaluating agents](knowledge/evaluating-agents.md) |
| Design tool-using agents | [Harness engineering](knowledge/harness-engineering.md) |
| Secure untrusted tool boundaries | [Agent security](knowledge/agent-security.md) |
| Deploy the workbench and API | [Deployment](deployment.md) |
| Understand the architecture and trade-offs | [Blueprint](architecture/BLUEPRINT.md) |

!!! warning "Evidence, not certification"

    Assay produces technical evidence and names the gaps it cannot fill. It is not a
    legal opinion, conformity assessment, safety certificate, or substitute for an
    operator-owned risk-management process.
