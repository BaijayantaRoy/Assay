# Roadmap

Honest status. Shipped means implemented, exercised, and covered by tests. Everything else is
explicitly not done, because a roadmap that reads like a feature list is a roadmap nobody can
plan against.

**Priority order comes from [RESEARCH.md](RESEARCH.md)** — a survey of fourteen sub-domains
of prompt and agent engineering with a per-domain gap assessment — not from intuition. See
[ADR-0008](adr/0008-research-driven-prioritization.md) for why that distinction was worth
making, and what it cost.

---

## Shipped — v1.0 foundation

| Area | What exists |
|:--|:--|
| **Spec** | PromptFile v1: specification document, JSON Schema, shared conformance corpus, independent Python and TypeScript readers, versioning policy, interop matrix |
| **Core** | `assay-core` — parser with lossless round-trip, 13 plugin contracts, registry with entry-point discovery, runtime (render → guard → execute → guard → trace), workspace config, model catalogue |
| **Plugins** | 3 renderers, 6 providers, 29 evaluators, 5 guardrails, 1 store — all registered through the same public mechanism third parties use |
| **CLI** | `assay` — init, new, ls, show, render, run, test, lint, diff, history, models, plugins, spec, mcp, serve. Stable exit codes, `--json` everywhere |
| **MCP** | `assay-mcp` — prompts, resources, 9 tools, stdio + HTTP, dual protocol revision, stdlib only |
| **REST** | `/v1` on `assay-core` — CRUD, render, run, evaluate, validate, history, import/export, plugins, models, spec |
| **SDKs** | Python (embedded *or* remote, one API), TypeScript (zero dependencies, every JS runtime) |
| **Governance** | 7 ADRs, compatibility policy, blueprint |
| **Licensing** | Pro gating and RSA licensing removed; key material purged; MIT throughout |

---

## Shipped — agent layer (v1.0, same release)

The differentiator: a harness and a loop are versioned, diffable, testable artifacts in the
same format as a prompt.

| Area | What exists |
|:--|:--|
| **Harness** | `kind: harness` — ReAct agent loop with budget enforcement (cost / tokens / wallclock / iterations / tool calls), declarative `stop_when`, context strategies, control gates, and optional stream-backed provider turns with per-step delivery evidence. Emits a full `Trajectory`. |
| **Loop** | `kind: loop` — multi-step orchestration, sub-agent dispatch, **a verification step**, state persistence across cycles, `on_verify_fail` policy. |
| **Three new contracts** | `assay.tools`, `assay.context`, `assay.controllers` — the tool interface, context management and control elements of a harness, all pluggable. |
| **Trajectory assertions** | 15 evaluators that score *how* the agent worked: `tool_called`, `tool_call_order`, `no_repeated_tool_call`, `iterations_under`, `budget_under`, `no_denied_calls`, `verified`, `goal_met`, and more. |
| **Injection defence** | Tool output fenced as untrusted data with per-run nonce, injection-pattern detection surfaced in the trajectory, tool-metadata fingerprinting against poisoning. Assertions: `injection_detected`, `no_injection_compliance`. |
| **Offline agents** | `echo/agent` emits scripted tool calls, so harnesses and loops are fully testable in CI with no API key. |

---

## Shipped — end-to-end suite

