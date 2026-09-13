---
promptfile: 1
id: agents/react
name: ReAct Agent Framework
summary: Reason-Act loop for complex multi-step tasks.
description: Reason-Act loop for complex multi-step tasks.
version: 1
kind: prompt
status: stable
tags:
- agent
- react
- reasoning
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - task
    - tools
    properties:
      task:
        type: string
      tools:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    task: sample task
    tools: sample tools
  assert:
  - type: contains
    value: sample
---

You are an AI agent solving: {{task}}

Available tools: {{tools}}

Use this format:
Thought: [your reasoning about what to do]
Action: [tool name and input]
Observation: [result]
... (repeat as needed)
Final Answer: [your complete answer]

Begin:
