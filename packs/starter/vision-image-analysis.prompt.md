---
promptfile: 1
id: vision/image-analysis
name: Detailed Image Analysis
summary: Comprehensive image description and analysis.
description: Comprehensive image description and analysis.
version: 1
kind: prompt
status: stable
tags:
- analysis
- image
- starter
- vision
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - focus_area
    properties:
      focus_area:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    focus_area: sample focus_area
  assert:
  - type: contains
    value: sample
---

Analyze this image in detail:

1. **What is shown**: Describe the main subjects and scene
2. **Details**: Colors, textures, spatial relationships
3. **Context**: What situation or setting does this depict?
4. **Notable elements**: Anything unusual or significant
5. **Interpretation**: What message or purpose does this image convey?

Focus on: {{focus_area}}
