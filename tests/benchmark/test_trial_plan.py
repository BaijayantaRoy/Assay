from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "benchmarks" / "assurance-wedge" / "plan_trials.py"
SPEC = importlib.util.spec_from_file_location("assurance_wedge_plan", PLAN_PATH)
assert SPEC and SPEC.loader
PLANNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLANNER)
PROTOCOL = PLANNER.load_json(ROOT / "benchmarks" / "assurance-wedge" / "protocol.json")


def build(comparators=None, operators=None):
    return PLANNER.build_plan(
        PROTOCOL,
        comparator_ids=comparators or ["promptfoo", "langsmith", "langfuse", "braintrust"],
        operator_ids=operators or ["operator-a", "operator-b"],
        task_author_id="task-author",
    )


def test_full_target_plan_has_unique_coverage_complete_assignments():
    plan = build()
    assert plan["plan_kind"] == "role-template-not-evidence"
    assert plan["claim_minimum_trial_records"] == 40
    assert plan["planned_trial_records"] == 50
    ids = [item["suggested_trial_id"] for item in plan["assignments"]]
    assert len(ids) == len(set(ids))

    grouped = defaultdict(list)
    for assignment in plan["assignments"]:
        grouped[(assignment["product_id"], assignment["metric_id"])].append(assignment)
    for product_id in plan["product_ids"]:
        for metric in PROTOCOL["metrics"]:
            assignments = grouped[(product_id, metric["id"])]
            assert len(assignments) >= PROTOCOL["qualification"]["minimum_trials_per_product_metric"]
            assert {item["task_id"] for item in assignments} == set(metric["tasks"])
            assert len({item["operator_id"] for item in assignments}) >= 2


def test_minimum_three_comparator_plan_has_forty_assignments():
    plan = build(comparators=["promptfoo", "langsmith", "langfuse"])
    assert plan["planned_trial_records"] == 40


@pytest.mark.parametrize(
    ("operators", "author", "message"),
    [
        (["operator-a", "operator-a"], "task-author", "operator ids must be distinct"),
        (["operator-a", "task-author"], "task-author", "task author cannot"),
    ],
)
def test_plan_rejects_non_independent_operator_roles(operators, author, message):
    with pytest.raises(ValueError, match=message):
        PLANNER.build_plan(
            PROTOCOL,
            comparator_ids=["promptfoo", "langsmith", "langfuse"],
            operator_ids=operators,
            task_author_id=author,
        )
