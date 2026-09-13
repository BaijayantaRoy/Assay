"""Shared evaluation mechanics: datasets, uncertainty, and failure attribution.

All three execution surfaces (prompt, harness, loop) use this module so their reports
carry identical denominators and cannot drift into subtly different meanings.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .contracts import EvalResult
from .errors import ValidationError
from .promptfile import PromptFile

_MAX_DATASET_BYTES = 10 * 1024 * 1024


def _dataset_path(prompt: PromptFile, reference: str, workspace_root: Path) -> Path:
    if reference.startswith("promptfile://"):
        raise ValidationError(
            "promptfile:// eval datasets are not implemented; use a workspace-relative JSONL file"
        )
    raw = Path(reference)
    if raw.is_absolute():
        raise ValidationError("eval dataset paths must be workspace-relative")
    base = prompt.path.parent if prompt.path else workspace_root
    candidate = (base / raw).resolve()
    root = workspace_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"eval dataset escapes the workspace: {reference}") from exc
    if not candidate.is_file():
        raise ValidationError(f"eval dataset not found: {reference}")
    if candidate.stat().st_size > _MAX_DATASET_BYTES:
        raise ValidationError("eval datasets larger than 10 MiB are refused")
    if candidate.suffix.lower() not in {".jsonl", ".json"}:
        raise ValidationError("eval datasets must be .jsonl or .json")
    return candidate


def _read_dataset(path: Path) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"eval dataset is not UTF-8: {path.name}") from exc
    try:
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid eval dataset {path.name}: {exc}") from exc
    if not isinstance(rows, list):
        raise ValidationError(f"eval dataset {path.name} must contain a list of cases")
    return rows


def resolve_eval_cases(
    prompt: PromptFile,
    cases: list[dict[str, Any]],
    *,
    workspace_root: Path,
) -> list[dict[str, Any]]:
    """Expand ``evals[].dataset`` references into ordinary inline cases.

    Each row must be an object with an ``input`` object. Assertions on the dataset
    declaration apply to every row; row assertions are appended. This preserves the
    source assertion instead of letting a row silently replace the policy being tested.
    """
    expanded: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for declaration in cases:
        if not isinstance(declaration, dict):
            raise ValidationError("eval cases must be objects")
        reference = declaration.get("dataset")
        if not reference:
            candidates = [dict(declaration)]
        else:
            path = _dataset_path(prompt, str(reference), workspace_root)
            rows = _read_dataset(path)
            candidates = []
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    raise ValidationError(
                        f"eval dataset {path.name} row {index} must be an object"
                    )
                row_input = row.get("input")
                if not isinstance(row_input, dict):
                    raise ValidationError(
                        f"eval dataset {path.name} row {index} needs an input object"
                    )
                base_id = str(declaration.get("id") or path.stem)
                row_id = str(row.get("id") or index)
                combined = {
                    key: value
                    for key, value in declaration.items()
                    if key not in {"dataset", "input", "assert", "expected_output"}
                }
                combined["id"] = f"{base_id}/{row_id}"
                combined["input"] = row_input
                if "expected_output" in row:
                    combined["expected_output"] = row["expected_output"]
                elif "expected_output" in declaration:
                    combined["expected_output"] = declaration["expected_output"]
                assertions = [
                    *(declaration.get("assert") or []),
                    *(row.get("assert") or []),
                ]
                combined["assert"] = assertions
                candidates.append(combined)

        for candidate in candidates:
            case_id = str(candidate.get("id") or "?")
            if case_id in seen_ids:
                raise ValidationError(f"duplicate eval case id after dataset expansion: {case_id}")
            seen_ids.add(case_id)
            expanded.append(candidate)
    return expanded


def _weighted_score(results: list[EvalResult]) -> float | None:
    if not results:
        return None
    total_weight = sum(result.weight for result in results) or 1.0
    return sum(result.score * result.weight for result in results) / total_weight


def score_confidence_interval(
    case_results: list[list[EvalResult]],
    *,
    unverified_cases: int,
    resamples: int = 1000,
    seed: int = 1729,
) -> dict[str, Any]:
    """Case-cluster percentile bootstrap interval for the weighted eval score.

    Assertions inside one case are correlated, so the resampling unit is the case, not
    the assertion. Empty/unverified cases are excluded and named in the denominator.
    Fewer than three usable cases withhold bounds rather than report false precision.
    """
    usable = [group for group in case_results if group]
    flat = [result for group in usable for result in group]
    point = _weighted_score(flat)
    report: dict[str, Any] = {
        "point": round(point, 4) if point is not None else None,
        "low": None,
        "high": None,
        "level": 0.95,
        "usable_cases": len(usable),
        "excluded_unverified_cases": unverified_cases,
        "method": "withheld",
    }
    if point is None:
        report["reason"] = "zero usable cases"
        return report
    if len(usable) < 3:
        report["reason"] = "fewer than three usable cases"
        return report

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled = [usable[rng.randrange(len(usable))] for _ in usable]
        estimate = _weighted_score([result for group in sampled for result in group])
        if estimate is not None:
            estimates.append(estimate)
    estimates.sort()
    tail = 0.025
    low = estimates[max(0, int(tail * len(estimates)))]
    high = estimates[min(len(estimates) - 1, int((1 - tail) * len(estimates)))]
    report.update(
        {
            "low": round(low, 4),
            "high": round(high, 4),
            "method": "case-cluster percentile bootstrap",
            "resamples": resamples,
            "seed": seed,
        }
    )
    return report


def failure_attribution(
    case_results: list[tuple[str, list[EvalResult]]],
) -> list[dict[str, Any]]:
    """Group failed assertions by the smallest component the evaluator identified."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for case_id, results in case_results:
        for result in results:
            if result.passed:
                continue
            attribution = result.details.get("attribution") or []
            if not attribution:
                if result.evaluator in {"runtime", "harness", "loop"}:
                    attribution = [{"type": "runtime", "id": result.evaluator}]
                elif result.reason.startswith("evaluator error:"):
                    attribution = [{"type": "evaluator", "id": result.evaluator}]
                else:
                    attribution = [{"type": "output", "id": "final_output"}]
            for component in attribution:
                component_type = str(component.get("type") or "unknown")
                component_id = str(component.get("id") or "unknown")
                key = (component_type, component_id)
                entry = grouped.setdefault(
                    key,
                    {
                        "component_type": component_type,
                        "component": component_id,
                        "failure_count": 0,
                        "cases": set(),
                        "evaluators": set(),
                    },
                )
                entry["failure_count"] += 1
                entry["cases"].add(case_id)
                entry["evaluators"].add(result.evaluator)
    return [
        {
            **{key: value for key, value in entry.items() if key not in {"cases", "evaluators"}},
            "cases": sorted(entry["cases"]),
            "evaluators": sorted(entry["evaluators"]),
        }
        for entry in sorted(
            grouped.values(),
            key=lambda item: (-item["failure_count"], item["component_type"], item["component"]),
        )
    ]


