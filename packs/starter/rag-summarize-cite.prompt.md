---
promptfile: 1
id: rag/summarize-cite
name: Summarize with Citations
summary: Summarize documents with source attribution.
description: Summarize documents with source attribution.
version: 1
kind: prompt
status: stable
tags:
- citations
- rag
- starter
- summarization
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - documents
    - length
    properties:
      documents:
        type: string
      length:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    documents: sample documents
    length: sample length
  assert:
  - type: contains
    value: sample
---

Summarize the following documents:

<documents>
{{documents}}
</documents>

Requirements:
- Group related information
- Cite source for each claim [Doc X]
- Highlight contradictions between sources
- Length: {{length}}
