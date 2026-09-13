---
promptfile: 1
id: reasoning/decision
name: Decision Analysis Framework
summary: Structured pros/cons and decision making.
description: Structured pros/cons and decision making.
version: 1
kind: prompt
status: stable
tags:
- analysis
- chain_of_thought
- cot
- decision
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - constraints
    - context
    - decision
    - values
    properties:
      constraints:
        type: string
      context:
        type: string
      decision:
        type: string
      values:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    constraints: sample constraints
    context: sample context
    decision: sample decision
    values: sample values
  assert:
  - type: contains
    value: sample
---

Help me decide: {{decision}}

Context: {{context}}
Constraints: {{constraints}}
Values that matter most: {{values}}

Analyze all options. Weight pros and cons. Give a clear recommendation with reasoning.
