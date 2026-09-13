"""
Guardrails Router
POST /guardrails/scan           — Scan text for PII, injection, toxicity, hallucination
POST /guardrails/validate       — Validate LLM output against rules
"""
from fastapi import APIRouter

from ...services.guardrails import scan_text, validate_output

router = APIRouter(prefix="/guardrails", tags=["guardrails"])


@router.post("/scan")
def scan(body: dict):
    """Scan text for security and safety issues."""
    text = body.get("text", "")
    if not text.strip():
        return {"risk_score": 0, "risk_level": "safe", "clean": True, "findings": [],
                "pii_count": 0, "injection_detected": False, "toxicity_detected": False,
                "hallucination_signals": 0}
    return scan_text(text)


@router.post("/validate")
def validate(body: dict):
    """
    Validate LLM output against rules.
    Body: { output: str, rules: [{ type: 'contains'|'not_contains'|'regex'|'min_length'|'max_length'|'json_valid', value: ... }] }
    """
    output = body.get("output", "")
    rules = body.get("rules", [])
    return validate_output(output, rules)
