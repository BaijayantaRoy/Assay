---
promptfile: 1
id: memory/rolling-summary
name: Rolling Summary Memory
summary: Summarize conversation to fit context window.
description: Summarize conversation to fit context window.
version: 1
kind: prompt
status: stable
tags:
- memory
- starter
- summarization
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - recent_messages
    - rolling_summary
    - user_message
    properties:
      recent_messages:
        type: string
      rolling_summary:
        type: string
      user_message:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    recent_messages: sample recent_messages
    rolling_summary: sample rolling_summary
    user_message: sample user_message
  assert:
  - type: contains
    value: sample
---

Previous conversation summary:
{{rolling_summary}}

Recent messages:
{{recent_messages}}

User: {{user_message}}

Before answering, update the summary internally.
