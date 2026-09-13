"""``/v1/packs`` — the starter catalogue, and installing from it.

The Starter Library page was broken in a way worth recording: 23 starter prompts existed
in ``backend/api/routers/library.py`` as Python dicts, and the page fetched
``/prompts/all`` instead — the user's own database, empty on a fresh install. So the
library was always empty, and the content it was meant to show was unreachable by any
surface.

Fixing the fetch would have been the smaller repair. The starters are now real
PromptFiles in ``packs/`` instead, which means they validate against the published spec,
carry their own eval cases, are reviewable in a pull request, and can be listed by
``assay ls`` once installed. A starter that is not itself a PromptFile teaches the wrong
thing about the format on the first screen a newcomer sees.

Installing copies files into the workspace. Nothing is templated or rewritten — what you
read in the catalogue is what lands on disk.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from assay_core import PromptFile, Workspace
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .router import get_workspace

router = APIRouter(prefix="/v1/packs", tags=["v1 · packs"])
PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _packs_root() -> Path:
    """Repository ``packs/`` directory. Ships with the distribution, read-only."""
    return Path(__file__).resolve().parents[3] / "packs"


def _pack_dir(pack_id: str) -> Path:
    root = _packs_root().resolve()
    if not PACK_ID_RE.fullmatch(pack_id):
        raise HTTPException(404, {"code": "assay.pack_not_found",
                                  "message": f"no pack named {pack_id!r}"})
    directory = (root / pack_id).resolve()
    if directory.parent != root or not directory.is_dir():
        raise HTTPException(404, {"code": "assay.pack_not_found",
                                  "message": f"no pack named {pack_id!r}"})
    return directory


class InstallRequest(BaseModel):
    ids: list[str] = Field(default_factory=list,
                           description="Artifact ids to install. Empty means the whole pack.")
    overwrite: bool = Field(False, description="Replace files that already exist.")


def _read_pack(directory: Path) -> dict:
    items, unreadable = [], []
    for path in sorted(directory.glob("*.prompt.*")):
        try:
            artifact = PromptFile.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:
            unreadable.append({"file": path.name, "error": str(exc)[:200]})
            continue
        items.append({
            "pack_id": directory.name,
            "id": artifact.id,
            "name": artifact.name,
            # `summary` and `description` are spec fields, not attributes on the parser —
            # they live in `.data` so unknown keys round-trip untouched.
            "summary": artifact.data.get("summary") or artifact.data.get("description") or "",
            "kind": "harness" if artifact.is_harness else "loop" if artifact.is_loop else artifact.kind,
            "tags": artifact.tags,
            "status": artifact.status,
            "variables": sorted(artifact.template_variables()),
            "has_evals": bool(artifact.evals),
            "eval_scope": artifact.data.get("x-assay-eval-scope") or "unspecified",
            "file": path.name,
            "body_preview": artifact.body.strip()[:400],
        })

    categories: dict[str, int] = {}
    for item in items:
        namespace = item["id"].split("/")[0] if "/" in item["id"] else "misc"
        categories[namespace] = categories.get(namespace, 0) + 1

    return {
        "id": directory.name,
        "name": directory.name.replace("-", " ").title(),
        "count": len(items),
        "categories": categories,
        "items": items,
        "unreadable": unreadable,
    }


@router.get("", summary="List available starter packs")
def list_packs() -> dict:
    root = _packs_root()
    if not root.exists():
        return {"packs": [], "total": 0}
    packs = [_read_pack(d) for d in sorted(root.iterdir()) if d.is_dir()]
    return {"packs": packs, "total": sum(p["count"] for p in packs)}


@router.get("/{pack_id}", summary="One pack in full")
def get_pack(pack_id: str) -> dict:
    return _read_pack(_pack_dir(pack_id))


@router.post("/{pack_id}/install", summary="Copy pack artifacts into this workspace")
def install_pack(
    pack_id: str,
    payload: InstallRequest,
    workspace: Workspace = Depends(get_workspace),
) -> dict:
    """Copy selected artifacts into the workspace prompts directory.

    Existing files are skipped rather than overwritten unless asked. Silently replacing
    something a user wrote would be the worst possible behaviour for a button labelled
    "install".
    """
    directory = _pack_dir(pack_id)

    target = workspace.root / (workspace.config.get("prompts") or "prompts")
    target.mkdir(parents=True, exist_ok=True)

    wanted = set(payload.ids)
    installed, skipped, failed = [], [], []

    for path in sorted(directory.glob("*.prompt.*")):
        try:
            artifact = PromptFile.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failed.append({"file": path.name, "error": str(exc)[:200]})
            continue
        if wanted and artifact.id not in wanted:
            continue

        destination = target / path.name
        if destination.exists() and not payload.overwrite:
            skipped.append({"id": artifact.id, "reason": "already exists"})
            continue
        try:
            shutil.copy2(path, destination)
            installed.append({"id": artifact.id, "path": str(destination.relative_to(workspace.root))})
        except Exception as exc:
            failed.append({"file": path.name, "error": str(exc)[:200]})

    return {
        "pack": pack_id,
        "installed": installed,
        "skipped": skipped,
        "failed": failed,
        "counts": {"installed": len(installed), "skipped": len(skipped), "failed": len(failed)},
        "note": (
            "Nothing was overwritten. Re-run with overwrite=true to replace existing files."
            if skipped and not payload.overwrite else None
        ),
    }
