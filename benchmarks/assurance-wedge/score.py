"""Deterministic, fail-closed scorer for the portable assurance benchmark.

The scorer intentionally produces a withheld claim when evidence is absent, incomplete,
single-operator, missing provenance, or tied at a zero comparator baseline. Unusable loss-rate
trials score every delivered opportunity as missed; incomplete duration trials consume the
full protocol timebox. This keeps inconvenient trials in the measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = HERE / "protocol.json"
DEFAULT_TRIALS = HERE / "trials" / "current.json"
DEFAULT_RESULT = HERE / "results" / "current.json"
DEFAULT_PORTAL_RESULT = ROOT / "frontend" / "lib" / "benchmark-result.generated.json"


class EvidenceError(ValueError):
    """A trial is structurally incapable of supporting a benchmark claim."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_trials(
    protocol: dict[str, Any],
    document: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> list[dict[str, Any]]:
    if document.get("protocol") != protocol["protocol"]:
        raise EvidenceError("trial protocol does not match the scorer protocol")
    trials = document.get("trials")
    if not isinstance(trials, list):
        raise EvidenceError("trials must be a list")

    metric_by_id = {metric["id"]: metric for metric in protocol["metrics"]}
    task_ids = {task["id"] for task in protocol["tasks"]}
    seen: set[str] = set()
    required = {
        "id", "product_id", "product_version", "metric_id", "task_id",
        "operator_id", "task_author_id", "environment", "usable", "completed",
        "measurement", "raw_artifacts",
    }
    digest_chars = set("0123456789abcdef")

    for index, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise EvidenceError(f"trial {index} must be an object")
        missing = sorted(required - trial.keys())
        if missing:
            raise EvidenceError(f"trial {index} is missing: {', '.join(missing)}")
        trial_id = trial["id"]
        if not isinstance(trial_id, str) or not trial_id:
            raise EvidenceError(f"trial {index} has no id")
        if trial_id in seen:
            raise EvidenceError(f"duplicate trial id: {trial_id}")
        seen.add(trial_id)
        if trial["metric_id"] not in metric_by_id:
            raise EvidenceError(f"{trial_id}: unknown metric {trial['metric_id']}")
        if trial["task_id"] not in task_ids:
            raise EvidenceError(f"{trial_id}: unknown task {trial['task_id']}")
        metric = metric_by_id[trial["metric_id"]]
        if trial["task_id"] not in metric["tasks"]:
            raise EvidenceError(f"{trial_id}: task does not belong to metric")
        for field in ("product_id", "product_version", "operator_id", "task_author_id"):
            if not isinstance(trial[field], str) or not trial[field].strip():
                raise EvidenceError(f"{trial_id}: {field} must be non-empty")
        if protocol["qualification"]["require_task_author_operator_separation"]:
            if trial["operator_id"] == trial["task_author_id"]:
                raise EvidenceError(f"{trial_id}: task author cannot operate the trial")
        environment = trial["environment"]
        if not isinstance(environment, dict) or environment.get("clean_setup") is not True:
            raise EvidenceError(f"{trial_id}: clean_setup must be true")
        for field in ("os", "runtime"):
            if not isinstance(environment.get(field), str) or not environment[field].strip():
                raise EvidenceError(f"{trial_id}: environment.{field} must be non-empty")
        if not isinstance(trial["usable"], bool) or not isinstance(trial["completed"], bool):
            raise EvidenceError(f"{trial_id}: usable and completed must be booleans")
        artifacts = trial["raw_artifacts"]
        if not isinstance(artifacts, list) or not artifacts:
            raise EvidenceError(f"{trial_id}: at least one raw artifact is required")
        for artifact in artifacts:
            digest = artifact.get("sha256") if isinstance(artifact, dict) else None
            uri = artifact.get("uri") if isinstance(artifact, dict) else None
            if not isinstance(uri, str) or not uri:
                raise EvidenceError(f"{trial_id}: raw artifact uri is required")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or set(digest) - digest_chars
            ):
                raise EvidenceError(f"{trial_id}: raw artifact needs a lowercase SHA-256 digest")
            if artifact_root is not None:
                raw_path = (artifact_root / uri).resolve()
                root = artifact_root.resolve()
                if raw_path != root and root not in raw_path.parents:
                    raise EvidenceError(f"{trial_id}: raw artifact escapes the trial directory")
                if not raw_path.is_file():
                    raise EvidenceError(f"{trial_id}: raw artifact does not exist: {uri}")
                actual = hashlib.sha256(raw_path.read_bytes()).hexdigest()
                if actual != digest:
                    raise EvidenceError(f"{trial_id}: raw artifact digest does not match: {uri}")
        _validate_measurement(trial, metric)
    return trials


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    number = float(value)
    if number < 0 or (positive and number <= 0):
        raise EvidenceError(f"{label} is outside its allowed range")
    return number


