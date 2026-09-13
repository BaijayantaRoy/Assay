from __future__ import annotations

import json

import pytest

from assay_core import PromptFile, Runtime, Workspace
from assay_core.contracts import EvalResult
from assay_core.errors import ValidationError
from assay_core.evaluation import (
    compare_eval_reports,
    failure_attribution,
    resolve_eval_cases,
    score_confidence_interval,
)


def _result(score: float, *, passed: bool | None = None) -> EvalResult:
    return EvalResult(
        passed=score >= 0.5 if passed is None else passed,
        score=score,
        evaluator="test",
    )


def test_dataset_cases_expand_relative_to_the_prompt_and_keep_base_assertions(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    prompt_path = prompts / "greet.prompt.md"
    dataset = prompts / "greet.dataset.jsonl"
    dataset.write_text(
        '\n'.join(
            [
                json.dumps({"id": "ada", "input": {"name": "Ada"}}),
                json.dumps(
                    {
                        "id": "grace",
                        "input": {"name": "Grace"},
                        "expected_output": "Hello Grace",
                        "assert": [{"type": "contains", "value": "Grace"}],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    prompt = PromptFile(
        data={"promptfile": 1, "id": "test/greet"},
        body="Hello {{name}}",
        path=prompt_path,
    )

    cases = resolve_eval_cases(
        prompt,
        [
            {
                "id": "dataset",
                "dataset": "greet.dataset.jsonl",
                "assert": [{"type": "not_empty"}],
            }
        ],
        workspace_root=tmp_path,
    )

    assert [case["id"] for case in cases] == ["dataset/ada", "dataset/grace"]
    assert cases[0]["assert"] == [{"type": "not_empty"}]
    assert cases[1]["assert"] == [
        {"type": "not_empty"},
        {"type": "contains", "value": "Grace"},
    ]
    assert cases[1]["expected_output"] == "Hello Grace"


def test_dataset_paths_cannot_escape_the_workspace(tmp_path):
    prompt = PromptFile(
        data={"promptfile": 1, "id": "test/greet"},
        path=tmp_path / "prompts" / "greet.prompt.md",
    )

    with pytest.raises(ValidationError, match="escapes the workspace"):
        resolve_eval_cases(
            prompt,
            [{"id": "bad", "dataset": "../../outside.jsonl"}],
            workspace_root=tmp_path,
        )


def test_dataset_rows_require_explicit_input_objects(tmp_path):
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text('{"id":"missing-input"}\n', encoding="utf-8")
    prompt = PromptFile(
        data={"promptfile": 1, "id": "test/greet"},
        path=tmp_path / "greet.prompt.md",
    )

    with pytest.raises(ValidationError, match="needs an input object"):
        resolve_eval_cases(
            prompt,
            [{"id": "bad", "dataset": "bad.jsonl"}],
            workspace_root=tmp_path,
        )


def test_score_interval_withholds_bounds_for_too_few_usable_cases():
    report = score_confidence_interval(
        [[_result(1.0)], [_result(0.0)]], unverified_cases=3
    )

    assert report["point"] == 0.5
    assert report["low"] is None and report["high"] is None
    assert report["reason"] == "fewer than three usable cases"
    assert report["excluded_unverified_cases"] == 3


def test_score_interval_is_a_seeded_case_cluster_bootstrap():
    groups = [[_result(1.0)], [_result(1.0)], [_result(0.0)], [_result(0.5)]]

    first = score_confidence_interval(groups, unverified_cases=0, resamples=300, seed=9)
    second = score_confidence_interval(groups, unverified_cases=0, resamples=300, seed=9)

    assert first == second
    assert first["method"] == "case-cluster percentile bootstrap"
    assert first["low"] <= first["point"] <= first["high"]
    assert first["low"] < first["high"]


def test_failure_attribution_groups_components_across_cases():
    tool_failure = EvalResult(
        passed=False,
        score=0,
        evaluator="tool_called",
        details={"attribution": [{"type": "tool", "id": "fs.read"}]},
    )
    output_failure = EvalResult(
        passed=False,
        score=0,
        evaluator="contains",
        reason="missing",
    )

    report = failure_attribution(
        [("one", [tool_failure, output_failure]), ("two", [tool_failure])]
    )

    assert report[0] == {
        "component_type": "tool",
        "component": "fs.read",
        "failure_count": 2,
        "cases": ["one", "two"],
        "evaluators": ["tool_called"],
    }
    assert report[1]["component_type"] == "output"
    assert report[1]["component"] == "final_output"


def test_runtime_evaluate_expands_dataset_and_reports_denominators(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    prompt_path = prompts / "greet.prompt.md"
    prompt_path.write_text(
        "---\npromptfile: 1\nid: test/greet\nmodel: {primary: echo/echo}\n"
        "evals:\n  - id: names\n    dataset: names.jsonl\n"
        "    assert: [{type: contains, value: Hello}]\n---\nHello {{name}}",
        encoding="utf-8",
    )
    (prompts / "names.jsonl").write_text(
        "\n".join(
            json.dumps({"id": name.lower(), "input": {"name": name}})
            for name in ("Ada", "Grace", "Linus")
        ),
        encoding="utf-8",
    )
    prompt = PromptFile.load(prompt_path)
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")

    report = runtime.evaluate(prompt)

    assert [case["id"] for case in report["cases"]] == [
        "names/ada",
        "names/grace",
        "names/linus",
    ]
    assert report["total_assertions"] == 3
    assert report["unverified_cases"] == 0
    assert report["score_ci"]["usable_cases"] == 3
    assert report["score_ci"]["point"] == report["score"] == 1.0
    assert report["failure_attribution"] == []


def _report(scores: list[float | None], *, cost: float = 0.0) -> dict:
    return {
        "cases": [
            {"id": f"c{index}", "results": (
                [] if score is None else [{"score": score, "passed": score >= 0.5}]
            )}
            for index, score in enumerate(scores)
        ],
        "total_cost_usd": cost,
    }


def test_paired_comparison_declares_winner_only_when_interval_excludes_zero():
    result = compare_eval_reports(
        _report([0.0, 0.0, 0.1, 0.0], cost=0.01),
        _report([1.0, 0.9, 1.0, 0.8], cost=0.02),
        resamples=500,
        seed=4,
    )
    assert result["usable"] is True
    assert result["paired_cases"] == 4
    assert result["delta_ci"]["low"] > 0
    assert result["winner"] == "b"
    assert result["cost_usd"]["total"] == pytest.approx(0.03)


def test_paired_comparison_withholds_winner_for_too_few_cases():
    result = compare_eval_reports(_report([0.0, 1.0]), _report([1.0, 1.0]))
    assert result["usable"] is True
    assert result["delta"] == 0.5
    assert result["delta_ci"]["low"] is None
    assert result["winner"] is None
    assert "withheld" in result["reason"]


def test_positive_point_delta_does_not_win_when_interval_includes_zero():
    result = compare_eval_reports(
        _report([0.0, 1.0, 1.0]),
        _report([1.0, 1.0, 1.0]),
        resamples=500,
        seed=8,
    )
    assert result["delta"] > 0
    assert result["delta_ci"]["low"] == 0
    assert result["winner"] is None
    assert "includes zero" in result["reason"]


def test_paired_comparison_refuses_mismatched_case_ids():
    left = _report([1.0])
    right = _report([1.0])
    right["cases"][0]["id"] = "different"
    result = compare_eval_reports(left, right)
    assert result["usable"] is False
    assert result["delta"] is None
