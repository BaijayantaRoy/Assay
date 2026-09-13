"""
Evaluation Router — Phase B:
  - /datasets/                 CRUD datasets
  - /datasets/{id}/rows        Add rows (bulk or single)
  - /datasets/{id}/rows/upload Upload CSV
  - /evaluations/run           Launch evaluation run
  - /evaluations/{id}          Get run status + results
  - /evaluations/{id}/annotate Human annotation (thumbs up/down)
  - /evaluations/compare       Multi-model comparison run
"""

import csv
import io
import re
import json
import math
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlmodel import Session, select

from ...database import get_session
from ...models import (
    Dataset, DatasetRow, EvaluationRun, EvaluationResult,
    PromptVersion,
)
from ...services.llm_service import run_llm

router = APIRouter(prefix="/datasets", tags=["evaluation"])


# ─── Dataset CRUD ────────────────────────────────────────────────────────

@router.get("/")
def list_datasets(project_id: Optional[UUID] = None, session: Session = Depends(get_session)):
    q = select(Dataset).order_by(Dataset.created_at.desc())
    if project_id:
        q = q.where(Dataset.project_id == project_id)
    return session.exec(q).all()


@router.post("/")
def create_dataset(body: dict, session: Session = Depends(get_session)):
    ds = Dataset(
        project_id=body["project_id"],
        name=body["name"],
        description=body.get("description"),
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)
    return ds


@router.get("/{dataset_id}")
def get_dataset(dataset_id: UUID, session: Session = Depends(get_session)):
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    rows = session.exec(select(DatasetRow).where(DatasetRow.dataset_id == dataset_id)).all()
    return {**ds.model_dump(), "rows": [r.model_dump() for r in rows]}


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: UUID, session: Session = Depends(get_session)):
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Delete rows first
    rows = session.exec(select(DatasetRow).where(DatasetRow.dataset_id == dataset_id)).all()
    for r in rows:
        session.delete(r)
    session.delete(ds)
    session.commit()
    return {"deleted": True}


# ─── Dataset Rows ────────────────────────────────────────────────────────

