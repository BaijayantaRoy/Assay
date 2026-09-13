---
promptfile: 1
id: loops/verified-pipeline
name: Verified Pipeline
summary: A two-step loop where each handoff is verified, not just the final result.
description: >-
  A worked example of loop engineering. Errors compound across handoffs, so each step
  carries its own check and the chain stops at the step that broke rather than 18 steps
  later. Uses shell commands so verification is an exit code, not a model's opinion.
version: 1
kind: loop
status: stable
tags: [loops, verification, example]
license: MIT

loop:
  trigger: goal
  goal: both artifacts exist and the final check passes
  max_cycles: 3
  budget:
    cost_usd: 1.00
    wallclock_s: 120
  detect_stalls: true

  steps:
    - id: stage-one
      command: "echo stage-one-output > stage1.txt"
      output: stage1
      verify:
        command: "python -c \"from pathlib import Path; raise SystemExit(not (Path('stage1.txt').is_file() and Path('stage1.txt').stat().st_size > 0))\""
        success_when: { type: exit_code, value: 0 }
      on_error: stop

    - id: stage-two
      command: "echo stage-two-output > stage2.txt"
      output: stage2
      verify:
        command: "python -c \"from pathlib import Path; raise SystemExit(not (Path('stage2.txt').is_file() and Path('stage2.txt').stat().st_size > 0))\""
        success_when: { type: exit_code, value: 0 }
      on_error: stop

  verify:
    command: "python -c \"from pathlib import Path; raise SystemExit(not all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in ('stage1.txt', 'stage2.txt')))\""
    success_when: { type: exit_code, value: 0 }

  on_verify_fail: retry

evals:
  - id: converges-and-every-handoff-checks-out
    assert:
      - { type: goal_met }
      - { type: steps_verified }
      - { type: cycles_under, value: 2 }
---
Run both stages and verify each handoff.
