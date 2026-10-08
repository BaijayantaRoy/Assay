---
name: assay-prompts
description: Use when working in a repository that contains an assay.yaml or a prompts/ directory of .prompt.md files — reuse an existing tested prompt instead of writing one inline, run or render one, add a new PromptFile with eval cases, or check that a prompt edit did not regress. Also use when the user mentions Assay, PromptFile, a prompt library, an agent harness, or asks to test prompts.
---

# Working with an Assay workspace

This repository keeps its prompts and agents as **files**, not as strings scattered through
the code. Each one is a **PromptFile**: YAML frontmatter plus a Markdown body, carrying its
template, model binding, guardrails and **its own test cases**.

The single most useful thing to know: **before writing a prompt inline, check whether one
already exists here.** Reusing a tested artifact beats writing an untested one, and this is
the mistake worth avoiding most often.

## Orient yourself first

```bash
assay ls                    # every artifact with its id, kind and whether it has evals
assay show <id>             # the full source of one
```

`assay ls` is cheap and offline. Run it before assuming a prompt does or does not exist.

If `assay` is not on PATH, the workspace may not have it installed:
`pip install assay-cli`.

## Using an existing prompt

```bash
assay render <id> -v key=value      # fill the template, no model call, no cost
assay run    <id> -v key=value      # execute against the model the file declares
```

Prefer `render` when you only need to see the text. It never spends money.

**In application code, reference the artifact by id and render it.** Do not paste the
prompt body into a source file — that creates a second copy which will drift from the
tested one, and the test will keep passing while production uses different text.

```python
from assay import Client
client = Client.local("./prompts")
result = client.run("support/refund-triage", {"message": user_message})
```

## Writing a new one

```bash
assay new support/refund-triage
```

Then edit the file. A minimal PromptFile:

```markdown
---
promptfile: 1
id: support/refund-triage
name: Refund Triage
summary: Classifies inbound support messages into a routing queue.
version: 1
kind: prompt
status: draft
model:
  primary: anthropic/claude-opus-5-5
  params: { temperature: 0 }
input:
  schema:
    type: object
    required: [message]
    properties:
      message: { type: string }
evals:
  - id: obvious-refund
    input: { message: "I want my money back" }
    assert:
      - { type: contains, value: REFUND }
      - { type: not_empty }
---

Classify the customer message. Respond with the queue name only.

Message: {{ message }}
```

**Every new artifact needs at least one eval case.** An artifact with no evals passes every
run by default, which is not the same as working. If you cannot think of an assertion,
`{ type: not_empty }` is the honest floor — it proves the template rendered and the model
answered, and claims nothing about quality.

## Checking your work

```bash
assay test          # run every embedded eval — exits 4 on failure
assay test <id>     # just this one
assay lint          # validate against the PromptFile spec
```

**Run `assay test` after editing anything under the prompts directory.** It is offline,
deterministic, needs no API key, and takes seconds. If it fails, fix the artifact rather
than loosening the assertion — an assertion relaxed until it passes is not a test.

## Agent harnesses

A harness is an agent declared in a file: the loop, the tools it may call, the budget it
may spend, what it remembers, and the controls that stop it.

```bash
assay run <harness-id> -v goal='...'   # run it and get the trajectory
assay redteam <harness-id>             # measure its injection defences
```

Every run produces a **trajectory** — the record of what the agent actually did — and
assertions check the path, not just the final answer. That matters because an agent can
reach the right result through a tool call it should never have made.

Trajectory assertions worth knowing: `tool_called`, `tool_not_called`, `tool_call_order`,
`no_denied_calls`, `iterations_under`, `completed`.

## Things that will trip you up

**`verified` is tri-state.** `null` means nothing was checked — it is neither a pass nor a
failure. Do not report an unverified run as passing.

**The spec key is `promptfile:`, not `assay:`.** The format is deliberately not named
after the tool.

**Unknown frontmatter keys are preserved, not dropped.** If you see a field you do not
recognise, leave it alone; something else is using it.

**A red-team run against an offline provider measures the defences, not model
susceptibility.** The report says which mode it ran in. Do not quote a 0% attack-success
rate as evidence a model is safe.

## Making the workspace visible to other tools

```bash
assay agents init          # write AGENTS.md so any coding agent can find these prompts
assay mcp                  # run the MCP server (search, render, run, test as tools)
```