def accuracy_cost_report(score: float | None, case_reports: list[dict]) -> dict:
    """Pair measured accuracy with actual and single-sample-reference spend.

    This is one operating point, not a causal claim that sampling produced the score.
    A curve requires rerunning the same cases at another sample count.
    """
    total_cost = sum(float(case.get("cost_usd", 0.0)) for case in case_reports)
    single_cost = sum(
        float(case.get("single_sample_cost_usd", case.get("cost_usd", 0.0)))
        for case in case_reports
    )
    usable_cases = sum(case.get("passed") is not None for case in case_reports)
    sample_counts = [int(case.get("samples_requested", 1)) for case in case_reports]
    selections = sorted({str(case.get("selection", "single")) for case in case_reports})
    return {
        "score": score,
        "total_cost_usd": round(total_cost, 8),
        "single_sample_reference_cost_usd": round(single_cost, 8),
        "incremental_test_time_cost_usd": round(total_cost - single_cost, 8),
        "cost_multiplier": round(total_cost / single_cost, 6) if single_cost > 0 else None,
        "cost_per_usable_case_usd": (
            round(total_cost / usable_cases, 8) if usable_cases else None
        ),
        "samples_requested": max(sample_counts, default=1),
        "selection": selections[0] if len(selections) == 1 else selections,
        "usable_cases": usable_cases,
        "note": (
            "Measured score/cost operating point; rerun at another sample count for a "
            "causal accuracy-versus-cost comparison."
        ),
    }


