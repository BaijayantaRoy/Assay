"""Loops, per-step verification and routing-loop detection — RESEARCH §3.6.

The theme: a loop that *reports* success is not a loop that *succeeded*. These tests
mostly check that failures are caught and surfaced at the point they occur.
"""

from __future__ import annotations

import threading

import pytest

from assay_core import LoopRuntime, PromptFile, Runtime, Workspace
from assay_core.builtins.trajectory import (
    CyclesUnderEvaluator,
    GoalMetEvaluator,
    StepsVerifiedEvaluator,
    VerifiedEvaluator,
)
from assay_core.errors import LoopError


@pytest.fixture
def loops(tmp_path):
    (tmp_path / "prompts").mkdir(exist_ok=True)
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    return LoopRuntime(runtime), tmp_path


def make(source: str) -> PromptFile:
    return PromptFile.parse(source)


PASSING = """---
promptfile: 1
id: loops/passing
kind: loop
loop:
  trigger: goal
  goal: the marker file exists
  max_cycles: 3
  steps:
    - id: create
      command: "echo done > marker.txt"
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" marker.txt'
    success_when: { type: exit_code, value: 0 }
---
Create the marker.
"""

FAILING = """---
promptfile: 1
id: loops/failing
kind: loop
loop:
  goal: an impossible file exists
  max_cycles: 2
  steps:
    - id: noop
      command: "echo nothing"
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" never-created.txt'
    success_when: { type: exit_code, value: 0 }
  on_verify_fail: retry
---
Never succeeds.
"""

UNVERIFIED = """---
promptfile: 1
id: loops/unverified
kind: loop
loop:
  goal: something
  max_cycles: 1
  steps:
    - id: noop
      command: "echo hi"
---
No verification at all.
"""


# ---------------------------------------------------------------------------
# Verification is the point
# ---------------------------------------------------------------------------


def test_loop_stops_as_soon_as_verification_passes(loops):
    runtime, root = loops
    run = runtime.run(make(PASSING))
    assert run.goal_met
    assert run.status == "goal_met"
    assert run.cycle_count == 1          # no wasted cycles after success
    assert (root / "marker.txt").exists()


def test_loop_retries_then_stops_when_nothing_is_changing(loops):
    """A retry loop whose steps produce identical output is stalled, not merely failing.

    Stopping early is the point: the remaining cycles would cost money and change
    nothing. Distinguishing "stalled" from "verification_failed" matters because the
    fixes differ — one means the work is wrong, the other means there is no work.
    """
    runtime, _ = loops
    run = runtime.run(make(FAILING))
    assert not run.goal_met
    assert run.status == "stalled"
    assert "nothing is changing" in run.stop_reason
    assert all(c.verified is False for c in run.cycles)


def test_stall_detection_can_be_disabled(loops):
    """Some loops legitimately repeat while the world changes underneath them."""
    runtime, _ = loops
    run = runtime.run(make(FAILING.replace("  on_verify_fail: retry",
                                           "  detect_stalls: false\n  on_verify_fail: retry")))
    assert run.status == "max_cycles"
    assert run.cycle_count == 2


def test_a_loop_with_no_verification_reports_none_not_success(loops):
    """An unverified loop must not be able to claim success by default."""
    runtime, _ = loops
    run = runtime.run(make(UNVERIFIED))
    assert run.cycles[0].verified is None
    assert not run.goal_met


def test_verified_assertion_fails_when_nothing_verified(loops):
    runtime, _ = loops
    run = runtime.run(make(UNVERIFIED))
    from assay_core.loop import _synthetic_trajectory

    result = VerifiedEvaluator().evaluate(
        "", assertion={"type": "verified"},
        context={"trajectory": _synthetic_trajectory(run), "loop_run": run},
    )
    assert not result.passed
    assert "nothing checked" in result.reason


def test_linter_flags_a_loop_without_verification():
    problems = make(UNVERIFIED).validate(strict=True)
    assert any("marks its own homework" in p for p in problems)


# ---------------------------------------------------------------------------
# Per-step verification — RESEARCH §3.6, error compounding
# ---------------------------------------------------------------------------


STEP_VERIFIED = """---
promptfile: 1
id: loops/step-verified
kind: loop
loop:
  goal: both steps produce their files
  max_cycles: 1
  steps:
    - id: first
      command: "echo a > a.txt"
      verify:
        command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" a.txt'
        success_when: { type: exit_code, value: 0 }
    - id: second
      command: "echo b > b.txt"
      verify:
        command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" b.txt'
        success_when: { type: exit_code, value: 0 }
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not all(pathlib.Path(p).is_file() for p in sys.argv[1:]))" a.txt b.txt'
    success_when: { type: exit_code, value: 0 }
---
Two verified steps.
"""

