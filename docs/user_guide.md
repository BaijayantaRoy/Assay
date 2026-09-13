# Assay user guide

Assay is a file-native assurance workbench for prompts and agents. A prompt, harness, or
loop is stored as a **PromptFile**: YAML frontmatter plus a Markdown body containing its
model binding, controls, and eval cases. The CLI, MCP server, REST API, SDKs, and web
workbench all operate on that same artifact.

The central rule is simple: evidence is reported only for what was actually checked. An
artifact without usable eval evidence is **unverified**, not passed; a rate with no usable
samples is withheld, not displayed as 0%.

## Contents

1. [Start Assay](#1-start-assay)
2. [Understand the workspace](#2-understand-the-workspace)
3. [Create and edit PromptFiles](#3-create-and-edit-promptfiles)
4. [Use the starter library](#4-use-the-starter-library)
5. [Run and test artifacts](#5-run-and-test-artifacts)
6. [Compare variants and models](#6-compare-variants-and-models)
7. [Build and verify agents](#7-build-and-verify-agents)
8. [Run security and governance checks](#8-run-security-and-governance-checks)
9. [Inspect cost and observability](#9-inspect-cost-and-observability)
10. [Connect other tools](#10-connect-other-tools)
11. [Import, export, and bootstrap](#11-import-export-and-bootstrap)
12. [Use the API and SDKs](#12-use-the-api-and-sdks)
13. [Configure providers and models](#13-configure-providers-and-models)
14. [Troubleshoot](#14-troubleshoot)

## 1. Start Assay

For repository development, install the three editable packages:

```bash
pip install -e packages/assay-core -e packages/assay-cli -e packages/assay-mcp
```

Then use the platform launcher:

```powershell
start-assay.bat fresh
```

```bash
./start-assay.sh fresh
```

The workbench is served at `http://localhost:3001`; the backend and interactive API
documentation are at `http://localhost:8001` and `http://localhost:8001/docs`.

For a standalone prompt workspace:

```bash
pip install assay-cli
assay init my-prompts
cd my-prompts
assay ls
assay test
```

Assay works offline with its deterministic `echo` provider. Real provider calls require
credentials in the process environment. Secret values never need to enter a PromptFile or
the browser.

## 2. Understand the workspace

The workbench reads the same file-backed `/v1` API used by the other product surfaces.
There is no organization database and no separate web-only prompt catalogue.

- **Dashboard** shows the current workspace inventory, verification coverage, security
  evidence, audit evidence, and token economy. Each number includes its relevant base or
  unavailable state.
- **Projects** are derived namespaces. The id `billing/dunning-email` appears under the
  `billing` project; there is no separate project record to create or delete.
- **All Prompts** lists PromptFiles from the workspace. Open one to inspect its source,
  render it, run embedded evals, and review version history.
- **Spec & Plugins** shows the PromptFile contract and the capabilities registered in this
  installation. Unknown extension fields round-trip unchanged by design.

The source of truth normally lives under `prompts/`. Version history is backed by the
workspace store and Git when available, rather than by an unrelated SQL record.

## 3. Create and edit PromptFiles

### Prompt Studio

Prompt Studio has two builders:

- **Anatomy Builder** assembles role, context, task, constraints, examples, output format,
  vision, memory, and custom blocks.
- **Vibe Coding Studio** creates a structured coding prompt from a component description,
  stack, and visual direction.

Enter an id such as `billing/dunning-email` and select **Save draft**. Studio deliberately
saves an unverified draft: it does not invent eval cases or claim model quality. Open the
new artifact from **All Prompts** and add meaningful evals before promotion.

### Prompt editor

The prompt detail page exposes the complete PromptFile source. Save operations create a
new version. Rendering substitutes declared variables without calling a provider. Embedded
evals run through the same engine as `assay test`.

Jinja variables use `{{ variable }}` syntax and should be declared in `input.schema`:

```markdown
---
promptfile: 1
id: support/refund-triage
name: Refund triage
kind: prompt
status: draft
engine: {template: jinja2, strict: true}
input:
  schema:
    type: object
    required: [message]
    properties:
      message: {type: string, minLength: 1}
model: {primary: echo/echo, params: {temperature: 0}}
evals:
  - id: preserves-request
    input: {message: duplicate charge}
    assert: [{type: contains, value: duplicate charge}]
---

Classify this request: {{ message }}
```

Hosted providers retry only explicit rate-limit responses. The default is two retries with
0.5-second exponential backoff and at most 30 seconds of total waiting per provider attempt.
`Retry-After` seconds or HTTP dates are respected within that ceiling. Generic provider or
authentication failures are never retried automatically. Override the bounded policy in
`model.params` when needed:

```yaml
model:
  primary: openai/gpt-5
  params:
    rate_limit_retries: 3       # 0..5
    rate_limit_backoff_s: 0.5   # 0..10
    rate_limit_max_wait_s: 20   # 0..60 total
```

These runtime-only keys are not forwarded to the provider. Successful completions retain
retry count, wait time, provider/model, and delay source under `completion.raw.rate_limit`,
and reported latency includes the wait. Streaming does not retry after a response starts.

Run `assay lint` after structural edits. Strict rendering rejects malformed templates and
missing variables instead of silently producing incomplete output.

## 4. Use the starter library

The repository ships 203 installable PromptFiles across ten packs. The Library page searches
and filters across every pack, and can install selections from multiple packs in one action.

Every catalog artifact includes at least one deterministic offline **render-contract** eval.
That proves its template can render and preserve the supplied sample; it does **not** prove
semantic quality against a live model. The Library labels that evidence scope explicitly.

After installation:

1. Adapt the artifact to the real task and provider.
2. Add representative success, boundary, and failure cases.
3. Break an important behavior deliberately and confirm the eval goes red.
4. Promote the status only after the evidence supports it.

## 5. Run and test artifacts

The core offline workflow is:

```bash
assay show support/refund-triage
assay render support/refund-triage -v customer_tier=pro -v message="charged twice"
assay run support/refund-triage -v customer_tier=pro -v message="charged twice"
assay test support/refund-triage
assay test support/refund-triage --max-workers 4
assay lint --policy
```

`assay test` exits with code 4 when an eval fails, so it can gate CI. A PromptFile with no
evals remains unverified. A case whose assertion could not be evaluated is reported beside
the usable denominator rather than counted as a pass.

`--max-workers N` (1–32) runs ordinary prompt eval cases through the bounded async
runtime. Reports remain in declaration order and include the actual ceiling and wall time.
Harness and loop evals retain their orchestration-specific execution path. The default is
one worker so existing provider-rate and cost behavior does not change silently.

The **Eval Lab** runs inline or workspace-relative JSON/JSONL datasets. It reports case
failures, assertion evidence, usable samples, uncertainty, cost, and attribution. Dataset
paths are constrained to the workspace.

## 6. Compare variants and models

- **Model Comparator** runs one PromptFile against selected models and reports output,
  latency, token use, and estimated cost. It is an execution comparison, not a quality win
  unless a quality evaluator was actually run.
- **A/B Testing** performs paired evaluation of two PromptFiles on the same cases. It reports
  wins, losses, ties, unusable pairs, confidence intervals, and cost. If there are too few
  usable pairs, the conclusion is withheld.
- **Judge Calibration** first checks whether human raters agree. Only then does it measure
  judge-to-human correlation. Calibration certificates expire and apply only to the labelled
  rubric and distribution used to create them.

## 7. Build and verify agents

### Harnesses

A harness declares its allowed tools, budget, memory, and controls. Running it produces a
trajectory: the ordered record of what the agent actually did. Trajectory assertions can
check tool use, arguments, ordering, and outcome, so a correct final answer reached through
a prohibited path can still fail.

```bash
assay run agents/researcher -v goal="find the source of this setting"
assay test agents/researcher
```

Set `harness.stream_model_calls: true` when the provider's incremental tool-call path is
part of what you need to assure. Assay assembles fragmented JSON arguments before dispatch,
records delivery mode and chunk count on every trajectory step, and runs ordinary trajectory
assertions against the assembled calls. It rejects `model.params.samples > 1` in this mode;
silently choosing among several live streams would make the executed path ambiguous.

### Loops

Loops compose sequential, concurrent, or supervised steps. Verification is recorded at each
handoff, not inferred from the final output. `verified: null` means a handoff was not checked;
it must never be coerced to false or true. Stall and convergence states are reported directly.

### Memory

Agent memory is file-backed and namespaced. Recall combines entity, keyword, and recency
signals, with exact identifiers such as paths and tool names ranked strongly. It is offline
and does not use embeddings; paraphrase recall is therefore a documented limitation.

## 8. Run security and governance checks

- **Guardrails** runs deterministic PII and injection-pattern detectors. A clean pattern scan
  is not a safety guarantee.
- **Red Team** runs versioned attacks and benign controls against a harness. Attack success
  and benign false-positive rates are reported only for usable samples. Assay's corpus is a
  regression gate, not exhaustive security coverage.
- **Governance** maps available workspace evidence to controls and states the remaining gap
  beside every control. It is not a compliance certification.

Use the CLI for reproducible gates:

```bash
assay redteam agents/researcher
assay redteam agents/researcher -c spec/redteam/adaptive-v1.jsonl --strategy adaptive
assay audit
assay governance
```

The strategy corpus stages payloads across successful tool results. `sequence` advances one
turn per result; `adaptive` waits for declared tool, argument, or result conditions. Reports
show planned and delivered turns. If a harness does not exercise every declared stage, that
case is an error excluded from the denominator—not a defended attack.

Injection defense remains partial. Pattern matching is bypassable, obfuscated payloads are
intentionally retained as known misses, and no clean run proves safety outside the tested
corpus.

## 9. Inspect cost and observability

Set `governance.audit: true` in `assay.yaml` to write local run evidence under
`.assay/audit/`. The feature is opt-in because audit data should not appear unexpectedly in
a repository.

- **Analytics** derives token, estimated-cost, latency, model, and artifact views from that
  audit log. If auditing is off, the page says so instead of showing fabricated zeroes.
- **Observability** separates local audit evidence, OpenTelemetry configuration, and external
  collector delivery. A configured exporter is not proof that a collector received a span;
  verify delivery in the destination.
- Audit integrity reports distinguish sealed records, legacy unsealed records, and records
  that were not checked.

Token counts and costs are estimates unless the provider supplies measured usage. Assay
labels them accordingly.

## 10. Connect other tools

The **Integrations** page supports four workflows:

1. Generate marker-delimited `AGENTS.md` or `CLAUDE.md` context for coding agents. Re-running
   generation updates the Assay block without overwriting surrounding hand-written text.
2. Copy an MCP configuration containing the actual workspace path.
3. Render a PromptFile and copy plain text into a chatbot. Only the rendered text travels;
   evals and guardrails do not accompany a clipboard paste.
4. Inspect and synchronize the shared model catalogue.

Example MCP configuration:

```json
{
  "mcpServers": {
    "assay": {
      "command": "assay",
      "args": ["mcp"],
      "env": {"ASSAY_WORKSPACE": "/absolute/path/to/workspace"}
    }
  }
}
```

## 11. Import, export, and bootstrap

Preview imports before writing:

```bash
assay import promptfooconfig.yaml --dry-run --json
assay import promptfooconfig.yaml --prefix migrated
assay test --prefix migrated/
```

The importer accepts Promptfoo configuration, OpenAI/Anthropic-style JSON requests, Genkit
`.prompt`, and a safe static subset of Microsoft POML. Unsupported source semantics are
preserved as extension metadata and called out as warnings; they are never silently counted
as native eval evidence. Imported artifacts remain unverified drafts.

Langfuse and PromptLayer prompts can be fetched by immutable version or release label:

```powershell
$env:LANGFUSE_PUBLIC_KEY = "pk-lf-..."
$env:LANGFUSE_SECRET_KEY = "sk-lf-..."
assay import langfuse://movie-critic --label production --prefix migrated --dry-run

$env:PROMPTLAYER_API_KEY = "pl-..."
assay import promptlayer://support-response --version 2 --prefix migrated --dry-run
```

Credentials remain request headers and are not stored in the resulting artifact. Remote
imports refuse redirects, credential-bearing URLs, unsafe origins, and responses over 10 MiB.

A workspace can also be bootstrapped from one PromptFile or an Assay `/v1/export` document:

```bash
assay init my-prompts --from https://example.com/export.json --dry-run --json
assay init my-prompts --from https://example.com/export.json
```

## 12. Use the API and SDKs

The stable REST surface is `/v1`. The deprecated unversioned database API is disabled by
default; `ASSAY_ENABLE_LEGACY_API=1` exists only for controlled migration. `/health` reports
whether it is enabled.

For clients that already speak OpenAI Chat Completions:

```bash
pip install "assay-cli[serve]"
assay serve --proxy
```

Call `POST http://127.0.0.1:8787/v1/chat/completions` with a reviewed artifact as the model:

```json
{
  "model": "assay:support/refund-triage@1",
  "variables": {
    "customer_tier": "pro",
    "message": "I was charged twice"
  }
}
```

The bounded adapter supports one completion, validates the PromptFile input schema before a
provider call, and adds provenance, usage, latency, environment, and estimated cost. Set
`"stream": true` for SSE text and artifact-declared tool-call chunks; the final chunk carries
usage and Assay streaming evidence. Fragmented arguments are validated and forwarded in
OpenAI-compatible `delta.tool_calls` form. Declared output guardrails force full-answer
buffering so blocked or redacted text cannot leak as an earlier chunk. It rejects conversation
history, client-supplied tools, sampled selection, multiple choices, unknown behavior-changing
fields, and bodies over 1 MiB. Set `ASSAY_PROXY_TOKEN` before any non-loopback bind; all
`/v1/*` routes then require that bearer token. Public `/health` exposes readiness only, not
workspace identity.

Python and TypeScript SDKs live under `packages/`. The Python client can read a workspace
directly or call the server while retaining the same core operation names.

## 13. Configure providers and models

Provider credentials belong in the backend or CLI process environment, commonly loaded from
a root `.env` file:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

Restart the backend after changing its environment. **Settings** reports provider presence
only; it neither accepts nor returns secret values. Theme preference is local to the browser.

**Global Models** is a searchable catalogue sourced from models.dev with an OpenRouter
fallback. Check the sync timestamp and source before treating it as current. Seed data is a
starting point, not evidence of present provider availability or pricing.

## 14. Troubleshoot

### Backend does not start

- Confirm Python 3.10 or newer: `python --version`.
- Reinstall the editable packages from the repository root.
- Run `assay lint` to catch malformed workspace artifacts.
- Check `http://localhost:8001/health`; the stable `/v1` service does not require ChromaDB or
  the legacy database.

### Frontend does not start

- Install dependencies with `npm install` in `frontend/`.
- Run `npm run lint`, `npx tsc --noEmit`, and `npm run build` to separate source errors from
  runtime connectivity errors.
- Confirm the backend is on port 8001 and the frontend is on port 3001.

### A run fails

- Render first with `assay render <id> -v key=value` to isolate schema/template problems.
- Confirm the bound provider is registered and its credential is available to the process.
- Read the error code: capability, guardrail, schema, provider, and not-found failures are
  intentionally distinct.

### An eval says unverified or not checked

That is not a transport error. It means no usable assertion evidence was produced for that
case or control. Add an evaluator/case that can genuinely fail, fix missing provider evidence,
or retain the honest unverified state.

### Docker build does not progress

Run `docker compose config --quiet` first, then build each service separately with plain
progress output. A stalled local daemon is not proof that an image works or fails; verify in a
clean builder or CI before release.

For unresolved defects, open a [GitHub issue](https://github.com/BaijayantaRoy/Assay/issues) with
the command, error code, platform, and the smallest PromptFile that reproduces it.
