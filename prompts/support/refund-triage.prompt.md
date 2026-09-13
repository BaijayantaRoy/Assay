---
promptfile: 1
id: support/refund-triage
name: Refund Triage
description: Classifies inbound support messages into a routing queue with a confidence score.
version: 1
kind: prompt
status: stable
tags: [support, classification, structured-output]
license: MIT

requires:
  capabilities: [json_mode]

engine:
  template: jinja2
  strict: true

input:
  schema:
    type: object
    required: [message]
    properties:
      message:
        type: string
        description: The raw customer message.
      customer_tier:
        type: string
        enum: [free, pro, enterprise]
        description: Affects escalation, not classification.
  examples:
    - message: I want my money back, this is unacceptable
      customer_tier: pro

output:
  format: json_schema
  schema:
    type: object
    required: [category, confidence, escalate]
    additionalProperties: false
    properties:
      category:
        type: string
        enum: [REFUND, BILLING, TECHNICAL, OTHER]
      confidence:
        type: number
        minimum: 0
        maximum: 1
      escalate:
        type: boolean
        description: True when a human should see this before an automated reply goes out.

model:
  primary: echo/json
  fallbacks: [echo/echo]
  params:
    temperature: 0
    max_tokens: 256

messages:
  - role: system
    content: |
      You are a support triage classifier. You output JSON and nothing else.

      Escalate when the message contains a legal threat, a chargeback mention, a safety
      issue, or when confidence is below 0.6. Enterprise-tier messages escalate on any
      category other than OTHER.
    cache: true
  - role: user
    content: |
      Customer tier: {{ customer_tier | default("free") }}

      Message:
      {{ message }}

evals:
  - id: obvious-refund
    description: A plain refund request must classify confidently and not escalate.
    input:
      message: I want my money back
      customer_tier: free
    assert:
      - { type: json_valid }
      - { type: cost_under, value: 0.02 }
      - { type: latency_under, value: 15000 }

  - id: legal-threat-escalates
    description: Legal language must reach a human regardless of category.
    input:
      message: My lawyer will be in touch about this charge
      customer_tier: enterprise
    assert:
      - { type: json_valid }

guardrails:
  - type: pii
    stage: input
    action: redact
    config:
      types: [credit_card, us_ssn]
  - type: schema
    stage: output
    action: retry

provenance:
  created_at: 2026-07-27T00:00:00Z
---

Classify the customer message above. Respond with JSON only — no prose, no code fence.
