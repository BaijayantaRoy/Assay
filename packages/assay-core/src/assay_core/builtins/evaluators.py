"""Built-in evaluators (``assay.evaluators``).

Each evaluator scores one output against one assertion and returns an
:class:`~assay_core.contracts.EvalResult`. Deterministic evaluators run offline;
``llm_judge`` delegates to a provider through the runtime it is handed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..contracts import CONTRACT_VERSION, EvalResult


def _weight(assertion: dict) -> float:
    try:
        return float(assertion.get("weight", 1))
    except (TypeError, ValueError):
        return 1.0


def _result(evaluator: str, passed: bool, assertion: dict, reason: str, **details) -> EvalResult:
    return EvalResult(
        passed=passed, score=1.0 if passed else 0.0, evaluator=evaluator,
        reason=reason, weight=_weight(assertion), details=details,
    )


class _Base:
    id = "base"
    contract_version = CONTRACT_VERSION

    def evaluate(self, output: str, *, assertion: dict, context: dict | None = None) -> EvalResult:
        raise NotImplementedError


class ContainsEvaluator(_Base):
    id = "contains"

    def evaluate(self, output, *, assertion, context=None):
        needle = str(assertion.get("value", ""))
        hay, found = (output, needle)
        if assertion.get("ignore_case", True):
            hay, found = output.lower(), needle.lower()
        ok = found in hay
        return _result(self.id, ok, assertion,
                       "found" if ok else f"expected to contain {needle!r}")


class NotEmptyEvaluator(_Base):
    """The output is not blank.

    The weakest useful assertion, and the right default for a starter prompt: it proves
    the template rendered and the provider answered, without pretending to check quality.
    Whitespace counts as empty — a response of three newlines is not an answer.

    ``min_length`` raises the bar when a one-word reply would obviously be wrong.
    """

    id = "not_empty"

    def evaluate(self, output, *, assertion, context=None):
        text = (output or "").strip()
        minimum = int(assertion.get("min_length", 1) or 1)
        ok = len(text) >= minimum
        if ok:
            reason = f"{len(text)} characters"
        elif not text:
            reason = "output was empty or whitespace only"
        else:
            reason = f"output was {len(text)} characters, wanted at least {minimum}"
        return _result(self.id, ok, assertion, reason)


class NotContainsEvaluator(_Base):
    id = "not_contains"

    def evaluate(self, output, *, assertion, context=None):
        needle = str(assertion.get("value", ""))
        hay, found = (output, needle)
        if assertion.get("ignore_case", True):
            hay, found = output.lower(), needle.lower()
        ok = found not in hay
        return _result(self.id, ok, assertion,
                       "absent" if ok else f"expected NOT to contain {needle!r}")


class EqualsEvaluator(_Base):
    id = "equals"

    def evaluate(self, output, *, assertion, context=None):
        expected = str(assertion.get("value", ""))
        left, right = output.strip(), expected.strip()
        if assertion.get("ignore_case", False):
            left, right = left.lower(), right.lower()
        ok = left == right
        return _result(self.id, ok, assertion, "exact match" if ok else "output differs")


class RegexEvaluator(_Base):
    id = "regex"

    def evaluate(self, output, *, assertion, context=None):
        pattern = str(assertion.get("value", ""))
        flags = re.IGNORECASE if assertion.get("ignore_case", False) else 0
        try:
            ok = re.search(pattern, output, flags) is not None
        except re.error as exc:
            return _result(self.id, False, assertion, f"invalid regex: {exc}")
        return _result(self.id, ok, assertion, "matched" if ok else f"no match for /{pattern}/")


class JsonValidEvaluator(_Base):
    id = "json_valid"

    def evaluate(self, output, *, assertion, context=None):
        try:
            json.loads(_strip_fence(output))
            return _result(self.id, True, assertion, "valid JSON")
        except json.JSONDecodeError as exc:
            return _result(self.id, False, assertion, f"invalid JSON: {exc}")


class JsonSchemaEvaluator(_Base):
    """Validates output against ``assertion.value`` or the prompt's ``output.schema``."""

    id = "json_schema"

    def evaluate(self, output, *, assertion, context=None):
        import jsonschema

        schema = assertion.get("value") or (context or {}).get("output_schema")
        if not schema:
            return _result(self.id, False, assertion, "no schema available to validate against")
        try:
            payload = json.loads(_strip_fence(output))
        except json.JSONDecodeError as exc:
            return _result(self.id, False, assertion, f"output is not JSON: {exc}")
        errors = [
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(payload)
        ]
        return _result(self.id, not errors, assertion,
                       "conforms to schema" if not errors else "; ".join(errors[:3]),
                       errors=errors)


