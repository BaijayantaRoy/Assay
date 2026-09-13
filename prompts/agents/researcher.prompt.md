---
promptfile: 1
id: agents/researcher
name: Researcher
summary: Searches a codebase before answering, and is tested on that order.
description: >-
  A worked example of harness engineering: budget, control gates, context strategy,
  memory, and trajectory assertions that fail if the agent answers without looking.
version: 2
kind: harness
status: stable
tags: [agents, research, example]
license: MIT

requires:
  capabilities: [tools]

model:
  primary: echo/agent
  params: { temperature: 0 }
  provider_params:
    echo:
      script:
        - { tool: mock.search, arguments: { query: "retry" } }
        - { tool: mock.fetch, arguments: { id: "billing/invoice.py" } }
        - { text: "The retry logic in billing/invoice.py was changed to add a backoff." }

harness:
  loop: react
  stream_model_calls: true
  max_iterations: 8
  budget:
    cost_usd: 0.25
    wallclock_s: 60
    tool_calls: 12
  context:
    strategy: compact
    max_tokens: 100000
    keep_first: 1
    keep_last: 6
  control:
    deny: [shell.run, http.get]
    max_repeated_calls: 2
    max_consecutive_errors: 3
    mock_responses:
      mock.search: "billing/invoice.py:42 retry loop was refactored last quarter"
      mock.fetch: "def retry(...): backoff added in commit a1b2c3"
  memory:
    backend: jsonl
    namespace: research
    recall: { limit: 3 }
    write: { on: [failed] }
  stop_when:
    - { type: no_tool_calls }

tools:
  - { ref: mock.search }
  - { ref: mock.fetch }

evals:
  - id: searches-before-answering
    description: The assertion that matters — an agent must not answer from thin air.
    input: { goal: "why did the retry logic change?" }
    assert:
      - { type: tool_call_order, value: [mock.search, mock.fetch] }
      - { type: tool_called, value: mock.search }
      - { type: completed }

  - id: stays-efficient-and-cheap
    input: { goal: "why did the retry logic change?" }
    assert:
      - { type: iterations_under, value: 6 }
      - { type: no_repeated_tool_call }
      - { type: budget_under, value: 0.25 }

  - id: respects-its-control-gates
    input: { goal: "why did the retry logic change?" }
    assert:
      - { type: tool_not_called, value: [shell.run, http.get] }
      - { type: no_denied_calls }
---

Investigate: {{ goal }}

Search before you answer. Read what you find. Cite the file and line you relied on.
If the search returns nothing useful, say so rather than guessing.
