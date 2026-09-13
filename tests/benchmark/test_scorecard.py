from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCORE_PATH = ROOT / "benchmarks" / "assurance-wedge" / "score.py"
SPEC = importlib.util.spec_from_file_location("assurance_wedge_score", SCORE_PATH)
assert SPEC and SPEC.loader
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)
PROTOCOL = SCORER.load_json(ROOT / "benchmarks" / "assurance-wedge" / "protocol.json")
DIGEST = "a" * 64


def trial(
    index: int,
    product: str,
    metric: str,
    task: str,
    measurement: dict,
    *,
    operator: str | None = None,
    usable: bool = True,
    completed: bool = True,
) -> dict:
    return {
        "id": f"{product}-{metric}-{index}",
        "product_id": product,
        "product_version": "test-version",
        "metric_id": metric,
        "task_id": task,
        "operator_id": operator or ("operator-a" if index % 2 else "operator-b"),
        "task_author_id": "task-author",
        "environment": {"os": "test-os", "runtime": "test-runtime", "clean_setup": True},
        "usable": usable,
        "completed": completed,
        "measurement": measurement,
        "raw_artifacts": [{"uri": f"raw/{product}-{index}.json", "sha256": DIGEST}],
    }


def document(*trials: dict) -> dict:
    return {"protocol": PROTOCOL["protocol"], "trials": list(trials)}


def metric(result: dict, metric_id: str) -> dict:
    return next(item for item in result["metrics"] if item["id"] == metric_id)


def rate_trials(product: str, detected: int, *, usable_index: int | None = None) -> list[dict]:
    tasks = [
        "zero-usable-sample",
        "unchecked-handoff",
        "missing-cost-evidence",
        "uncalibrated-judge",
    ]
    return [
        trial(
            index,
            product,
            "false-assurance-miss-rate",
            task,
            {"delivered_faults": 4, "detected_faults": detected},
            usable=index != usable_index,
        )
        for index, task in enumerate(tasks, start=1)
    ]


def test_empty_evidence_withholds_every_competitive_claim():
    result = SCORER.score(PROTOCOL, document())
    assert result["claim_status"] == "withheld"
    assert result["competitive_kpis_proven"] == 0
    assert [item["status"] for item in result["metrics"]] == ["not_measured"] * 3
    assert result["recorded_trial_count"] == 0
    assert result["minimum_qualifying_trial_records"] == 40
    assert result["minimum_record_gap"] == 40


def test_loss_rate_can_prove_the_declared_threshold_with_two_operators():
    result = SCORER.score(
        PROTOCOL,
        document(*rate_trials("assay", 4), *rate_trials("competitor", 3)),
    )
    scored = metric(result, "false-assurance-miss-rate")
    assert scored["assay"]["value"] == 0
    assert scored["best_comparator"]["value"] == 0.25
    assert scored["threshold_met"] is True


def test_zero_baseline_tie_is_not_misreported_as_fifty_percent_better():
    result = SCORER.score(
        PROTOCOL,
        document(*rate_trials("assay", 4), *rate_trials("competitor", 4)),
    )
    scored = metric(result, "false-assurance-miss-rate")
    assert scored["threshold_met"] is False
    assert "zero comparator baseline" in " ".join(scored["reasons"]).lower()


def test_unusable_trial_remains_in_the_loss_rate_denominator():
    result = SCORER.score(
        PROTOCOL,
        document(*rate_trials("assay", 4, usable_index=2)),
    )
    scored = metric(result, "false-assurance-miss-rate")["assay"]
    assert scored["opportunities"] == 16
    assert scored["successes"] == 12
    assert scored["value"] == pytest.approx(0.25, abs=1e-6)


def test_repeating_one_easy_task_cannot_qualify_a_product():
    repeated = [
        trial(
            index,
            "assay",
            "false-assurance-miss-rate",
            "zero-usable-sample",
            {"delivered_faults": 4, "detected_faults": 4},
        )
        for index in range(1, 5)
    ]

    scored = metric(SCORER.score(PROTOCOL, document(*repeated)), "false-assurance-miss-rate")["assay"]
    assert scored["qualified"] is False
    assert scored["covered_task_ids"] == ["zero-usable-sample"]
    assert scored["missing_task_ids"] == [
        "missing-cost-evidence",
        "uncalibrated-judge",
        "unchecked-handoff",
    ]


def test_incomplete_change_trial_consumes_the_timebox_and_disqualifies_result():
    trials = [
        trial(
            index,
            "assay",
            "auditable-change-effort",
            "failing-then-passing-eval",
            {"elapsed_minutes": 3},
            completed=index != 2,
        )
        for index in range(1, 4)
    ]
    result = SCORER.score(PROTOCOL, document(*trials))
    scored = metric(result, "auditable-change-effort")["assay"]
    assert scored["raw_minutes"] == [3.0, 45.0, 3.0]
    assert scored["value"] == 3.0
    assert scored["qualified"] is False


def test_author_cannot_operate_their_own_trial():
    evidence = rate_trials("assay", 4)[0]
    evidence["task_author_id"] = evidence["operator_id"]
    with pytest.raises(SCORER.EvidenceError, match="task author cannot operate"):
        SCORER.score(PROTOCOL, document(evidence))


def test_cli_mode_verifies_raw_artifact_content():
    artifact_root = ROOT / "benchmarks" / "assurance-wedge"
    raw = artifact_root / "protocol.json"
    evidence = rate_trials("assay", 4)[0]
    evidence["raw_artifacts"] = [{
        "uri": "protocol.json",
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
    }]
    SCORER.score(PROTOCOL, document(evidence), artifact_root=artifact_root)
    evidence["raw_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(SCORER.EvidenceError, match="digest does not match"):
        SCORER.score(PROTOCOL, document(evidence), artifact_root=artifact_root)