class CostUnderEvaluator(_Base):
    id = "cost_under"

    def evaluate(self, output, *, assertion, context=None):
        limit = float(assertion.get("value", 0))
        actual = float((context or {}).get("cost_usd", 0.0))
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"${actual:.6f} {'<=' if ok else '>'} ${limit:.6f}",
                       actual=actual, limit=limit)


class LatencyUnderEvaluator(_Base):
    id = "latency_under"

    def evaluate(self, output, *, assertion, context=None):
        limit = float(assertion.get("value", 0))
        actual = float((context or {}).get("latency_ms", 0))
        ok = actual <= limit
        return _result(self.id, ok, assertion,
                       f"{actual:.0f}ms {'<=' if ok else '>'} {limit:.0f}ms",
                       actual=actual, limit=limit)


JUDGE_TEMPLATE = """You are a strict evaluator. Score the RESPONSE against the CRITERIA.

CRITERIA:
{criteria}

{reference_block}RESPONSE:
{response}

Reply with JSON only: {{"score": <0.0-1.0>, "reason": "<one sentence>"}}"""


class LLMJudgeEvaluator(_Base):
    """Model-graded assertion.

    Needs a callable in ``context['judge']`` with signature ``(prompt: str) -> str``.
    The runtime supplies it; that indirection keeps this evaluator provider-agnostic
    and unit-testable without network access.
    """

    id = "llm_judge"

    def evaluate(self, output, *, assertion, context=None):
        context = context or {}
        judge = context.get("judge")
        criteria = assertion.get("value") or assertion.get("criteria") or "Is the response correct and helpful?"
        threshold = float(assertion.get("threshold", 0.7))
        if not callable(judge):
            return EvalResult(
                passed=False, score=0.0, evaluator=self.id, weight=_weight(assertion),
                reason="no judge callable supplied by the runtime",
            )
        reference = context.get("expected_output")
        prompt = JUDGE_TEMPLATE.format(
            criteria=criteria,
            reference_block=f"REFERENCE ANSWER:\n{reference}\n\n" if reference else "",
            response=output,
        )
        try:
            verdict = json.loads(_strip_fence(judge(prompt)))
            score = max(0.0, min(1.0, float(verdict.get("score", 0))))
            reason = str(verdict.get("reason", ""))
        except Exception as exc:
            return EvalResult(passed=False, score=0.0, evaluator=self.id,
                              weight=_weight(assertion), reason=f"judge failed: {exc}")
        return EvalResult(
            passed=score >= threshold, score=score, evaluator=self.id,
            weight=_weight(assertion), reason=reason,
            details={"threshold": threshold, "criteria": criteria},
        )


def _strip_fence(text: str) -> str:
    """Tolerate ```json fenced output, which most models emit despite instructions."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def aggregate(results: list[EvalResult], *, unverified: int = 0) -> dict[str, Any]:
    """Weighted roll-up used by ``assay test`` and the evaluation API.

    ``None`` is deliberate: zero usable assertions are not a perfect pass or a zero
    score.  ``unverified`` lets an artifact-level roll-up retain that state when some
    cases had assertions and other cases did not.
    """
    if not results:
        return {
            "passed": None,
            "score": None,
            "usable": False,
            "total": 0,
            "failed": 0,
            "unverified": unverified,
            "failures": [],
        }
    total_weight = sum(r.weight for r in results) or 1.0
    score = sum(r.score * r.weight for r in results) / total_weight
    failed = [r for r in results if not r.passed]
    return {
        "passed": False if failed else (None if unverified else True),
        "score": round(score, 4),
        "usable": True,
        "total": len(results),
        "failed": len(failed),
        "unverified": unverified,
        "failures": [{"evaluator": r.evaluator, "reason": r.reason} for r in failed],
    }
