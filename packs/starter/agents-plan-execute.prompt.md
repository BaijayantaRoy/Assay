---
promptfile: 1
id: agents/plan-execute
name: Plan-Execute Agent
summary: Create a plan then execute each step.
description: Create a plan then execute each step.
version: 1
kind: prompt
status: stable
tags:
- agent
- planning
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - constraints
    - resources
    - task
    properties:
      constraints:
        type: string
      resources:
        type: string
      task:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    constraints: sample constraints
    resources: sample resources
    task: sample task
  assert:
  - type: contains
    value: sample
---

Task: {{task}}

Step 1 — PLAN: Break this into concrete sub-tasks.
Step 2 — EXECUTE: Work through each sub-task systematically.
Step 3 — VERIFY: Check your output meets the original task.

Resources available: {{resources}}
Constraints: {{constraints}}
