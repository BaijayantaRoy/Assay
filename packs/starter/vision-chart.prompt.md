---
promptfile: 1
id: vision/chart
name: Chart & Graph Interpreter
summary: Extract insights from charts and graphs.
description: Extract insights from charts and graphs.
version: 1
kind: prompt
status: stable
tags:
- chart
- data
- starter
- vision
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - context
    properties:
      context:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    context: sample context
  assert:
  - type: contains
    value: sample
---

Analyze this chart/graph:

1. **Chart type**: What kind of visualization is this?
2. **Data summary**: Key numbers, trends, and patterns
3. **Key insight**: The single most important takeaway
4. **Anomalies**: Anything unexpected in the data
5. **Recommendation**: What action does this data suggest?

Context: {{context}}