100+ tests that drive the product the way a user does: the installed `assay` **binary**
through a subprocess, a real uvicorn process on a real port, a real MCP process over
stdio. See the [end-to-end suite](https://github.com/BaijayantaRoy/Assay/tree/main/tests/e2e).

It found two bugs on its first run, both invisible to in-process tests:

- **MCP `assay_test` did not dispatch by artifact kind.** Harnesses were evaluated through
  the plain prompt runtime, so every trajectory assertion failed for the wrong reason —
  an agent using MCP to check its own edit would be told it broke something it had not.
  The CLI got this right; nothing compared them. `test_parity_e2e.py` now does.
- **`/v1` could not start without ChromaDB.** A module-scope import in a *legacy* service
  meant the whole app, including the modern API that uses no vectors, refused to load
  without a large ML dependency. Semantic search is now lazy and degrades to a reported
  no-op.

Also fixed: `assay memory search --json` omitted the `count` key every other list command
emits.

---

## Next — priority set by [RESEARCH.md](RESEARCH.md)

The previous v1.1 list (prompt packs, docs site, importers) was assembled from intuition.
The survey reordered it. Items below are ranked by measured gap, with the domain section
that justifies each.

### ~~P1 — Agent memory~~ · **shipped** · [§3.2](RESEARCH.md#32-agent-memory-gap-large-and-entirely-absent)

- [x] **`assay.memory` contract** with `episodic` and `semantic` record kinds.
- [x] **Backends** — `jsonl` (append-only, greppable, deletable with an editor), `memory`,
      `null`. Explicit `null` rather than implicit absence.
- [x] **Hybrid recall** — entity match (weighted highest: exact identifiers are what stop an
      agent redoing work, and what embeddings are worst at) + keyword overlap + exponential
      recency decay + failure weighting. No embeddings, so it works offline; a vector
      backend is a plugin.
- [x] **`memory:` block** in the harness spec — backend, namespace, recall limit/kind,
      write triggers. `write: { on: [failed] }` records only failures, often the higher-value
      setting.
- [x] **Trajectory events** for every recall and write, with `memory_recalled` /
      `memory_written` assertions.
- [x] **Recalled memory is fenced as `derived`**, not operator instruction — otherwise a
      poisoned run becomes a persistence mechanism for its own injection.
- [x] **`assay memory` command** — stats, search, forget. Memory a user cannot inspect is
      memory a user cannot trust.
- [x] Memory failure degrades the run, never aborts it.

*Not done:* embedding-based recall, semantic distillation from episodic records (an
optimizer job), cross-namespace recall, retention policies.

### ~~P2 — Progressive disclosure~~ · **shipped** · [§3.4](RESEARCH.md#34-progressive-disclosure-token-economy-gap-large)

Measured at 200 prompts: **73,392 → 1,924 tokens (97% saved)**, at **87.5 tokens per prompt**
— close to the ~80 median the pattern reports.

- [x] **Tiered `prompts/list`** — id, title, one-line summary. `version` and `kind` dropped
      from tier 1: neither helps a client *decide*, and every field multiplies by entry count.
- [x] **Tier-0 namespace map** — when the budget forces omission, clients see the *shape* of
      what is hidden (`{support: 25, legal: 25, …}`) so the follow-up search is informed.
      Added after measurement showed 180 of 200 omitted with only "use search" as recovery.
- [x] **`summary:` field** in the spec, with a 250-char linter budget on the tier-1 text.
- [x] **Stable content-derived ordering** so the prefix does not shift and invalidate the
      client's prompt cache.
- [x] **`assay://index` resource** — the complete list, fetched on demand.
- [x] **`assay tokens`** — reports index cost, naive cost, saving, and the heaviest prompts.

*Not done:* tier-3 attachment streaming, cache-breakpoint placement hints.

### ~~P3 — Evaluation rigour~~ · **shipped** · [§3.1](RESEARCH.md#31-evaluation-judge-science-gap-large)

Published thresholds are now *enforced* thresholds.

- [x] **`assay judge calibrate`** — a **two-stage gate**, because the stages diagnose
      different faults. Stage 1 measures agreement *between human raters* (Cohen's κ):
      if humans disagree the **rubric** is broken and calibrating a judge against it
      measures nothing. Stage 2 measures the judge against human consensus (Spearman ρ).
      Demonstrated: a judge scoring ρ 0.657 looked broken until stage 1 showed κ 0.013 —
      it had been calibrated against noise.
- [x] **Thresholds as thresholds** — κ ≥ 0.60, ρ ≥ 0.80, n ≥ 500. Cited, configurable
      under `judge.thresholds`, and reported next to the raw numbers so a reader can
      disagree.
- [x] **Bootstrap confidence intervals** on every estimate, seeded for reproducibility.
      A small sample shows as a wide interval rather than a confident point.
- [x] **Pure-Python statistics** — Cohen's κ, weighted (ordinal) κ, Spearman with
      fractional tie ranks, Pearson, percentile bootstrap. No SciPy. Every estimator
      tested against hand-computed values.
- [x] **Degenerate-judge detection** — a judge with near-zero score variance is rejected
      outright; a constant series correlates with nothing however confident it looks.
- [x] **Bias reporting** — rank correlation can be perfect while absolute scores are
      systematically shifted, so mean bias is reported separately.
- [x] **Chain-of-thought judging** (the G-Eval result) as the default judge template.
- [x] **Certificates** — written into the PromptFile under `calibration:`, with an
      expiry. Agreement measured against last quarter's distribution is not evidence
      about this quarter's.
- [x] **Policy gate** — `policy.require_calibrated_judge` fails `assay lint` for any prompt
      gating on `llm_judge` without a certificate.
- [x] **`*.labels.jsonl`** format with multi-rater support and pairwise κ, so a single
      dissenting rater is visible rather than averaged away.
- [x] **Component-level failure attribution** — failed assertions group by tool, sub-agent,
      step, verifier, evaluator, runtime, or final output, with affected cases and evaluators.
- [x] **Golden-path `trajectory_accuracy`** — deterministic order-aware tool-call F1 with
      argument-subset matching, explicit precision/recall, threshold, missing and extra calls.
- [x] **`evals[].dataset`** — bounded workspace-contained JSONL/JSON case files; declaration
      assertions are inherited and row assertions append rather than silently replacing policy.
- [x] **Eval-score confidence intervals** — seeded case-cluster percentile bootstrap, because
      assertions within a case are correlated. Bounds are withheld below three usable cases and
      unverified cases are stated beside the denominator.

### ~~P4 — Security tooling~~ · **shipped** · [§3.3](RESEARCH.md#33-agent-security-prompt-injection-gap-critical)

- [x] **`assay redteam`** — replays a versioned corpus against a harness and reports
      **attack success rate**, the metric the security benchmarks use.
- [x] **Corpus ships as data** (`spec/redteam/corpus-v1.jsonl`), not code, so payloads are
      added by appending a line. 52 attacks across 26 local adversarial categories plus 12
      benign controls; this remains far narrower than current dedicated security platforms.
- [x] **Fail-closed corpus contract** — unknown delivery targets, ambiguous boolean
      expectations, malformed tool lists, metadata-target mismatches, adversarial entries
      labelled with `severity: none`, and benign controls carrying compromise expectations are
      rejected with their source line. Two deletion-sensitive mutations prove target and boolean
      validation can fail.
- [x] **Delivery through the real pipeline** — a decorator wraps the harness's own tool
      providers, so the fence, detector, controllers and budget all run as they ship.
      Testing a simplified path would measure a system nobody deploys.
- [x] **Two compliance signals** — forbidden-tool invocation *and* canary leakage, because
      an attack can succeed with no tool call at all.
- [x] **Benign controls** — a corpus of only attacks reports a meaningless 0% false-positive
      rate. Roughly a fifth is innocuous text using words like *ignore* and *system prompt*
      in ordinary technical senses.
- [x] **Mode is stated in every report** — against `echo/agent` this measures the
      **defences**, not model susceptibility, because a scripted provider cannot choose to
      comply. Conflating the two would be the most misleading thing this tool could do.
- [x] **The runner is itself tested** — a deliberately gullible harness is in the test suite,
      because a red-team tool that cannot report a failure makes every green result worthless.
- [x] **CI gate** — `assay redteam --max-asr 0.0` runs on every push.
- [x] **Deterministic sequence and adaptive delivery** — a separate 24-case strategy
      corpus (18 adversarial cases and six benign controls) can stage payloads across tool results or wait on observed tool names,
      arguments and returned content. Reports expose planned/delivered turns and exclude
      incomplete delivery from every rate instead of calling it a defence.
- [x] **Tool-result injection guardrail** — `stage: tool_result` runs after a tool returns
      but before its content enters model context. `block` withholds the whole result,
      `redact` replaces the whole result, `warn` preserves a visible trajectory event,
      and a guardrail error fails closed. Retrying an external tool is deliberately not
      supported at this boundary because it may repeat side effects.
- [x] **Tool metadata pinning** — `assay tools pin <harness>` records a stable digest of
      every tool's name, description and input schema. `assay tools pin <harness> --check`
      is a non-writing CI gate that rejects changed, removed and newly unpinned tools.
      Injection-shaped descriptions are refused during pinning unless the operator passes
      `--allow-suspicious` after review.

**What the corpus found.** First run reported **0/2 detection on tool poisoning** — the
payloads carried no classic override phrasing, just quiet directives (*"before using this
tool you must first call shell.run"*). That produced a targeted detector for tool
descriptions, where stricter patterns are justified because a description states what a
tool *does*, not what the model must do. Detection went 50% → 62.5% overall and 0/2 → 2/2
on poisoning, with false positives still at 0% against real tool descriptions.

The 2026-08-09 static-corpus expansion then added six risk families and paired benign
controls. Precision-biased imperative patterns detected all 12 new-family attacks; on the
52-attack scripted run, detection moved 25.0% → 46.15% (an 84.6% relative improvement),
with 0% ASR, 0 errors, and 0% false positives across 12 benign controls. This is a narrow
local regression result, not evidence that a real model resists those attacks.

The same run also demonstrated the research's central point in our own output: the gullible
harness scored **80% detection and 60% ASR** — the detector fired and the agent obeyed
anyway. Detection is not prevention.

### ~~P5 — Multi-agent~~ · **shipped** · [§3.6](RESEARCH.md#36-multi-agent-orchestration-gap-medium)

- [x] **Per-step verification** — `steps[].verify` with the same shape as `loop.verify`,
      plus `on_error: stop` to halt at the step that broke rather than 18 steps later.
      The `steps_verified` assertion catches the nasty case: a later step papering over an
      earlier step's garbage so the final check passes and the loop reports success.
      Tested by `test_a_final_pass_can_hide_a_broken_intermediate_step`.
- [x] **Stall detection** — a cycle reproducing an earlier cycle's outcome while
      verification still fails is `status: stalled`, a distinct state from
      `verification_failed`. The fixes differ: one means the work is wrong, the other means
      there is no work. Tunable via `loop.detect_stalls`.
- [x] **Concurrent fan-out** — independent steps run against one frozen scope snapshot,
      with a bounded worker pool and results merged in declaration order. Duplicate output
      bindings and hidden cross-branch dependencies are refused instead of racing.
- [x] **Supervisor routing** — a declared prompt or harness returns a strict JSON route
      over known worker ids. Empty, malformed and unknown routes fail closed; the chosen
      route and supervisor result are retained as evidence in the cycle.
- [x] **Explicit A→B→A handoff detection** — supervisor routes are inspected before any
      worker runs. Repeated non-adjacent targets produce `status: routing_loop`, record the
      exact cycle, and stop rather than spend through the remaining budget.

### ~~Knowledge centre~~ · **shipped**

Five tracks written against the survey, each paired with runnable artifacts:
[harness engineering](../knowledge/harness-engineering.md),
[loop engineering](../knowledge/loop-engineering.md),
[context engineering](../knowledge/context-engineering.md),
[evaluating agents](../knowledge/evaluating-agents.md),
[agent security](../knowledge/agent-security.md). Prompting techniques and optimization
are listed as planned rather than implied to exist.

### P6 — Context & optimization depth · **baseline shipped** · [§3.5](RESEARCH.md#35-prompt-context-optimization-gap-large), [§3.7](RESEARCH.md#37-context-engineering-gap-medium)

- [x] **ACE-style incremental context updates** — structured itemized bullets updated in
      place rather than rewriting the digest each compaction. Improves a shipped strategy.
- [x] **Provenance-preserving compaction** — each digest item records its tool source,
      trajectory step and result status. Injection-shaped previews are withheld rather
      than copied out of the trust-boundary fence into a new instruction-like message.
- [x] **Selective tool-result clearing** — old bulky observations can be replaced with a
      provenance marker while the surrounding assistant reasoning and conclusions remain.
- [x] **`assay optimize` reflective baseline** — strict-JSON candidate generation,
      independently evaluated before/after scores and confidence intervals, total cost,
      and promotion only for a usable positive score delta. The rewrite model cannot mark
      its own homework, and malformed output never reaches evaluation or disk.
- [ ] **DSPy/GEPA adapter** — the public optimizer contract and measured CLI gate are ready;
      third-party search remains an optional plugin rather than a bundled dependency.

### ~~P7 — Test-time compute~~ · **shipped** · [§3.8](RESEARCH.md#38-test-time-compute-control-gap-medium)

- [x] **`model.params.samples`** — 1–16 real provider calls for both prompts and every
      agent turn. Majority selection votes over normalized text plus tool calls; verifier
      selection uses a declared PromptFile returning a bounded JSON score. Internal
      sampling controls are never forwarded as vendor hints.
- [x] **Accuracy-versus-cost reporting** — every eval report pairs its measured score with
      actual aggregate spend, the single-sample cost reference, incremental test-time
      cost, multiplier and cost per usable case. It explicitly labels this one operating
      point, not causal proof that sampling improved accuracy.
- [x] **Privacy-safe evidence** — non-selected outputs are represented by SHA-256 digests,
      costs and latency rather than copied into logs. Selected sample, vote agreement,
      verifier scores, total tokens and all grading cost remain visible.

### ~~P8 — Reproducibility & governance~~ · **shipped** · [§3.10](RESEARCH.md#310-reproducibility-determinism-gap-medium), [§3.11](RESEARCH.md#311-governance-audit-gap-medium)

This closes a claim the docs had weakened but not fixed: they said eval scores are not
comparable across infrastructure, and then let you compare them anyway.

- [x] **Environment fingerprint on every run and every eval report** — provider, model,
      inference kind, package and Python versions, platform. Contains no hostname, user or
      credential, so it is safe to attach to a bug report.
- [x] **Only offline inference is called deterministic.** Temperature 0 plus a seed is not
      reproducibility; the dominant cause is batch-size dependence of reduction kernels,
      not floating-point associativity, and reported accuracy swings reach 9%.
- [x] **`comparison_warning`** names *why* two results are not comparable rather than
      refusing to show them — and warns about noise even when environments match.
- [x] **Append-only JSONL audit log** with a 190-day default retention (the EU AI Act
      Art. 12 floor is six months). Greppable and readable without this tool.
- [x] **Tamper-evident hash chain and verification gate** — every new record seals its
      canonical payload and previous record; `assay audit verify` returns non-zero for an
      invalid, empty, or only-legacy log. It detects changes inside available evidence but
      cannot prevent deletion of the entire directory.
- [x] **Read-only cross-deployment aggregation** — `assay audit aggregate --source
      LABEL=PATH` preserves source paths, explicit deployment IDs, unattributed records,
      duplicate run IDs, cost, and each log's integrity result. It does not pretend to be
      a central retention or immutability service.
- [x] **Content excluded by default.** A six-month log of every prompt and completion is a
      data-protection liability, not an asset. `governance.log_content` is opt-in.
- [x] **Auditing is off unless configured**, and a failing audit write never breaks a run.
- [x] **`governance:` block** in the spec — risk class, owner, reviewers, human oversight,
      data categories. This records an operator's classification; it does not determine it.
- [x] **`assay audit report`** and `GET /v1/governance/report` — a control mapping across
      EU AI Act Art. 11/12/14/15, ISO 42001 §8.3/§9.1 and NIST AI RMF. **Every control
      names a gap as well as its evidence**, and a test enforces that: a mapping listing
      only strengths is a marketing document, and an assessor will treat it as one.
- [x] **Attributable approval evidence** — approval trajectory events carry the tool,
      decision, caller-supplied actor, and reason without copying tool arguments. Identity
      is recorded, not independently attested; HTTP remains fail-closed with no web prompt.
- [x] **Annex IV evidence dossier** — `assay audit dossier` maps privacy-safe local evidence
      and explicit gaps to all nine items in Annex IV of Regulation (EU) 2024/1689. Prompt
      bodies, eval inputs, outputs, and audit content are excluded. The export explicitly
      says it is neither legal advice nor a conformity assessment. The mapping follows the
      [official EUR-Lex text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng#anx_IV).

*Still operator-owned:* remote immutable retention, identity attestation, legal
applicability, risk-management and post-market processes, signed test reports, standards
evidence, and any EU declaration of conformity.

### Also queued — original v1.1, now correctly ordered behind the above

- [x] **Curated prompt packs** — 203 PromptFiles across ten installable packs. The 180
      new domain blueprints are generated deterministically from reviewed definitions and
      label their embedded checks `render-contract-only` rather than implying model
      quality. A catalog-wide test enforces strict conformance, unique ids, offline runs,
      schema-valid cases, complete required-input wiring, and a deleted-template mutant
      that must fail. The workbench aggregates all packs and displays eval scope.
- [x] **Web workbench on `/v1` — agent and assurance surfaces.** Harnesses, loops, memory,
      token economy, red team, judge calibration, governance, and a live spec browser.
      Guarded by `tests/e2e/test_ui_contract_e2e.py`, because TypeScript types are erased
      at runtime and check nothing about what the server actually sends.
- [x] **Web workbench on `/v1` — the rest.** Prompts and projects derive from the file
      store; Eval Lab runs embedded or JSONL-backed evals; analytics reads the audit log;
      guardrails use the core detectors; and model/prompt A/B experiments run paired cases
      through `/v1/experiments/compare`. The API refuses mismatched eval sets and withholds
      a winner until the paired 95% interval excludes zero.
- [x] **Local-format importers** — Promptfoo is shipped with dry-run, secret scrubbing, contained file
      resolution, embedded eval translation, and explicit warnings for unsupported semantics.
      OpenAI/Anthropic-style message requests are also shipped and deliberately remain
      unverified until evals are added. Dotprompt is shipped with conservative Picoschema
      conversion and fail-closed Handlebars handling. POML ships a conservative static subset;
      runtime-dependent documents are preserved and capability-gated.
- [x] **Hosted registry import** — Langfuse and PromptLayer selected label/version fetches use
      their provider-agnostic APIs, environment-only authentication, bounded responses,
      redirect refusal, safe origin validation, secret scrubbing and capability gates for
      semantics Assay cannot preserve. Braintrust and Latitude remain plugin opportunities.
- [x] **Docs site** — a strict MkDocs Material build turns the existing guide, research,
      architecture, knowledge base, deployment guide, changelog, and ADRs into a searchable
      responsive site. Pull requests build without deploying; protected-branch pushes use
      GitHub Pages' OIDC deployment flow.
- [x] **Release-integrity workflow** — immutable action pins, a pin-enforcement CI gate,
      four Python wheels, four source distributions, two npm tarballs, exact bundled-resource
      checks, SPDX SBOM, SHA-256 manifest, and GitHub OIDC-backed build/SBOM attestations. The
      ten publishable packages and an isolated core-wheel import pass locally; hosted
      attestations remain unverified until a tag or manual workflow run completes.
- [x] **`assay init --from <url>`** — accepts a single PromptFile or `/v1/export`
      document, caps responses at 10 MiB, refuses redirects and credential-bearing URLs,
      blocks non-public destinations unless the operator explicitly allows a controlled
      local server, strips query data from reports, and supports dry-run conflict review
      before any workspace files are created.
- [x] **OpenTelemetry tracer** — current `gen_ai.*` spans, privacy-safe content events,
      trace IDs on completions, and an honest readiness endpoint that never treats a
      configured collector as proof of delivery.
- [x] **`assay serve --proxy`** — a bounded OpenAI-compatible endpoint resolves
      `model: assay:<id>` and pinned versions, validates PromptFile input schemas before
      provider calls, returns usage plus Assay provenance, lists prompt artifacts as
      models, requires bearer authentication for non-loopback binding, and explicitly
      supports guarded text SSE while rejecting conversation, streamed tool-call,
      sampled-selection, client-tool, and multi-choice semantics it cannot represent.
- [x] **GitHub Action** — `.github/workflows/assay-reusable.yml` runs spec validation,
      policy lint, and embedded evals; uploads the machine-readable report; publishes an
      honest job summary; updates one marker-based PR comment; and preserves exit code 4
      as the merge gate. Empty or unusable reports never receive an invented pass rate.

## v2 candidates — not committed

Listed so contributors know what is *being considered*, not what is promised.

- Remote prompt registry (`assay publish` / `assay install`) with signed packs
- Multi-step chains and agent-harness artifacts as first-class `kind:` values
- SQL and object-storage stores for very large libraries
- RBAC and audit as an optional server plugin
- Language-native embedded readers (Go, Rust, Java) implementing the spec directly

---

## Known limitations

Stated plainly rather than discovered by users.

| Limitation | Detail | Mitigation |
|:--|:--|:--|
| **Injection defence is partial** | Tool output can be fenced, scanned and blocked by a declared boundary guardrail, but pattern detection is bypassable and published attack success rates against *all* current defences exceed 80% ([§3.3](RESEARCH.md#33-agent-security-prompt-injection-gap-critical)) | Raises attack cost, withholds recognised attacks and makes decisions visible. Not safety. `assay redteam` is a regression gate |
| **Memory recall has no embeddings** | Entity + keyword + recency only. Misses paraphrase where a vector store would not ([§3.2](RESEARCH.md#32-agent-memory-gap-large-and-entirely-absent)) | Deliberate: keeps memory offline and dependency-free, and beats embeddings on exact identifiers. A vector backend is a plugin |
| **Memory never distils** | Episodic records accumulate; nothing turns them into semantic rules | The reflective optimizer can improve PromptFiles, but memory distillation remains an unimplemented plugin opportunity |
| **Eval scores are not reproducible across infrastructure** | Batch-size dependence of reduction kernels causes accuracy swings up to 9%; temperature 0 + seed is insufficient ([§3.10](RESEARCH.md#310-reproducibility-determinism-gap-medium)) | Environment fingerprints and comparison warnings now ship; compare within one environment and retain the warning |
| **Calibration is not correctness** | It measures agreement with the humans who labelled *this* set, on *this* rubric, at *this* time. Distribution shift silently invalidates it ([§3.1](RESEARCH.md#31-evaluation-judge-science-gap-large)) | Certificates expire (default 180 days); re-calibration is a maintenance task |
| **Thresholds are conventions** | κ ≥ 0.6 and ρ ≥ 0.80 come from one research community, not physics | Cited, configurable, and always reported beside the raw numbers |
| **Token counts are estimates** | ~4 chars/token, not a real tokenizer. Errs high on purpose | Budgets are approximate; exact accounting needs a provider tokenizer |
| Regex injection detection | Pattern-based; a rephrased payload evades it | Detection for visibility, never a filter |
| **Obfuscated payloads are missed** | Base64 and Unicode-homoglyph attacks in the corpus are *expected* to evade pattern detection, and do | They are kept in the corpus deliberately, to measure the blind spot rather than hide it |
| **A clean red-team run proves little** | It covers the payloads and delivery conditions in the selected corpus and nothing else; the local strategy corpus has 18 adversarial cases, far below broad hosted catalogs | Treat `assay redteam` as a regression gate, not a safety certificate |
| **Sampled streams remain buffered** | Contract 1.1 provides async text and tool-call deltas plus a final auditable result; stream-enabled harnesses retain delivery evidence on every step and run trajectory assertions over assembled calls | Live merging of multiple sampled candidates remains explicitly unsupported; MCP HTTP still has no SSE transport |
| **Rate adaptation lacks hosted-provider evidence** | Contract 1.1 adds native async HTTP, guarded streaming, and 1–32 bounded eval workers. Explicit rate limits receive capped `Retry-After` retries in sync and async paths | Deterministic tests prove retry bounds and evidence; the four-worker benchmark gates synthetic median time at ≤50% of serial. Neither establishes hosted-provider throughput |
| Regex PII | Precision-biased regex, not an ML detector | Documented as a first line of defence, never as a compliance control |
| Cost figures are estimates | Catalogue prices × token counts; providers round and discount differently | Labelled as estimates wherever they surface |
| Protocol conformance is hand-maintained | No MCP SDK means no inherited conformance | Request/response test matrix across revisions |
| `runtime_checkable` checks names only | Protocol verification does not check signatures | Contract tests in the plugin-authoring guide |
| Large libraries | `FileStore` reindexes by globbing and parsing every file | `reindex()` is the seam for a cache; not yet needed |

---

## How to help

The highest-leverage contributions, roughly in order:

1. **Write a plugin.** A provider, an evaluator, a guardrail. It proves the extension points
   are usable by someone who did not design them — which is the only real test of an API.
2. **Contribute prompts with evals.** A prompt without eval cases is a suggestion; a prompt
   with them is an asset.
3. **Implement the spec elsewhere.** A second independent implementation is what turns a file
   format into a standard.
4. **Break the compatibility promise.** Find a PromptFile that does not survive a round-trip.
   That is the bug we most want to hear about.

See [CONTRIBUTING](../CONTRIBUTING.md).
