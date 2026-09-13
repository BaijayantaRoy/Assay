# Prompt library

The starter set. Every prompt here carries eval cases, so `assay test` verifies the whole
directory — a prompt without evals is a suggestion, not an asset.

```bash
assay ls                          # what's here
assay show support/refund-triage  # inspect one
assay test                        # verify them all (offline, no API key)
```

| Prompt | Kind | What it demonstrates |
|:--|:--|:--|
| `shared/house-style` | system | A fragment other prompts include instead of copy-pasting |
| `support/refund-triage` | prompt | Structured output, capability requirements, PII redaction, schema-retry guardrail |
| `agents/code-reviewer` | agent | Agent-shaped prompt with an explicit no-findings path and an `x-` extension block |

## Layout

Directories are a convention, not a requirement — prompts are found by suffix, and the `id:`
field is the real identifier. A file can move without breaking anything that references it.

```
prompts/
├── _shared/     fragments included by other prompts
├── support/
└── agents/
```

## Adding one

```bash
assay new my-area/my-prompt --description "What it does"
$EDITOR prompts/my-area/my-prompt.prompt.md
assay test my-area/my-prompt
```

Two things make a contribution useful rather than just present:

**Eval cases that could fail.** An assertion that passes on any output tests nothing. Include
at least one case that pins down behaviour you actually care about.

**A stated `status`.** `draft` is honest and welcome. `stable` is a promise that the prompt has
evals and has been used in anger.

The format is documented in [`spec/promptfile-v1.md`](../spec/promptfile-v1.md).
