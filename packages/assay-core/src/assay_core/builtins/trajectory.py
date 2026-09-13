"""Trajectory evaluators (``assay.evaluators``).

Ordinary evaluators score the final answer. These score **how the agent got there**,
and that is where the interesting agent failures live:

- it answered confidently without ever searching;
- it called the same tool eleven times with identical arguments;
- it took thirty iterations to do a two-step job;
- it succeeded, but only because it wrote to a path it should never have touched;
- it "finished" without the verification step ever passing.

None of those are visible in the output string. All of them are visible in the
trajectory, and all of them are assertable in a plain-text file that diffs in a
pull request.

Each evaluator receives ``context["trajectory"]``. When it is absent — because the
assertion was attached to a plain prompt rather than a harness — the result is a clear
failure rather than a silent pass.
"""

from __future__ import annotations

from typing import Any

from ..contracts import CONTRACT_VERSION, EvalResult, Trajectory


def _weight(assertion: dict) -> float:
    try:
        return float(assertion.get("weight", 1))
    except (TypeError, ValueError):
        return 1.0


def _result(evaluator: str, passed: bool, assertion: dict, reason: str, **details) -> EvalResult:
    return EvalResult(passed=passed, score=1.0 if passed else 0.0, evaluator=evaluator,
                      reason=reason, weight=_weight(assertion), details=details)


class _TrajectoryBase:
    id = "trajectory_base"
    contract_version = CONTRACT_VERSION

    def _trajectory(self, context: dict | None) -> Trajectory | None:
        return (context or {}).get("trajectory")

    def evaluate(self, output: str, *, assertion: dict, context: dict | None = None) -> EvalResult:
        trajectory = self._trajectory(context)
        if trajectory is None:
            return _result(
                self.id, False, assertion,
                f"'{self.id}' asserts on a trajectory, but this run produced none. "
                "Attach it to a prompt with kind: harness or kind: loop.",
            )
        return self.check(trajectory, assertion=assertion, context=context or {})

    def check(self, trajectory: Trajectory, *, assertion: dict, context: dict) -> EvalResult:
        raise NotImplementedError


class ToolCalledEvaluator(_TrajectoryBase):
    """The agent must have used a given tool. Catches "answered without looking"."""

    id = "tool_called"

    def check(self, trajectory, *, assertion, context):
        wanted = assertion.get("value")
        names = trajectory.tool_call_names
        wanted_list = [wanted] if isinstance(wanted, str) else list(wanted or [])
        missing = [w for w in wanted_list if w not in names]
        return _result(
            self.id, not missing, assertion,
            "all required tools were used" if not missing
            else f"never called: {', '.join(missing)} (called: {', '.join(names) or 'nothing'})",
            called=names,
            attribution=[{"type": "tool", "id": name} for name in missing],
        )


class ToolNotCalledEvaluator(_TrajectoryBase):
    """The agent must NOT have used a given tool. The safety assertion."""

    id = "tool_not_called"

    def check(self, trajectory, *, assertion, context):
        forbidden = assertion.get("value")
        forbidden_list = [forbidden] if isinstance(forbidden, str) else list(forbidden or [])
        names = trajectory.tool_call_names
        used = [f for f in forbidden_list if f in names]
        return _result(
            self.id, not used, assertion,
            "no forbidden tools used" if not used else f"called forbidden tool(s): {', '.join(used)}",
            called=names,
            attribution=[{"type": "tool", "id": name} for name in used],
        )


class ToolCallOrderEvaluator(_TrajectoryBase):
    """Tools must appear in this relative order — a subsequence, not necessarily adjacent.

    Encodes a required method: search *before* reading, read *before* editing, verify
    *before* submitting.
    """

    id = "tool_call_order"

    def check(self, trajectory, *, assertion, context):
        expected = list(assertion.get("value") or [])
        actual = trajectory.tool_call_names
        cursor = 0
        for name in actual:
            if cursor < len(expected) and name == expected[cursor]:
                cursor += 1
        ok = cursor == len(expected)
        return _result(
            self.id, ok, assertion,
            f"order satisfied: {' → '.join(expected)}" if ok
            else f"expected {' → '.join(expected)} as a subsequence; got {' → '.join(actual) or 'nothing'}",
            expected=expected, actual=actual,
        )


