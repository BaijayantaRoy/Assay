---
promptfile: 1
id: system/assistant
name: Custom Assistant Blueprint
summary: Build a fully-configured AI assistant.
description: Build a fully-configured AI assistant.
version: 1
kind: prompt
status: stable
tags:
- assistant
- custom
- starter
- system
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - always_do
    - assistant_name
    - company
    - escalation_triggers
    - never_do
    - role
    - tone
    properties:
      always_do:
        type: string
      assistant_name:
        type: string
      company:
        type: string
      escalation_triggers:
        type: string
      never_do:
        type: string
      role:
        type: string
      tone:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    always_do: sample always_do
    assistant_name: sample assistant_name
    company: sample company
    escalation_triggers: sample escalation_triggers
    never_do: sample never_do
    role: sample role
    tone: sample tone
  assert:
  - type: contains
    value: sample
---

You are {{assistant_name}}, an AI assistant for {{company}}.

Primary role: {{role}}
Tone: {{tone}}
Always do: {{always_do}}
Never do: {{never_do}}
Escalate to human when: {{escalation_triggers}}
