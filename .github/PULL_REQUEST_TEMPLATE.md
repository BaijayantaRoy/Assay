<!--
Keep this short. The checklist exists because these four things are where this project
has actually broken before, not as ceremony.
-->

## What and why

<!-- What changes, and what problem it solves. Link an issue if there is one. -->

## Checklist

- [ ] `assay test` and `pytest` pass locally.
- [ ] **If this changes a `/v1` response shape:** `tests/e2e/test_ui_contract_e2e.py` still
      passes, or was updated alongside `frontend/lib/v1.ts`. TypeScript types are erased at
      runtime and verify nothing about what the server sends — a rename typechecks cleanly
      on both sides and renders `undefined` in the browser.
- [ ] **If this adds a capability the tool reports on:** it reports honestly when it has
      nothing to report. An unverified run says *not checked*, never *passed*; a rate
      computed from zero usable samples is withheld rather than shown as 0%.
- [ ] **If this touches the spec:** the change is compatible under
      [ADR-0004](../docs/architecture/adr/0004-compatibility-policy.md), or it says why a
      major bump is needed.
- [ ] Docs updated where they would otherwise now be wrong. A README that overstates what
      shipped is a defect.

## Anything you're unsure about

<!-- Genuinely useful. Say what you'd want a reviewer to look hardest at. -->
