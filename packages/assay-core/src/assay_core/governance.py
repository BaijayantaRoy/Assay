"""Audit logging and regulatory control mapping.

Why this exists
---------------
EU AI Act obligations for high-risk systems were due on 2 August 2026; the Digital Omnibus
(Regulation (EU) 2026/1744) moved them to **2 December 2027** for stand-alone Annex III
systems and **2 August 2028** for systems embedded in Annex I products. They require
automatic logging of events across a system's lifetime, with deployers retaining those
logs for **at least six months**. ISO 42001 supplies the management-system
scaffolding; NIST AI RMF is voluntary but shows up in procurement.

This project already had most of what an auditor wants and never said so. Prompts live in
git, so change history, authorship and review are inherent — arguably a better substrate
than a vendor's version table, because it is inspectable without the vendor. What was
missing was the *run* side: which artifact ran, when, at what cost, with what outcome.

What this module is, and is not
-------------------------------
It is an append-only JSONL run log plus a mapping from repository artifacts to framework
clauses. It is **not** a compliance product and does not make anything compliant. It
produces evidence a human can hand to an assessor, and names the gaps it cannot fill.

Content is deliberately excluded by default. A six-month log of every prompt and
completion is a data-protection liability, not an asset; the log records *that* a run
happened and what it cost, not what was said. Set ``governance.log_content: true`` if a
specific obligation requires it, and understand what you are then storing.
"""

from __future__ import annotations

import json
import hashlib
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

#: EU AI Act Article 12 sets a six-month floor for deployer log retention.
DEFAULT_RETENTION_DAYS = 190


@dataclass(slots=True)
class AuditRecord:
    """One executed artifact. Deliberately small and non-sensitive."""

    run_id: str
    artifact_id: str
    kind: str = "prompt"
    version: int = 1
    outcome: str = ""
    model: str = ""
    provider: str = ""
    cost_usd: float = 0.0
    total_tokens: int = 0
    latency_ms: int = 0
    environment: str = ""          # environment fingerprint, not the full snapshot
    actor: str = ""                # who or what triggered it, if the caller supplies it
    deployment_id: str = ""
    #: Delivery evidence is present for streamed runs and absent for ordinary runs.
    streaming: dict[str, Any] | None = None
    timestamp: str = ""
    previous_hash: str = ""
    record_hash: str = ""
    #: Only populated when governance.log_content is explicitly enabled.
    content: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        payload = {
            "timestamp": self.timestamp, "run_id": self.run_id,
            "artifact_id": self.artifact_id, "kind": self.kind, "version": self.version,
            "outcome": self.outcome, "model": self.model, "provider": self.provider,
            "cost_usd": round(self.cost_usd, 8), "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms, "environment": self.environment,
            "actor": self.actor,
            "deployment_id": self.deployment_id,
            "previous_hash": self.previous_hash,
        }
        if self.record_hash:
            payload["record_hash"] = self.record_hash
        if self.streaming is not None:
            payload["streaming"] = self.streaming
        if self.content is not None:
            payload["content"] = self.content
        return payload