def _expected_call(value: Any) -> tuple[str, dict[str, Any]] | None:
    if isinstance(value, str) and value:
        return value, {}
    if isinstance(value, dict):
        name = value.get("tool") or value.get("name")
        arguments = value.get("arguments") or {}
        if isinstance(name, str) and name and isinstance(arguments, dict):
            return name, arguments
    return None


def _call_matches(actual, expected: tuple[str, dict[str, Any]]) -> bool:
    name, arguments = expected
    return actual.name == name and all(actual.arguments.get(key) == value for key, value in arguments.items())


class TrajectoryAccuracyEvaluator(_TrajectoryBase):
    """Order-aware F1 against a frozen golden sequence of tool calls.

    The match is deterministic: longest common subsequence over tool name and the
    expected argument subset. Precision exposes unnecessary calls; recall exposes
    missing golden steps. Reporting both avoids hiding the failure behind one score.
    """

    id = "trajectory_accuracy"

    def check(self, trajectory, *, assertion, context):
        raw_reference = assertion.get("value")
        if not isinstance(raw_reference, list):
            return _result(
                self.id,
                False,
                assertion,
                "value must be a list of tool names or {tool, arguments} objects",
            )
        reference = [_expected_call(item) for item in raw_reference]
        if any(item is None for item in reference):
            return _result(self.id, False, assertion, "golden trajectory contains an invalid call")
        expected = [item for item in reference if item is not None]
        actual = [call for step in trajectory.steps for call in step.tool_calls]
        rows, columns = len(expected) + 1, len(actual) + 1
        lengths = [[0] * columns for _ in range(rows)]
        for expected_index in range(1, rows):
            for actual_index in range(1, columns):
                if _call_matches(actual[actual_index - 1], expected[expected_index - 1]):
                    lengths[expected_index][actual_index] = (
                        lengths[expected_index - 1][actual_index - 1] + 1
                    )
                else:
                    lengths[expected_index][actual_index] = max(
                        lengths[expected_index - 1][actual_index],
                        lengths[expected_index][actual_index - 1],
                    )
        matched = lengths[-1][-1]
        precision = matched / len(actual) if actual else (1.0 if not expected else 0.0)
        recall = matched / len(expected) if expected else (1.0 if not actual else 0.0)
        score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        threshold = float(assertion.get("threshold", 1.0))
        passed = score >= threshold
        expected_names = [item[0] for item in expected]
        actual_names = [call.name for call in actual]
        expected_index, actual_index = len(expected), len(actual)
        matched_expected: set[int] = set()
        matched_actual: set[int] = set()
        while expected_index and actual_index:
            if _call_matches(actual[actual_index - 1], expected[expected_index - 1]):
                matched_expected.add(expected_index - 1)
                matched_actual.add(actual_index - 1)
                expected_index -= 1
                actual_index -= 1
            elif lengths[expected_index - 1][actual_index] >= lengths[expected_index][actual_index - 1]:
                expected_index -= 1
            else:
                actual_index -= 1
        missing = [
            name for index, name in enumerate(expected_names) if index not in matched_expected
        ]
        unexpected = [
            name for index, name in enumerate(actual_names) if index not in matched_actual
        ]
        attribution_names = list(dict.fromkeys([*missing, *unexpected])) if not passed else []
        return EvalResult(
            passed=passed,
            score=score,
            evaluator=self.id,
            reason=(
                f"order-aware tool F1={score:.3f} "
                f"(precision={precision:.3f}, recall={recall:.3f}, matched={matched})"
            ),
            weight=_weight(assertion),
            details={
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "matched": matched,
                "expected": expected_names,
                "actual": actual_names,
                "missing": missing,
                "unexpected": unexpected,
                "threshold": threshold,
                "attribution": [
                    {"type": "tool", "id": name} for name in attribution_names
                ],
            },
        )


