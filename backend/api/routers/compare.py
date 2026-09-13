"""
Multi-Model Comparator Router
POST /compare/run   — Run same prompt against multiple models in parallel
GET  /compare/      — List past compare runs
GET  /compare/{id}  — Get compare run with results
"""
import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select

from ...database import get_session
from ...models import CompareRun, CompareResult, PromptVersion
from ...services.llm_service import run_llm

router = APIRouter(prefix="/compare", tags=["compare"])


async def _run_single(model: str, content: str, variables: dict, params: dict) -> dict:
    """Run one model in the executor to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_llm(model=model, content=content, variables=variables, params=params)
        )
        return {"model": model, **result, "error": None}
    except Exception as e:
        return {
            "model": model, "response": "", "prompt_tokens": 0,
            "completion_tokens": 0, "total_tokens": 0,
            "latency_ms": 0, "estimated_cost_usd": 0.0, "error": str(e),
        }


@router.post("/run")
async def run_comparison(body: dict, session: Session = Depends(get_session)):
    """
    Run the same prompt against multiple models simultaneously.
    Body: {
      prompt_version_id: str,
      models: ["gpt-4o", "claude-sonnet-4-...", "gemini-2.5-flash"],
      variables: { key: value },
      params: { temperature: 0.7, max_tokens: 1024 }
    }
    """
    version_id = body.get("prompt_version_id")
    models = body.get("models", [])
    variables = body.get("variables", {})
    params = body.get("params", {"temperature": 0.7, "max_tokens": 1024})

    if not version_id:
        raise HTTPException(status_code=400, detail="prompt_version_id is required")
    if not models or len(models) < 2:
        raise HTTPException(status_code=400, detail="At least 2 models required for comparison")
    if len(models) > 6:
        raise HTTPException(status_code=400, detail="Maximum 6 models per comparison")

    version = session.get(PromptVersion, UUID(version_id))
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    # Save the compare run
    compare_run = CompareRun(
        prompt_version_id=UUID(version_id),
        models=models,
        variables=variables,
    )
    session.add(compare_run)
    session.commit()
    session.refresh(compare_run)

    # Run all models in parallel
    tasks = [_run_single(m, version.content, variables, params) for m in models]
    results = await asyncio.gather(*tasks)

    # Save results
    saved_results = []
    for r in results:
        cr = CompareResult(
            compare_run_id=compare_run.id,
            model=r["model"],
            response=r.get("response", ""),
            prompt_tokens=r.get("prompt_tokens", 0),
            completion_tokens=r.get("completion_tokens", 0),
            latency_ms=r.get("latency_ms", 0),
            estimated_cost_usd=r.get("estimated_cost_usd", 0.0),
            error=r.get("error"),
        )
        session.add(cr)
        session.commit()
        session.refresh(cr)
        saved_results.append({
            "id": str(cr.id),
            "model": cr.model,
            "response": cr.response,
            "prompt_tokens": cr.prompt_tokens,
            "completion_tokens": cr.completion_tokens,
            "latency_ms": cr.latency_ms,
            "estimated_cost_usd": cr.estimated_cost_usd,
            "error": cr.error,
        })

    return {
        "compare_run_id": str(compare_run.id),
        "prompt_version_id": version_id,
        "results": saved_results,
        "created_at": compare_run.created_at.isoformat(),
    }


@router.get("/")
def list_compare_runs(limit: int = 20, session: Session = Depends(get_session)):
    runs = session.exec(
        select(CompareRun).order_by(CompareRun.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "prompt_version_id": str(r.prompt_version_id),
            "models": r.models,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/{run_id}")
def get_compare_run(run_id: str, session: Session = Depends(get_session)):
    run = session.get(CompareRun, UUID(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Compare run not found")

    results = session.exec(
        select(CompareResult).where(CompareResult.compare_run_id == run.id)
    ).all()

    return {
        "id": str(run.id),
        "prompt_version_id": str(run.prompt_version_id),
        "models": run.models,
        "variables": run.variables,
        "created_at": run.created_at.isoformat(),
        "results": [
            {
                "id": str(r.id), "model": r.model, "response": r.response,
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "latency_ms": r.latency_ms, "estimated_cost_usd": r.estimated_cost_usd,
                "error": r.error,
            }
            for r in results
        ],
    }
