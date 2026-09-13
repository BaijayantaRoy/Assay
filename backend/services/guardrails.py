"""
Guardrails Service — Security, Safety & Quality checks for prompts and LLM outputs.

Checks:
  - PII Detection     : email, phone, SSN, credit card, IP, passport
  - Prompt Injection  : jailbreak / override patterns
  - Toxicity          : harmful content keywords
  - Hallucination Risk: confidence signals in the response
  - Output Validation : schema / regex / keyword rules
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# PII Patterns
# ---------------------------------------------------------------------------
PII_PATTERNS = {
    "email":        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone_us":     r"\b(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b",
    "ssn":          r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    "credit_card":  r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
    "ip_address":   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "api_key":      r"\b(sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z\-_]{35}|AKIA[0-9A-Z]{16})\b",
}

# ---------------------------------------------------------------------------
# Prompt Injection Patterns
# ---------------------------------------------------------------------------
INJECTION_PATTERNS = [
    r"ignore (all |previous |above |prior )?(instructions?|prompts?|context|rules?)",
    r"you are now (a |an )?(DAN|jailbreak|unrestricted|unfiltered|evil|bad)",
    r"forget (everything|all|previous|your instructions)",
    r"pretend (you are|to be|that you('?re| are)) (not|without|free from)",
    r"(act|respond|behave) as if (you have no|you('?re| are) free from|there are no) (restrictions?|limits?|rules?|guidelines?|filters?)",
    r"do anything now",
    r"jailbreak",
    r"bypass (the |your |all )?(safety|filter|restriction|guideline|policy|rule)",
    r"disregard (your|the|all) (safety|ethics?|guidelines?|restrictions?|rules?)",
    r"override (your|the|all) (instructions?|safety|policy|restrictions?)",
    r"new instructions?:?\s+ignore",
    r"system:\s*you are now",
    r"<\|im_start\|>system",  # ChatML injection
]

# ---------------------------------------------------------------------------
# Toxicity Keywords (simplified — production would use a model)
# ---------------------------------------------------------------------------
TOXICITY_KEYWORDS = [
    "how to make a bomb", "how to synthesize", "child exploitation",
    "self-harm", "suicide method", "weapon of mass", "bioweapon",
    "hack into", "ransomware", "phishing email template",
    "generate hate speech", "racial slur",
]

# ---------------------------------------------------------------------------
# Hallucination risk signals in LLM outputs
# ---------------------------------------------------------------------------
HALLUCINATION_SIGNALS = [
    r"as of my (knowledge|training) (cutoff|date)",
    r"I('m| am) not (sure|certain|100%)",
    r"I (believe|think|suppose) (but|however|though)",
    r"(may|might|could) (not be|be inaccurate|have changed)",
    r"please (verify|check|confirm|double.check) this",
    r"I (don't|do not) have (real.time|current|up.to.date)",
    r"(approximately|roughly|around|about) \d",  # approximate numbers
    r"I (cannot|can't) (guarantee|verify|confirm)",
]


def scan_text(text: str) -> dict:
    """
    Scan text for PII, injection, toxicity and hallucination signals.
    Returns structured results with found issues and overall risk level.
    """
    text_lower = text.lower()
    findings = []
    risk_score = 0  # 0-100

    # PII scan
    pii_found = []
    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            pii_found.append({
                "type": pii_type,
                "count": len(matches),
                "sample": str(matches[0])[:20] + ("..." if len(str(matches[0])) > 20 else ""),
            })
            risk_score += 20

    if pii_found:
        findings.append({
            "category": "pii",
            "severity": "high",
            "label": "PII Detected",
            "description": f"Found {len(pii_found)} type(s) of personally identifiable information.",
            "items": pii_found,
        })

    # Prompt injection scan
    injection_found = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            injection_found.append(pattern[:50])
            risk_score += 30

    if injection_found:
        findings.append({
            "category": "injection",
            "severity": "critical",
            "label": "Prompt Injection Detected",
            "description": "This text contains patterns commonly used in prompt injection / jailbreak attacks.",
            "count": len(injection_found),
        })

    # Toxicity scan
    toxic_found = [kw for kw in TOXICITY_KEYWORDS if kw in text_lower]
    if toxic_found:
        risk_score += 40
        findings.append({
            "category": "toxicity",
            "severity": "critical",
            "label": "Harmful Content Detected",
            "description": f"Potentially harmful content patterns detected ({len(toxic_found)} match(es)).",
        })

    # Hallucination signals (for LLM outputs)
    halluc_count = sum(1 for p in HALLUCINATION_SIGNALS if re.search(p, text_lower))
    if halluc_count > 0:
        risk_score += min(halluc_count * 10, 30)
        findings.append({
            "category": "hallucination_risk",
            "severity": "medium" if halluc_count <= 2 else "high",
            "label": "Hallucination Risk Signals",
            "description": f"Output contains {halluc_count} uncertainty signal(s) that may indicate hallucination.",
            "count": halluc_count,
        })

    risk_score = min(100, risk_score)
    risk_level = "safe" if risk_score == 0 else "low" if risk_score < 20 else "medium" if risk_score < 50 else "high" if risk_score < 80 else "critical"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "findings": findings,
        "pii_count": len(pii_found),
        "injection_detected": len(injection_found) > 0,
        "toxicity_detected": len(toxic_found) > 0,
        "hallucination_signals": halluc_count if "halluc_count" in dir() else 0,
        "clean": risk_score == 0,
    }


def validate_output(output: str, rules: list[dict]) -> dict:
    """
    Validate an LLM output against a set of rules.
    Rules: [{ type: 'contains'|'not_contains'|'regex'|'min_length'|'max_length'|'json_valid', value: ... }]
    """
    results = []
    all_passed = True

    for rule in rules:
        rtype = rule.get("type")
        value = rule.get("value", "")
        passed = True
        message = ""

        if rtype == "contains":
            passed = str(value).lower() in output.lower()
            message = f"Output must contain: '{value}'"
        elif rtype == "not_contains":
            passed = str(value).lower() not in output.lower()
            message = f"Output must NOT contain: '{value}'"
        elif rtype == "regex":
            passed = bool(re.search(str(value), output, re.IGNORECASE))
            message = f"Output must match pattern: {value}"
        elif rtype == "min_length":
            passed = len(output) >= int(value)
            message = f"Output must be at least {value} characters (got {len(output)})"
        elif rtype == "max_length":
            passed = len(output) <= int(value)
            message = f"Output must be at most {value} characters (got {len(output)})"
        elif rtype == "json_valid":
            try:
                import json
                json.loads(output)
                passed = True
            except Exception:
                passed = False
            message = "Output must be valid JSON"
        elif rtype == "starts_with":
            passed = output.strip().startswith(str(value))
            message = f"Output must start with: '{value}'"

        if not passed:
            all_passed = False

        results.append({"type": rtype, "passed": passed, "message": message, "value": value})

    return {"all_passed": all_passed, "results": results, "pass_rate": sum(1 for r in results if r["passed"]) / max(len(results), 1)}
