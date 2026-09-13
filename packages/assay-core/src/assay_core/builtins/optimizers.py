"""Built-in prompt optimizers (``assay.optimizers``)."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable

from ..contracts import CONTRACT_VERSION
from ..errors import OptimizationError
from ..promptfile import PromptFile


class ReflectiveRewriteOptimizer:
    """One evidence-grounded rewrite pass with a caller-supplied model function.

    The optimizer does not grade itself. It receives the baseline case report, asks for
    a strict JSON candidate, and leaves before/after evaluation and write gating to the
    caller. This separation makes it impossible for the rewriting model to declare its
    own candidate an improvement.
    """

    id = "reflective"
    contract_version = CONTRACT_VERSION

    def optimize(
        self,
        prompt: PromptFile,
        *,
        dataset: list[dict],
        budget: dict | None = None,
    ) -> dict[str, Any]:
        config = dict(budget or {})
        rewrite: Callable[[str], Any] | None = config.get("rewrite")
        if not callable(rewrite):
            raise OptimizationError("reflective optimizer requires a rewrite model callback")

        max_source = int(config.get("max_source_chars", 50_000))
        max_candidate = int(config.get("max_candidate_chars", 100_000))
        evidence = []
        for case in dataset:
            failed = [
                {
                    "type": result.get("type") or result.get("evaluator"),
                    "reason": result.get("reason", ""),
                    "score": result.get("score"),
                }
                for result in (case.get("results") or case.get("assertions") or [])
                if result.get("passed") is False
            ]
            if failed or case.get("error"):
                evidence.append({
                    "case": case.get("id"),
                    "input": case.get("input", {}),
                    "failures": failed,
                    "error": case.get("error"),
                })

        request = (
            "You are improving a versioned prompt using measured baseline failures.\n"
            "Return exactly one JSON object with string fields `body` and `rationale`.\n"
            "`body` must be only the revised Markdown prompt body, not frontmatter.\n"
            "Preserve every {{ variable }} and do not insert literal expected answers merely "
            "to satisfy tests. Generalize from the evidence.\n\n"
            "CURRENT PROMPTFILE:\n"
            + prompt.to_text()[:max_source]
            + "\n\nMEASURED FAILURES:\n"
            + json.dumps(evidence, ensure_ascii=False, default=str)[:20_000]
        )
        raw = rewrite(request)
        rewrite_cost = 0.0
        if isinstance(raw, tuple):
            raw, rewrite_cost = raw[0], float(raw[1] or 0.0)
        text = str(raw).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OptimizationError(
                f"optimizer returned invalid JSON: {exc}; candidate was not evaluated or written"
            ) from exc
        if not isinstance(payload, dict):
            raise OptimizationError("optimizer response must be a JSON object")
        body = payload.get("body")
        rationale = payload.get("rationale")
        if not isinstance(body, str) or not body.strip():
            raise OptimizationError("optimizer response has no non-empty string `body`")
        if not isinstance(rationale, str) or not rationale.strip():
            raise OptimizationError("optimizer response has no non-empty string `rationale`")
        if len(body) > max_candidate:
            raise OptimizationError(
                f"optimizer candidate is {len(body)} characters; limit is {max_candidate}"
            )
        if prompt.renderer_id == "jinja2":
            source_variables = set(re.findall(
                r"\{\{\s*([A-Za-z_][\w.]*)", prompt.body
            ))
            candidate_variables = set(re.findall(
                r"\{\{\s*([A-Za-z_][\w.]*)", body
            ))
        elif prompt.renderer_id == "fstring":
            source_variables = set(re.findall(r"(?<!\{)\{([A-Za-z_]\w*)\}(?!\})", prompt.body))
            candidate_variables = set(re.findall(r"(?<!\{)\{([A-Za-z_]\w*)\}(?!\})", body))
        else:
            source_variables = candidate_variables = set()
        missing_variables = sorted(source_variables - candidate_variables)
        if missing_variables:
            raise OptimizationError(
                "optimizer candidate removed template variable(s): "
                + ", ".join(missing_variables)
            )

        data = copy.deepcopy(prompt.data)
        data["version"] = prompt.version + 1
        provenance = dict(data.get("provenance") or {})
        provenance["derived_from"] = f"{prompt.id}@{prompt.version}"
        data["provenance"] = provenance
        data["optimization"] = {
            "optimizer": self.id,
            "baseline_cases": len(dataset),
            "rationale": rationale.strip(),
        }
        candidate = PromptFile(
            data=data,
            body=body.strip(),
            path=prompt.path,
            source_format=prompt.source_format,
        )
        return {
            "candidate": candidate,
            "rationale": rationale.strip(),
            "rewrite_cost_usd": round(rewrite_cost, 8),
            "evidence_cases": len(evidence),
        }
