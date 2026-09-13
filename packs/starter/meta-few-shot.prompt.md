---
promptfile: 1
id: meta/few-shot
name: Few-Shot Example Generator
summary: Auto-generate few-shot examples for any task.
description: Auto-generate few-shot examples for any task.
version: 1
kind: prompt
status: stable
tags:
- examples
- few-shot
- meta
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - input_format
    - n
    - output_format
    - task_description
    properties:
      input_format:
        type: string
      n:
        type: string
      output_format:
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
    input_format: sample input_format
    n: sample n
    output_format: sample output_format
    task_description: sample task_description
  assert:
  - type: contains
    value: sample
---

Generate {{n}} diverse few-shot examples for this task:

Task: {{task_description}}
Input format: {{input_format}}
Output format: {{output_format}}

Ensure examples cover edge cases and variety.
