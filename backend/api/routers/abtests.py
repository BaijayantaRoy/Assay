"""
A/B Testing Router
GET  /abtests/               — List all A/B tests
POST /abtests/               — Create a new A/B test
GET  /abtests/{id}           — Get test details + metrics
POST /abtests/{id}/feedback  — Record a thumbs up/down for a variant
POST /abtests/{id}/conclude  — Mark winner and close test
DELETE /abtests/{id}         — Delete test
"""
from math import comb
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ...database import get_session
from ...models import ABTest, ABVariant, PromptVersion, Prompt

router = APIRouter(prefix="/abtests", tags=["abtests"])


@router.get("/")
def list_tests(session: Session = Depends(get_session)):
    tests = session.exec(select(ABTest).order_by(ABTest.created_at.desc())).all()
    result = []
    for t in tests:
        variants = session.exec(select(ABVariant).where(ABVariant.ab_test_id == t.id)).all()
        result.append({
            "id": str(t.id), "name": t.name, "description": t.description,
            "status": t.status, "traffic_split": t.traffic_split,
            "winner": t.winner, "created_at": t.created_at.isoformat(),
            "variants": [_variant_dict(v) for v in variants],
        })
    return result


@router.post("/")
def create_test(body: dict, session: Session = Depends(get_session)):
    """
    Body: {
      name, description, prompt_id,
      variant_a: { prompt_version_id, model },
      variant_b: { prompt_version_id, model },
      traffic_split: 50
    }
    """
    prompt = session.get(Prompt, UUID(body["prompt_id"]))
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    test = ABTest(
        name=body["name"],
        description=body.get("description"),
        prompt_id=UUID(body["prompt_id"]),
        traffic_split=body.get("traffic_split", 50),
    )
    session.add(test)
    session.commit()
    session.refresh(test)

    for label, key in [("A", "variant_a"), ("B", "variant_b")]:
        v_data = body.get(key, {})
        variant = ABVariant(
            ab_test_id=test.id,
            label=label,
            prompt_version_id=UUID(v_data["prompt_version_id"]),
            model=v_data.get("model", "gpt-6.1-sol"),
        )
        session.add(variant)

    session.commit()
    return {"id": str(test.id), "name": test.name, "status": test.status}


@router.get("/{test_id}")
def get_test(test_id: str, session: Session = Depends(get_session)):
    test = session.get(ABTest, UUID(test_id))
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")

    variants = session.exec(select(ABVariant).where(ABVariant.ab_test_id == test.id)).all()
    var_dicts = [_variant_dict(v) for v in variants]

    # Compute an exact, denominator-carrying result. Small samples are explicitly
    # withheld rather than converted into a made-up confidence percentage.
    significance = _compute_significance(var_dicts)

    return {
        "id": str(test.id), "name": test.name, "description": test.description,
        "status": test.status, "traffic_split": test.traffic_split,
        "winner": test.winner, "created_at": test.created_at.isoformat(),
        "variants": var_dicts,
        "significance": significance,
    }


@router.post("/{test_id}/feedback")
def record_feedback(test_id: str, body: dict, session: Session = Depends(get_session)):
    """
    body: { variant_label: "A" | "B", feedback: "up" | "down", cost_usd: float, latency_ms: float }
    """
    test = session.get(ABTest, UUID(test_id))
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    variants = session.exec(select(ABVariant).where(ABVariant.ab_test_id == test.id)).all()
    variant = next((v for v in variants if v.label == body.get("variant_label", "A")), None)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    variant.runs += 1
    if body.get("feedback") == "up":
        variant.thumbs_up += 1
    elif body.get("feedback") == "down":
        variant.thumbs_down += 1

    cost = body.get("cost_usd", 0.0)
    latency = body.get("latency_ms", 0.0)
    variant.total_cost_usd += cost
    # Rolling average latency
    if variant.runs > 0:
        variant.avg_latency_ms = ((variant.avg_latency_ms * (variant.runs - 1)) + latency) / variant.runs

    session.add(variant)
    session.commit()
    return {"ok": True, "variant": _variant_dict(variant)}