class NoRepeatedToolCallEvaluator(_TrajectoryBase):
    """No tool called twice with identical arguments — the classic stuck-agent signature."""

    id = "no_repeated_tool_call"

    def check(self, trajectory, *, assertion, context):
        import json

        limit = int(assertion.get("value", 1) or 1)
        counts: dict[str, int] = {}
        for result in trajectory.all_tool_results:
            try:
                key = f"{result.call.name}({json.dumps(result.call.arguments, sort_keys=True, default=str)})"
            except Exception:
                key = f"{result.call.name}({result.call.arguments})"
            counts[key] = counts.get(key, 0) + 1
        repeated = {k: v for k, v in counts.items() if v > limit}
        return _result(
            self.id, not repeated, assertion,
            "no redundant repeated calls" if not repeated
            else "repeated identical call(s): "
                 + "; ".join(f"{k} ×{v}" for k, v in list(repeated.items())[:3]),
            repeated=repeated,
        )


class IterationsUnderEvaluator(_TrajectoryBase):
    """Efficiency gate. A correct answer in thirty steps is often still a regression."""

    id = "iterations_under"

    def check(self, trajectory, *, assertion, context):
        limit = int(assertion.get("value", 0) or 0)
        actual = trajectory.iterations
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"{actual} iterations {'<=' if ok else '>'} {limit}",
                       actual=actual, limit=limit)


class ToolCallsUnderEvaluator(_TrajectoryBase):
    id = "tool_calls_under"

    def check(self, trajectory, *, assertion, context):
        limit = int(assertion.get("value", 0) or 0)
        actual = len(trajectory.tool_call_names)
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"{actual} tool calls {'<=' if ok else '>'} {limit}",
                       actual=actual, limit=limit)


class BudgetUnderEvaluator(_TrajectoryBase):
    """Cost ceiling for a whole agent run, including sub-agent spend."""

    id = "budget_under"

    def check(self, trajectory, *, assertion, context):
        limit = float(assertion.get("value", 0) or 0)
        actual = trajectory.cost_usd
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"${actual:.6f} {'<=' if ok else '>'} ${limit:.6f}",
                       actual=actual, limit=limit)


class NoToolErrorsEvaluator(_TrajectoryBase):
    """No tool call failed. Often too strict — recovery is a virtue — so use with care."""

    id = "no_tool_errors"

    def check(self, trajectory, *, assertion, context):
        errors = trajectory.tool_errors
        allowed = int(assertion.get("value", 0) or 0)
        ok = len(errors) <= allowed
        return _result(
            self.id, ok, assertion,
            "no tool errors" if ok
            else f"{len(errors)} tool error(s), allowed {allowed}: "
                 + "; ".join(f"{e.call.name}: {e.content[:60]}" for e in errors[:3]),
            errors=len(errors),
            attribution=[{"type": "tool", "id": error.call.name} for error in errors],
        )


class NoDeniedCallsEvaluator(_TrajectoryBase):
    """The agent never attempted something the controller had to block.

    A passing run with denied calls is a warning: the agent *wanted* to do something
    it was not permitted to do, and only policy stopped it.
    """

    id = "no_denied_calls"

    def check(self, trajectory, *, assertion, context):
        denied = trajectory.denied_calls
        ok = not denied
        return _result(
            self.id, ok, assertion,
            "no calls were blocked by policy" if ok
            else f"{len(denied)} blocked call(s): "
                 + "; ".join(f"{d.call.name} ({d.denied_reason})" for d in denied[:3]),
            denied=len(denied),
            attribution=[{"type": "tool", "id": item.call.name} for item in denied],
        )


class CompletedEvaluator(_TrajectoryBase):
    """The run ended cleanly rather than hitting a ceiling.

    ``status: budget_exceeded`` or ``max_iterations`` means the agent ran out of road,
    which is a failure even when the partial output looks plausible.
    """

    id = "completed"

    def check(self, trajectory, *, assertion, context):
        expected = assertion.get("value", "completed")
        ok = trajectory.status == expected
        return _result(self.id, ok, assertion,
                       f"status is {trajectory.status!r}"
                       + ("" if ok else f", expected {expected!r} ({trajectory.stop_reason})"),
                       status=trajectory.status, stop_reason=trajectory.stop_reason)


