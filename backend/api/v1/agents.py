"""``/v1`` — agent, memory, security and evaluation-quality endpoints.

Everything here is a thin adapter over ``assay_core``, so these endpoints, the ``assay`` CLI
and the MCP server are three faces of one engine. If a harness behaves one way in the
terminal and another over HTTP, that is a bug in this file, not a feature of either.

Browsable at ``/docs``, and rendered by the workbench's Agents and Assurance pages. The
field names in the responses below are read directly by ``frontend/lib/v1.ts``; renaming
one is a breaking UI change even though nothing in either type system will say so. That
seam is guarded by ``tests/e2e/test_ui_contract_e2e.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from assay_core import (
    AgentRuntime,
    LoopRuntime,
    AssayError,
    Runtime,
    Workspace,
    calibration,
    disclosure,
    redteam,
)

from .router import get_runtime, get_store, get_workspace, _http

router = APIRouter(prefix="/v1", tags=["v1 · agents"])


# ---------------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    goal: str | None = Field(None, description="What this run is trying to achieve.")
    model: str | None = None
    sandbox_root: str | None = Field(
        None, description="Workspace-relative directory tools are confined to. Paths outside "
                          "the workspace are rejected."
    )
    dry_run: bool = Field(
        False, description="Add the read-only controller: see what the agent would do."
    )


class LoopRunRequest(AgentRunRequest):
    max_cycles: int | None = Field(None, ge=1, le=100)


class RedTeamRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    model: str | None = Field(
        None,
        description="Supply a real model to test susceptibility. Without one the run "
                    "measures the defences only.",
    )
    categories: list[str] | None = Field(
        None, description="Restrict to corpus categories, e.g. ['tool_poisoning']."
    )
    strategies: list[Literal["static", "sequence", "adaptive"]] | None = Field(
        None, description="Restrict to deterministic delivery strategies."
    )
    corpus: str | None = Field(None, description="Path to a custom corpus jsonl.")


class CalibrateRequest(BaseModel):
    cases: list[dict] = Field(
        description="Labelled cases: {id, output, ratings: {rater: score}, judge_score?}."
    )
    resamples: int = Field(1000, ge=50, le=10000)


def get_agent_runtime(runtime: Runtime = Depends(get_runtime)) -> AgentRuntime:
    return AgentRuntime(runtime)


def _contained_sandbox_root(requested: str | None, workspace: Workspace) -> str:
    """Resolve an API sandbox without allowing it to escape the exposed workspace."""

    root = workspace.root.resolve()
    candidate = Path(requested) if requested else root
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(403, {
            "code": "assay.security.sandbox_escape",
            "message": "sandbox_root must resolve inside the configured Assay workspace",
        }) from exc
    return str(resolved)


def _artifact(store, prompt_id: str, expect: str):
    try:
        artifact = store.get(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc
    if expect == "harness" and not artifact.is_harness:
        raise HTTPException(400, {
            "code": "assay.kind_mismatch",
            "message": f"{prompt_id!r} is kind {artifact.kind!r}, not a harness",
        })
    if expect == "loop" and not artifact.is_loop:
        raise HTTPException(400, {
            "code": "assay.kind_mismatch",
            "message": f"{prompt_id!r} is kind {artifact.kind!r}, not a loop",
        })
    return artifact


# ---------------------------------------------------------------------------
# harnesses
# ---------------------------------------------------------------------------


@router.get("/harnesses", summary="List harnesses")
def list_harnesses(store=Depends(get_store)) -> list[dict]:
    out = []
    for prompt_id in store.list():
        try:
            artifact = store.get(prompt_id)
        except AssayError:
            continue
        if not artifact.is_harness:
            continue
        harness = artifact.harness
        out.append({
            "id": artifact.id, "name": artifact.name, "version": artifact.version,
            "status": artifact.status,
            "tools": [t.get("ref") or t.get("name") for t in artifact.tools],
            "max_iterations": harness.get("max_iterations"),
            "stream_model_calls": bool(harness.get("stream_model_calls", False)),
            "budget": harness.get("budget") or {},
            "memory": bool(harness.get("memory")),
            "has_evals": bool(artifact.evals),
        })
    return out


@router.post("/harnesses/{prompt_id:path}/run", summary="Run an agent harness")
def run_harness(
    prompt_id: str,
    payload: AgentRunRequest = Body(default_factory=AgentRunRequest),
    store=Depends(get_store),
    agents: AgentRuntime = Depends(get_agent_runtime),
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    """Execute the agent loop and return the **full trajectory**.

    Not just the answer: every step, tool call, observation, guardrail decision, memory
    operation and injection detection. Most interesting agent failures are visible in the
    shape of the trajectory and invisible in the output alone.
    """
    harness = _artifact(store, prompt_id, "harness")
    variables = dict(payload.variables)
    if payload.goal:
        variables["goal"] = payload.goal
    try:
        trajectory = agents.run(
            harness, variables, model=payload.model,
            sandbox_root=_contained_sandbox_root(payload.sandbox_root, workspace),
            dry_run=payload.dry_run,
            # No interactive approver over HTTP: a gate that opens itself when nobody is
            # watching is not a gate.
            approver=None,
        )
    except AssayError as exc:
        raise _http(exc) from exc
    return trajectory.to_dict()


@router.post("/harnesses/{prompt_id:path}/evaluate", summary="Run harness trajectory evals")
def evaluate_harness(
    prompt_id: str,
    model: str | None = Query(None),
    store=Depends(get_store),
    agents: AgentRuntime = Depends(get_agent_runtime),
) -> dict:
    harness = _artifact(store, prompt_id, "harness")
    try:
        return agents.evaluate(harness, model=model)
    except AssayError as exc:
        raise _http(exc) from exc


@router.post("/harnesses/{prompt_id:path}/redteam", summary="Red-team a harness")
def redteam_harness(
    prompt_id: str,
    payload: RedTeamRequest = Body(default_factory=RedTeamRequest),
    store=Depends(get_store),
    agents: AgentRuntime = Depends(get_agent_runtime),
) -> dict:
    """Replay the injection corpus and report the attack success rate.

    The response always states its **mode**: without a real `model`, this measures the
    defences (fence, detector, controls) and not model susceptibility. A clean result
    covers the payloads in the corpus and nothing else — published attack success rates
    against current defences exceed 80%.
    """
    harness = _artifact(store, prompt_id, "harness")
    try:
        report = redteam.run_corpus(
            agents, harness, corpus=payload.corpus, variables=payload.variables,
            model=payload.model, categories=payload.categories,
            strategies=payload.strategies,
        )
    except redteam.RedTeamError as exc:
        raise HTTPException(400, exc.to_dict()) from exc
    except AssayError as exc:
        raise _http(exc) from exc
    return report.to_dict()


@router.get("/redteam/corpus", summary="The shipped injection corpus")
def get_corpus(corpus: str | None = Query(None)) -> dict:
    try:
        attacks = redteam.load_corpus(corpus)
    except redteam.RedTeamError as exc:
        raise HTTPException(400, exc.to_dict()) from exc
    return {
        "count": len(attacks),
        "categories": sorted({a.category for a in attacks}),
        "strategies": sorted({a.strategy for a in attacks}),
        "attacks": [
            {"id": a.id, "category": a.category, "severity": a.severity,
             "target": a.target, "description": a.description,
             "forbidden_tools": a.forbidden_tools, "expects_canary": a.expect_canary,
             "strategy": a.strategy, "turns": len(a.turns) if a.turns else 1}
            for a in attacks
        ],
    }


# ---------------------------------------------------------------------------
# loops
# ---------------------------------------------------------------------------


@router.get("/loops", summary="List loops")
def list_loops(store=Depends(get_store)) -> list[dict]:
    out = []
    for prompt_id in store.list():
        try:
            artifact = store.get(prompt_id)
        except AssayError:
            continue
        if not artifact.is_loop:
            continue
        loop = artifact.loop
        out.append({
            "id": artifact.id, "name": artifact.name, "version": artifact.version,
            "status": artifact.status, "trigger": loop.get("trigger", "manual"),
            "goal": loop.get("goal", ""), "max_cycles": loop.get("max_cycles"),
            "steps": len(loop.get("steps") or []),
            "has_verification": bool(loop.get("verify")),
        })
    return out


@router.post("/loops/{prompt_id:path}/run", summary="Run an outer loop")
def run_loop(
    prompt_id: str,
    payload: LoopRunRequest = Body(default_factory=LoopRunRequest),
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    """Run steps, verify, repeat until the goal verifies or a ceiling is hit.

    ``verified`` in the response is the field that matters: an agent reporting success is
    a claim, a verification step that passes is evidence.
    """
    artifact = _artifact(store, prompt_id, "loop")
    variables = dict(payload.variables)
    if payload.goal:
        variables["goal"] = payload.goal
    try:
        run = LoopRuntime(runtime).run(
            artifact, variables, model=payload.model,
            max_cycles=payload.max_cycles, dry_run=payload.dry_run,
        )
    except AssayError as exc:
        raise _http(exc) from exc
    return run.to_dict()


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


def _memory(runtime: Runtime, backend: str):
    try:
        return runtime.registry.get("assay.memory", backend)
    except AssayError as exc:
        raise _http(exc) from exc


@router.get("/memory", summary="Memory statistics")
def memory_stats(
    namespace: str | None = Query(None),
    backend: str = Query("jsonl"),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    return _memory(runtime, backend).stats(namespace=namespace)


@router.get("/memory/search", summary="Search what agents remembered")
def memory_search(
    q: str = Query(description="Free-text query. Entity matches rank highest."),
    namespace: str = Query("default"),
    kind: Literal["episodic", "semantic"] | None = Query(None),
    limit: int = Query(5, ge=1, le=100),
    backend: str = Query("jsonl"),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    hits = _memory(runtime, backend).recall(q, namespace=namespace, kind=kind, limit=limit)
    return {"query": q, "namespace": namespace, "count": len(hits),
            "results": [{**h.to_dict(), "score": h.score} for h in hits]}


@router.delete("/memory", summary="Forget records")
def memory_forget(
    namespace: str = Query("default"),
    record_id: str | None = Query(None, description="Omit to clear the whole namespace."),
    backend: str = Query("jsonl"),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    return {"removed": _memory(runtime, backend).forget(
        namespace=namespace, record_id=record_id
    )}


# ---------------------------------------------------------------------------
# progressive disclosure
# ---------------------------------------------------------------------------


@router.get("/index", summary="Tier-1 prompt index")
def prompt_index(
    budget: int | None = Query(None, description="Override the tier-1 token budget."),
    ws: Workspace = Depends(get_workspace),
    store=Depends(get_store),
) -> dict:
    """The compact index an MCP client sees before loading anything.

    Names and one-line summaries only; bodies and schemas arrive at tier 2.
    """
    config = dict(ws.config.get("disclosure") or {})
    if budget:
        config["max_tokens"] = budget
    prompts = []
    for prompt_id in store.list():
        try:
            prompts.append(store.get(prompt_id))
        except AssayError:
            continue
    report = disclosure.build_index(
        prompts, budget=disclosure.DisclosureBudget.from_config(config)
    )
    return {
        "prompts": [e.to_dict() for e in report.entries],
        "namespaces": report.namespaces,
        "omitted": report.omitted,
        "disclosure": report.to_dict(),
    }


@router.get("/tokens", summary="What this library costs a client's context")
def token_report(
    budget: int | None = Query(None),
    ws: Workspace = Depends(get_workspace),
    store=Depends(get_store),
) -> dict:
    """Measured context cost, tier by tier.

    Token counts are estimates at ~4 chars/token and err high on purpose; exact
    accounting needs a provider tokenizer.
    """
    config = dict(ws.config.get("disclosure") or {})
    if budget:
        config["max_tokens"] = budget
    prompts = []
    for prompt_id in store.list():
        try:
            prompts.append(store.get(prompt_id))
        except AssayError:
            continue
    return disclosure.workspace_report(
        prompts, budget=disclosure.DisclosureBudget.from_config(config)
    )


# ---------------------------------------------------------------------------
# judge calibration
# ---------------------------------------------------------------------------


@router.post("/judge/calibrate", summary="Calibrate a judge against human labels")
def calibrate_judge(
    payload: CalibrateRequest,
    ws: Workspace = Depends(get_workspace),
) -> dict:
    """Two-stage gate.

    Stage 1 measures agreement **between human raters** — if humans disagree, the rubric
    is ambiguous and calibrating a judge against it measures nothing. Stage 2 measures the
    judge against their consensus. Thresholds are conventions, reported beside the raw
    numbers so a reader can disagree.
    """
    cases = [calibration.LabelledCase.from_dict(c) for c in payload.cases]
    try:
        report = calibration.calibrate(
            cases,
            thresholds=calibration.Thresholds.from_config(
                (ws.config.get("judge") or {}).get("thresholds")
            ),
            resamples=payload.resamples,
        )
    except calibration.CalibrationError as exc:
        raise HTTPException(422, exc.to_dict()) from exc
    return report.to_dict()


@router.get("/audit", summary="Run-log statistics")
def audit_stats(ws: Workspace = Depends(get_workspace)) -> dict:
    """Auditing is off unless `governance.audit: true` in assay.yaml.

    ``audit_enabled`` distinguishes two very different empty states: a workspace where
    auditing has never been turned on, versus one where it has and nothing has run yet.
    Both show zero records; only one of them is fixed by running something.
    """
    from assay_core.governance import AuditLog

    config = dict(ws.config.get("governance") or {})
    stats = AuditLog(
        config.get("audit_root") or (ws.root / ".assay" / "audit"),
        retention_days=int(config.get("retention_days", 190)),
    ).stats()
    stats["audit_enabled"] = bool(config.get("audit"))
    return stats


@router.get("/observability", summary="Observability and export readiness")
def observability_status(ws: Workspace = Depends(get_workspace)) -> dict:
    """Report only locally provable telemetry state.

    A declared endpoint is not proof that a collector received a span, so delivery stays
    explicitly unverified. This endpoint never probes or transmits to the configured
    collector merely because a dashboard was opened.
    """
    records = ws.registry().records("assay.tracers")
    registered = any(record.name == "opentelemetry" and record.ok for record in records)
    api_available = False
    provider_name = None
    recording_provider = False
    try:
        from opentelemetry import trace

        api_available = True
        provider = trace.get_tracer_provider()
        provider_name = f"{type(provider).__module__}.{type(provider).__name__}"
        recording_provider = type(provider).__module__.startswith("opentelemetry.sdk")
    except ImportError:
        pass

    governance = dict(ws.config.get("governance") or {})
    return {
        "tracer_registered": registered,
        "otel_api_available": api_available,
        "provider": provider_name,
        "recording_provider": recording_provider,
        "otlp_endpoint_declared": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()),
        "content_capture": os.getenv("ASSAY_OTEL_LOG_CONTENT", "").strip().lower()
                           in {"1", "true", "yes", "on"},
        "audit_enabled": bool(governance.get("audit")),
        "export_verified": None,
        "note": (
            "Collector delivery is not checked from this read-only endpoint. Verify it in "
            "the configured telemetry backend; a declared endpoint alone is not evidence."
        ),
    }


@router.get("/audit/log", summary="Recent run records")
def audit_log(
    artifact_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    ws: Workspace = Depends(get_workspace),
) -> dict:
    from assay_core.governance import AuditLog

    config = dict(ws.config.get("governance") or {})
    log = AuditLog(config.get("audit_root") or (ws.root / ".assay" / "audit"))
    records = log.read(artifact_id=artifact_id, limit=limit)
    return {"count": len(records), "records": records}


@router.get("/governance/report", summary="Regulatory control mapping")
def governance_report(ws: Workspace = Depends(get_workspace)) -> dict:
    """Evidence this repository can produce, and the gaps it cannot fill.

    Not a compliance assessment. Every control names a gap as well as its evidence —
    a mapping that lists only strengths is a marketing document.
    """
    from assay_core.governance import AuditLog, control_report

    config = dict(ws.config.get("governance") or {})
    return control_report(
        ws, AuditLog(config.get("audit_root") or (ws.root / ".assay" / "audit"))
    )


@router.get("/judge/{prompt_id:path}/certificate", summary="Check a judge's certificate")
def judge_certificate(
    prompt_id: str,
    max_age_days: int = Query(180, ge=1),
    store=Depends(get_store),
) -> dict:
    try:
        prompt = store.get(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc
    ok, reason = calibration.is_certified(prompt, max_age_days=max_age_days)
    return {"id": prompt.id, "certified": ok, "reason": reason,
            "certificate": prompt.data.get("calibration")}
