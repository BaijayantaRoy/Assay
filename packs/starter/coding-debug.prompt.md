---
promptfile: 1
id: coding/debug
name: Expert Bug Investigator
summary: Deep-dive bug analysis for any codebase.
description: Deep-dive bug analysis for any codebase.
version: 1
kind: prompt
status: stable
tags:
- coding
- debug
- starter
- vibe_coding
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - code
    - error_message
    - language
    properties:
      code:
        type: string
      error_message:
        type: string
      language:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    code: sample code
    error_message: sample error_message
    language: sample language
  assert:
  - type: contains
    value: sample
---

You are a senior {{language}} engineer. Investigate this bug:

Code:
```{{language}}
{{code}}
```

Error: {{error_message}}

Provide: root cause, fix, and how to prevent this class of bug in future.