def compare_eval_reports(
    variant_a: dict[str, Any],
    variant_b: dict[str, Any],
    *,
    resamples: int = 2000,
    seed: int = 2718,
) -> dict[str, Any]:
    """Paired comparison of two reports evaluated on the same case identifiers.

    The unit is the eval case, not each assertion. Cases without usable scores in either
    variant are excluded and named. Fewer than three paired cases produce a point delta
    but no interval or winner claim.
    """
    a_cases = {str(case.get("id")): case for case in variant_a.get("cases") or []}
    b_cases = {str(case.get("id")): case for case in variant_b.get("cases") or []}
    if set(a_cases) != set(b_cases):
        return {
            "usable": False,
            "paired_cases": 0,
            "excluded_cases": [],
            "delta": None,
            "delta_ci": {"low": None, "high": None, "level": 0.95, "method": "withheld"},
            "winner": None,
            "reason": "Variant reports do not contain the same eval case identifiers.",
        }

    def case_score(case: dict) -> float | None:
        scores = [
            float(result["score"])
            for result in (case.get("results") or [])
            if result.get("score") is not None
        ]
        return sum(scores) / len(scores) if scores else None

    pairs: list[tuple[str, float, float]] = []
    excluded: list[str] = []
    for case_id in sorted(a_cases):
        a_score = case_score(a_cases[case_id])
        b_score = case_score(b_cases[case_id])
        if a_score is None or b_score is None:
            excluded.append(case_id)
        else:
            pairs.append((case_id, a_score, b_score))
    if not pairs:
        return {
            "usable": False,
            "paired_cases": 0,
            "excluded_cases": excluded,
            "delta": None,
            "delta_ci": {"low": None, "high": None, "level": 0.95, "method": "withheld"},
            "winner": None,
            "reason": "Zero cases had usable scores for both variants.",
        }

    deltas = [b_score - a_score for _, a_score, b_score in pairs]
    point = sum(deltas) / len(deltas)
    interval = {
        "low": None, "high": None, "level": 0.95,
        "method": "withheld", "resamples": 0, "seed": seed,
    }
    winner = None
    reason = "Fewer than three paired cases; uncertainty and winner are withheld."
    if len(deltas) >= 3:
        rng = random.Random(seed)
        estimates = sorted(
            sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas)
            for _ in range(resamples)
        )
        low = estimates[max(0, int(0.025 * len(estimates)))]
        high = estimates[min(len(estimates) - 1, int(0.975 * len(estimates)))]
        interval.update({
            "low": round(low, 4), "high": round(high, 4),
            "method": "paired case bootstrap", "resamples": resamples,
        })
        if low > 0:
            winner = "b"
            reason = "Variant B's paired 95% delta interval is above zero."
        elif high < 0:
            winner = "a"
            reason = "Variant A's paired 95% delta interval is above zero."
        else:
            reason = "The paired 95% delta interval includes zero; no winner is established."
    return {
        "usable": True,
        "paired_cases": len(pairs),
        "excluded_cases": excluded,
        "delta": round(point, 4),
        "delta_direction": "b_minus_a",
        "delta_ci": interval,
        "winner": winner,
        "reason": reason,
        "cost_usd": {
            "a": float(variant_a.get("total_cost_usd") or 0),
            "b": float(variant_b.get("total_cost_usd") or 0),
            "total": round(
                float(variant_a.get("total_cost_usd") or 0)
                + float(variant_b.get("total_cost_usd") or 0),
                8,
            ),
        },
        "note": (
            "Paired case bootstrap over this declared eval set. This does not establish "
            "performance on another population or future model version."
        ),
    }
