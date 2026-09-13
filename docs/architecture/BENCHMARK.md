# Competitive benchmark and 50%-better scorecard

**Evidence date:** 2026-08-09  
**Scope:** prompt and agent assurance tooling, not every feature of an AI engineering platform

## Executive conclusion

Assay cannot honestly claim to be 50% better *overall* than Promptfoo, LangSmith, Langfuse,
or Braintrust. Those products lead in different categories and several already provide
features that weak comparisons still describe as unique to Assay.

The defensible benchmark position is narrower:

> **Portable assurance-as-code:** the executable artifact, evals, controls, lifecycle state,
> and honest evidence semantics travel together across CLI, MCP, REST, SDK, and web surfaces.

Assay should claim “50% better” only after a repeatable benchmark demonstrates at least a 50%
improvement on a named measure in that wedge. Until then, the phrase is a target, not a result.

## Current market baseline

| Product | Current strength that changes the benchmark | Implication for Assay |
|:--|:--|:--|
| Promptfoo | [157 red-team plugins across six categories](https://www.promptfoo.dev/docs/red-team/plugins/), plus [static, conversational, agentic, multimodal, indirect, and regression strategies](https://www.promptfoo.dev/docs/red-team/strategies/) | Assay is materially behind in security breadth. A small local corpus must be described as a regression gate, never comprehensive coverage. |
| Promptfoo | [Assertions include agent/tool trajectory checks](https://www.promptfoo.dev/docs/configuration/expected-outputs/) | “Trajectory testing” alone is not a moat. Assay must differentiate through portable per-handoff evidence and evidence integrity. |
| Promptfoo | [Some generation and grading paths send data to hosted inference](https://www.promptfoo.dev/docs/red-team/troubleshooting/data-handling/) | Assay's deterministic local corpus is useful, but the comparison must name the narrower coverage bought by that privacy boundary. |
| LangSmith | [Context Hub versions full agent and skill repositories and promotes commits to staging/production](https://docs.langchain.com/langsmith/use-the-context-hub) | File/repository versioning and environment promotion are no longer unique differentiators. |
| LangSmith | [Prompt management includes commit history, owners, webhooks, and environment rollback](https://docs.langchain.com/langsmith/manage-prompts) | Assay is behind in hosted collaboration, ownership controls, and deployment operations. |
| Langfuse | [Integrated tracing, prompt management, experiments, datasets, and production evaluation](https://langfuse.com/docs) | Assay is behind in production observability and team analytics; OpenTelemetry export is a bridge, not feature parity. |
| Braintrust | [Evaluation spans playground iteration, immutable experiments, CI, online scoring, and production feedback](https://www.braintrust.dev/docs/evaluate) | Assay is behind in the full online evaluation lifecycle and production feedback loops. |

## What Assay can lead on

The benchmark wedge consists of eight independently testable properties:

1. **Artifact-contained evidence** — evals, controls, schema, and lifecycle state are part of
   the PromptFile rather than separate dashboard configuration.
2. **Lossless forward compatibility** — unknown fields round-trip untouched.
3. **Tri-state verification** — `null` means not checked and is never coerced into pass/fail.
4. **Honest denominators** — unusable samples are reported and zero-usable rates are withheld.
5. **Mutation-proven gates** — critical tests are deliberately mutated and must fail.
6. **Per-handoff evidence** — loops retain verification at every step, not only the final text.
7. **Offline reference path** — the deterministic `echo` provider can exercise core behavior,
   the CLI, MCP, API, and proxy without a credential or remote inference.
8. **Surface parity evidence** — real binaries, sockets, and stdio are tested against the same
   engine and public field contracts.

These properties are meaningful only when measured. Their current repository evidence is:

| Measure | Current evidence | Status |
|:--|--:|:--|
| Core tests | Last complete aggregate: 623 passed. Current security delta: 48/48 focused tests passed | The post-delta aggregate hit its two-minute outer ceiling while the Windows output pipe failed; it is not reported as a current aggregate pass |
| End-to-end tests | Last complete aggregate: 125 passed, zero skipped | Full rerun is pending after the security delta; focused API and runtime UI-contract checks pin the new corpus count |
| Critical mutation anchors | 46/46 anchors valid; prior 44/44 full campaign plus 2/2 current security-contract mutants killed | Combined evidence covers every declared mutant, but the full 46-mutant campaign has not been rerun as one current batch; not whole-program mutation coverage |
| Installable catalog | 203 PromptFiles | Every item has an offline render-contract eval; semantic model quality is not claimed |
| Repository artifacts | 5 | All 5 carry embedded evals and pass; render-contract checks do not establish hosted-model semantic quality |
| Plugin contracts | 13 | Contract surface count, not proof of third-party ecosystem adoption |
| Local red-team corpora | Static: 52 attacks in 26 adversarial categories + 12 benign controls. Strategy: 18 sequence/adaptive attacks across at least 15 risk families + 6 benign controls | Deterministic regression coverage with a fail-closed corpus contract and honest incomplete-delivery exclusion; not comparable to Promptfoo's plugin and strategy breadth |
| Independent PromptFile implementation | TypeScript reader/writer passes the same 3 valid + 3 invalid fixtures as Python; Python also passes 100 generated unknown-value examples | Demonstrates two implementations, schema-drift checking, and semantic unknown-field preservation; not proof of third-party adoption |
| Browser contracts | Last full interaction matrix: 47 passed; current security interaction/accessibility delta: 1 passed. Five reviewed visual baselines each pass their latest comparison | Desktop, mobile navigation, streamed harness, red-team corpus, Delivery Status, and specification surfaces are covered; the post-delta full browser matrix is pending |
| Bounded eval throughput | 120.529 ms vs 380.965 ms serial median (3.16×; 3 repetitions) | 12-case synthetic fixed-latency workload, four workers, ordered semantic parity and peak=4; not a hosted-model or competitor benchmark |
| Repository scale | 802.746 ms discovery and 1,339.414 ms load+render median | Generated 1,000-artifact/20-namespace workload over 3 repetitions with complete-id, edge-render, and unknown-metadata checks; not a hosted filesystem benchmark |
| Strict docs build | Last strict build passed before the current documentation delta | The current Python environment lacks MkDocs, so the latest wording is not reported as rebuilt |
| Release integrity workflow | 10/10 publishable packages build locally; isolated assay-core wheel loads 4 exact resources | Workflow adds package inventory, SBOM, checksums, and attestations; no hosted tag/attestation run was executed in this environment |
| Docker image build | Backend and standalone frontend images built; both Compose services reached healthy; four external HTTP probes returned 200 | Verified on Docker Desktop 4.75.0 in this environment; this is not a signed release-tag build in a clean hosted builder |
| Competitive scorecard | 0/3 primary KPIs proven; claim withheld | The v1 protocol, neutral fixtures, operator recorder, trial schema, deterministic scorer, canonical result, and ten benchmark tests ship. The shared competitor trial ledger is empty, so component evidence is not promoted into a competitor result |

The current scripted red-team run is a regression measurement inside Assay, not a competitor
benchmark: 52/52 attacks usable, zero errors, 0% ASR, 46.15% detection, and 0% false positives
across 12 benign controls. The detector moved from 25.0% to 46.15% on the expanded corpus
(84.6% relative), while the mode explicitly states that no real-model susceptibility was tested.

## The 50%-better experiment

Run this benchmark against Assay and at least three relevant products using the same seeded
repository, operator instructions, and stopwatch. Publish raw tasks and outputs.

The executable protocol lives in
[`benchmarks/assurance-wedge/`](https://github.com/BaijayantaRoy/Assay/tree/main/benchmarks/assurance-wedge).
Its scorer requires three trials and two operators per product/metric, full coverage of every
task declared for that metric, raw-artifact digests, task-author/operator separation, and at
least three comparators. Because the reporting metric declares four distinct faults, the honest
minimum is 40 records across Assay plus three comparators—not 36 repeated easy tasks. Unusable
loss-rate trials get zero success credit, incomplete effort trials consume the full timebox, and
a 0%-versus-0% tie cannot satisfy the relative target.

| Dimension | Unit | 50%-better release target | Failure condition |
|:--|:--|:--|:--|
| Time to auditable change | Median minutes from clone to reviewed change with a failing-then-passing eval | Assay median ≤ 50% of the best measured comparator | Setup assistance, cached credentials, or hidden manual steps differ between products |
| False-assurance resistance | Seeded reporting faults detected / total | Assay detects 100% and at least 50% more than the best comparator | A zero-sample, uncalibrated-judge, unchecked-handoff, or missing-cost fault appears green |
| Portable evidence retention | Required evidence fields preserved after export/import and offline review | 100%, and at least 50% fewer lost fields than the best comparator | Eval, control, provenance, lifecycle, or unknown extension data is lost without an explicit warning |
| Handoff audit completeness | Verified handoffs / eligible handoffs, with unchecked separately counted | 100% evidence representation and ≥50% fewer unattributed handoffs | Final success is presented as proof that intermediate handoffs were checked |
| Reproduction effort | Median commands and manual transformations to reproduce a CI result on a clean machine | ≤50% of best comparator | Network-only artifact lookup or dashboard-only evaluator configuration is required |

No result may be published unless:

- environment and product versions are recorded;
- the task author is separated from the operator where practical;
- failures and unusable trials remain in the denominator;
- raw artifacts and scoring code are public;
- a second person can reproduce the ranking;
- “50%” names the exact dimension and baseline.

## Priority gaps

1. **Security breadth:** expand the new deterministic sequence/adaptive baseline across more
   locally reproducible risk families while retaining benign controls and privacy labels. Do
   not chase a raw plugin count at the expense of measured behavior.
2. **Competitive execution:** run the published assurance-wedge protocol with independent
   operators against at least three relevant products. Until qualifying raw trials exist, keep
   every 50%-better KPI and the overall claim withheld.
3. **Visual breadth:** extend the four reviewed baselines to high-risk analytics, governance,
   red-team, and creation workflows without turning snapshots into a substitute for interaction
   and accessibility checks.
4. **Property testing:** broaden generated cross-language values beyond JSON-native data and
   recruit independently maintained implementations. Discovery/render/eval latency budgets now
   ship, but local synthetic gates are not competitor evidence.
5. **Supply chain:** execute the new SBOM/provenance workflow on a release tag, sign
   packs/reports, and repeat the verified container build in a clean builder.
6. **Runtime throughput:** publish real-provider retry/throughput evidence. Guarded text and
   streamed tool calls now ship across four network adapters, REST, proxy and both SDKs, and
   bounded `Retry-After` adaptation is deterministic; none of that is hosted-provider or
   competitor throughput evidence.
7. **Production bridge:** deepen OpenTelemetry/Langfuse/Braintrust integrations rather than
   rebuilding their observability control planes.
8. **External interoperability:** publish the independent TypeScript reader, recruit a
   third-party implementation, and add bidirectional conformance fixtures. Two in-repository
   readers prove less than an implementation maintained by someone else.

## Claim policy

Acceptable today:

- “Assay is designed for portable assurance-as-code.”
- “The last full 44-mutant campaign and both new security-contract mutations were killed; all 46 current anchors are valid.”
- “The catalog contains 203 artifacts with render-contract checks.”
- “All five repository PromptFiles carry embedded evals and currently pass.”
- “The competitive scorecard currently proves zero of three primary KPIs; the claim is withheld.”
- “Promptfoo is broader in red teaming; Langfuse and Braintrust are broader in production
  operations.”

Not acceptable today:

- “Assay is 50% better than every similar product.”
- “Assay has comprehensive prompt-injection protection.”
- “All 203 catalog prompts are production-quality against real models.”
- “A configured exporter proves trace delivery.”
- “The current local container proof establishes signed release provenance.”
