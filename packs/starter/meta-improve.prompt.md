---
promptfile: 1
id: meta/improve
name: Prompt Improver
summary: Analyze and enhance any prompt automatically.
description: Analyze and enhance any prompt automatically.
version: 1
kind: prompt
status: stable
tags:
- improve
- meta
- optimize
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - goal
    - prompt
    - target_model
    properties:
      goal:
        type: string
      prompt:
        type: string
      target_model:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    goal: sample goal
    prompt: sample prompt
    target_model: sample target_model
  assert:
  - type: contains
    value: sample
---

You are a prompt engineering expert. Improve this prompt:

<original_prompt>
{{prompt}}
</original_prompt>

Target model: {{target_model}}
Goal: {{goal}}

Provide:
1. Issues with the original
2. Improved version
3. Explanation of changes
