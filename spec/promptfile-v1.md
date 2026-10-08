# PromptFile v1 — Open Prompt Artifact Specification

**Status:** Stable · **Spec version:** `promptfile: 1` · **Schema:** [`schemas/promptfile-v1.schema.json`](schemas/promptfile-v1.schema.json)

PromptFile is a plain-text, git-native, model-agnostic format for describing a prompt and everything
needed to run, test, and govern it. It is the storage substrate of Assay, but it is
deliberately specified as a standalone format: any tool may read or write it without depending on
this project.

The format exists because prompts are source code. Source code belongs in files that diff cleanly,
review in pull requests, and survive the tool that created them.

---

## 1. Design goals

| Goal | How the format achieves it |
|:--|:--|
| **Diffable** | YAML frontmatter + markdown body. One prompt, one file, line-oriented. |
| **Model-agnostic** | Portable `model.params`; native fields quarantined in `model.provider_params`. |
| **Lossless round-trip** | Unknown keys and values MUST survive parse → modify → write unchanged. |
| **Forward compatible** | Integer `promptfile:` major version, reserved `x-` extension namespace, capability negotiation via `requires:`. |
| **Executable** | Input/output JSON Schema, tools, attachments, and model binding travel with the prompt. |
| **Testable** | `evals:` embeds assertions so a prompt is CI-gateable with no external config. |
| **Governable** | `status`, `deprecation`, `provenance`, `license`, `authors` are first-class. |

---

## 2. File shapes

A PromptFile is one of:

| Extension | Body | Use |
|:--|:--|:--|
| `.prompt.md` | Markdown after frontmatter becomes `body` | The default. Best for prose-heavy prompts. |
| `.prompt.yaml` / `.prompt.yml` | Pure YAML, `body` or `messages` as keys | Best for multi-message and generated files. |
| `.prompt.json` | Pure JSON | Machine-generated / interop. |

All three are the same document model. Converting between them MUST be lossless.

### Minimal example

```markdown
---
promptfile: 1
id: support/refund-triage
name: Refund Triage
---
Classify the customer message below as REFUND, BILLING, or OTHER.

Message: {{ message }}
```

### Full example

```markdown
---
promptfile: 1
id: support/refund-triage
name: Refund Triage
description: Routes inbound support mail to the correct queue.
version: 7
kind: prompt
status: stable
tags: [support, classification, production]
license: Apache-2.0
authors:
  - name: Jane Engineer

requires:
  capabilities: [json_mode]
  min_context_tokens: 16000

engine:
  template: jinja2
  strict: true

input:
  schema:
    type: object
    required: [message]
    properties:
      message: { type: string }
      customer_tier: { type: string, enum: [free, pro, enterprise] }
  examples:
    - message: "I want my money back"
      customer_tier: pro

output:
  format: json_schema
  schema:
    type: object
    required: [category, confidence]
    properties:
      category: { type: string, enum: [REFUND, BILLING, OTHER] }
      confidence: { type: number }

model:
  primary: anthropic/claude-opus-5-5
  fallbacks: [openai/gpt-6.1-sol, google/gemini-3.1-pro-preview]
  params:
    temperature: 0
    max_tokens: 512
  provider_params:
    anthropic:
      thinking: { type: enabled, budget_tokens: 2000 }

messages:
  - role: system
    content: You are a precise support triage classifier.
    cache: true
  - role: user
    content: |
      Customer tier: {{ customer_tier | default("free") }}
      Message: {{ message }}

evals:
  - id: obvious-refund
    input: { message: "I want my money back", customer_tier: pro }
    assert:
      - { type: json_schema }
      - { type: contains, value: REFUND }
      - { type: cost_under, value: 0.01 }
      - { type: latency_under, value: 4000 }

guardrails:
  - { type: pii, stage: input, action: redact }
  - { type: schema, stage: output, action: retry }

provenance:
  imported_from: langfuse
  created_at: 2026-07-27T09:00:00Z
---
```

---

## 3. Field reference

Only `promptfile` and `id` are required. Everything else has a defined default.

### 3.1 Identity

- **`promptfile`** *(integer, required)* — spec major version. A reader that does not implement version *N*
  MUST refuse the file with a clear error. It MUST NOT attempt best-effort parsing.
- **`id`** *(string, required)* — stable slug, lowercase, path segments allowed
  (`^[a-z0-9]([a-z0-9._-]*[a-z0-9])?(/…)*$`). **Immutable.** Renaming the file does not change the id.
- **`version`** *(integer)* — monotonic revision counter. Content changes bump it. Git holds the
  full history; this field is the human-facing handle used by API and CLI (`refund-triage@7`).
