---
promptfile: 1
id: vision/ocr
name: Document OCR & Structure
summary: Extract and structure text from images.
description: Extract and structure text from images.
version: 1
kind: prompt
status: stable
tags:
- document
- ocr
- starter
- vision
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - additional_task
    properties:
      additional_task:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    additional_task: sample additional_task
  assert:
  - type: contains
    value: sample
---

Extract all text from this image. Preserve the original structure:

- Maintain headings, bullet points, and formatting
- Note tables with their alignment
- Flag any text that is unclear with [unclear]
- Output in clean markdown

Additional task: {{additional_task}}
