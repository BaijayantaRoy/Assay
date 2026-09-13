---
promptfile: 1
id: agents/multi-agent
name: Multi-Agent Orchestrator
summary: Coordinate multiple specialist agents.
description: Coordinate multiple specialist agents.
version: 1
kind: prompt
status: stable
tags:
- agent
- multi-agent
- orchestration
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - agent_descriptions
    - task
    properties:
      agent_descriptions:
        type: string
      task:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    agent_descriptions: sample agent_descriptions
    task: sample task
  assert:
  - type: contains
    value: sample
---

You are the orchestrator managing these specialist agents:
{{agent_descriptions}}

User task: {{task}}

Decompose the task, assign to appropriate agents, and synthesize results. Show your delegation decisions.
