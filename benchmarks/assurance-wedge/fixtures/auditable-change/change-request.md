# Change request

When the supplied message does not contain enough policy evidence to decide, the assistant must
classify it as `escalate`, say that policy evidence is missing, and never promise approval.

## Required red-to-green evidence

1. Start from the unchanged `prompt.md` and `existing-cases.json`.
2. Add the supplied `new-case.json` through the product's supported eval workflow.
3. Retain evidence that the new case fails before the prompt is fixed.
4. Change the prompt, rerun all cases, and retain evidence that all cases pass.
5. Produce a reviewable artifact showing the configuration, red result, green result, commands,
   manual transformations, elapsed time, product version, and environment.

The stopwatch begins when the operator opens this file in a clean environment and stops when the
reviewable green evidence is saved. A run that does not finish within 45 minutes is incomplete.
