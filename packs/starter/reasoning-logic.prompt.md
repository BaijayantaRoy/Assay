---
promptfile: 1
id: reasoning/logic
name: Logical Deduction
summary: Systematic logic and deduction framework.
description: Systematic logic and deduction framework.
version: 1
kind: prompt
status: stable
tags:
- chain_of_thought
- cot
- deduction
- logic
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - given
    - goal
    - problem
    properties:
      given:
        type: string
      goal:
        type: string
      problem:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    given: sample given information
    goal: sample goal
    problem: sample problem
  assert:
  - type: contains
    value: sample
---

Apply rigorous logical reasoning to:

{{problem}}

Given information: {{given}}
What we need to find: {{goal}}

Step through the logic. Identify valid inferences. State your conclusion with confidence level.
