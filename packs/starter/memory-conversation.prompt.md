---
promptfile: 1
id: memory/conversation
name: Conversation History Injection
summary: Maintain context across long conversations.
description: Maintain context across long conversations.
version: 1
kind: prompt
status: stable
tags:
- context
- memory
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - conversation_history
    - user_message
    properties:
      conversation_history:
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
    conversation_history: sample conversation_history
    user_message: sample user_message
  assert:
  - type: contains
    value: sample
---

You are a helpful assistant with memory of our conversation.

<conversation_history>
{{conversation_history}}
</conversation_history>

User: {{user_message}}