@router.post("/{test_id}/conclude")
def conclude_test(test_id: str, body: dict, session: Session = Depends(get_session)):
    test = session.get(ABTest, UUID(test_id))
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    test.status = "concluded"
    test.winner = body.get("winner")  # "a" | "b"
    session.add(test)
    session.commit()
    return {"id": str(test.id), "status": test.status, "winner": test.winner}


@router.delete("/{test_id}")
def delete_test(test_id: str, session: Session = Depends(get_session)):
    test = session.get(ABTest, UUID(test_id))
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    variants = session.exec(select(ABVariant).where(ABVariant.ab_test_id == test.id)).all()
    for v in variants:
        session.delete(v)
    session.delete(test)
    session.commit()
    return {"ok": True}


def _variant_dict(v: ABVariant) -> dict:
    total_feedback = v.thumbs_up + v.thumbs_down
    win_rate = round(v.thumbs_up / total_feedback * 100, 1) if total_feedback > 0 else None
    return {
        "id": str(v.id), "label": v.label,
        "prompt_version_id": str(v.prompt_version_id),
        "model": v.model, "runs": v.runs,
        "thumbs_up": v.thumbs_up, "thumbs_down": v.thumbs_down,
        "win_rate": win_rate,
        "total_cost_usd": round(v.total_cost_usd, 6),
        "avg_latency_ms": round(v.avg_latency_ms, 0),
        "avg_score": v.avg_score,
    }


def _compute_significance(variants: list[dict]) -> dict:
    """Two-sided Fisher exact test with a conservative release sample floor."""
    if len(variants) < 2:
        return {
            "usable": False, "significant": None, "confidence": None,
            "p_value": None, "message": "Two variants are required",
        }
    a = variants[0]
    b = variants[1]
    a_n = a["thumbs_up"] + a["thumbs_down"]
    b_n = b["thumbs_up"] + b["thumbs_down"]
    if a_n == 0 or b_n == 0:
        return {
            "usable": False, "significant": None, "confidence": None,
            "p_value": None, "a_n": a_n, "b_n": b_n,
            "message": f"Not checked — both variants need observations (A:{a_n}, B:{b_n})",
        }

    a_rate = a["thumbs_up"] / a_n
    b_rate = b["thumbs_up"] / b_n
    diff = a_rate - b_rate

    minimum = 20
    if a_n < minimum or b_n < minimum:
        return {
            "usable": False, "significant": None, "confidence": None,
            "p_value": None, "a_n": a_n, "b_n": b_n,
            "a_rate": round(a_rate * 100, 1),
            "b_rate": round(b_rate * 100, 1),
            "difference": round(diff * 100, 1),
            "message": f"Not checked — need at least {minimum} observations per variant "
                       f"(A:{a_n}, B:{b_n})",
        }

    p_value = _fisher_exact_two_sided(
        a["thumbs_up"], a["thumbs_down"], b["thumbs_up"], b["thumbs_down"]
    )
    significant = p_value < 0.05
    confidence = round((1.0 - p_value) * 100, 1)

    return {
        "usable": True,
        "significant": significant,
        "confidence": confidence,
        "p_value": round(p_value, 6),
        "method": "fisher_exact_two_sided",
        "a_n": a_n,
        "b_n": b_n,
        "a_rate": round(a_rate * 100, 1),
        "b_rate": round(b_rate * 100, 1),
        "difference": round(diff * 100, 1),
        "message": ("Difference meets the predeclared 5% significance threshold"
                    if significant else "No statistically significant difference at α=0.05"),
    }


def _fisher_exact_two_sided(a_up: int, a_down: int, b_up: int, b_down: int) -> float:
    """Return the exact two-sided p-value for a 2×2 table.

    This small standard-library implementation avoids presenting a heuristic as a
    statistical test and keeps the calculation reproducible without SciPy.
    """

    a_n = a_up + a_down
    b_n = b_up + b_down
    successes = a_up + b_up
    total = a_n + b_n
    denominator = comb(total, successes)

    def probability(a_successes: int) -> float:
        return (comb(a_n, a_successes) * comb(b_n, successes - a_successes)) / denominator

    lower = max(0, successes - b_n)
    upper = min(a_n, successes)
    observed = probability(a_up)
    tolerance = 1e-12
    return min(1.0, sum(
        probability(candidate)
        for candidate in range(lower, upper + 1)
        if probability(candidate) <= observed + tolerance
    ))
