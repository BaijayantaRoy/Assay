"""Built-in controllers (``assay.controllers``).

Control is the fourth harness element, and the one that separates a demo from something
you can point at a real system. A controller is consulted *before* every tool call and
*before* every iteration, so a policy can stop a run rather than merely reporting on it
afterwards.

All controllers fail closed: an error while deciding is a denial, not an allowance.
"""

from __future__ import annotations

import fnmatch
from typing import Any

from ..contracts import CONTRACT_VERSION, GuardrailResult, ToolCall, Trajectory


def _allow(controller: str) -> GuardrailResult:
    return GuardrailResult(allowed=True, guardrail=controller)


def _deny(controller: str, reason: str, action: str = "block") -> GuardrailResult:
    return GuardrailResult(allowed=False, action=action, reason=reason, guardrail=controller)


class PolicyController:
    """The default. Enforces deny lists, approval gates and repetition limits.

    Configured from the ``control:`` block of a harness file:

    ```yaml
    control:
      deny: [shell.run, fs.write]        # never, regardless of anything else
      require_approval: [fs.write]       # needs an approver callback to proceed
      allow_shell: false
      allow_hosts: ["docs.example.com"]
      max_repeated_calls: 3              # same tool + same args
      max_consecutive_errors: 3
    ```
    """

    id = "policy"
    contract_version = CONTRACT_VERSION

    def before_tool(self, call: ToolCall, *, config: dict, context: dict) -> GuardrailResult:
        try:
            for pattern in config.get("deny") or []:
                if fnmatch.fnmatch(call.name, pattern):
                    return _deny(self.id, f"tool {call.name!r} is denied by control.deny")

            allow = config.get("allow_tools")
            if allow and not any(fnmatch.fnmatch(call.name, p) for p in allow):
                return _deny(self.id, f"tool {call.name!r} is not in control.allow_tools")

            needs_approval = [
                p for p in (config.get("require_approval") or [])
                if fnmatch.fnmatch(call.name, p)
            ]
            if needs_approval:
                approver = context.get("approver")
                trajectory: Trajectory | None = context.get("trajectory")
                actor = context.get("approver_identity") or ""
                if not callable(approver):
                    if trajectory is not None:
                        trajectory.events.append({
                            "type": "approval", "tool": call.name, "approved": False,
                            "actor": actor, "reason": "no approver configured",
                        })
                    return _deny(
                        self.id,
                        f"tool {call.name!r} requires approval but no approver is configured",
                    )
                raw_decision = approver(call)
                if isinstance(raw_decision, dict):
                    approved = bool(raw_decision.get("approved"))
                    actor = str(raw_decision.get("actor") or actor)
                    reason = str(raw_decision.get("reason") or "")
                else:
                    approved = bool(raw_decision)
                    reason = ""
                if trajectory is not None:
                    trajectory.events.append({
                        "type": "approval", "tool": call.name, "approved": approved,
                        "actor": actor or "unattributed", "reason": reason,
                    })
                if not approved:
                    suffix = f": {reason}" if reason else ""
                    return _deny(self.id, f"approval denied for {call.name!r}{suffix}")

            # Repetition is the signature failure of an agent that has lost the plot:
            # it calls the same tool with the same arguments and expects a new answer.
            limit = int(config.get("max_repeated_calls", 0) or 0)
            if limit:
                trajectory: Trajectory | None = context.get("trajectory")
                if trajectory is not None:
                    signature = (call.name, _freeze(call.arguments))
                    repeats = sum(
                        1 for r in trajectory.all_tool_results
                        if (r.call.name, _freeze(r.call.arguments)) == signature
                    )
                    if repeats >= limit:
                        return _deny(
                            self.id,
                            f"{call.name} already called {repeats}× with identical arguments; "
                            f"control.max_repeated_calls is {limit}",
                        )
            return _allow(self.id)
        except Exception as exc:  # fail closed
            return _deny(self.id, f"controller error, denying: {exc}")

    def before_iteration(self, trajectory: Trajectory, *, config: dict,
                         context: dict) -> GuardrailResult:
        try:
            limit = int(config.get("max_consecutive_errors", 0) or 0)
            if limit and trajectory.steps:
                streak = 0
                for step in reversed(trajectory.steps):
                    if not step.tool_results:
                        break
                    if all(r.is_error for r in step.tool_results):
                        streak += 1
                    else:
                        break
                if streak >= limit:
                    return _deny(
                        self.id,
                        f"{streak} consecutive iterations of only tool errors; "
                        f"control.max_consecutive_errors is {limit}",
                    )
            return _allow(self.id)
        except Exception as exc:
            return _deny(self.id, f"controller error, denying: {exc}")


class ReadOnlyController:
    """Blocks every tool that can mutate state.

    Useful for running an untrusted or newly authored harness against a real workspace
    to see what it *would* do. Pair with `assay agent run --dry-run`.
    """

    id = "read_only"
    contract_version = CONTRACT_VERSION

    MUTATING = ("fs.write", "shell.run", "*.write", "*.delete", "*.create", "*.update")

    def before_tool(self, call: ToolCall, *, config: dict, context: dict) -> GuardrailResult:
        extra = tuple(config.get("also_block") or ())
        for pattern in self.MUTATING + extra:
            if fnmatch.fnmatch(call.name, pattern):
                return _deny(self.id, f"{call.name} is blocked: harness is running read-only")
        return _allow(self.id)

    def before_iteration(self, trajectory, *, config, context) -> GuardrailResult:
        return _allow(self.id)


def _freeze(value: Any) -> str:
    """Stable string form of tool arguments, for repetition detection."""
    import json

    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:
        return str(value)
