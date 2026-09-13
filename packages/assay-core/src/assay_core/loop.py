"""The loop executor — loop engineering as a versioned artifact.

A **harness** equips one agent run. A **loop** is the outer system that keeps going:
it discovers work, dispatches it to agents or sub-agents, **verifies the result**,
persists state, and decides whether to run again.

That distinction is the whole point. The harness is what happens inside one run; the
loop is what turns a single run into a system that makes progress without someone
typing the next message.

```yaml
kind: loop
loop:
  trigger: goal
  goal: The test suite passes
  max_cycles: 5
  budget: { cost_usd: 2.00, wallclock_s: 900 }

  steps:
    - id: find-failures
      run: agents/test-scanner        # a harness, a prompt, or a command
      output: failures
    - id: fix
      run: agents/fixer
      with: { failures: "{{ failures }}" }

  verify:
    command: "pytest -q"
    success_when: { type: exit_code, value: 0 }

  on_verify_fail: retry
  state: { path: .assay/state/{{ loop_id }}.json }
```

The verification step is the load-bearing part
----------------------------------------------
An agent reporting success is making a claim. A verification step that passes is
evidence. Loops that skip verification appear to work and quietly accumulate wrong
results — the agent marks its own homework and always gives itself an A.

So verification here is a *separate, non-model* check by default: a command's exit code,
a regex over its output, a file's existence. When the check is itself a model call, that
is allowed but it is opt-in and named as such, because a model grading a model is a
weaker signal and the artifact should say so out loud.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from .contracts import CycleResult, LoopRun
from .errors import LoopError
from .harness import AgentRuntime
from .promptfile import PromptFile
from .runtime import Runtime

logger = logging.getLogger("assay.loop")

DEFAULT_MAX_CYCLES = 5
HARD_CYCLE_CAP = 100


class LoopRuntime:
    """Executes ``kind: loop`` artifacts."""

    def __init__(
        self,
        runtime: Runtime | None = None,
        *,
        agent_runtime: AgentRuntime | None = None,
    ) -> None:
        self.runtime = runtime or Runtime()
        self.agents = agent_runtime or AgentRuntime(self.runtime)
        self.registry = self.runtime.registry
        self.workspace = self.runtime.workspace
        self.store = self.workspace.store()

    # -- public API --------------------------------------------------------

    def run(
        self,
        loop: PromptFile,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        max_cycles: int | None = None,
        on_cycle: Callable[[CycleResult], None] | None = None,
        dry_run: bool = False,
    ) -> LoopRun:
        config = dict(loop.data.get("loop") or {})
        variables = dict(variables or {})

        budget = dict(config.get("budget") or {})
        cycles_allowed = min(
            int(max_cycles or config.get("max_cycles", DEFAULT_MAX_CYCLES)), HARD_CYCLE_CAP
        )

        run = LoopRun(
            loop_id=loop.id,
            loop_version=loop.version,
            goal=str(variables.get("goal") or config.get("goal") or ""),
            trigger=config.get("trigger", "manual"),
            run_id=str(uuid.uuid4()),
        )
        run.state = self._load_state(config, loop, variables)
        started = time.perf_counter()
        seen_signatures: set[str] = set()
        # Values produced by steps become variables for later steps and for verification.
        scope: dict[str, Any] = {**run.state.get("scope", {}), **variables, "goal": run.goal}

        try:
            for index in range(cycles_allowed):
                elapsed = time.perf_counter() - started
                exceeded = self._budget_exceeded(run, budget, elapsed)
                if exceeded:
                    run.status = "budget_exceeded"
                    run.stop_reason = exceeded
                    break

                orchestration = dict(config.get("orchestration") or {})
                pattern = orchestration.get("pattern", "sequential")
                if pattern not in ("sequential", "concurrent", "supervisor"):
                    raise LoopError(f"unknown orchestration pattern {pattern!r}")
                cycle = CycleResult(index=index, orchestration=pattern)
                cycle_started = time.perf_counter()
                steps = list(config.get("steps") or [])

                supervisor_outcome = None
                if pattern == "supervisor":
                    steps, supervisor_outcome = self._supervisor_plan(
                        orchestration, steps, scope, model=model, dry_run=dry_run
                    )
                    cycle.step_results.append(supervisor_outcome)
                    cycle.cost_usd += supervisor_outcome.get("cost_usd", 0.0)
                    if supervisor_outcome.get("failed"):
                        cycle.verified = False
                        cycle.verification_detail = supervisor_outcome.get(
                            "error", "supervisor failed to produce a valid route"
                        )
                        cycle.wallclock_s = time.perf_counter() - cycle_started
                        run.cycles.append(cycle)
                        run.cost_usd += cycle.cost_usd
                        run.status = "failed"
                        run.stop_reason = cycle.verification_detail
                        if on_cycle:
                            on_cycle(cycle)
                        break

                cycle.route = [_step_route_key(step) for step in steps]
                detect_handoffs = orchestration.get(
                    "detect_handoff_cycles", pattern == "supervisor"
                )
                handoff_cycle = _find_handoff_cycle(cycle.route) if detect_handoffs else []
                if handoff_cycle:
                    cycle.handoff_cycle = handoff_cycle
                    cycle.verified = False
                    cycle.verification_detail = (
                        "explicit handoff cycle detected: " + " → ".join(handoff_cycle)
                    )
                    cycle.wallclock_s = time.perf_counter() - cycle_started
                    run.cycles.append(cycle)
                    run.cost_usd += cycle.cost_usd
                    run.status = "routing_loop"
                    run.stop_reason = cycle.verification_detail
                    run.state.setdefault("handoff_cycles", []).append({
                        "cycle": index, "route": cycle.route,
                        "detected": handoff_cycle,
                    })
                    if on_cycle:
                        on_cycle(cycle)
                    break

                execution_pattern = (
                    orchestration.get("worker_pattern", "sequential")
                    if pattern == "supervisor" else pattern
                )
                if execution_pattern == "concurrent":
                    self._validate_concurrent_steps(steps)
                    frozen_scope = dict(scope)
                    workers = min(max(int(orchestration.get("max_workers", 4)), 1), 16)
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        outcomes = list(pool.map(
                            lambda step: self._run_step(
                                step, frozen_scope, model=model, dry_run=dry_run
                            ),
                            steps,
                        ))
                elif execution_pattern == "sequential":
                    outcomes = None
                else:
                    raise LoopError(
                        f"unknown supervisor worker_pattern {execution_pattern!r}"
                    )

                for position, step in enumerate(steps):
                    outcome = (
                        outcomes[position] if outcomes is not None
                        else self._run_step(step, scope, model=model, dry_run=dry_run)
                    )

                    # Verify at the handoff, not only at the end of the cycle.
                    #
                    # Errors compound: a 90%-accurate step feeding another 90%-accurate
                    # step does not yield 90%. By step 18 of a 20-step chain you have a
                    # confident, coherent, wrong result. Checking at each handoff is the
                    # documented mitigation — it turns a silent corruption into a visible
                    # failure at the step that caused it.
                    if step.get("verify"):
                        step_scope = {**scope, "output": outcome.get("output", "")}
                        if step.get("output"):
                            step_scope[step["output"]] = outcome.get("output", "")
                        verified, detail = self._verify(
                            {"verify": step["verify"]}, step_scope, cycle, model=model
                        )
                        outcome["verified"] = verified
                        outcome["verification_detail"] = detail
                        if verified is False:
                            outcome["failed"] = True
                            logger.warning("step %s failed verification: %s",
                                           step.get("id"), detail)

                    cycle.step_results.append(outcome)
                    cycle.cost_usd += outcome.get("cost_usd", 0.0)
                    if step.get("output"):
                        scope[step["output"]] = outcome.get("output", "")

                    policy = step.get("on_error", "continue")
                    if outcome.get("failed") and policy == "stop":
                        cycle.verification_detail = (
                            f"step {step.get('id')} failed"
                            + (f": {outcome.get('verification_detail','')}"
                               if outcome.get("verification_detail") else "")
                            + "; stopping this cycle"
                        )
                        break

                verified, detail = self._verify(config, scope, cycle, model=model)
                cycle.verified = verified
                cycle.verification_detail = detail or cycle.verification_detail
                cycle.goal_met = verified is True
                cycle.wallclock_s = time.perf_counter() - cycle_started

                run.cycles.append(cycle)
                run.cost_usd += cycle.cost_usd
                if on_cycle:
                    on_cycle(cycle)

                if cycle.goal_met:
                    run.status = "goal_met"
                    run.stop_reason = detail or "verification passed"
                    break

                policy = config.get("on_verify_fail", "retry")
                if policy == "stop":
                    run.status = "verification_failed"
                    run.stop_reason = detail or "verification failed; on_verify_fail is 'stop'"
                    break
                if policy == "escalate":
                    run.status = "verification_failed"
                    run.stop_reason = f"escalating after failed verification: {detail}"
                    run.state.setdefault("escalations", []).append(
                        {"cycle": index, "detail": detail}
                    )
                    break

                # Routing-loop detection. A→B→A is a named multi-agent failure mode: the
                # loop keeps running, keeps spending, and never converges because each
                # cycle undoes the last. Identical step outcomes across cycles is the
                # cheapest reliable signal that it is happening.
                signature = _cycle_signature(cycle)
                if (signature and signature in seen_signatures
                        and config.get("detect_stalls", True)):
                    # "stalled" rather than "verification_failed": the distinction matters
                    # when reading a report. Verification failing means the work was wrong.
                    # Stalling means the work did not change at all — a different problem
                    # with a different fix.
                    run.status = "stalled"
                    run.stop_reason = (
                        f"cycle {index} produced exactly the outcome of an earlier cycle "
                        "and verification still failed, so nothing is changing. Stopping "
                        "rather than burning the remaining cycles. Set "
                        "loop.detect_stalls: false to disable this check."
                    )
                    run.state.setdefault("routing_loops", []).append(
                        {"cycle": index, "signature": signature}
                    )
                    break
                seen_signatures.add(signature)

                # retry: feed the failure forward so the next cycle knows what went wrong.
                scope["last_failure"] = detail
                scope["cycle"] = index + 1
            else:
                if not run.cycles or not run.cycles[-1].goal_met:
                    run.status = "max_cycles"
                    run.stop_reason = f"reached max_cycles ({cycles_allowed}) without meeting the goal"

        except LoopError:
            raise
        except Exception as exc:
            logger.exception("loop %s crashed", loop.id)
            run.status = "failed"
            run.stop_reason = f"{type(exc).__name__}: {exc}"

        run.wallclock_s = time.perf_counter() - started
        run.state["scope"] = {k: v for k, v in scope.items() if _serialisable(v)}
        run.state["last_run"] = run.run_id
        run.state["last_status"] = run.status
        self._save_state(config, loop, variables, run.state)
        return run

    # -- evaluation --------------------------------------------------------

    def evaluate(self, loop: PromptFile, *, cases: list[dict] | None = None,
                 model: str | None = None) -> dict:
        """Run each eval case as a full loop and assert on the loop run."""
        from .builtins.evaluators import aggregate
        from .contracts import EvalResult
        from .evaluation import (
            accuracy_cost_report,
            failure_attribution,
            resolve_eval_cases,
            score_confidence_interval,
        )

        cases = resolve_eval_cases(
            loop,
            cases if cases is not None else loop.evals,
            workspace_root=self.workspace.root,
        )
        case_reports: list[dict] = []
        all_results: list[EvalResult] = []
        grouped_results: list[tuple[str, list[EvalResult]]] = []

        for case in cases:
            try:
                run = self.run(loop, case.get("input") or {}, model=model)
            except Exception as exc:
                failure = EvalResult(passed=False, score=0.0, evaluator="loop",
                                     reason=f"loop run failed: {exc}")
                all_results.append(failure)
                case_id = str(case.get("id", "?"))
                grouped_results.append((case_id, [failure]))
                case_reports.append({"id": case_id, "passed": False,
                                     "error": str(exc), "results": []})
                continue

            last_output = ""
            if run.cycles and run.cycles[-1].step_results:
                last_output = run.cycles[-1].step_results[-1].get("output", "")

            context = {
                "loop_run": run,
                "trajectory": _synthetic_trajectory(run),
                "cost_usd": run.cost_usd,
                "latency_ms": int(run.wallclock_s * 1000),
                "judge": self.runtime._make_judge(model),
            }
            results: list[EvalResult] = []
            for assertion in case.get("assert") or []:
                try:
                    evaluator = self.registry.get("assay.evaluators", assertion["type"])
                    results.append(
                        evaluator.evaluate(last_output, assertion=assertion, context=context)
                    )
                except Exception as exc:
                    results.append(EvalResult(passed=False, score=0.0,
                                              evaluator=assertion.get("type", "?"),
                                              reason=f"evaluator error: {exc}"))
            all_results.extend(results)
            case_id = str(case.get("id", "?"))
            grouped_results.append((case_id, results))
            summary = aggregate(results)
            sampling = [
                item
                for cycle in run.cycles
                for outcome in cycle.step_results
                for item in (outcome.get("sampling") or [])
            ]
            sampled_total = sum(float(item.get("total_cost_usd", 0.0)) for item in sampling)
            sampled_single = sum(
                float(item.get("single_sample_cost_usd", 0.0)) for item in sampling
            )
            case_reports.append({
                "id": case_id, "passed": summary["passed"],
                "score": summary["score"], "output": last_output,
                "cost_usd": run.cost_usd, "latency_ms": int(run.wallclock_s * 1000),
                "cycles": run.cycle_count, "status": run.status,
                "sampling": sampling,
                "samples_requested": max(
                    [int(item.get("samples_requested", 1)) for item in sampling], default=1
                ),
                "selection": sampling[0].get("selection", "single") if sampling else "single",
                "single_sample_cost_usd": run.cost_usd - sampled_total + sampled_single,
                "results": [{"evaluator": r.evaluator, "passed": r.passed,
                             "score": r.score, "reason": r.reason,
                             "details": r.details} for r in results],
            })

        unverified_cases = sum(1 for case in case_reports if case.get("passed") is None)
        overall = aggregate(all_results, unverified=unverified_cases)
        score_ci = score_confidence_interval(
            [results for _, results in grouped_results],
            unverified_cases=unverified_cases,
        )
        return {
            "prompt_id": loop.id, "prompt_version": loop.version, "kind": loop.kind,
            "model": model or self.runtime.default_model,
            "passed": overall["passed"], "score": overall["score"],
            "score_ci": score_ci,
            "usable": overall["usable"],
            "cases": case_reports,
            "total_assertions": overall["total"], "failed_assertions": overall["failed"],
            "unverified_cases": unverified_cases,
            "failure_attribution": failure_attribution(grouped_results),
            "accuracy_cost": accuracy_cost_report(overall["score"], case_reports),
            "total_cost_usd": round(sum(c.get("cost_usd", 0) for c in case_reports), 6),
        }

    # -- steps -------------------------------------------------------------

    def _supervisor_plan(
        self,
        orchestration: dict,
        steps: list[dict],
        scope: dict,
        *,
        model: str | None,
        dry_run: bool,
    ) -> tuple[list[dict], dict]:
        """Ask a declared supervisor for a strict JSON route over known step ids."""
        supervisor = orchestration.get("supervisor")
        if not supervisor:
            raise LoopError("supervisor orchestration requires orchestration.supervisor")

        by_id: dict[str, dict] = {}
        catalogue = []
        for position, step in enumerate(steps):
            step_id = step.get("id")
            if not step_id:
                raise LoopError("every supervisor worker step requires an explicit id")
            if step_id in by_id:
                raise LoopError(f"duplicate supervisor worker id {step_id!r}")
            by_id[step_id] = step
            catalogue.append({
                "id": step_id,
                "run": step.get("run"),
                "description": step.get("description", ""),
                "position": position,
            })

        plan_scope = {
            **scope,
            "available_steps": json.dumps(catalogue, ensure_ascii=False),
        }
        outcome = self._run_step(
            {
                "id": "supervisor",
                "run": supervisor,
                "with": {"available_steps": "{{ available_steps }}"},
            },
            plan_scope,
            model=model,
            dry_run=dry_run,
        )
        outcome["orchestration_role"] = "supervisor"
        if outcome.get("failed"):
            return [], outcome

        try:
            payload = json.loads(str(outcome.get("output", "")))
            route = payload.get("route") if isinstance(payload, dict) else payload
            if not isinstance(route, list) or not route or not all(
                isinstance(item, str) and item for item in route
            ):
                raise ValueError("expected a non-empty JSON route array")
            unknown = [step_id for step_id in route if step_id not in by_id]
            if unknown:
                raise ValueError("unknown worker id(s): " + ", ".join(unknown))
        except (json.JSONDecodeError, ValueError) as exc:
            outcome["failed"] = True
            outcome["error"] = f"invalid supervisor route: {exc}"
            return [], outcome

        outcome["route"] = route
        return [by_id[step_id] for step_id in route], outcome

    def _validate_concurrent_steps(self, steps: list[dict]) -> None:
        """Refuse fan-out definitions that silently depend on another branch."""
        outputs = [step.get("output") for step in steps if step.get("output")]
        if len(outputs) != len(set(outputs)):
            raise LoopError("concurrent steps must bind distinct output names")
        for step in steps:
            material = json.dumps(
                {"with": step.get("with") or {}, "command": step.get("command") or ""},
                default=str,
            )
            dependencies = [name for name in outputs if re.search(
                r"\{\{\s*" + re.escape(name) + r"\s*\}\}", material
            )]
            if dependencies:
                raise LoopError(
                    f"concurrent step {step.get('id')!r} depends on fan-out output(s) "
                    f"{', '.join(dependencies)}; use sequential orchestration"
                )

    def _run_step(self, step: dict, scope: dict, *, model: str | None,
                  dry_run: bool) -> dict:
        """Dispatch one loop step: a command, a harness, or a prompt."""
        step_id = step.get("id") or step.get("run") or "step"
        started = time.perf_counter()

        try:
            if step.get("command"):
                return self._run_command_step(step, scope, step_id, started, dry_run=dry_run)

            target = step.get("run")
            if not target:
                return {"id": step_id, "failed": True,
                        "error": "step has neither 'run' nor 'command'"}

            artifact = self.store.get(target)
            step_vars = {**scope, **_render_mapping(step.get("with") or {}, scope)}

            if artifact.kind in ("harness", "agent"):
                trajectory = self.agents.run(artifact, step_vars, model=model, dry_run=dry_run)
                sampling = [
                    event for event in trajectory.events
                    if event.get("type") == "test_time_compute"
                ]
                return {
                    "id": step_id, "run": target, "type": "harness",
                    "output": trajectory.output, "status": trajectory.status,
                    "iterations": trajectory.iterations,
                    "tool_calls": trajectory.tool_call_names,
                    "cost_usd": trajectory.cost_usd,
                    "sampling": sampling,
                    "failed": trajectory.status in ("failed", "budget_exceeded"),
                    "wallclock_s": round(time.perf_counter() - started, 3),
                }

            result = self.runtime.run(artifact, step_vars, model=model)
            return {
                "id": step_id, "run": target, "type": "prompt",
                "output": result.text, "cost_usd": result.cost_usd, "failed": False,
                "sampling": [result.sampling] if result.sampling else [],
                "wallclock_s": round(time.perf_counter() - started, 3),
            }
        except Exception as exc:
            logger.warning("loop step %s failed: %s", step_id, exc)
            return {"id": step_id, "failed": True, "error": f"{type(exc).__name__}: {exc}",
                    "wallclock_s": round(time.perf_counter() - started, 3)}

    def _run_command_step(self, step: dict, scope: dict, step_id: str, started: float,
                          *, dry_run: bool) -> dict:
        command = _render_text(step["command"], scope)
        if dry_run:
            return {"id": step_id, "type": "command", "command": command,
                    "output": "[dry-run: command not executed]", "failed": False,
                    "exit_code": 0}
        completed = _shell(command, cwd=self.workspace.root,
                           timeout=int(step.get("timeout_s", 300)))
        return {
            "id": step_id, "type": "command", "command": command,
            "output": completed["output"], "exit_code": completed["exit_code"],
            "failed": completed["exit_code"] != 0,
            "wallclock_s": round(time.perf_counter() - started, 3),
        }

    # -- verification ------------------------------------------------------

    def _verify(self, config: dict, scope: dict, cycle: CycleResult,
                *, model: str | None) -> tuple[bool | None, str]:
        """Run the verification step. Returns (verified, detail).

        ``None`` means no verification was configured — which the ``verified``
        evaluator reports as a failure, because an unverified loop is exactly the
        failure mode this design exists to prevent.
        """
        verify = config.get("verify")
        if not verify:
            return None, "no verification configured"

        # 1. Command verification — the strongest signal. No model involved.
        if verify.get("command"):
            command = _render_text(verify["command"], scope)
            completed = _shell(command, cwd=self.workspace.root,
                               timeout=int(verify.get("timeout_s", 300)))
            ok, detail = _check_success(verify.get("success_when"), completed)
            return ok, f"`{command}` → {detail}"

        # 2. Assertion over a value already in scope.
        if verify.get("assert"):
            from .builtins.evaluators import aggregate

            target = _render_text(str(verify.get("value", "{{ last_output }}")), scope)
            results = []
            for assertion in verify["assert"]:
                evaluator = self.registry.get("assay.evaluators", assertion["type"])
                results.append(evaluator.evaluate(target, assertion=assertion, context=scope))
            summary = aggregate(results)
            failures = "; ".join(f["reason"] for f in summary.get("failures", []))
            return summary["passed"], failures or "all assertions passed"

        # 3. Model-graded verification. Weaker; named explicitly so the file admits it.
        if verify.get("run"):
            artifact = self.store.get(verify["run"])
            result = self.runtime.run(artifact, scope, model=model)
            text = result.text.strip()
            passed = bool(re.match(r"^\s*(pass|yes|true|ok)\b", text, re.IGNORECASE))
            return passed, f"model-graded: {text[:200]}"

        return None, "verification block present but empty"

    # -- state -------------------------------------------------------------

    def _state_path(self, config: dict, loop: PromptFile, variables: dict) -> Path | None:
        state = config.get("state")
        if not state:
            return None
        raw = state.get("path") or ".assay/state/{{ loop_id }}.json"
        rendered = _render_text(raw, {**variables, "loop_id": loop.id.replace("/", "_")})
        return (self.workspace.root / rendered).resolve()

    def _load_state(self, config: dict, loop: PromptFile, variables: dict) -> dict:
        path = self._state_path(config, loop, variables)
        if path and path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("could not read loop state at %s: %s", path, exc)
        return {}

    def _save_state(self, config: dict, loop: PromptFile, variables: dict, state: dict) -> None:
        path = self._state_path(config, loop, variables)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("could not write loop state to %s: %s", path, exc)

    # -- budget ------------------------------------------------------------

    def _budget_exceeded(self, run: LoopRun, budget: dict, elapsed: float) -> str:
        if budget.get("cost_usd") is not None and run.cost_usd >= float(budget["cost_usd"]):
            return f"cost ${run.cost_usd:.4f} reached budget ${float(budget['cost_usd']):.4f}"
        if budget.get("wallclock_s") is not None and elapsed >= float(budget["wallclock_s"]):
            return f"{elapsed:.1f}s reached budget {budget['wallclock_s']}s"
        if budget.get("cycles") is not None and run.cycle_count >= int(budget["cycles"]):
            return f"{run.cycle_count} cycles reached budget {budget['cycles']}"
        return ""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _shell(command: str, *, cwd: Path, timeout: int) -> dict:
    try:
        completed = subprocess.run(command, shell=True, cwd=cwd, capture_output=True,
                                   text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "output": f"timed out after {timeout}s"}
    except Exception as exc:
        return {"exit_code": 1, "output": f"{type(exc).__name__}: {exc}"}
    return {
        "exit_code": completed.returncode,
        "output": (completed.stdout or "") + (completed.stderr or ""),
    }


def _check_success(condition: dict | None, completed: dict) -> tuple[bool, str]:
    condition = condition or {"type": "exit_code", "value": 0}
    kind = condition.get("type", "exit_code")
    value = condition.get("value", 0)
    output = completed["output"]

    if kind == "exit_code":
        ok = completed["exit_code"] == int(value)
        return ok, f"exit {completed['exit_code']} (wanted {value})"
    if kind == "output_contains":
        ok = str(value) in output
        return ok, f"output {'contains' if ok else 'does not contain'} {value!r}"
    if kind == "output_not_contains":
        ok = str(value) not in output
        return ok, f"output {'omits' if ok else 'contains'} {value!r}"
    if kind == "output_matches":
        ok = re.search(str(value), output) is not None
        return ok, f"output {'matches' if ok else 'does not match'} /{value}/"
    return False, f"unknown success_when type {kind!r}"


def _render_text(template: str, scope: dict) -> str:
    """Minimal ``{{ name }}`` substitution.

    Deliberately not the full Jinja2 renderer: loop plumbing substitutes identifiers
    into commands and paths, and a template language with logic in that position is an
    injection surface, not a feature.
    """
    def substitute(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(scope.get(key, ""))

    return re.sub(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}", substitute, template)


def _render_mapping(mapping: dict, scope: dict) -> dict:
    return {
        key: _render_text(value, scope) if isinstance(value, str) else value
        for key, value in mapping.items()
    }


def _cycle_signature(cycle: CycleResult) -> str:
    """Stable fingerprint of what a cycle actually did and produced.

    Used to detect a loop that repeats itself. Deliberately based on step ids plus
    outputs rather than on timing or cost, so an identical re-run is recognised even
    when it took a different number of milliseconds.
    """
    import hashlib

    parts = []
    for outcome in cycle.step_results:
        parts.append(str(outcome.get("id", "")))
        parts.append(str(outcome.get("output", ""))[:500])
        parts.append(str(outcome.get("failed", False)))
    if not parts:
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _step_route_key(step: dict) -> str:
    return str(step.get("run") or step.get("id") or "step")


def _find_handoff_cycle(route: list[str]) -> list[str]:
    """Return the first repeated route segment A→…→A, excluding adjacent repeats."""
    last_seen: dict[str, int] = {}
    for index, target in enumerate(route):
        previous = last_seen.get(target)
        if previous is not None and index - previous >= 2:
            return route[previous:index + 1]
        last_seen[target] = index
    return []


def _serialisable(value: Any) -> bool:
    try:
        json.dumps(value, default=str)
        return True
    except Exception:
        return False


def _synthetic_trajectory(run: LoopRun):
    """Flatten a loop run into a trajectory-shaped view.

    Lets trajectory assertions (``tool_called``, ``verified``, ``budget_under``) work on
    loops as well as harnesses, so one assertion vocabulary covers both.
    """
    from .contracts import Step, ToolCall, ToolResult, Trajectory

    trajectory = Trajectory(harness_id=run.loop_id, goal=run.goal, run_id=run.run_id)
    for cycle in run.cycles:
        step = Step(index=cycle.index)
        for outcome in cycle.step_results:
            name = outcome.get("run") or outcome.get("id") or "step"
            call = ToolCall(name=name, arguments={})
            step.tool_calls.append(call)
            step.tool_results.append(ToolResult(
                call=call, content=str(outcome.get("output", "")),
                is_error=bool(outcome.get("failed")),
            ))
            for tool in outcome.get("tool_calls") or []:
                inner = ToolCall(name=tool, arguments={})
                step.tool_calls.append(inner)
                step.tool_results.append(ToolResult(call=inner, content=""))
        trajectory.steps.append(step)

    trajectory.cost_usd = run.cost_usd
    trajectory.wallclock_s = run.wallclock_s
    trajectory.status = "completed" if run.goal_met else run.status
    trajectory.stop_reason = run.stop_reason
    trajectory.verified = run.cycles[-1].verified if run.cycles else None
    trajectory.verification_detail = run.cycles[-1].verification_detail if run.cycles else ""
    if run.cycles and run.cycles[-1].step_results:
        trajectory.output = str(run.cycles[-1].step_results[-1].get("output", ""))
    return trajectory
