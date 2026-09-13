---
promptfile: 1
id: memory/persona
name: Persistent Persona Memory
summary: Keep the AI's persona consistent across sessions.
description: Keep the AI's persona consistent across sessions.
version: 1
kind: prompt
status: stable
tags:
- memory
- persona
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - persona_description
    - persona_name
    - session_context
    - user_input
    properties:
      persona_description:
        type: string
      persona_name:
        type: string
      session_context:
        type: string
      user_input:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    persona_description: sample persona_description
    persona_name: sample persona_name
    session_context: sample session_context
    user_input: sample user_input
  assert:
  - type: contains
    value: sample
---

You are {{persona_name}}, a {{persona_description}}.

Previous session context:
{{session_context}}

Continue being {{persona_name}}. Respond to: {{user_input}}