- **`status`** — `draft` → `review` → `stable` → `deprecated` → `archived`.

### 3.2 Capability negotiation — `requires`

The single most important forward-compatibility mechanism. A prompt declares what a runtime must be
able to do; runtimes that cannot MUST refuse rather than silently degrade.

```yaml
requires:
  capabilities: [tools, vision, json_mode, cache_control, reasoning]
  min_context_tokens: 200000
  plugins:
    assay-provider-anthropic: ">=1.0,<3"
```

Capability strings are an open vocabulary. New modalities in 2029 are new strings — no format change.

### 3.3 Templating — `engine`

`engine.template` names a renderer resolved through the plugin registry (`assay.renderers` entry
point). `jinja2` is the default and the only dialect a conforming implementation MUST ship.
`engine.strict: true` (default) makes an undefined variable an error, not an empty string.

### 3.4 Model binding — `model`

`model.primary` uses canonical `provider/model` references. `model.params` holds the portable
parameter set; provider plugins map these onto native fields. Anything non-portable goes in
`model.provider_params.<provider>` and is passed through untouched — so a provider shipping a novel
knob tomorrow needs no spec change.

`model.fallbacks` is an ordered list tried on hard failure or capability mismatch.

Portable test-time compute uses `model.params.samples` (1–16). Assay makes that many real
provider calls; it does not forward `samples` as a provider hint. `selection: majority`
votes over normalized response text plus tool calls. `selection: verifier` additionally
requires `verifier: <prompt-id>`; that PromptFile receives `candidate` and returns strict
JSON `{ "score": 0.0, "reason": "..." }`. Reports include the selected index, agreement
or verifier scores, hashes (not content) for alternative outputs, aggregate tokens and
cost, and the single-sample cost reference.

For `kind: harness`, `harness.stream_model_calls: true` routes every model turn through
the provider's optional streaming contract (or one explicitly labelled buffered chunk for a
legacy provider). Fragmented tool arguments MUST be assembled by stable call index and decode to
JSON objects before dispatch. Each trajectory step records its own delivery mode and received
chunk count. It cannot be combined with `model.params.samples > 1`, because live candidate
selection would make the delivered path ambiguous.

### 3.5 Content — `messages` vs `body`

If `messages` is present it is authoritative and `body` is ignored for execution. If absent, `body`
is rendered as a single `user` message. `messages[].cache: true` is a portable hint requesting a
provider cache breakpoint after that message; providers without prompt caching ignore it.

### 3.6 Composition — `includes` and `attachments`

`includes` merges other PromptFiles before rendering (later entries win; `messages` concatenate).
`attachments` loads external files or `promptfile://` resources and binds them to variables at render time.
Together these give reusable system-prompt fragments without a bespoke import syntax.

### 3.7 Testing — `evals`

Embedded assertions make a prompt self-testing. Assertion `type` is resolved through the evaluator
plugin registry (`assay.evaluators`), so `contains` and `llm_judge` and a bespoke company evaluator
are all the same shape. Unknown assertion types are permitted for plugin interoperability and
become an explicit evaluator error when no installed plugin resolves them — never a silent pass.

Large case sets may live beside the PromptFile as UTF-8 JSONL or JSON:

```yaml
evals:
  - id: refund-regression
    dataset: refund-triage.dataset.jsonl
    assert:
      - { type: json_schema }
      - { type: contains, value: REFUND }
```

Each row is an object with an `input` object and optional `id`, `expected_output`, and `assert`.
Declaration assertions apply to every row; row assertions are appended. Paths resolve relative to
the PromptFile, MUST remain inside the workspace, and files over 10 MiB are refused. Duplicate ids
after expansion are errors. `promptfile://` dataset handles are reserved but not implemented in v1.

Harness evals may freeze an ordered golden tool path with `trajectory_accuracy`. Its `value` is a
list of tool names or `{tool, arguments}` objects. Assay reports order-aware LCS precision, recall,
and F1; supplied arguments are required subsets. The default threshold is `1.0`.

Every prompt, harness, and loop eval report includes an `accuracy_cost` operating point:
measured score, total spend, single-sample reference spend, incremental sampling cost,
cost multiplier and cost per usable case. This is not a causal curve; compare against a
separate run at another sample count before claiming that more compute improved accuracy.

### 3.8 Extensions — `x-`

Any key beginning `x-` is reserved for vendors and future features. Conforming tools MUST preserve
these keys verbatim through parse → modify → write. This is what allows an ecosystem to experiment
without forking the format.

---

## 4. Conformance requirements

A **conforming reader**:

