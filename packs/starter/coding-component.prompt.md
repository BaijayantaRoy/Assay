---
promptfile: 1
id: coding/component
name: React Component (Glassmorphism)
summary: Generate a stunning glassmorphism React component.
description: Generate a stunning glassmorphism React component.
version: 1
kind: prompt
status: stable
tags:
- glassmorphism
- react
- starter
- ui
- vibe_coding
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - color_palette
    - component_name
    - functionality
    properties:
      color_palette:
        type: string
      component_name:
        type: string
      functionality:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    color_palette: sample color_palette
    component_name: sample component_name
    functionality: sample functionality
  assert:
  - type: contains
    value: sample
---

Create a React component for {{component_name}}.

Design vibe: glassmorphism — frosted glass panels, subtle blur backdrop, soft gradients.
Color palette: {{color_palette}}
Functionality: {{functionality}}

Use Tailwind CSS. Include hover animations and smooth transitions. Make it stunning.
