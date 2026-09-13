"""Built-in guardrails (``assay.guardrails``).

Guardrails run either side of the model call. They fail *closed*: an evaluator that
errors is a violation, not a pass. Actions are ``block`` (raise), ``warn`` (record),
``redact`` (transform and continue) and ``retry`` (signal the runtime to re-run).
"""

from __future__ import annotations

import json
import re

from .. import provenance
from ..contracts import CONTRACT_VERSION, GuardrailResult

BOTH = frozenset({"input", "output"})


class _Base:
    id = "base"
    contract_version = CONTRACT_VERSION
    stages = BOTH

    def check(self, text: str, *, config: dict, stage: str, context: dict | None = None) -> GuardrailResult:
        raise NotImplementedError

    def _ok(self, reason: str = "") -> GuardrailResult:
        return GuardrailResult(allowed=True, reason=reason, guardrail=self.id)

    def _violate(self, config: dict, reason: str, transformed: str | None = None) -> GuardrailResult:
        return GuardrailResult(
            allowed=False, action=config.get("action", "block"),
            reason=reason, transformed=transformed, guardrail=self.id,
        )


class RegexBlockGuardrail(_Base):
    """Blocks (or redacts) text matching any configured pattern."""

    id = "regex_block"

    def check(self, text, *, config, stage, context=None):
        patterns = config.get("patterns") or ([config["pattern"]] if config.get("pattern") else [])
        flags = re.IGNORECASE if config.get("ignore_case", True) else 0
        hits = []
        redacted = text
        for pattern in patterns:
            try:
                if re.search(pattern, text, flags):
                    hits.append(pattern)
                    redacted = re.sub(pattern, config.get("replacement", "[REDACTED]"), redacted, flags=flags)
            except re.error:
                return self._violate(config, f"invalid guardrail pattern: {pattern!r}")
        if not hits:
            return self._ok()
        return self._violate(config, f"matched blocked pattern(s): {', '.join(hits)}", redacted)


class MaxLengthGuardrail(_Base):
    id = "max_length"

    def check(self, text, *, config, stage, context=None):
        limit = int(config.get("max_chars") or config.get("value") or 0)
        if not limit or len(text) <= limit:
            return self._ok()
        return self._violate(
            config, f"{len(text)} characters exceeds limit of {limit}", text[:limit]
        )


#: Conservative, precision-biased patterns. A false negative is preferable to
#: mangling legitimate content; use a dedicated PII plugin for regulated workloads.
PII_PATTERNS: dict[str, str] = {
    "email": r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    "us_ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
    "phone": r"\b(?:\+?\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
    "jwt": r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b",
    "api_key": r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b",
}


class PIIGuardrail(_Base):
    """Detects and optionally redacts common sensitive tokens.

    Regex PII detection is a first line of defence, not a compliance control. Ship
    an ML-based detector as a plugin for regulated workloads — the contract is identical.
    """

    id = "pii"

    def check(self, text, *, config, stage, context=None):
        enabled = config.get("types") or list(PII_PATTERNS)
        found: dict[str, int] = {}
        redacted = text
        for kind in enabled:
            pattern = PII_PATTERNS.get(kind) or config.get("custom", {}).get(kind)
            if not pattern:
                continue
            matches = re.findall(pattern, text)
            if matches:
                found[kind] = len(matches)
                redacted = re.sub(pattern, f"[{kind.upper()}]", redacted)
        if not found:
            return self._ok()
        summary = ", ".join(f"{k}×{v}" for k, v in found.items())
        return self._violate(config, f"detected PII: {summary}", redacted)


class SchemaGuardrail(_Base):
    """Enforces that output parses as JSON matching a schema. Pairs with ``action: retry``."""

    id = "schema"
    stages = frozenset({"output"})

    def check(self, text, *, config, stage, context=None):
        import jsonschema

        schema = config.get("schema") or (context or {}).get("output_schema")
        if not schema:
            return self._ok("no schema configured")
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return self._violate(config, f"output is not valid JSON: {exc}")
        errors = [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(payload)]
        if errors:
            return self._violate(config, "; ".join(errors[:3]))
        return self._ok()


class InjectionGuardrail(_Base):
    """Detect injection-shaped instructions at the tool-result trust boundary.

    This is deliberately precision-biased detection, not a claim that clean content is
    safe. ``redact`` replaces the whole tool result: selectively removing known phrases
    would leave an attacker free to route around the detector.
    """

    id = "injection"
    stages = frozenset({"tool_result"})

    def check(self, text, *, config, stage, context=None):
        flags = provenance.scan(text)
        if not flags:
            return self._ok("no recognised injection pattern")
        replacement = config.get(
            "replacement",
            f"[BLOCKED UNTRUSTED TOOL OUTPUT: {', '.join(flags)}]",
        )
        return self._violate(
            config,
            f"matched injection-associated pattern(s): {', '.join(flags)}",
            replacement,
        )