1. MUST reject a file whose `promptfile` major version it does not implement.
2. MUST validate against the JSON Schema for its version.
3. MUST ignore unknown fields it does not understand.
4. MUST NOT execute a prompt whose `requires.capabilities` it cannot satisfy.

A **conforming writer**:

1. MUST preserve unknown fields, including all `x-` keys, on round-trip.
2. MUST preserve key order of fields it did not modify where the serializer allows.
3. MUST NOT reorder or reformat the body.
4. MUST emit `promptfile` as the first key.

A **conforming runtime** additionally:

1. MUST record which plugin resolved each of: renderer, provider, evaluator, guardrail.
2. MUST fail closed on guardrail errors when `action: block`.

Run `assay lint` to check conformance; run `assay spec validate <file>` for schema-only validation.

---

## 5. Versioning and compatibility policy

| Change | Version impact |
|:--|:--|
| New optional field | none — additive, `promptfile: 1` |
| New enum member in an open vocabulary (`kind`, `capabilities`, assertion `type`) | none |
| New `x-` extension | none |
| Field becomes required, or semantics change | `promptfile: 2` |
| Field removal | deprecate for ≥ 12 months, then `promptfile: 2` |

**Backward compatibility:** every `promptfile: 1` file ever written stays readable by every future v1 tool.

**Forward compatibility:** a v1 file written by a newer tool with fields an older tool does not know
stays *usable* by that older tool — unknown fields are ignored for execution and preserved on write.

No automated major-version migration command ships in v1. A future migration tool MUST preserve
unknown fields and MUST require explicit user confirmation before rewriting a PromptFile.

---

## 6. Interop

Assay exposes importers and exporters as plugins (`assay.importers` / `assay.exporters`), so
PromptFile can be a hub format rather than a competing island. The table distinguishes the
built-in migration paths from planned plugin targets:

The canonical conformance fixtures live in `spec/conformance/`. They are executed by the
Python reader in `assay-core` and the independent Node.js reader/writer in
`packages/promptfile-typescript` (`@assay/promptfile`). Both implementations must accept the
same valid Markdown/YAML/JSON documents, reject the same invalid version/schema/duplicate-key
documents, preserve unknown values semantically, and reach a stable serialization fixed point.
Comments, quoting style, and byte-for-byte YAML presentation are not promised.

| Format | Direction | Status | Notes |
|:--|:--|:--|:--|
| **Promptfoo** YAML/JSON | ← | Built in | Inline/file prompts and supported assertions become draft PromptFiles; unsupported semantics remain explicit `x-import` warnings. |
| Google **dotprompt** (`.prompt`) | ← | Built in | Simple variables become Jinja; helpers/partials remain literal and explicitly non-executable until a compatible renderer is installed. Picoschema is translated conservatively. |
| Microsoft **POML** (`.poml`) | ← | Built in | Static text/message components, simple variables, model parameters and static JSON output schemas are translated. Runtime expressions, conditions, loops, tools, includes, styling and unsupported components are preserved verbatim and require the `poml-runtime` capability, so Assay cannot execute them by accident. |
| **Langfuse** prompt API | ← | Built in | `langfuse://name` fetches a selected label/version with environment-only Basic auth. Text/chat prompts, simple variables, safe model parameters, static JSON schemas, labels and immutable versions map to draft PromptFiles; composition or application-specific config is capability-gated. |
| **PromptLayer** raw template API | ← | Built in | `promptlayer://name` fetches stable provider-agnostic template data with an environment-only API key. Chat/completion templates, f-string/Jinja variables, safe model parameters, tags and versions map to draft PromptFiles; snippets and unsupported parameters are capability-gated. |
| **Braintrust**, **Latitude** | ↔ | Planned plugins | Hosted metadata and version semantics require source-specific mappings. |
| **OpenAI / Anthropic** raw messages | ← | Built in | Roles, message content and safe request parameters map directly; provider-only fields stay explicit warnings and no eval evidence is invented. |
| **MCP** `prompts/get` | → | Built in | Served natively by the Assay MCP server. |

---

## 7. Repository layout convention

```
prompts/
├── assay.yaml                  # workspace config: registry, defaults, plugins
├── support/
│   ├── refund-triage.prompt.md
│   └── refund-triage.dataset.jsonl
├── agents/
│   └── researcher.prompt.md  # kind: agent
└── _shared/
    └── house-style.prompt.md # included by others
```

`assay.yaml` is the only workspace-level file. Everything else is discoverable by glob, so the layout
above is a convention, not a requirement.

---

## 8. License

This specification is published under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Implement it freely, including in commercial and competing products.
