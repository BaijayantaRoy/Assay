---
promptfile: 1
id: reasoning/math
name: Mathematical Reasoning
summary: Step-by-step math problem solving.
description: Step-by-step math problem solving.
version: 1
kind: prompt
status: stable
tags:
- chain_of_thought
- cot
- math
- reasoning
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - problem
    properties:
      problem:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    problem: sample problem
  assert:
  - type: contains
    value: sample
---

Solve this problem step by step:

{{problem}}

Show all work. Check your answer. If you make an assumption, state it explicitly.
