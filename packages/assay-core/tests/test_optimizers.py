"""Reflective optimization is evidence-based and cannot promote itself."""

from __future__ import annotations

import json

import pytest

from assay_core import PromptFile
from assay_core.builtins.optimizers import ReflectiveRewriteOptimizer
from assay_core.errors import OptimizationError


def _prompt() -> PromptFile:
    return PromptFile(
        data={
            "promptfile": 1,
            "id": "support/greet",
            "version": 3,
            "engine": {"template": "jinja2"},
            "unknown_future_field": {"keep": True},
        },
        body="Greet {{ name }} briefly.",
    )


def test_reflective_optimizer_builds_a_versioned_candidate_from_failure_evidence():
    seen = []

    def rewrite(request):
        seen.append(request)
        return json.dumps({
            "body": "Say Hello to {{ name }} in one short sentence.",
            "rationale": "Makes the required greeting explicit without hard-coding a name.",
        }), 0.012

    result = ReflectiveRewriteOptimizer().optimize(
        _prompt(),
        dataset=[{
            "id": "hello",
            "results": [{
                "evaluator": "contains", "passed": False, "score": 0.0,
                "reason": "output did not contain 'Hello'",
            }],
        }],
        budget={"rewrite": rewrite},
    )
    candidate = result["candidate"]

    assert seen and "MEASURED FAILURES" in seen[0]
    assert "did not contain" in seen[0]
    assert candidate.body == "Say Hello to {{ name }} in one short sentence."
    assert candidate.version == 4
    assert candidate.data["unknown_future_field"] == {"keep": True}
    assert candidate.data["provenance"]["derived_from"] == "support/greet@3"
    assert result["rewrite_cost_usd"] == 0.012


def test_optimizer_rejects_non_json_instead_of_evaluating_instruction_echo():
    with pytest.raises(OptimizationError, match="invalid JSON"):
        ReflectiveRewriteOptimizer().optimize(
            _prompt(), dataset=[], budget={"rewrite": lambda request: "[user] " + request}
        )


def test_optimizer_rejects_candidate_that_drops_a_template_variable():
    response = json.dumps({"body": "Say Hello.", "rationale": "Shorter."})
    with pytest.raises(OptimizationError, match="removed template variable.*name"):
        ReflectiveRewriteOptimizer().optimize(
            _prompt(), dataset=[], budget={"rewrite": lambda request: response}
        )