BAD_HANDOFF = """---
promptfile: 1
id: loops/bad-handoff
kind: loop
loop:
  goal: finish the chain
  max_cycles: 1
  steps:
    - id: broken
      command: "echo produced-nothing-useful"
      verify:
        command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" expected-artifact.txt'
        success_when: { type: exit_code, value: 0 }
      on_error: stop
    - id: downstream
      command: "echo this-should-not-run > downstream.txt"
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" downstream.txt'
    success_when: { type: exit_code, value: 0 }
---
The first handoff is corrupt.
"""


def test_each_step_records_its_own_verification(loops):
    runtime, _ = loops
    run = runtime.run(make(STEP_VERIFIED))
    outcomes = run.cycles[0].step_results
    assert [o["verified"] for o in outcomes] == [True, True]
    assert run.goal_met


def test_a_failed_handoff_stops_the_chain_at_the_step_that_broke(loops):
    """Error compounding: catch it where it happens, not 18 steps later."""
    runtime, root = loops
    run = runtime.run(make(BAD_HANDOFF))

    outcomes = run.cycles[0].step_results
    assert len(outcomes) == 1                      # downstream never ran
    assert outcomes[0]["id"] == "broken"
    assert outcomes[0]["verified"] is False
    assert not (root / "downstream.txt").exists()
    assert not run.goal_met


def test_steps_verified_assertion_catches_a_bad_handoff(loops):
    runtime, _ = loops
    run = runtime.run(make(BAD_HANDOFF))
    result = StepsVerifiedEvaluator().evaluate(
        "", assertion={"type": "steps_verified"}, context={"loop_run": run}
    )
    assert not result.passed
    assert "broken" in result.reason
    assert result.details["attribution"] == [{"type": "step", "id": "broken"}]


def test_steps_verified_passes_when_every_handoff_checks_out(loops):
    runtime, _ = loops
    run = runtime.run(make(STEP_VERIFIED))
    result = StepsVerifiedEvaluator().evaluate(
        "", assertion={"type": "steps_verified"}, context={"loop_run": run}
    )
    assert result.passed
    assert "2/2" in result.reason


def test_a_final_pass_can_hide_a_broken_intermediate_step(loops):
    """The reason step-level verification exists at all.

    The cycle-level check passes, but an intermediate handoff failed. `verified` says
    fine; `steps_verified` catches it.
    """
    runtime, _ = loops
    source = """---
promptfile: 1
id: loops/hidden
kind: loop
loop:
  goal: final file exists
  max_cycles: 1
  steps:
    - id: bad-middle
      command: "echo x"
      verify:
        command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" never.txt'
        success_when: { type: exit_code, value: 0 }
      on_error: continue
    - id: rescue
      command: "echo ok > final.txt"
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" final.txt'
    success_when: { type: exit_code, value: 0 }
---
x
"""
    run = runtime.run(make(source))
    assert run.goal_met                                   # the loop thinks it succeeded
    assert not StepsVerifiedEvaluator().evaluate(         # but a handoff was broken
        "", assertion={"type": "steps_verified"}, context={"loop_run": run}
    ).passed


# ---------------------------------------------------------------------------
# Routing-loop detection
# ---------------------------------------------------------------------------


def test_a_loop_going_round_in_circles_is_detected(loops):
    """A→B→A: keeps running, keeps spending, never converges."""
    runtime, _ = loops
    source = """---
promptfile: 1
id: loops/circular
kind: loop
loop:
  goal: never reachable
  max_cycles: 6
  steps:
    - id: same-every-time
      command: "echo identical-output"
  verify:
    command: 'python -c "import pathlib,sys; raise SystemExit(not pathlib.Path(sys.argv[1]).is_file())" unreachable.txt'
    success_when: { type: exit_code, value: 0 }
  on_verify_fail: retry
---
x
"""
    run = runtime.run(make(source))
    assert run.status == "stalled"
    assert "nothing is changing" in run.stop_reason
    assert run.cycle_count < 6           # stopped early instead of burning all cycles
    assert run.state.get("routing_loops")


# ---------------------------------------------------------------------------
# Concurrent and supervisor orchestration
# ---------------------------------------------------------------------------


def test_concurrent_fanout_overlaps_work_and_merges_in_declaration_order(loops, monkeypatch):
    runtime, _ = loops
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_step(step, scope, *, model, dry_run):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=3)
        with lock:
            active -= 1
        return {"id": step["id"], "output": step["id"], "failed": False}

    monkeypatch.setattr(runtime, "_run_step", fake_step)
    loop = make("""---
promptfile: 1
id: loops/concurrent
kind: loop
loop:
  max_cycles: 1
  orchestration: { pattern: concurrent, max_workers: 2 }
  steps:
    - { id: first, run: workers/one, output: first_result }
    - { id: second, run: workers/two, output: second_result }
---
fan out
""")

    run = runtime.run(loop)
    cycle = run.cycles[0]
    assert peak == 2
    assert [outcome["id"] for outcome in cycle.step_results] == ["first", "second"]
    assert cycle.orchestration == "concurrent"
    assert cycle.route == ["workers/one", "workers/two"]