def _validate_measurement(trial: dict[str, Any], metric: dict[str, Any]) -> None:
    trial_id = trial["id"]
    measurement = trial["measurement"]
    if not isinstance(measurement, dict):
        raise EvidenceError(f"{trial_id}: measurement must be an object")
    if metric["kind"] == "loss_rate":
        total = _number(measurement.get(metric["denominator_field"]), f"{trial_id}: denominator", positive=True)
        successes = _number(measurement.get(metric["success_field"]), f"{trial_id}: successes")
        if successes > total:
            raise EvidenceError(f"{trial_id}: successes cannot exceed the denominator")
    else:
        _number(measurement.get(metric["value_field"]), f"{trial_id}: duration")


def _product_metric(
    trials: list[dict[str, Any]],
    metric: dict[str, Any],
    product_id: str,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    selected = [
        trial for trial in trials
        if trial["metric_id"] == metric["id"] and trial["product_id"] == product_id
    ]
    operators = sorted({trial["operator_id"] for trial in selected})
    covered_tasks = sorted({trial["task_id"] for trial in selected})
    missing_tasks = sorted(set(metric["tasks"]) - set(covered_tasks))
    required_trials = protocol["qualification"]["minimum_trials_per_product_metric"]
    required_operators = protocol["qualification"]["minimum_distinct_operators"]
    task_coverage_met = (
        not protocol["qualification"].get("require_all_metric_tasks", False)
        or not missing_tasks
    )
    qualified = (
        len(selected) >= required_trials
        and len(operators) >= required_operators
        and task_coverage_met
    )

    result: dict[str, Any] = {
        "product_id": product_id,
        "trial_count": len(selected),
        "operator_count": len(operators),
        "covered_task_ids": covered_tasks,
        "missing_task_ids": missing_tasks,
        "usable_trial_count": sum(trial["usable"] for trial in selected),
        "completed_trial_count": sum(trial["completed"] for trial in selected),
        "qualified": qualified,
        "value": None,
    }
    if not selected:
        return result

    if metric["kind"] == "loss_rate":
        total = 0.0
        successes = 0.0
        for trial in selected:
            measurement = trial["measurement"]
            opportunities = float(measurement[metric["denominator_field"]])
            total += opportunities
            # An unusable result cannot receive credit for detecting/preserving evidence.
            if trial["usable"]:
                successes += float(measurement[metric["success_field"]])
        result["opportunities"] = int(total) if total.is_integer() else total
        result["successes"] = int(successes) if successes.is_integer() else successes
        result["value"] = round((total - successes) / total, 6)
    else:
        timebox = float(protocol["qualification"]["auditable_change_timebox_minutes"])
        durations = [
            min(float(trial["measurement"][metric["value_field"]]), timebox)
            if trial["completed"] and trial["usable"]
            else timebox
            for trial in selected
        ]
        result["raw_minutes"] = durations
        result["value"] = round(statistics.median(durations), 6)
        if metric.get("require_all_completed"):
            result["qualified"] = qualified and all(
                trial["completed"] and trial["usable"] for trial in selected
            )
    return result


def minimum_qualifying_trial_records(protocol: dict[str, Any]) -> int:
    """Smallest ledger that can satisfy trial count and full task coverage."""
    per_product = sum(
        max(
            protocol["qualification"]["minimum_trials_per_product_metric"],
            len(metric["tasks"]),
        )
        for metric in protocol["metrics"]
    )
    return per_product * (1 + protocol["claim_policy"]["minimum_comparators"])


def score(
    protocol: dict[str, Any],
    document: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    trials = validate_trials(protocol, document, artifact_root=artifact_root)
    assay_id = protocol["assay_product_id"]
    products = sorted({trial["product_id"] for trial in trials})
    metric_results = []

    for metric in protocol["metrics"]:
        product_results = {
            product_id: _product_metric(trials, metric, product_id, protocol)
            for product_id in products
        }
        assay = product_results.get(assay_id) or _product_metric(
            trials, metric, assay_id, protocol
        )
        comparators = [
            result for product_id, result in product_results.items()
            if product_id != assay_id and result["qualified"] and result["value"] is not None
        ]
        best = min(comparators, key=lambda item: item["value"]) if comparators else None
        reasons: list[str] = []
        if not assay["qualified"]:
            reasons.append("Assay lacks required trials, independent operators, or declared-task coverage.")
        if best is None:
            reasons.append("No qualifying comparator result exists.")
        threshold_met = False
        if assay["qualified"] and best is not None:
            best_value = float(best["value"])
            assay_value = float(assay["value"])
            if best_value == 0:
                reasons.append("A zero comparator baseline cannot prove relative improvement.")
            else:
                threshold_met = assay_value <= best_value * float(metric["relative_target_fraction"])
                if metric.get("assay_absolute_target") is not None:
                    threshold_met = threshold_met and assay_value <= float(metric["assay_absolute_target"])
                if not threshold_met:
                    reasons.append("The declared 50%-better threshold was not met.")
        status = "verified" if threshold_met else (
            "not_measured" if assay["trial_count"] == 0 and not comparators else "insufficient_or_failed"
        )
        metric_results.append({
            "id": metric["id"],
            "name": metric["name"],
            "unit": metric["unit"],
            "status": status,
            "threshold_met": threshold_met,
            "assay": assay,
            "best_comparator": best,
            "qualified_comparator_count": len(comparators),
            "qualified_comparator_ids": sorted(item["product_id"] for item in comparators),
            "reasons": reasons,
        })

    comparator_sets = [set(item["qualified_comparator_ids"]) for item in metric_results]
    qualified_comparator_ids = sorted(
        set.intersection(*comparator_sets) if comparator_sets else set()
    )
    minimum_comparators = protocol["claim_policy"]["minimum_comparators"]
    all_metrics_pass = all(result["threshold_met"] for result in metric_results)
    enough_comparators = len(qualified_comparator_ids) >= minimum_comparators
    claim_verified = all_metrics_pass and enough_comparators
    minimum_records = minimum_qualifying_trial_records(protocol)
    return {
        "protocol": protocol["protocol"],
        "evidence_date": protocol["evidence_date"],
        "protocol_sha256": canonical_sha256(protocol),
        "trials_sha256": canonical_sha256(document),
        "claim_status": "verified" if claim_verified else "withheld",
        "claim_verified": claim_verified,
        "competitive_kpis_proven": sum(result["threshold_met"] for result in metric_results),
        "primary_kpi_count": len(metric_results),
        "qualifying_comparator_count": len(qualified_comparator_ids),
        "minimum_comparators": minimum_comparators,
        "recorded_trial_count": len(trials),
        "minimum_qualifying_trial_records": minimum_records,
        "minimum_record_gap": max(0, minimum_records - len(trials)),
        "metrics": metric_results,
        "limitations": [
            "Component tests are not substituted for shared-task competitor measurements.",
            "A product name in the trial file does not qualify it unless each metric meets trial and operator requirements.",
            "Independent reproduction and raw artifacts remain mandatory for a verified claim.",
        ],
    }


def render(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--trials", type=Path, default=DEFAULT_TRIALS)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--portal-output", type=Path, default=DEFAULT_PORTAL_RESULT)
    parser.add_argument("--check", action="store_true", help="fail if checked-in results drift")
    args = parser.parse_args()

    result = score(
        load_json(args.protocol),
        load_json(args.trials),
        artifact_root=args.trials.resolve().parent,
    )
    expected = render(result)
    if args.check:
        drift = [
            str(path) for path in (args.output, args.portal_output)
            if not path.exists() or path.read_text(encoding="utf-8") != expected
        ]
        if drift:
            print(json.dumps({"valid": False, "drift": drift}, indent=2))
            return 1
        print(json.dumps({
            "valid": True,
            "claim_status": result["claim_status"],
            "competitive_kpis_proven": result["competitive_kpis_proven"],
            "primary_kpi_count": result["primary_kpi_count"],
        }, indent=2))
        return 0

    for path in (args.output, args.portal_output):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
    print(expected, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
