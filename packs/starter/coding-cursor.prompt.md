---
promptfile: 1
id: coding/cursor
name: Cursor/Windsurf Agent Task
summary: Optimized prompt for AI coding agent tools.
description: Optimized prompt for AI coding agent tools.
version: 1
kind: prompt
status: stable
tags:
- agent
- cursor
- starter
- vibe_coding
- windsurf
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - constraints
    - files
    - stack
    - task_description
    properties:
      constraints:
        type: string
      files:
        type: string
      stack:
        type: string
      task_description:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    constraints: sample constraints
    files: sample files
    stack: sample stack
    task_description: sample task_description
  assert:
  - type: contains
    value: sample
---

Task: {{task_description}}

Context:
- Stack: {{stack}}
- File(s) to modify: {{files}}
- Constraints: {{constraints}}

Implement this completely. Write production-quality code. Add comments for non-obvious logic.