@router.post("/{dataset_id}/rows")
def add_rows(dataset_id: UUID, body: dict, session: Session = Depends(get_session)):
    """
    Add one or more rows.
    Body: { "rows": [{"inputs": {}, "expected_output": "..."}] }
    """
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    rows_data = body.get("rows", [body])  # single row or list
    created = []
    for r in rows_data:
        row = DatasetRow(
            dataset_id=dataset_id,
            inputs=r.get("inputs", {}),
            expected_output=r.get("expected_output"),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        created.append(row)
    return created


@router.post("/{dataset_id}/rows/upload")
def upload_csv(
    dataset_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Upload a CSV file as dataset rows.
    Columns: any variable names + optional 'expected_output'
    """
    ds = session.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    added = 0
    for row_dict in reader:
        expected = row_dict.pop("expected_output", None)
        row = DatasetRow(
            dataset_id=dataset_id,
            inputs=dict(row_dict),
            expected_output=expected,
        )
        session.add(row)
        added += 1

    session.commit()
    return {"added": added}


# ─── Evaluation Runs ─────────────────────────────────────────────────────

def _extract_variables(content: str):
    return list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", content)))


def _parse_judge_response(response: str) -> tuple[float, str]:
    """Parse a judge response without inventing a neutral score on failure."""

    payload = json.loads(response)
    if "score" not in payload:
        raise ValueError("judge response omitted score")
    score = float(payload["score"])
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("judge score must be a finite number between 0 and 1")
    return score, str(payload.get("reasoning") or "")


def _run_evaluation_background(
    run_id: str,
    version_id: str,
    dataset_id: Optional[str],
    evaluator_type: str,
    judge_model: str,
    params: dict,
):
    """Background task: run evaluation for all dataset rows."""
    from ...database import engine
    from sqlmodel import Session as S

    with S(engine) as session:
        run = session.get(EvaluationRun, UUID(run_id))
        version = session.get(PromptVersion, UUID(version_id))

        if not run or not version:
            return

        run.status = "running"
        session.add(run)
        session.commit()

        rows = []
        if dataset_id:
            rows = session.exec(
                select(DatasetRow).where(DatasetRow.dataset_id == UUID(dataset_id))
            ).all()
        else:
            # If no dataset, run once with empty variables
            rows = [None]

        completed = 0
        errors = 0
        scores = []

        for row in rows:
            inputs = row.inputs if row else {}
            expected = row.expected_output if row else None

            generation_error = None
            try:
                result = run_llm(
                    model=params.get("model", "gpt-4o-mini"),
                    content=version.content,
                    variables=inputs,
                    params=params,
                )
                output = result["response"]
                rendered = result["rendered_prompt"]
                prompt_tokens = result["prompt_tokens"]
                completion_tokens = result["completion_tokens"]
                cost = result["estimated_cost_usd"]
                model_used = result["model"]
            except Exception as e:
                output = f"ERROR: {str(e)}"
                generation_error = f"Generation failed: {type(e).__name__}: {e}"
                rendered = version.content
                prompt_tokens = completion_tokens = 0
                cost = 0.0
                model_used = params.get("model", "unknown")

            score = None
            reasoning = None

            if generation_error:
                errors += 1
                reasoning = generation_error

            # LLM-as-Judge evaluation
            elif evaluator_type == "llm_judge" and expected is not None:
                judge_prompt = f"""You are an evaluator. Score how well the AI response matches the expected output.

Expected: {expected}
Actual: {output}

Rate the response from 0.0 to 1.0 where:
1.0 = Perfect match or semantically equivalent
0.7 = Mostly correct with minor differences
0.5 = Partially correct
0.3 = Mostly incorrect but some relevance
0.0 = Completely wrong

Respond with JSON: {{"score": 0.85, "reasoning": "explanation"}}"""
                try:
                    judge_result = run_llm(
                        model=judge_model,
                        content=judge_prompt,
                        variables={},
                        params={"temperature": 0.1, "max_tokens": 200},
                    )
                    score, reasoning = _parse_judge_response(judge_result["response"])
                except Exception as exc:
                    errors += 1
                    score = None
                    reasoning = f"Judge evaluation failed: {type(exc).__name__}: {exc}"

            elif evaluator_type == "exact_match" and expected is not None:
                score = 1.0 if output.strip() == expected.strip() else 0.0
                reasoning = "Exact match" if score == 1.0 else "No match"

            result_row = EvaluationResult(
                evaluation_run_id=UUID(run_id),
                dataset_row_id=row.id if row else None,
                rendered_prompt=rendered,
                output=output,
                score=score,
                reasoning=reasoning,
                model=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=cost,
            )
            session.add(result_row)
            session.commit()

            if score is not None:
                scores.append(score)
            completed += 1

            run.completed_rows = completed
            session.add(run)
            session.commit()

        run.status = "failed" if errors else "completed"
        run.avg_score = (sum(scores) / len(scores)) if scores else None
        run.total_rows = len(rows)
        from datetime import datetime, timezone
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()


eval_router = APIRouter(prefix="/evaluations", tags=["evaluation"])


@eval_router.post("/run")
def start_evaluation(
    body: dict,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Start an evaluation run.
    Body:
      {
        "prompt_version_id": "uuid",
        "dataset_id": "uuid",         # optional
        "evaluator_type": "llm_judge", # llm_judge | human | exact_match
        "judge_model": "gpt-4o-mini", # model for LLM-as-Judge
        "model": "gpt-4o",            # model for running the prompt
        "temperature": 0.7,
        "max_tokens": 1024
      }
    """
    version_id = body.get("prompt_version_id")
    dataset_id = body.get("dataset_id")
    evaluator_type = body.get("evaluator_type", "llm_judge")
    judge_model = body.get("judge_model", "gpt-4o-mini")

    version = session.get(PromptVersion, UUID(version_id))
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if dataset_id:
        ds = session.get(Dataset, UUID(dataset_id))
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
        row_count = len(session.exec(select(DatasetRow).where(DatasetRow.dataset_id == UUID(dataset_id))).all())
    else:
        row_count = 1

    run = EvaluationRun(
        prompt_version_id=UUID(version_id),
        dataset_id=UUID(dataset_id) if dataset_id else None,
        evaluator_type=evaluator_type,
        status="queued",
        total_rows=row_count,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    params = {
        "model": body.get("model", "gpt-4o-mini"),
        "temperature": body.get("temperature", 0.7),
        "max_tokens": body.get("max_tokens", 1024),
    }

    background_tasks.add_task(
        _run_evaluation_background,
        str(run.id), str(version_id), dataset_id,
        evaluator_type, judge_model, params,
    )

    return run


@eval_router.get("/{run_id}")
def get_evaluation_run(run_id: UUID, session: Session = Depends(get_session)):
    """Get run status and all results."""
    run = session.get(EvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    results = session.exec(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run_id)
    ).all()
    return {**run.model_dump(), "results": [r.model_dump() for r in results]}


@eval_router.get("/")
def list_evaluation_runs(
    prompt_version_id: Optional[UUID] = None,
    session: Session = Depends(get_session),
):
    q = select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    if prompt_version_id:
        q = q.where(EvaluationRun.prompt_version_id == prompt_version_id)
    return session.exec(q).all()


@eval_router.post("/{run_id}/annotate/{result_id}")
def annotate_result(
    run_id: UUID,
    result_id: UUID,
    body: dict,
    session: Session = Depends(get_session),
):
    """
    Human annotation on a single result.
    Body: {"annotation": "thumbs_up" | "thumbs_down"}
    """
    result = session.get(EvaluationResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    annotation = body.get("annotation")
    if annotation not in ["thumbs_up", "thumbs_down", None]:
        raise HTTPException(status_code=400, detail="Invalid annotation")

    result.human_annotation = annotation
    # Map to score
    if annotation == "thumbs_up":
        result.score = 1.0
    elif annotation == "thumbs_down":
        result.score = 0.0

    session.add(result)
    session.commit()
    session.refresh(result)
    return result


@eval_router.post("/compare")
def compare_models(
    body: dict,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Run the same prompt version against multiple models in parallel.
    Body:
      {
        "prompt_version_id": "uuid",
        "models": ["gpt-4o", "claude-sonnet-4-20250514", "gemini-2.5-flash"],
        "dataset_id": "uuid",   # optional
        "variables": {},        # optional — single test
        "params": {}
      }
    """
    version_id = body.get("prompt_version_id")
    models = body.get("models", ["gpt-4o-mini"])
    dataset_id = body.get("dataset_id")

    version = session.get(PromptVersion, UUID(version_id))
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Create a run per model
    runs = []
    params = body.get("params", {})
    for model in models:
        run = EvaluationRun(
            prompt_version_id=UUID(version_id),
            dataset_id=UUID(dataset_id) if dataset_id else None,
            evaluator_type="llm_judge",
            status="queued",
            total_rows=1,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        merged_params = {**params, "model": model}
        background_tasks.add_task(
            _run_evaluation_background,
            str(run.id), version_id, dataset_id,
            "llm_judge", params.get("judge_model", "gpt-4o-mini"), merged_params,
        )
        runs.append(run)

    return {"runs": [r.model_dump() for r in runs], "models": models}