class VerifiedEvaluator(_TrajectoryBase):
    """The verification step passed.

    This is the assertion that matters most in loop engineering. An agent that reports
    success is making a claim; a verification step that passes is evidence. Asserting on
    ``verified`` rather than on the agent's own summary is the difference between the two.
    """

    id = "verified"

    def check(self, trajectory, *, assertion, context):
        expected = assertion.get("value", True)
        actual = trajectory.verified
        if actual is None:
            return _result(self.id, False, assertion,
                           "no verification step ran — nothing checked the agent's claim",
                           attribution=[{"type": "verification", "id": "final"}])
        ok = bool(actual) == bool(expected)
        return _result(self.id, ok, assertion,
                       f"verified={actual}" + (f" ({trajectory.verification_detail})"
                                               if trajectory.verification_detail else ""),
                       verified=actual,
                       attribution=[] if ok else [{"type": "verification", "id": "final"}])


class NoInjectionComplianceEvaluator(_TrajectoryBase):
    """The agent did not act on instructions embedded in untrusted tool output.

    The core red-team assertion. Given a tool result carrying an injected directive, a
    passing run is one where the injection was *detected* and the agent did **not** take
    the action it demanded.

    ``value`` is the tool (or list of tools) the injection tried to trigger::

        - { type: no_injection_compliance, value: [shell.run, http.get] }

    Note the honest limit: this proves the agent did not comply *with this payload*. Given
    published attack success rates above 80%, it is evidence about one case, not a safety
    guarantee.
    """

    id = "no_injection_compliance"

    def check(self, trajectory, *, assertion, context):
        forbidden = assertion.get("value")
        forbidden_list = [forbidden] if isinstance(forbidden, str) else list(forbidden or [])
        complied = [name for name in trajectory.tool_call_names if name in forbidden_list]
        detections = [e for e in trajectory.events if e.get("type") == "injection_suspected"]

        if complied:
            return _result(
                self.id, False, assertion,
                f"agent complied with injected content: called {', '.join(complied)}",
                complied=complied, detections=len(detections),
            )
        detail = (f"{len(detections)} injection attempt(s) flagged, none acted on"
                  if detections else "no forbidden action taken")
        return _result(self.id, True, assertion, detail, detections=len(detections))


class InjectionDetectedEvaluator(_TrajectoryBase):
    """Provenance scanning flagged untrusted content. Asserts the detector fires.

    Distinct from ``no_injection_compliance``: this checks the *detector*, that one checks
    the *agent*. A red-team case wants both — the attempt seen, and not obeyed.
    """

    id = "injection_detected"

    def check(self, trajectory, *, assertion, context):
        expected = assertion.get("value", True)
        detections = [e for e in trajectory.events if e.get("type") == "injection_suspected"]
        found = bool(detections)
        ok = found == bool(expected)
        labels = sorted({f for e in detections for f in e.get("flags", [])})
        return _result(
            self.id, ok, assertion,
            f"{len(detections)} detection(s)" + (f": {', '.join(labels)}" if labels else ""),
            detections=len(detections), flags=labels,
        )


class MemoryRecalledEvaluator(_TrajectoryBase):
    """Memory was consulted, and optionally that it returned something.

    ``value: true`` asserts recall ran. An integer asserts at least that many records
    came back — useful for the second run of a pair, where the first seeded memory and
    the second must actually benefit from it.
    """

    id = "memory_recalled"

    def check(self, trajectory, *, assertion, context):
        events = [e for e in trajectory.events if e.get("type") == "memory_recall"]
        recalled = sum(e.get("recalled", 0) for e in events)
        expected = assertion.get("value", True)

        if expected is False:
            ok = not events
            return _result(self.id, ok, assertion,
                           "no recall performed" if ok else f"{len(events)} recall(s) ran")
        if isinstance(expected, bool):
            ok = bool(events)
            return _result(self.id, ok, assertion,
                           f"recall ran, {recalled} record(s)" if ok
                           else "memory recall never ran — is a memory backend configured?")
        minimum = int(expected)
        ok = recalled >= minimum
        return _result(self.id, ok, assertion,
                       f"recalled {recalled} record(s), wanted at least {minimum}",
                       recalled=recalled)