def test_concurrent_fanout_refuses_hidden_cross_branch_dependencies(loops):
    runtime, _ = loops
    loop = make("""---
promptfile: 1
id: loops/dependent-fanout
kind: loop
loop:
  max_cycles: 1
  orchestration: { pattern: concurrent }
  steps:
    - { id: first, command: "echo a", output: first_result }
    - { id: second, command: "echo {{ first_result }}" }
---
invalid fan out
""")

    with pytest.raises(LoopError, match="depends on fan-out output"):
        runtime.run(loop)


def test_supervisor_selects_a_strict_route_over_known_workers(loops, monkeypatch):
    runtime, _ = loops
    called = []

    def fake_step(step, scope, *, model, dry_run):
        called.append(step["id"])
        if step["id"] == "supervisor":
            assert "worker-a" in scope["available_steps"]
            return {"id": "supervisor", "output": '{"route":["worker-b"]}',
                    "failed": False, "cost_usd": 0.1}
        return {"id": step["id"], "output": "done", "failed": False}

    monkeypatch.setattr(runtime, "_run_step", fake_step)
    loop = make("""---
promptfile: 1
id: loops/supervised
kind: loop
loop:
  max_cycles: 1
  orchestration: { pattern: supervisor, supervisor: agents/router }
  steps:
    - { id: worker-a, run: agents/a, description: Handles A }
    - { id: worker-b, run: agents/b, description: Handles B }
---
route the work
""")

    run = runtime.run(loop)
    cycle = run.cycles[0]
    assert called == ["supervisor", "worker-b"]
    assert cycle.step_results[0]["orchestration_role"] == "supervisor"
    assert cycle.step_results[0]["route"] == ["worker-b"]
    assert cycle.route == ["agents/b"]


def test_invalid_supervisor_route_fails_closed_without_running_workers(loops, monkeypatch):
    runtime, _ = loops
    called = []

    def fake_step(step, scope, *, model, dry_run):
        called.append(step["id"])
        return {"id": step["id"], "output": '{"route":["unknown"]}', "failed": False}

    monkeypatch.setattr(runtime, "_run_step", fake_step)
    loop = make("""---
promptfile: 1
id: loops/bad-supervisor
kind: loop
loop:
  max_cycles: 1
  orchestration: { pattern: supervisor, supervisor: agents/router }
  steps:
    - { id: worker-a, run: agents/a }
---
route
""")

    run = runtime.run(loop)
    assert called == ["supervisor"]
    assert run.status == "failed"
    assert run.cycles[0].verified is False
    assert "unknown worker" in run.stop_reason


def test_supervisor_handoff_cycle_is_named_and_stopped_before_workers_run(loops, monkeypatch):
    runtime, _ = loops
    called = []

    def fake_step(step, scope, *, model, dry_run):
        called.append(step["id"])
        return {"id": step["id"], "output": '{"route":["a","b","a"]}',
                "failed": False}

    monkeypatch.setattr(runtime, "_run_step", fake_step)
    loop = make("""---
promptfile: 1
id: loops/handoff-cycle
kind: loop
loop:
  max_cycles: 5
  orchestration: { pattern: supervisor, supervisor: agents/router }
  steps:
    - { id: a, run: agents/a }
    - { id: b, run: agents/b }
---
route
""")

    run = runtime.run(loop)
    assert called == ["supervisor"]
    assert run.status == "routing_loop"
    assert run.cycle_count == 1
    assert run.cycles[0].handoff_cycle == ["agents/a", "agents/b", "agents/a"]
    assert run.state["handoff_cycles"][0]["detected"] == [
        "agents/a", "agents/b", "agents/a"
    ]


# ---------------------------------------------------------------------------
# Budgets and assertions
# ---------------------------------------------------------------------------


def test_max_cycles_is_respected(loops):
    runtime, _ = loops
    run = runtime.run(make(FAILING), max_cycles=1)
    assert run.cycle_count == 1


def test_cycles_under_and_goal_met_assertions(loops):
    runtime, _ = loops
    run = runtime.run(make(PASSING))
    ctx = {"loop_run": run}
    assert CyclesUnderEvaluator().evaluate("", assertion={"type": "cycles_under", "value": 3},
                                           context=ctx).passed
    assert GoalMetEvaluator().evaluate("", assertion={"type": "goal_met"}, context=ctx).passed


def test_goal_met_assertion_fails_on_a_failing_loop(loops):
    runtime, _ = loops
    run = runtime.run(make(FAILING))
    assert not GoalMetEvaluator().evaluate(
        "", assertion={"type": "goal_met"}, context={"loop_run": run}
    ).passed


def test_state_persists_across_runs(loops):
    runtime, root = loops
    source = PASSING.replace(
        "  verify:", "  state: { path: .assay/state/test-loop.json }\n  verify:"
    )
    first = runtime.run(make(source))
    assert (root / ".assay" / "state" / "test-loop.json").exists()
    second = runtime.run(make(source))
    assert second.state.get("last_run") != first.run_id


def test_dry_run_does_not_execute_commands(loops):
    runtime, root = loops
    runtime.run(make(PASSING), dry_run=True)
    assert not (root / "marker.txt").exists()
