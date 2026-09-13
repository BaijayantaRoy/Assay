---
promptfile: 1
id: coding/fullstack
name: Full-Stack Feature Plan
summary: Plan a complete feature from DB to UI.
description: Plan a complete feature from DB to UI.
version: 1
kind: prompt
status: stable
tags:
- architecture
- fullstack
- starter
- vibe_coding
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - feature_name
    - stack
    properties:
      feature_name:
        type: string
      stack:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    feature_name: sample feature_name
    stack: sample stack
  assert:
  - type: contains
    value: sample
---

Plan the full implementation of {{feature_name}} for a {{stack}} application.

Include:
1. Database schema
2. API endpoints
3. Frontend components
4. State management
5. Edge cases to handle

Be specific and production-ready.