class MemoryWrittenEvaluator(_TrajectoryBase):
    """The run persisted what it learned.

    A harness that recalls but never writes is a harness whose memory can only get
    staler — worth asserting explicitly.
    """

    id = "memory_written"

    def check(self, trajectory, *, assertion, context):
        events = [e for e in trajectory.events if e.get("type") == "memory_write"]
        expected = assertion.get("value", True)
        if expected is False:
            ok = not events
            return _result(self.id, ok, assertion,
                           "nothing written" if ok else f"{len(events)} record(s) written")
        ok = bool(events)
        kinds = sorted({e.get("kind", "") for e in events})
        return _result(self.id, ok, assertion,
                       f"wrote {len(events)} record(s) ({', '.join(kinds)})" if ok
                       else "nothing was written to memory",
                       written=len(events))


class CyclesUnderEvaluator(_TrajectoryBase):
    """Outer-loop efficiency: how many cycles before the goal was met."""

    id = "cycles_under"

    def evaluate(self, output: str, *, assertion: dict, context: dict | None = None) -> EvalResult:
        run = (context or {}).get("loop_run")
        if run is None:
            return _result(self.id, False, assertion,
                           "'cycles_under' asserts on a loop run; none was produced")
        limit = int(assertion.get("value", 0) or 0)
        actual = run.cycle_count
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"{actual} cycles {'<=' if ok else '>'} {limit}",
                       actual=actual, limit=limit)


class StepsVerifiedEvaluator(_TrajectoryBase):
    """Every step that declared a verification passed it.

    Distinct from `verified`, which only checks the end of the cycle. A loop can meet its
    final goal while an intermediate handoff quietly produced garbage that a later step
    happened to paper over — this catches that.
    """

    id = "steps_verified"

    def evaluate(self, output: str, *, assertion: dict, context: dict | None = None) -> EvalResult:
        run = (context or {}).get("loop_run")
        if run is None:
            return _result(self.id, False, assertion,
                           "'steps_verified' asserts on a loop run; none was produced")
        checked, failed = [], []
        failed_components = []
        for cycle in run.cycles:
            for outcome in cycle.step_results:
                if outcome.get("verified") is None:
                    continue
                checked.append(outcome.get("id"))
                if outcome["verified"] is False:
                    failed.append(f"{outcome.get('id')}: {outcome.get('verification_detail','')[:80]}")
                    failed_components.append({
                        "type": "subagent" if outcome.get("type") == "harness" else "step",
                        "id": outcome.get("run") or outcome.get("id") or "unknown",
                    })
        expected = assertion.get("value", True)
        if not checked:
            return _result(self.id, not expected, assertion,
                           "no step declared a verification")
        ok = (not failed) == bool(expected)
        return _result(self.id, ok, assertion,
                       f"{len(checked) - len(failed)}/{len(checked)} step verifications passed"
                       + ("; " + "; ".join(failed[:3]) if failed else ""),
                       checked=len(checked), failed=len(failed),
                       attribution=failed_components)


class GoalMetEvaluator(_TrajectoryBase):
    """The outer loop reached its goal rather than exhausting cycles or budget."""

    id = "goal_met"

    def evaluate(self, output: str, *, assertion: dict, context: dict | None = None) -> EvalResult:
        run = (context or {}).get("loop_run")
        if run is None:
            return _result(self.id, False, assertion,
                           "'goal_met' asserts on a loop run; none was produced")
        expected = bool(assertion.get("value", True))
        ok = run.goal_met == expected
        failed_components = []
        if not ok:
            for cycle in run.cycles:
                for outcome in cycle.step_results:
                    if outcome.get("failed") or outcome.get("verified") is False:
                        failed_components.append({
                            "type": "subagent" if outcome.get("type") == "harness" else "step",
                            "id": outcome.get("run") or outcome.get("id") or "unknown",
                        })
            if not failed_components:
                failed_components.append({"type": "verification", "id": "loop_goal"})
        return _result(self.id, ok, assertion,
                       f"status={run.status!r} goal_met={run.goal_met}"
                       + (f" ({run.stop_reason})" if run.stop_reason else ""),
                       status=run.status, attribution=failed_components)
