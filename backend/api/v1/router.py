"""``/v1`` — the stable public API.

Every endpoint is a thin adapter over :mod:`assay_core`. No business logic lives here;
that is what keeps the REST API, the CLI and the MCP server behaviourally identical.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assay_core import (
    AssayError,
    ModelCatalog,
    PromptFile,
    Runtime,
    Workspace,
    __spec_version__,
    __version__ as CORE_VERSION,
)

API_VERSION = "1"
router = APIRouter(prefix="/v1", tags=["v1"])


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------


def get_workspace() -> Workspace:
    """The prompt workspace this server exposes.

    ``ASSAY_WORKSPACE`` points at a directory of PromptFiles. Without it the server
    searches upward from the process working directory, so a plain ``assay serve``
    inside a prompt repository just works.
    """
    return Workspace.find(os.getenv("ASSAY_WORKSPACE"))


def get_store(ws: Workspace = Depends(get_workspace)):
    return ws.store()


def get_runtime(ws: Workspace = Depends(get_workspace)) -> Runtime:
    return Runtime(workspace=ws)


def _http(exc: AssayError) -> HTTPException:
    status = {
        "assay.store.not_found": 404,
        "assay.spec.validation": 422,
        "assay.spec.unsupported_version": 422,
        "assay.runtime.capability_unmet": 409,
        "assay.guardrail.violation": 422,
        "assay.provider.auth": 401,
        "assay.provider.rate_limit": 429,
    }.get(exc.code, 502 if exc.code.startswith("assay.provider") else 400)
    return HTTPException(status_code=status, detail=exc.to_dict())


# ---------------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------------


class PromptSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    version: int
    kind: str = "prompt"
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    model: str | None = None
    variables: list[str] = Field(default_factory=list)
    has_evals: bool = False


class PromptDetail(PromptSummary):
    source: str = Field(description="The raw PromptFile text.")
    document: dict[str, Any] = Field(description="Parsed frontmatter plus body.")
    required_capabilities: list[str] = Field(default_factory=list)


class RenderRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


class RunRequest(RenderRequest):
    params: dict[str, Any] = Field(default_factory=dict)
    skip_guardrails: bool = False


class CreateRequest(BaseModel):
    id: str = Field(
        max_length=512,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?(/[a-z0-9]([a-z0-9._-]*[a-z0-9])?)*$",
    )
    body: str
    name: str | None = None
    description: str | None = None
    kind: str = "prompt"
    status: Literal["draft", "review", "stable", "deprecated", "archived"] = "draft"
    tags: list[str] = Field(default_factory=list)
    model: str | None = None
    commit_message: str | None = None


class UpdateRequest(BaseModel):
    body: str | None = None
    name: str | None = None
    description: str | None = None
    status: Literal["draft", "review", "stable", "deprecated", "archived"] | None = None
    tags: list[str] | None = None
    model: str | None = None
    commit_message: str | None = None


class ImportRequest(BaseModel):
    source: str = Field(description="Raw PromptFile text, in any of the three encodings.")
    commit_message: str | None = None


class ScanRequest(BaseModel):
    text: str = Field(max_length=200_000)


class ExperimentVariant(BaseModel):
    prompt_id: str
    version: int | None = Field(None, ge=1)
    model: str | None = None


class ExperimentRequest(BaseModel):
    variant_a: ExperimentVariant
    variant_b: ExperimentVariant


def _summary(pf: PromptFile) -> dict:
    return {
        "id": pf.id, "name": pf.name,
        "description": pf.data.get("description") or "",
        "version": pf.version, "kind": pf.kind, "status": pf.status,
        "tags": pf.tags, "model": pf.model_ref,
        "variables": sorted(pf.template_variables()),
        "has_evals": bool(pf.evals),
    }


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------


@router.get("/", summary="API root")
def api_root(ws: Workspace = Depends(get_workspace)) -> dict:
    return {
        "api_version": API_VERSION,
        "core_version": CORE_VERSION,
        "spec": f"promptfile-v{__spec_version__}",
        "workspace": ws.name,
        "surfaces": {"rest": "/v1", "openapi": "/openapi.json", "mcp": "assay mcp",
                     "cli": "assay --help"},
    }


@router.get("/health", summary="Liveness probe")
def health() -> dict:
    return {"status": "ok", "api_version": API_VERSION, "core_version": CORE_VERSION}


@router.get("/plugins", summary="Installed plugin inventory")
def plugins(ws: Workspace = Depends(get_workspace)) -> dict:
    return ws.registry().describe()


@router.get("/models", summary="Model catalogue")
def models(
    provider: str | None = Query(None),
    ws: Workspace = Depends(get_workspace),
) -> dict:
    catalog = ModelCatalog.autoload(ws.root)
    entries = catalog.by_provider(provider) if provider else catalog.all()
    return {"count": len(entries), "models": [
        {"ref": f"{m.provider}/{m.id}", "id": m.id, "provider": m.provider,
         "name": m.display_name, "context_window": m.context_window,
         "max_output_tokens": m.max_output_tokens,
         "input_cost_per_mtok": m.input_cost_per_mtok,
         "output_cost_per_mtok": m.output_cost_per_mtok,
         "capabilities": sorted(m.capabilities), "deprecated": m.deprecated}
        for m in entries
    ]}


@router.get("/spec", summary="PromptFile JSON Schema")
def spec() -> dict:
    from assay_core.promptfile import load_schema

    return load_schema()


@router.post("/guardrails/scan", summary="Scan text with built-in deterministic detectors")
def scan_guardrails(payload: ScanRequest) -> dict:
    """Expose the same precision-biased PII and injection detectors core uses.

    A clean scan is never labelled safe: pattern matching only establishes whether a
    known pattern was observed. Toxicity and hallucination are deliberately absent — the
    built-in engine has no defensible detector for either claim.
    """
    from assay_core import provenance
    from assay_core.builtins.guardrails import PII_PATTERNS

    pii: dict[str, int] = {}
    for kind, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, payload.text)
        if matches:
            pii[kind] = len(matches)
    injection_flags = provenance.scan(payload.text)
    findings = [
        {"category": "pii", "label": kind, "count": count,
         "description": f"Recognised {count} {kind} pattern(s)."}
        for kind, count in pii.items()
    ] + [
        {"category": "injection", "label": label, "count": 1,
         "description": "Recognised injection-associated language."}
        for label in injection_flags
    ]
    return {
        "checked": True,
        "recognised_risk": bool(findings),
        "pii_count": sum(pii.values()),
        "pii_by_type": pii,
        "injection_detected": bool(injection_flags),
        "injection_flags": injection_flags,
        "findings": findings,
        "note": (
            "Known patterns were recognised; review and enforce declared guardrails."
            if findings else
            "No built-in pattern was recognised. This is not evidence that the text is safe."
        ),
        "limitations": [
            "Regex PII detection is precision-biased and incomplete.",
            "Injection pattern detection is bypassable by rephrasing or obfuscation.",
            "Toxicity and hallucination were not checked.",
        ],
    }


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------


@router.get("/prompts", response_model=list[PromptSummary], summary="List prompts")
def list_prompts(
    prefix: str | None = Query(None),
    tag: list[str] | None = Query(None),
    status: str | None = Query(None),
    store=Depends(get_store),
) -> list[dict]:
    results = []
    for prompt_id in store.list(prefix=prefix):
        try:
            pf = store.get(prompt_id)
        except AssayError:
            continue
        if tag and not set(tag) & set(pf.tags):
            continue
        if status and pf.status != status:
            continue
        results.append(_summary(pf))
    return results


@router.get("/prompts/{prompt_id:path}/history", summary="Version history")
def prompt_history(prompt_id: str, store=Depends(get_store)) -> dict:
    try:
        return {"id": prompt_id, "history": store.history(prompt_id)}
    except AssayError as exc:
        raise _http(exc) from exc


@router.get("/prompts/{prompt_id:path}", response_model=PromptDetail, summary="Get a prompt")
def get_prompt(
    prompt_id: str,
    version: int | None = Query(None, ge=1),
    store=Depends(get_store),
) -> dict:
    try:
        pf = store.get(prompt_id, version=version)
    except AssayError as exc:
        raise _http(exc) from exc
    return {**_summary(pf), "source": pf.to_text(), "document": pf.to_dict(),
            "required_capabilities": sorted(pf.required_capabilities)}


@router.post("/prompts", response_model=PromptSummary, status_code=201, summary="Create a prompt")
def create_prompt(payload: CreateRequest, store=Depends(get_store)) -> dict:
    data: dict[str, Any] = {
        "promptfile": __spec_version__, "id": payload.id,
        "name": payload.name or payload.id.rsplit("/", 1)[-1],
        "description": payload.description or "", "version": 1,
        "kind": payload.kind, "status": payload.status, "tags": payload.tags,
        "engine": {"template": "jinja2", "strict": True},
    }
    if payload.model:
        data["model"] = {"primary": payload.model}
    pf = PromptFile(data=data, body=payload.body)
    errors = pf.validate()
    if errors:
        raise HTTPException(422, {"code": "assay.spec.validation", "errors": errors})
    try:
        store.put(pf, message=payload.commit_message)
    except AssayError as exc:
        raise _http(exc) from exc
    return _summary(pf)


@router.patch("/prompts/{prompt_id:path}", response_model=PromptSummary, summary="Update a prompt")
def update_prompt(prompt_id: str, payload: UpdateRequest, store=Depends(get_store)) -> dict:
    try:
        pf = store.get(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc
    if payload.body is not None:
        pf.body = payload.body
    for field in ("name", "description", "status", "tags"):
        value = getattr(payload, field)
        if value is not None:
            pf.data[field] = value
    if payload.model:
        pf.data.setdefault("model", {})["primary"] = payload.model
    pf.bump(message=payload.commit_message)
    errors = pf.validate()
    if errors:
        raise HTTPException(422, {"code": "assay.spec.validation", "errors": errors})
    store.put(pf, message=payload.commit_message)
    return _summary(pf)


@router.delete("/prompts/{prompt_id:path}", status_code=204, summary="Delete a prompt")
def delete_prompt(prompt_id: str, store=Depends(get_store)) -> Response:
    try:
        store.delete(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)


@router.post("/prompts/{prompt_id:path}/render", summary="Render without calling a model")
def render_prompt(
    prompt_id: str,
    payload: RenderRequest,
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    try:
        pf = store.get(prompt_id)
        rendered = runtime.render(pf, payload.variables, model=payload.model)
    except AssayError as exc:
        raise _http(exc) from exc
    return {"id": pf.id, "version": pf.version, "model": rendered.model,
            "params": rendered.params,
            "messages": [m.to_dict() for m in rendered.messages]}


@router.post("/prompts/{prompt_id:path}/run", summary="Execute against a model")
def run_prompt(
    prompt_id: str,
    payload: RunRequest,
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    if payload.skip_guardrails and os.getenv(
        "ASSAY_ALLOW_GUARDRAIL_BYPASS", ""
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(403, detail={
            "code": "assay.security.guardrail_bypass_disabled",
            "message": "HTTP guardrail bypass is disabled. Set the explicit server-side "
                       "override only in a controlled diagnostic environment.",
        })
    try:
        pf = store.get(prompt_id)
        result = runtime.run(pf, payload.variables, model=payload.model,
                             params=payload.params or None,
                             skip_guardrails=payload.skip_guardrails)
    except AssayError as exc:
        raise _http(exc) from exc
    return result.to_dict()


@router.post(
    "/prompts/{prompt_id:path}/stream",
    summary="Stream text/tool-call deltas and final run evidence",
)
async def stream_prompt(
    prompt_id: str,
    payload: RunRequest,
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
):
    if payload.skip_guardrails and os.getenv(
        "ASSAY_ALLOW_GUARDRAIL_BYPASS", ""
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(403, detail={
            "code": "assay.security.guardrail_bypass_disabled",
            "message": "HTTP guardrail bypass is disabled. Set the explicit server-side "
                       "override only in a controlled diagnostic environment.",
        })
    try:
        pf = store.get(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc

    async def generate():
        try:
            async for event in runtime.astream(
                pf,
                payload.variables,
                model=payload.model,
                params=payload.params or None,
                skip_guardrails=payload.skip_guardrails,
            ):
                yield (
                    "data: "
                    + json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
                    + "\n\n"
                )
        except AssayError as exc:
            yield "data: " + json.dumps({
                "type": "error",
                "error": exc.to_dict(),
            }, ensure_ascii=False, separators=(",", ":")) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/prompts/{prompt_id:path}/evaluate", summary="Run embedded eval cases")
async def evaluate_prompt(
    prompt_id: str,
    model: str | None = Query(None),
    judge_model: str | None = Query(None),
    max_workers: int = Query(1, ge=1, le=32),
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    try:
        pf = store.get(prompt_id)
        return await runtime.aevaluate(
            pf,
            model=model,
            judge_model=judge_model,
            max_concurrency=max_workers,
        )
    except AssayError as exc:
        raise _http(exc) from exc


@router.post("/experiments/compare", summary="Paired A/B comparison on one declared eval set")
def compare_experiment(
    payload: ExperimentRequest,
    ws: Workspace = Depends(get_workspace),
    store=Depends(get_store),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    from assay_core.evaluation import compare_eval_reports, resolve_eval_cases

    try:
        prompt_a = store.get(payload.variant_a.prompt_id, version=payload.variant_a.version)
        prompt_b = store.get(payload.variant_b.prompt_id, version=payload.variant_b.version)
        cases_a = resolve_eval_cases(prompt_a, prompt_a.evals, workspace_root=ws.root)
        cases_b = resolve_eval_cases(prompt_b, prompt_b.evals, workspace_root=ws.root)
    except AssayError as exc:
        raise _http(exc) from exc
    if not cases_a or not cases_b:
        raise HTTPException(422, detail={
            "code": "assay.experiment.no_cases",
            "message": "Both variants need at least one declared eval case.",
        })
    if cases_a != cases_b:
        raise HTTPException(422, detail={
            "code": "assay.experiment.incomparable_cases",
            "message": "Variants must resolve to the same eval cases and assertions.",
        })
    try:
        report_a = runtime.evaluate(prompt_a, model=payload.variant_a.model)
        report_b = runtime.evaluate(prompt_b, model=payload.variant_b.model)
    except AssayError as exc:
        raise _http(exc) from exc
    return {
        "variant_a": {
            "prompt_id": prompt_a.id, "version": prompt_a.version,
            "model": report_a.get("model"), "report": report_a,
        },
        "variant_b": {
            "prompt_id": prompt_b.id, "version": prompt_b.version,
            "model": report_b.get("model"), "report": report_b,
        },
        "comparison": compare_eval_reports(report_a, report_b),
    }


@router.post("/prompts/{prompt_id:path}/validate", summary="Validate against the spec")
def validate_prompt(prompt_id: str, strict: bool = Query(True), store=Depends(get_store)) -> dict:
    try:
        pf = store.get(prompt_id)
    except AssayError as exc:
        raise _http(exc) from exc
    errors = pf.validate(strict=strict)
    return {"id": pf.id, "valid": not errors, "problems": errors}


# ---------------------------------------------------------------------------
# import / export
# ---------------------------------------------------------------------------


@router.post("/import", response_model=PromptSummary, status_code=201,
             summary="Import raw PromptFile text")
def import_prompt(payload: ImportRequest, store=Depends(get_store)) -> dict:
    try:
        pf = PromptFile.parse(payload.source)
        errors = pf.validate()
        if errors:
            raise HTTPException(422, {"code": "assay.spec.validation", "errors": errors})
        store.put(pf, message=payload.commit_message)
    except AssayError as exc:
        raise _http(exc) from exc
    return _summary(pf)


@router.get("/export", summary="Export the whole workspace")
def export_workspace(
    fmt: Literal["promptfile", "json"] = Query("promptfile"),
    store=Depends(get_store),
) -> dict:
    prompts = []
    for prompt_id in store.list():
        pf = store.get(prompt_id)
        prompts.append(pf.to_text() if fmt == "promptfile" else pf.to_dict())
    return {"spec": f"promptfile-v{__spec_version__}", "format": fmt,
            "count": len(prompts), "prompts": prompts}


# ---------------------------------------------------------------------------
# deprecation signalling
# ---------------------------------------------------------------------------


def deprecation_headers(response: Response, sunset: str | None = None) -> None:
    """Helper for future deprecations — sets RFC 8594 ``Deprecation``/``Sunset``.

    Kept here so that when a v1 endpoint is eventually superseded, the signalling
    path already exists and the policy is mechanically enforceable.
    """
    response.headers["Deprecation"] = "true"
    if sunset:
        response.headers["Sunset"] = sunset


def api_version_header(x_assay_api_version: str | None = Header(None)) -> str:
    """Clients may pin a version explicitly; unknown values fail fast rather than drift."""
    if x_assay_api_version and x_assay_api_version != API_VERSION:
        raise HTTPException(400, {
            "code": "assay.api.version_mismatch",
            "message": f"This server implements API v{API_VERSION}",
            "requested": x_assay_api_version,
        })
    return API_VERSION