class AuditLog:
    """Append-only JSONL run log with retention.

    JSONL rather than a database for the same reason prompts are files: it is greppable,
    diffable, and readable without this tool. An audit trail nobody can read without the
    vendor's software is a weak audit trail.
    """

    def __init__(self, root: str | Path | None = None, *,
                 retention_days: int = DEFAULT_RETENTION_DAYS) -> None:
        base = root or os.getenv("ASSAY_AUDIT_ROOT") or Path.cwd() / ".assay" / "audit"
        self.root = Path(base)
        self.retention_days = retention_days

    def _path_for(self, when: datetime) -> Path:
        # One file per month keeps individual files readable and retention trivial.
        return self.root / f"runs-{when.strftime('%Y-%m')}.jsonl"

    @contextmanager
    def _locked(self):
        """Cross-process lock around chain-head read plus append."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".append.lock"
        deadline = time.monotonic() + 5.0
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > 30:
                        path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for audit append lock")
                time.sleep(0.02)
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            path.unlink(missing_ok=True)

    def append(self, record: AuditRecord) -> AuditRecord:
        now = datetime.now(timezone.utc)
        record.timestamp = record.timestamp or now.isoformat()
        path = self._path_for(now)
        with self._locked():
            latest = self.read(limit=1)
            record.previous_hash = (
                str(latest[0].get("record_hash") or "legacy-unsealed")
                if latest else "genesis"
            )
            record.record_hash = _record_hash(record.to_dict())
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return record

    def verify_chain(self) -> dict:
        """Verify every hashed record in chronological file and line order."""
        hashed = 0
        legacy = 0
        corrupt = 0
        errors: list[str] = []
        previous = "genesis"
        head = None
        if self.root.is_dir():
            for path in sorted(self.root.glob("runs-*.jsonl")):
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        corrupt += 1
                        errors.append(f"{path.name}:{number}: invalid JSON")
                        continue
                    if not payload.get("record_hash"):
                        legacy += 1
                        previous = "legacy-unsealed"
                        continue
                    expected = _record_hash(payload)
                    if payload.get("record_hash") != expected:
                        errors.append(f"{path.name}:{number}: record hash mismatch")
                    if payload.get("previous_hash") != previous:
                        errors.append(f"{path.name}:{number}: previous hash mismatch")
                    previous = str(payload.get("record_hash"))
                    head = previous
                    hashed += 1
        valid: bool | None
        if errors:
            valid = False
        elif not hashed and not legacy:
            valid = None
        elif legacy:
            valid = None
        else:
            valid = True
        return {
            "valid": valid,
            "status": "invalid" if valid is False else "verified" if valid is True else
                      "partial" if legacy else "not_checked",
            "hashed_records": hashed,
            "legacy_unsealed_records": legacy,
            "corrupt_lines": corrupt,
            "head_hash": head,
            "errors": errors,
            "note": (
                "Legacy records have no cryptographic seal; integrity is not claimed for them."
                if legacy else
                "No records were checked." if valid is None else
                "Hash chaining detects modification or removal within the available log; "
                "it does not prevent deletion of the entire log."
            ),
        }

    def read(self, *, since: datetime | None = None,
             artifact_id: str | None = None, limit: int | None = 1000) -> list[dict]:
        records: list[dict] = []
        if not self.root.is_dir():
            return records
        for path in sorted(self.root.glob("runs-*.jsonl"), reverse=True):
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue        # one corrupt line must not hide the rest
                if artifact_id and record.get("artifact_id") != artifact_id:
                    continue
                if since:
                    try:
                        stamp = datetime.fromisoformat(record.get("timestamp", ""))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        if stamp < since:
                            continue
                    except Exception:
                        pass
                records.append(record)
                if limit is not None and len(records) >= limit:
                    return records
        return records

    def stats(self) -> dict:
        records = self.read(limit=None)
        by_artifact: dict[str, int] = {}
        total_cost = 0.0
        for record in records:
            by_artifact[record.get("artifact_id", "?")] = (
                by_artifact.get(record.get("artifact_id", "?"), 0) + 1
            )
            total_cost += float(record.get("cost_usd") or 0)
        stamps = [r.get("timestamp", "") for r in records if r.get("timestamp")]
        return {
            "records": len(records),
            "artifacts": len(by_artifact),
            "total_cost_usd": round(total_cost, 6),
            "oldest": min(stamps) if stamps else None,
            "newest": max(stamps) if stamps else None,
            "retention_days": self.retention_days,
            "path": str(self.root),
            "integrity": self.verify_chain(),
        }

    def prune(self) -> int:
        """Delete whole monthly files older than the retention window.

        Retention is a *maximum* in privacy law and a *minimum* in the AI Act. Pruning is
        therefore opt-in and never automatic: deleting evidence on a schedule nobody asked
        for is its own compliance failure.
        """
        if not self.root.is_dir():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = 0
        for path in self.root.glob("runs-*.jsonl"):
            try:
                month = datetime.strptime(path.stem.replace("runs-", ""), "%Y-%m")
            except ValueError:
                continue
            # Compare against the end of that month, so a partial month is never lost.
            month_end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            if month_end.replace(tzinfo=timezone.utc) < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def _record_hash(payload: dict) -> str:
    material = {key: value for key, value in payload.items() if key != "record_hash"}
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def aggregate_audit_logs(sources: dict[str, AuditLog]) -> dict:
    """Read several deployment logs without copying or rewriting their evidence.

    Source labels identify locations, not deployments. Deployment counts are based only
    on explicit ``deployment_id`` values in records; unattributed records stay visibly
    unattributed instead of being promoted to deployments by assumption.
    """
    deployments: set[str] = set()
    run_locations: dict[str, list[str]] = {}
    source_rows: list[dict] = []
    total_records = 0
    total_cost = 0.0
    unattributed = 0
    integrity_values: list[bool | None] = []

    for label, log in sorted(sources.items()):
        records = log.read(limit=None)
        integrity = log.verify_chain()
        integrity_values.append(integrity["valid"])
        source_deployments = sorted({
            str(row.get("deployment_id")) for row in records
            if row.get("deployment_id")
        })
        deployments.update(source_deployments)
        source_cost = sum(float(row.get("cost_usd") or 0) for row in records)
        source_unattributed = sum(not bool(row.get("deployment_id")) for row in records)
        unattributed += source_unattributed
        total_records += len(records)
        total_cost += source_cost
        for row in records:
            run_id = str(row.get("run_id") or "")
            if run_id:
                run_locations.setdefault(run_id, []).append(label)
        source_rows.append({
            "source": label,
            "path": str(log.root),
            "records": len(records),
            "total_cost_usd": round(source_cost, 6),
            "identified_deployments": source_deployments,
            "unattributed_records": source_unattributed,
            "integrity": integrity,
        })

    duplicates = [
        {"run_id": run_id, "sources": locations}
        for run_id, locations in sorted(run_locations.items())
        if len(locations) > 1
    ]
    if any(value is False for value in integrity_values):
        integrity_valid: bool | None = False
    elif integrity_values and all(value is True for value in integrity_values):
        integrity_valid = True
    else:
        integrity_valid = None
    return {
        "sources": len(source_rows),
        "records": total_records,
        "total_cost_usd": round(total_cost, 6),
        "identified_deployments": len(deployments),
        "deployment_ids": sorted(deployments),
        "unattributed_records": unattributed,
        "duplicate_run_ids": duplicates,
        "integrity": {
            "valid": integrity_valid,
            "status": (
                "invalid" if integrity_valid is False else
                "verified" if integrity_valid is True else "not_fully_verified"
            ),
            "note": (
                "All supplied logs have complete valid hash chains."
                if integrity_valid is True else
                "At least one supplied log has an invalid hash chain."
                if integrity_valid is False else
                "Integrity is withheld because at least one source is empty or contains "
                "legacy unsealed records."
            ),
        },
        "source_logs": source_rows,
        "note": (
            "This is a read-only aggregation of the supplied local logs. It does not "
            "establish central retention, remote immutability, or deployment identity "
            "for records that do not declare one."
        ),
    }


ANNEX_IV_SOURCE = "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng"


def annex_iv_dossier(workspace: Any, audit: AuditLog | None = None) -> dict:
    """Build a privacy-conscious Annex IV evidence index from declared local facts.

    This is deliberately an evidence *dossier*, not a conformity declaration. Prompt
    bodies, eval inputs, outputs, and audit content are excluded from the inventory.
    """
    audit = audit or AuditLog()
    artifacts: list[dict] = []
    parse_errors: list[dict] = []
    if workspace is not None:
        store = workspace.store()
        for artifact_id in store.list():
            try:
                prompt = store.get(artifact_id)
                data = prompt.data
                governance = dict(data.get("governance") or {})
                artifact_path = None
                if prompt.path:
                    try:
                        artifact_path = str(prompt.path.resolve().relative_to(workspace.root.resolve()))
                    except ValueError:
                        artifact_path = str(prompt.path.resolve())
                artifacts.append({
                    "id": prompt.id,
                    "name": prompt.name,
                    "kind": prompt.kind,
                    "version": prompt.version,
                    "status": prompt.status,
                    "summary": data.get("summary") or data.get("description") or None,
                    "source": artifact_path,
                    "model": {
                        "primary": prompt.model_ref,
                        "fallbacks": prompt.fallbacks,
                    },
                    "schemas_declared": {
                        "input": prompt.input_schema is not None,
                        "output": prompt.output_schema is not None,
                    },
                    "evals": {
                        "cases": len(prompt.evals),
                        "ids": [str(case.get("id") or "") for case in prompt.evals],
                        "assertion_types": sorted({
                            str(assertion.get("type"))
                            for case in prompt.evals
                            for assertion in (case.get("assert") or [])
                            if isinstance(assertion, dict) and assertion.get("type")
                        }),
                    },
                    "guardrails": [
                        str(item.get("id") or item.get("type") or "declared")
                        for item in prompt.guardrails if isinstance(item, dict)
                    ],
                    "governance": {
                        key: governance.get(key) for key in (
                            "risk_class", "owner", "reviewed_by", "reviewed_at",
                            "human_oversight", "data_categories",
                        ) if governance.get(key) not in (None, "", [])
                    },
                    "provenance_declared": bool(data.get("provenance")),
                })
            except Exception as exc:
                parse_errors.append({"id": artifact_id, "error": str(exc)})

    config = dict(getattr(workspace, "config", {}) or {})
    governance_config = dict(config.get("governance") or {})
    architecture_files: list[str] = []
    if workspace is not None:
        architecture = workspace.root / "docs" / "architecture"
        if architecture.is_dir():
            architecture_files = [
                str(path.relative_to(workspace.root))
                for path in sorted(architecture.rglob("*.md"))
            ]
    stats = audit.stats()
    eval_cases = sum(item["evals"]["cases"] for item in artifacts)
    oversight = [
        item["id"] for item in artifacts
        if item["governance"].get("human_oversight")
    ]
    risk_classified = [
        item["id"] for item in artifacts if item["governance"].get("risk_class")
    ]
    standards = list(governance_config.get("standards") or [])
    declaration = governance_config.get("eu_declaration_of_conformity")
    monitoring_plan = governance_config.get("post_market_monitoring_plan")

    def section(number: str, title: str, status: str,
                evidence: list[Any], gaps: list[str]) -> dict:
        return {
            "annex_item": number, "title": title, "status": status,
            "evidence": evidence, "gaps": gaps,
        }

    sections = [
        section("1", "General description of the AI system",
                "partial" if artifacts else "missing",
                [{"workspace": getattr(workspace, "name", None),
                  "artifact_inventory_count": len(artifacts),
                  "configured_interfaces": [key for key in ("backend", "frontend")
                                             if (getattr(workspace, "root", Path()) / key).exists()]}]
                if workspace is not None else [],
                ["Provider legal identity, deployment forms, intended hardware, and "
                 "complete deployer instructions require operator documentation."]),
        section("2", "Elements and development process",
                "partial" if artifacts or architecture_files else "missing",
                [{"architecture_documents": architecture_files},
                 {"artifact_models_and_controls_indexed": len(artifacts),
                  "embedded_eval_cases": eval_cases}],
                ["Third-party model development, training data provenance, computational "
                 "resources, design trade-offs, signed test reports, and system-level "
                 "cybersecurity measures are not established by PromptFiles alone."]),
        section("3", "Monitoring, functioning, control, capabilities, and limitations",
                "partial" if stats["records"] or eval_cases or oversight else "missing",
                [{"audit_log": stats}, {"artifacts_with_human_oversight": oversight},
                 {"embedded_eval_cases": eval_cases}],
                ["Foreseeable harms, affected-group performance, discrimination analysis, "
                 "system-level limitations, and input specifications need operator review."]),
        section("4", "Appropriateness of performance metrics",
                "partial" if eval_cases else "missing",
                [{"embedded_eval_cases": eval_cases,
                  "artifacts_with_evals": sum(item["evals"]["cases"] > 0 for item in artifacts)}]
                if eval_cases else [],
                ["Assay records metrics and uncertainty, but the provider must justify why "
                 "each metric is appropriate for the intended purpose and affected groups."]),
        section("5", "Risk management system",
                "partial" if risk_classified else "missing",
                [{"risk_classified_artifacts": risk_classified}] if risk_classified else [],
                ["A documented, continuous system-level risk-management process under "
                 "Article 9 is not created by artifact risk labels."]),
        section("6", "Relevant lifecycle changes",
                "partial" if artifacts else "missing",
                [{"versioned_artifacts": len(artifacts),
                  "artifacts_with_declared_provenance": sum(
                      item["provenance_declared"] for item in artifacts)}]
                if artifacts else [],
                ["Git and PromptFile versions supply change evidence only when repository "
                 "history and review policy are retained; relevance and approval of each "
                 "system-level change still require human sign-off."]),
        section("7", "Standards and technical specifications",
                "partial" if standards else "missing",
                [{"operator_declared_standards": standards}] if standards else [],
                ["No applied harmonised standard or alternative technical specification "
                 "is inferred automatically; declared use still needs independent evidence."]),
        section("8", "EU declaration of conformity",
                "partial" if declaration else "missing",
                [{"operator_declared_document": str(declaration)}] if declaration else [],
                ["Assay does not issue, sign, validate, or assert an EU declaration of conformity."]),
        section("9", "Post-market performance evaluation and monitoring plan",
                "partial" if monitoring_plan or stats["records"] else "missing",
                ([{"operator_declared_monitoring_plan": str(monitoring_plan)}]
                 if monitoring_plan else []) + [{"audit_log": stats}],
                ["Run logs are evidence inputs, not a complete post-market monitoring "
                 "system; feedback, incidents, corrective action, responsibilities, and "
                 "review cadence require an operator-owned plan."]),
    ]
    coverage: dict[str, int] = {}
    for item in sections:
        coverage[item["status"]] = coverage.get(item["status"], 0) + 1
    return {
        "format": "assay-annex-iv-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "legal_basis": {
            "regulation": "Regulation (EU) 2024/1689",
            "article": "Article 11(1)",
            "annex": "Annex IV, items 1–9",
            "source": ANNEX_IV_SOURCE,
        },
        "workspace": getattr(workspace, "name", None),
        "coverage": coverage,
        "sections": sections,
        "artifact_inventory": artifacts,
        "artifact_inventory_errors": parse_errors,
        "privacy": (
            "Prompt bodies, eval inputs, model outputs, and audit content are excluded "
            "from this generated inventory."
        ),
        "disclaimer": (
            "This is a generated evidence index, not a legal opinion, conformity "
            "assessment, certification, or EU declaration of conformity. A qualified "
            "human must validate applicability, completeness, evidence, and current law."
        ),
    }


# ---------------------------------------------------------------------------
# Framework mapping
# ---------------------------------------------------------------------------

#: What this repository can evidence, mapped to the clause it speaks to.
#:
#: `evidence` names an artifact an assessor can open. `gap` states plainly what the
#: repository does *not* provide, because a mapping that only lists strengths is a
#: marketing document and an assessor will treat it as one.
CONTROL_MAP: list[dict] = [
    {
        "control": "EU AI Act Art. 12 — automatic event logging",
        "status": "partial",
        "evidence": ".assay/audit/runs-*.jsonl — append-only run log: artifact, version, "
                    "outcome, model, cost, environment fingerprint, timestamp.",
        "gap": "Aggregation is read-only and hash chaining cannot prevent whole-log "
               "deletion. Central retention and remote immutability remain the operator's "
               "responsibility.",
    },
    {
        "control": "EU AI Act Art. 12 — deployer log retention (≥ 6 months)",
        "status": "supported",
        "evidence": "AuditLog retention defaults to 190 days; pruning is explicit and "
                    "never automatic.",
        "gap": "Nothing prevents an operator deleting the directory.",
    },
    {
        "control": "EU AI Act Art. 11 — technical documentation",
        "status": "supported",
        "evidence": "Each artifact is a PromptFile carrying purpose, model binding, "
                    "input/output schemas, guardrails, eval cases and lifecycle status. "
                    "docs/architecture/ holds the blueprint and decision records.",
        "gap": "The generated Annex IV dossier is an evidence index, not a completeness "
               "or conformity assessment; operator and assessor evidence is still required.",
    },
    {
        "control": "EU AI Act Art. 14 — human oversight",
        "status": "partial",
        "evidence": "harness.control.require_approval gates tool calls on an approver; "
                    "over HTTP, gated tools are denied rather than auto-approved.",
        "gap": "Approver identity is caller-asserted rather than independently attested, "
               "and there is no built-in interactive web approval UI.",
    },
    {
        "control": "EU AI Act Art. 15 — accuracy, robustness, cybersecurity",
        "status": "partial",
        "evidence": "assay test gates on embedded evals; assay redteam measures attack "
                    "success rate against a versioned injection corpus; guardrails and "
                    "capability negotiation fail closed.",
        "gap": "Published attack success rates against all current defences exceed 80%. "
               "Red-team results are a regression gate, not a security assurance.",
    },
    {
        "control": "ISO/IEC 42001 §8.3 — change control",
        "status": "supported",
        "evidence": "Prompts are files in git: full history, authorship, review through "
                    "pull requests, and assay history per artifact.",
        "gap": "Depends on the repository's own branch protection, which is outside this tool.",
    },
    {
        "control": "ISO/IEC 42001 §9.1 — monitoring and measurement",
        "status": "partial",
        "evidence": "Every run records cost, tokens, latency, outcome and an environment "
                    "fingerprint. The built-in OpenTelemetry tracer emits current gen_ai.* "
                    "span attributes with content disabled by default. assay judge calibrate "
                    "measures judge agreement against human labels with published thresholds.",
        "gap": "An operator must still configure an OpenTelemetry SDK/exporter and their "
               "collector's retention, sampling, and access policy.",
    },
    {
        "control": "NIST AI RMF — MEASURE 2.3 (repeatability)",
        "status": "partial",
        "evidence": "Environment fingerprints are recorded and cross-environment "
                    "comparisons are flagged as not comparable.",
        "gap": "Genuine bit-reproducibility is only achievable offline. Remote inference "
               "is not reproducible; the tooling reports this rather than fixing it.",
    },
    {
        "control": "Data protection — minimisation in logs",
        "status": "supported",
        "evidence": "Run logs exclude prompt and completion content by default; the "
                    "environment fingerprint contains no hostname, user or credential.",
        "gap": "Enabling governance.log_content stores content; that decision and its "
               "lawful basis are the operator's.",
    },
]


def control_report(workspace: Any = None, audit: AuditLog | None = None) -> dict:
    """Assemble an evidence report an assessor can read.

    States what is supported, what is partial, and what is missing — in that order of
    usefulness to someone doing an actual assessment.
    """
    audit = audit or AuditLog()
    stats = audit.stats()
    by_status: dict[str, int] = {}
    for entry in CONTROL_MAP:
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": getattr(workspace, "name", None),
        "summary": by_status,
        "audit_log": stats,
        "controls": CONTROL_MAP,
        "disclaimer": (
            "This report lists evidence this repository can produce and the gaps it "
            "cannot fill. It is not a compliance assessment and does not make any system "
            "compliant. Frameworks change; verify clause references against the current "
            "text before relying on them."
        ),
    }
