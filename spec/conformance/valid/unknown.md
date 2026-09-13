---
promptfile: 1
id: conformance/unknown
name: Unknown fields survive
model:
  primary: echo/echo
x-future:
  nested:
    - label: first
    - enabled: true
future_top_level:
  owner: another-tool
  weights: [0.1, 0.2, 0.7]
---

Preserve this body.
