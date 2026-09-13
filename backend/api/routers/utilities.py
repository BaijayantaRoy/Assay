"""
Utilities Router — Phase A+B:
  - /models           → list available LLM models
  - /stats            → dashboard stats
  - /playground/run   → REAL LLM execution with token tracking
  - /prompts/{id}/diff          → side-by-side version diff
  - /prompts/{id}/environment   → pin version to environment
  - /prompts/{id}/export        → export prompt as JSON
  - /projects/{id}/export       → export project as JSON
  - /projects/{id}/import       → import prompts from JSON
  - /run-logs         → retrieve production run logs
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func
from typing import Optional
from uuid import UUID
import json
import re
import difflib

from ...database import get_session
from ...models import (
    Prompt, PromptVersion, Project, Organization,
    EvaluationRun, RunLog, Dataset
)
from ...services.llm_service import run_llm

router = APIRouter(tags=["utilities"])



# ─── Stats ────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(session: Session = Depends(get_session)):
    """Dashboard statistics."""
    prompt_count = session.exec(select(func.count(Prompt.id))).one()
    project_count = session.exec(select(func.count(Project.id))).one()
    version_count = session.exec(select(func.count(PromptVersion.id))).one()
    eval_count = session.exec(select(func.count(EvaluationRun.id))).one()
    run_log_count = session.exec(select(func.count(RunLog.id))).one()
    dataset_count = session.exec(select(func.count(Dataset.id))).one()

    # Cost this month
    total_cost = session.exec(
        select(func.sum(RunLog.estimated_cost_usd))
    ).one() or 0.0

    return {
        "prompts": prompt_count,
        "projects": project_count,
        "versions": version_count,
        "evaluations": eval_count,
        "runs": run_log_count,
        "datasets": dataset_count,
        "total_cost_usd": round(total_cost, 4),
    }


# ─── Playground (REAL LLM execution) ─────────────────────────────────

@router.post("/playground/run")
def run_playground(
    body: dict,
    session: Session = Depends(get_session),
):
    """
    Execute a prompt through a real LLM.

    Body:
      {
        "content": "...",               # optional — uses version content if omitted
        "prompt_version_id": "uuid",    # optional
        "model": "gpt-4o",             # required
        "variables": {"key": "val"},    # optional
        "params": {                     # optional model params
            "temperature": 0.7,
            "max_tokens": 1024,
            "top_p": 1.0
        },
        "save_log": true               # optional — persist to run_logs table
      }
    """
    content = body.get("content")
    version_id = body.get("prompt_version_id")
    model = body.get("model", "gpt-4o-mini")
    variables = body.get("variables", {})
    params = body.get("params", {})
    save_log = body.get("save_log", False)

    # Load content from version if not provided directly
    if not content and version_id:
        version = session.get(PromptVersion, version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        content = version.content
        # Merge version config with request params (request wins)
        merged_params = {**version.config, **params}
        params = merged_params

    if not content:
        raise HTTPException(status_code=400, detail="No content provided")

    try:
        result = run_llm(model=model, content=content, variables=variables, params=params)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Optionally persist the run log
    if save_log and version_id:
        log = RunLog(
            prompt_version_id=UUID(str(version_id)),
            rendered_prompt=result["rendered_prompt"],
            response=result["response"],
            model=result["model"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            latency_ms=result["latency_ms"],
            estimated_cost_usd=result["estimated_cost_usd"],
            variables_used=variables,
        )
        session.add(log)
        session.commit()

    return result


# ─── Prompt Diff ───────────────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/diff")
def diff_versions(
    prompt_id: UUID,
    v1: int,
    v2: int,
    session: Session = Depends(get_session),
):
    """
    Return a unified diff between two version numbers.
    Query params: ?v1=1&v2=3
    """
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    versions = session.exec(
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id)
        .where(PromptVersion.version_number.in_([v1, v2]))
    ).all()

    by_num = {v.version_number: v for v in versions}
    if v1 not in by_num or v2 not in by_num:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    a_lines = by_num[v1].content.splitlines(keepends=True)
    b_lines = by_num[v2].content.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        a_lines, b_lines,
        fromfile=f"v{v1}",
        tofile=f"v{v2}",
        lineterm="",
    ))

    # Also return side-by-side for frontend rendering
    table = list(difflib.ndiff(a_lines, b_lines))

    return {
        "unified_diff": "".join(diff_lines),
        "ndiff": table,
        "v1": {"number": v1, "content": by_num[v1].content, "commit_message": by_num[v1].commit_message},
        "v2": {"number": v2, "content": by_num[v2].content, "commit_message": by_num[v2].commit_message},
    }


# ─── Environments ─────────────────────────────────────────────────────

@router.post("/prompts/{prompt_id}/environment")
def set_environment(
    prompt_id: UUID,
    body: dict,
    session: Session = Depends(get_session),
):
    """
    Pin a version to an environment.
    Body: {"environment": "production", "version_id": "uuid"}
    Valid environments: development, staging, production
    """
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    env = body.get("environment")
    version_id = body.get("version_id")

    valid_envs = ["development", "staging", "production"]
    if env not in valid_envs:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid environment. Must be one of: {valid_envs}"
        )

    version = session.get(PromptVersion, version_id)
    if not version or str(version.prompt_id) != str(prompt_id):
        raise HTTPException(status_code=404, detail="Version not found")

    pins = dict(prompt.environment_pins or {})
    pins[env] = str(version_id)
    prompt.environment_pins = pins
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return {"environment_pins": prompt.environment_pins}


@router.get("/prompts/{prompt_id}/environment/{env}")
def get_environment_version(
    prompt_id: UUID,
    env: str,
    session: Session = Depends(get_session),
):
    """
    Fetch the version pinned to a specific environment.
    This is used by external apps to dynamically load prompt versions.
    """
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    pins = prompt.environment_pins or {}
    version_id = pins.get(env)
    if not version_id:
        # Fall back to latest
        if not prompt.latest_version_id:
            raise HTTPException(status_code=404, detail=f"No version pinned to '{env}'")
        version_id = str(prompt.latest_version_id)

    version = session.get(PromptVersion, UUID(version_id))
    if not version:
        raise HTTPException(status_code=404, detail="Pinned version not found")

    return version


# ─── Run Logs ─────────────────────────────────────────────────────────

@router.get("/run-logs")
def list_run_logs(
    prompt_version_id: Optional[UUID] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    """List production run logs, optionally filtered by version."""
    q = select(RunLog).order_by(RunLog.created_at.desc()).limit(limit)
    if prompt_version_id:
        q = q.where(RunLog.prompt_version_id == prompt_version_id)
    return session.exec(q).all()


# ─── Export ───────────────────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/export")
def export_prompt(prompt_id: UUID, session: Session = Depends(get_session)):
    """Export a single prompt with all versions as JSON."""
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    versions = session.exec(
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version_number.asc())
    ).all()

    export_data = {
        "format": "assay/v2",
        "prompt": {
            "name": prompt.name,
            "description": prompt.description,
            "tags": prompt.tags,
            "environment_pins": prompt.environment_pins,
        },
        "versions": [
            {
                "version_number": v.version_number,
                "content": v.content,
                "config": v.config,
                "variables": v.variables,
                "commit_message": v.commit_message,
                "environment": v.environment,
            }
            for v in versions
        ],
    }

    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{prompt.name.replace(" ", "_")}.json"'
        },
    )


@router.get("/projects/{project_id}/export")
def export_project(project_id: UUID, session: Session = Depends(get_session)):
    """Export an entire project with all prompts and versions as JSON."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    prompts = session.exec(
        select(Prompt).where(Prompt.project_id == project_id)
    ).all()

    exported_prompts = []
    for prompt in prompts:
        versions = session.exec(
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt.id)
            .order_by(PromptVersion.version_number.asc())
        ).all()

        exported_prompts.append({
            "name": prompt.name,
            "description": prompt.description,
            "tags": prompt.tags,
            "environment_pins": prompt.environment_pins,
            "versions": [
                {
                    "version_number": v.version_number,
                    "content": v.content,
                    "config": v.config,
                    "variables": v.variables,
                    "commit_message": v.commit_message,
                    "environment": v.environment,
                }
                for v in versions
            ],
        })

    export_data = {
        "format": "assay/v2",
        "project": {"name": project.name, "description": project.description},
        "prompts": exported_prompts,
    }

    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{project.name.replace(" ", "_")}_export.json"'
        },
    )


