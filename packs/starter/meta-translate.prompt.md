---
promptfile: 1
id: meta/translate
name: Cross-Model Prompt Translator
summary: Convert a prompt optimized for one model to another.
description: Convert a prompt optimized for one model to another.
version: 1
kind: prompt
status: stable
tags:
- meta
- models
- starter
- translate
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - prompt
    - source_model
    - target_model
    properties:
      prompt:
        type: string
      source_model:
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
    prompt: sample prompt
    source_model: sample source_model
    target_model: sample target_model
  assert:
  - type: contains
    value: sample
---

Convert this {{source_model}} prompt to work best with {{target_model}}:

<prompt>
{{prompt}}
</prompt>

Account for {{target_model}}'s strengths and preferred formatting. Keep the intent identical.
