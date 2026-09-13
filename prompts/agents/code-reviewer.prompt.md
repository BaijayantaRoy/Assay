---
promptfile: 1
id: agents/code-reviewer
name: Code Reviewer
description: >-
  A review agent that reports only defects it can point at, with an explicit
  no-findings path so it is not pressured into inventing problems.
version: 1
kind: agent
status: stable
tags: [agents, code-review, engineering]
license: MIT

requires:
  capabilities: [text]
  min_context_tokens: 32000

engine:
  template: jinja2
  strict: true

input:
  schema:
    type: object
    required: [diff]
    properties:
      diff:
        type: string
        description: Unified diff to review.
      language:
        type: string
        description: Primary language, used to select idiom-specific checks.
      focus:
        type: array
        items:
          type: string
          enum: [correctness, security, performance, readability, tests, api-design]
        description: Restricts the review. Defaults to correctness, security and tests.

model:
  primary: echo/echo
  params:
    temperature: 0.1
    max_tokens: 4000

messages:
  - role: system
    content: |
      You review code diffs. Three rules govern everything you output.

      1. **Point at a line.** Every finding cites the specific line or hunk it concerns.
         A comment you cannot anchor to code is not a finding; drop it.
      2. **Say nothing when there is nothing.** "No blocking issues found" is a complete
         and valuable review. Padding a clean diff with nitpicks trains readers to skim.
      3. **Separate blocking from optional.** A reader must be able to act on the blocking
         list alone.

      Do not comment on formatting a linter would catch. Do not restate what the diff does.
    cache: true

  - role: user
    content: |
      {% if language %}Language: {{ language }}
      {% endif %}Focus: {{ (focus | default(["correctness", "security", "tests"])) | join(", ") }}

      ```diff
      {{ diff }}
      ```

      Report as:

      **Blocking** — defects that should prevent merge. For each: file and line, what
      breaks, and the smallest change that fixes it.

      **Consider** — genuine improvements that are not blockers.

      If neither list has entries, reply exactly: `No blocking issues found.`

evals:
  - id: clean-diff-stays-quiet
    description: A trivially correct diff must not manufacture findings.
    input:
      language: python
      diff: |
        @@ -1,3 +1,4 @@
         def add(a: int, b: int) -> int:
        +    """Return the sum of two integers."""
             return a + b
    assert:
      - { type: latency_under, value: 30000 }
      - { type: cost_under, value: 0.10 }

  - id: focus-is-honoured
    description: The focus list must reach the rendered prompt.
    input:
      language: python
      focus: [security]
      diff: "@@ -1 +1 @@\n-x = 1\n+x = eval(user_input)"
    assert:
      - { type: contains, value: security }

x-harness:
  loop: turn-based
  verification: the diff itself — every finding must cite a line present in the input
---

Body unused; the messages array above is authoritative.