# ─── Import ───────────────────────────────────────────────────────────

def _extract_variables(content: str) -> list:
    return list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", content)))


@router.post("/projects/{project_id}/import")
def import_prompts(
    project_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Import prompts from a JSON file into a project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        raw = file.file.read()
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    prompts_to_import = []
    if "prompts" in data:
        prompts_to_import = data["prompts"]
    elif "prompt" in data:
        p = dict(data["prompt"])
        if "versions" not in p and "versions" in data:
            p["versions"] = data["versions"]
        prompts_to_import = [p]
    else:
        raise HTTPException(status_code=400, detail="JSON must contain 'prompt' or 'prompts' key")

    imported_count = 0
    for pdata in prompts_to_import:
        new_prompt = Prompt(
            name=pdata.get("name", "Imported Prompt"),
            description=pdata.get("description"),
            project_id=project_id,
            tags=pdata.get("tags", []),
            environment_pins=pdata.get("environment_pins", {}),
        )
        session.add(new_prompt)
        session.commit()
        session.refresh(new_prompt)

        last_version = None
        for vdata in pdata.get("versions", []):
            content = vdata.get("content", "")
            new_version = PromptVersion(
                prompt_id=new_prompt.id,
                version_number=vdata.get("version_number", 1),
                content=content,
                config=vdata.get("config", {}),
                variables=_extract_variables(content),
                commit_message=vdata.get("commit_message", "Imported"),
                environment=vdata.get("environment", "development"),
            )
            session.add(new_version)
            session.commit()
            session.refresh(new_version)
            last_version = new_version

        if last_version:
            new_prompt.latest_version_id = last_version.id
            session.add(new_prompt)
            session.commit()

        imported_count += 1

    return {"imported": imported_count}
