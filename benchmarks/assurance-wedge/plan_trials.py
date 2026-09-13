"""Generate a deterministic, coverage-complete benchmark assignment plan.

The checked-in default uses role placeholders and is planning material, never trial evidence.
Replace the roles with real independent identities before execution; ``record_trial.py`` remains
the only supported path into the evidence ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = HERE / "protocol.json"
DEFAULT_OUTPUT = HERE / "plans" / "full-target-template.json"
DEFAULT_PORTAL_OUTPUT = ROOT / "frontend" / "lib" / "benchmark-plan.generated.json"
ROLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _unique_roles(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be distinct")
    if any(not ROLE_PATTERN.fullmatch(value) for value in values):
        raise ValueError(f"{label} must use lowercase record-safe ids")
    return values


def trials_per_product(protocol: dict[str, Any]) -> int:
    minimum = protocol["qualification"]["minimum_trials_per_product_metric"]
    return sum(max(minimum, len(metric["tasks"])) for metric in protocol["metrics"])


def build_plan(
    protocol: dict[str, Any],
    *,
    comparator_ids: list[str],
    operator_ids: list[str],
    task_author_id: str,
) -> dict[str, Any]:
    comparator_ids = _unique_roles(comparator_ids, "comparator ids")
    operator_ids = _unique_roles(operator_ids, "operator ids")
    if not ROLE_PATTERN.fullmatch(task_author_id):
        raise ValueError("task author id must use a lowercase record-safe id")
    if task_author_id in operator_ids:
        raise ValueError("task author cannot occupy an operator role")

    assay_id = protocol["assay_product_id"]
    allowed = set(protocol["target_products"]) - {assay_id}
    unknown = sorted(set(comparator_ids) - allowed)
    if unknown:
        raise ValueError(f"unknown comparator ids: {', '.join(unknown)}")
    required_comparators = protocol["claim_policy"]["minimum_comparators"]
    if len(comparator_ids) < required_comparators:
        raise ValueError(f"at least {required_comparators} comparators are required")
    required_operators = protocol["qualification"]["minimum_distinct_operators"]
    if len(operator_ids) < required_operators:
        raise ValueError(f"at least {required_operators} operators are required")

    products = [assay_id, *comparator_ids]
    minimum_trials = protocol["qualification"]["minimum_trials_per_product_metric"]
    assignments: list[dict[str, Any]] = []
    for product_id in products:
        for metric in protocol["metrics"]:
            tasks = metric["tasks"]
            count = max(minimum_trials, len(tasks))
            for index in range(count):
                task_id = tasks[index % len(tasks)]
                assignments.append({
                    "suggested_trial_id": f"{product_id}-{metric['id']}-{index + 1:02d}",
                    "product_id": product_id,
                    "metric_id": metric["id"],
                    "task_id": task_id,
                    "operator_id": operator_ids[index % len(operator_ids)],
                    "task_author_id": task_author_id,
                    "status": "identity-and-environment-not-confirmed",
                })

    claim_products = 1 + required_comparators
    return {
        "protocol": protocol["protocol"],
        "protocol_sha256": canonical_sha256(protocol),
        "plan_kind": "role-template-not-evidence",
        "identity_note": (
            "Operator ids are assignment roles only. Replace them with real independent "
            "identities and confirm clean environments before executing any trial."
        ),
        "product_ids": products,
        "operator_ids": operator_ids,
        "task_author_id": task_author_id,
        "claim_minimum_trial_records": trials_per_product(protocol) * claim_products,
        "planned_trial_records": len(assignments),
        "assignments": assignments,
    }


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2) + "\n"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--portal-output", type=Path, default=DEFAULT_PORTAL_OUTPUT)
    result.add_argument("--comparator", action="append", dest="comparators")
    result.add_argument("--operator", action="append", dest="operators")
    result.add_argument("--task-author-id", default="benchmark-task-author")
    result.add_argument("--check", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    protocol = load_json(args.protocol)
    comparators = args.comparators or [
        product for product in protocol["target_products"]
        if product != protocol["assay_product_id"]
    ]
    operators = args.operators or ["independent-operator-a", "independent-operator-b"]
    expected = render(build_plan(
        protocol,
        comparator_ids=comparators,
        operator_ids=operators,
        task_author_id=args.task_author_id,
    ))
    if args.check:
        drift = [
            path for path in (args.output, args.portal_output)
            if not path.is_file() or path.read_text(encoding="utf-8") != expected
        ]
        if drift:
            raise SystemExit(f"trial plan drift: regenerate {', '.join(map(str, drift))}")
        print(f"trial plan valid: {args.output} and {args.portal_output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    args.portal_output.parent.mkdir(parents=True, exist_ok=True)
    args.portal_output.write_text(expected, encoding="utf-8")
    plan = json.loads(expected)
    print(json.dumps({
        "output": str(args.output),
        "portal_output": str(args.portal_output),
        "products": len(plan["product_ids"]),
        "planned_trial_records": plan["planned_trial_records"],
        "plan_kind": plan["plan_kind"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
