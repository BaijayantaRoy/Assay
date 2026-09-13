---
promptfile: 1
id: rag/document-qa
name: Document Q&A
summary: Answer questions grounded in provided documents.
description: Answer questions grounded in provided documents.
version: 1
kind: prompt
status: stable
tags:
- grounding
- qa
- rag
- starter
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required:
    - documents
    - question
    properties:
      documents:
        type: string
      question:
        type: string
model:
  primary: echo/echo
  params:
    temperature: 0
evals:
- id: renders
  input:
    documents: sample documents
    question: sample question
  assert:
  - type: contains
    value: sample
---

Use only the following documents to answer the question. If the answer isn't in the documents, say so.

<documents>
{{documents}}
</documents>

Question: {{question}}

Cite which document(s) support your answer.
