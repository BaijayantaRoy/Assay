"""``/v1/workspace`` — one call describing the whole workspace.

The dashboard used to read three legacy endpoints and show four counters: projects,
prompts, versions, evaluations. It had no idea harnesses, loops, memory, red-teaming,
calibration, governance or the token economy existed, so the first screen of the product
described a version of it that stopped being accurate months ago.

This is the replacement. One request, everything, because a dashboard that fires nine
requests is a dashboard that renders in nine stages.

Two rules shape the shape of this response.

**An empty workspace is a state, not a score.** Zero verified harnesses out of zero
harnesses is not a failing grade — it means nothing has been written yet, and saying "0%"
would be the same dishonesty this project refuses everywhere else. Every section carries
its own denominator, and ``status`` distinguishes ``empty`` from ``attention``.

**Nothing here runs anything.** The dashboard is read-only by construction: it inspects
files and cached state. Loading a page must never execute an agent, spend money, or write
to memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from assay_core import Runtime, Workspace, calibration, disclosure
from assay_core.governance import AuditLog

from .router import get_runtime, get_store, get_workspace

router = APIRouter(prefix="/v1/workspace", tags=["v1 · workspace"])


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value or None


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _inventory(store) -> dict:
    """What is actually in this workspace, by kind."""
    kinds: dict[str, int] = {}
    namespaces: dict[str, int] = {}
    statuses: dict[str, int] = {}
    with_evals = 0
    unreadable: list[dict] = []

    ids = list(store.list())
    for prompt_id in ids:
        try:
            artifact = store.get(prompt_id)
        except Exception as exc:
            # A file that will not parse is the most useful thing this page can tell
            # someone, so it is surfaced rather than skipped.
            unreadable.append({"id": prompt_id, "error": str(exc)[:200]})
            continue

        kind = "harness" if artifact.is_harness else "loop" if artifact.is_loop else artifact.kind
        kinds[kind] = kinds.get(kind, 0) + 1
        namespaces[artifact.id.split("/")[0] if "/" in artifact.id else "(root)"] = (
            namespaces.get(artifact.id.split("/")[0] if "/" in artifact.id else "(root)", 0) + 1
        )
        statuses[artifact.status or "unset"] = statuses.get(artifact.status or "unset", 0) + 1
        if artifact.evals:
            with_evals += 1

    total = len(ids) - len(unreadable)
    return {
        "total": total,
        "kinds": kinds,
        "namespaces": namespaces,
        "statuses": statuses,
        "with_evals": with_evals,
        "without_evals": max(0, total - with_evals),
        "unreadable": unreadable,
        "status": "empty" if total == 0 else ("attention" if unreadable else "ok"),
    }


def _coverage(store) -> dict:
    """How much of this workspace can actually be checked.

    An artifact with no eval cases is not tested by anything. That is a legitimate
    choice, but it should be visible rather than implied by a green tick elsewhere.
    """
    total = 0
    tested = 0
    untested: list[str] = []
    for prompt_id in store.list():
        try:
            artifact = store.get(prompt_id)
        except Exception:
            continue
        total += 1
        if artifact.evals:
            tested += 1
        else:
            untested.append(artifact.id)

    return {
        "total": total,
        "tested": tested,
        # Deliberately null rather than 0.0 when there is nothing to measure. A ratio
        # with an empty denominator is not zero, it is undefined, and the UI renders the
        # difference.
        "ratio": round(tested / total, 4) if total else None,
        "untested": sorted(untested)[:20],
        "status": "empty" if total == 0 else ("ok" if tested == total else "attention"),
    }


def _calibration(store) -> dict:
    """Which judges carry a certificate, and whether it is still in date."""
    judges: list[dict] = []
    for prompt_id in store.list():
        try:
            artifact = store.get(prompt_id)
        except Exception:
            continue
        certificate = artifact.data.get("calibration")
        uses_judge = any(
            (assertion.get("type") or "").startswith("llm_judge")
            for case in (artifact.evals or [])
            for assertion in (case.get("assert") or [])
        )
        if not certificate and not uses_judge:
            continue
        certified, reason = calibration.is_certified(artifact)
        judges.append({
            "id": artifact.id,
            "certified": bool(certified),
            "reason": reason,
            "uses_judge": uses_judge,
        })

    uncertified = [j for j in judges if j["uses_judge"] and not j["certified"]]
    return {
        "judges": judges,
        "certified": sum(1 for j in judges if j["certified"]),
        "uncertified_in_use": len(uncertified),
        "status": (
            "empty" if not judges
            else "attention" if uncertified
            else "ok"
        ),
        # The reason this section exists at all, stated where someone will read it.
        "note": (
            "An uncalibrated judge is a random number generator with good manners. "
            "Scores from one are not evidence."
        ),
    }


def _security(workspace: Workspace) -> dict:
    """Last red-team result, if one has ever been run and recorded.

    Never runs an attack. Red-teaming costs money and time; a dashboard that launched it
    on page load would be a bill nobody asked for.
    """
    path = workspace.root / ".assay" / "redteam" / "latest.json"
    if not path.exists():
        return {
            "status": "empty",
            "note": "No red-team run recorded. Run `assay redteam <harness-id>` to measure "
                    "the defences against the shipped injection corpus.",
        }
    import json
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "attention", "note": f"Recorded report is unreadable: {exc}"}

    usable = bool(report.get("usable", False))
    return {
        "status": "ok" if usable and report.get("passed") else "attention",
        "usable": usable,
        # Withheld rather than shown when the run produced nothing. A 0% attack-success
        # rate from a run where every attack errored is the most dangerous number here.
        "attack_success_rate": report.get("attack_success_rate") if usable else None,
        "detection_rate": report.get("detection_rate") if usable else None,
        "mode": report.get("mode"),
        "mode_note": report.get("mode_note"),
        "created_at": report.get("created_at"),
        "harness_id": report.get("harness_id"),
        "note": None if usable else (
            f"The last run produced no usable result — {report.get('errored', 0)} attacks "
            "errored before they could be scored, so the rates are withheld."
        ),
    }


def _economy(runtime: Runtime, store) -> dict:
    """Token cost of the index versus loading everything."""
    artifacts = []
    for prompt_id in store.list():
        try:
            artifacts.append(store.get(prompt_id))
        except Exception:
            continue
    try:
        report = disclosure.workspace_report(artifacts)
    except Exception as exc:
        return {"status": "attention", "note": str(exc)[:200]}

    index = report.get("index", report)
    return {
        "status": "empty" if not report.get("prompts") else "ok",
        "prompts": report.get("prompts", 0),
        "index_tokens": index.get("index_tokens", 0),
        "full_tokens": index.get("full_tokens", 0),
        "saving_ratio": index.get("saving_ratio"),
        "over_budget": index.get("index_tokens", 0) > index.get("budget_tokens", 0),
    }


def _spend(workspace: Workspace) -> dict:
    """What has actually been spent, from the audit log — never an estimate."""
    log = AuditLog(workspace.root / ".assay" / "audit")
    stats = log.stats()
    enabled = bool((workspace.config.get("governance") or {}).get("audit"))
    return {
        "status": "empty" if not stats.get("records") else "ok",
        "audit_enabled": enabled,
        "records": stats.get("records", 0),
        "total_cost_usd": stats.get("total_cost_usd", 0.0),
        "oldest": _iso(stats.get("oldest")),
        "newest": _iso(stats.get("newest")),
        "note": None if enabled else (
            "Auditing is off. Runs are not being recorded, so spend and history are "
            "unavailable. Enable it in assay.yaml under governance.audit."
        ),
    }


def _plugins() -> dict:
    from assay_core import get_registry

    described = get_registry().describe()
    failures = [
        {"group": group, "name": entry["name"], "error": entry["error"]}
        for group, entries in described.items()
        for entry in entries
        if entry.get("error")
    ]
    return {
        "status": "attention" if failures else "ok",
        "groups": {group: len(entries) for group, entries in described.items()},
        "total": sum(len(entries) for entries in described.values()),
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------


@router.get("/health", summary="Everything the dashboard needs, in one call")
def workspace_health(
    workspace: Workspace = Depends(get_workspace),
    runtime: Runtime = Depends(get_runtime),
    store=Depends(get_store),
) -> dict:
    """A read-only picture of the whole workspace.

    Sections each carry their own ``status``: ``ok``, ``attention``, or ``empty``.
    ``empty`` is not a failure — it means the workspace has nothing of that kind yet, and
    the UI shows guidance instead of a zero.
    """
    sections = {
        "inventory": _inventory(store),
        "coverage": _coverage(store),
        "calibration": _calibration(store),
        "security": _security(workspace),
        "economy": _economy(runtime, store),
        "spend": _spend(workspace),
        "plugins": _plugins(),
    }

    attention = [name for name, s in sections.items() if s.get("status") == "attention"]
    empty = [name for name, s in sections.items() if s.get("status") == "empty"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": {
            "name": workspace.config.get("name") or workspace.root.name,
            "root": str(workspace.root),
            "default_model": (workspace.config.get("defaults") or {}).get("model"),
        },
        # True when the workspace has no artifacts at all — the UI swaps the whole page
        # for guided first steps rather than showing a grid of zeros.
        "is_new": sections["inventory"]["total"] == 0,
        "needs_attention": attention,
        "not_yet_used": empty,
        **sections,
    }
