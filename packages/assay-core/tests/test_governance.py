"""Environment fingerprinting, audit logging and control mapping — RESEARCH §3.10, §3.11.

The theme: a number without its provenance is not evidence. These tests check that the
provenance is recorded, that incomparable results are flagged rather than compared, and
that the audit trail contains nothing that makes it unsafe to keep for six months.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from assay_core import PromptFile, Runtime, Workspace, environment, governance
from assay_core.governance import (
    CONTROL_MAP,
    AuditLog,
    AuditRecord,
    aggregate_audit_logs,
    annex_iv_dossier,
    control_report,
)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def test_capture_records_what_produced_a_result():
    env = environment.capture(provider="anthropic", model="claude-opus-4")
    assert env.provider == "anthropic"
    assert env.assay_core and env.python and env.platform_name
    assert env.fingerprint


def test_only_offline_inference_is_called_deterministic():
    """Temperature 0 plus a seed is not reproducibility; saying otherwise misleads."""
    assert environment.capture(provider="echo", model="echo").deterministic is True
    assert environment.capture(provider="openai", model="gpt-4o").deterministic is False
    assert environment.capture(provider="ollama", model="llama3").deterministic is False


def test_fingerprint_is_stable_for_the_same_environment():
    a = environment.capture(provider="openai", model="gpt-4o")
    b = environment.capture(provider="openai", model="gpt-4o")
    assert a.fingerprint == b.fingerprint


def test_fingerprint_changes_when_the_model_changes():
    a = environment.capture(provider="openai", model="gpt-4o")
    b = environment.capture(provider="openai", model="gpt-4o-mini")
    assert a.fingerprint != b.fingerprint


def test_a_different_model_makes_results_incomparable():
    a = environment.capture(provider="openai", model="gpt-4o")
    b = environment.capture(provider="anthropic", model="claude-opus-4")
    comparable, differences = a.comparable_to(b)
    assert not comparable
    assert any("provider" in d for d in differences)


def test_comparison_warning_names_the_difference():
    a = environment.capture(provider="openai", model="gpt-4o")
    b = environment.capture(provider="anthropic", model="claude-opus-4")
    warning = environment.comparison_warning(a, b)
    assert warning and "not evidence of a change in quality" in warning


def test_same_remote_environment_still_warns_about_noise():
    """Identical infrastructure is necessary for comparison, not sufficient."""
    a = environment.capture(provider="openai", model="gpt-4o")
    b = environment.capture(provider="openai", model="gpt-4o")
    warning = environment.comparison_warning(a, b)
    assert warning and "not bit-reproducible" in warning


def test_offline_runs_produce_no_warning_at_all():
    a = environment.capture(provider="echo", model="echo")
    b = environment.capture(provider="echo", model="echo")
    assert environment.comparison_warning(a, b) is None


def test_fingerprint_contains_nothing_identifying():
    """This gets attached to bug reports. It must be safe to publish."""
    import getpass
    import socket

    payload = json.dumps(environment.capture(provider="openai", model="gpt-4o").to_dict())
    for secret in (socket.gethostname(), getpass.getuser()):
        if secret and len(secret) > 3:
            assert secret not in payload


def test_environment_round_trips():
    original = environment.capture(provider="google", model="gemini-2.5-pro")
    restored = environment.Environment.from_dict(original.to_dict())
    assert restored.fingerprint == original.fingerprint


# ---------------------------------------------------------------------------
# Runs carry their environment
# ---------------------------------------------------------------------------


PROMPT = """---
promptfile: 1
id: gov/example
model: { primary: echo/echo }
evals:
  - id: c
    input: { name: Ada }
    assert:
      - { type: contains, value: Ada }
---
Hello {{ name }}.
"""


@pytest.fixture
def runtime(tmp_path):
    return Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")


def test_run_result_records_its_environment(runtime):
    result = runtime.run(PromptFile.parse(PROMPT), {"name": "Ada"})
    assert result.environment is not None
    assert result.to_dict()["environment"]["provider"] == "echo"
    assert result.to_dict()["environment"]["deterministic"] is True


def test_eval_report_records_its_environment(runtime):
    """A score without its environment cannot be compared to another score."""
    report = runtime.evaluate(PromptFile.parse(PROMPT))
    assert "environment" in report
    assert report["environment"]["fingerprint"]


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit")


def record(**kwargs) -> AuditRecord:
    base = {"run_id": "r1", "artifact_id": "gov/example", "outcome": "completed",
            "model": "echo", "provider": "echo", "cost_usd": 0.01, "total_tokens": 20}
    base.update(kwargs)
    return AuditRecord(**base)


def test_append_and_read(audit):
    audit.append(record())
    entries = audit.read()
    assert len(entries) == 1
    assert entries[0]["artifact_id"] == "gov/example"
    assert entries[0]["timestamp"]
    assert entries[0]["previous_hash"] == "genesis"
    assert len(entries[0]["record_hash"]) == 64


def test_hash_chain_verifies_and_detects_record_tampering(audit, tmp_path):
    audit.append(record(run_id="r1"))
    audit.append(record(run_id="r2"))
    verified = audit.verify_chain()
    assert verified["valid"] is True
    assert verified["hashed_records"] == 2

    path = next((tmp_path / "audit").glob("runs-*.jsonl"))
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace('"outcome": "completed"', '"outcome": "tampered"', 1),
                    encoding="utf-8")

    broken = audit.verify_chain()
    assert broken["valid"] is False
    assert any("record hash mismatch" in error for error in broken["errors"])


def test_empty_audit_log_withholds_integrity_claim(audit):
    result = audit.verify_chain()
    assert result["valid"] is None
    assert result["status"] == "not_checked"
    assert result["note"] == "No records were checked."


def test_the_log_is_plain_jsonl_a_human_can_read(audit, tmp_path):
    audit.append(record())
    files = list((tmp_path / "audit").glob("runs-*.jsonl"))
    assert files
    parsed = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert parsed["artifact_id"] == "gov/example"


def test_content_is_excluded_by_default(audit):
    """A six-month log of every prompt and completion is a liability, not an asset."""
    audit.append(record())
    assert "content" not in audit.read()[0]


def test_content_is_included_only_when_asked_for(audit):
    audit.append(record(content={"output": "hello"}))
    assert audit.read()[0]["content"] == {"output": "hello"}


def test_read_can_filter_by_artifact(audit):
    audit.append(record(artifact_id="a/one"))
    audit.append(record(artifact_id="a/two"))
    assert len(audit.read(artifact_id="a/one")) == 1


def test_a_corrupt_line_does_not_hide_the_rest(audit, tmp_path):
    audit.append(record())
    path = next((tmp_path / "audit").glob("runs-*.jsonl"))
    path.write_text(path.read_text(encoding="utf-8") + "{ not json\n", encoding="utf-8")
    assert len(audit.read()) == 1


def test_stats_summarise_the_log(audit):
    audit.append(record(cost_usd=0.02))
    audit.append(record(artifact_id="a/other", cost_usd=0.03))
    stats = audit.stats()
    assert stats["records"] == 2
    assert stats["artifacts"] == 2
    assert stats["total_cost_usd"] == pytest.approx(0.05)


def test_cross_deployment_aggregation_preserves_identity_and_flags_duplicates(tmp_path):
    prod = AuditLog(tmp_path / "prod")
    staging = AuditLog(tmp_path / "staging")
    prod.append(record(run_id="shared", deployment_id="prod-sg", cost_usd=0.02))
    staging.append(record(run_id="shared", deployment_id="staging-sg", cost_usd=0.03))
    staging.append(record(run_id="unattributed", deployment_id="", cost_usd=0.01))

    result = aggregate_audit_logs({"prod": prod, "staging": staging})

    assert result["records"] == 3
    assert result["identified_deployments"] == 2
    assert result["deployment_ids"] == ["prod-sg", "staging-sg"]
    assert result["unattributed_records"] == 1
    assert result["total_cost_usd"] == pytest.approx(0.06)
    assert result["integrity"]["valid"] is True
    assert result["duplicate_run_ids"] == [
        {"run_id": "shared", "sources": ["prod", "staging"]}
    ]


def test_aggregation_with_empty_source_withholds_complete_integrity_claim(tmp_path):
    populated = AuditLog(tmp_path / "populated")
    populated.append(record())
    result = aggregate_audit_logs({"empty": AuditLog(tmp_path / "empty"),
                                   "populated": populated})
    assert result["integrity"]["valid"] is None
    assert result["integrity"]["status"] == "not_fully_verified"


def test_retention_default_clears_the_six_month_floor(audit):
    """EU AI Act Art. 12 sets six months as the minimum for deployers."""
    assert audit.retention_days >= 180


def test_prune_keeps_recent_logs(audit):
    audit.append(record())
    assert audit.prune() == 0        # nothing is old enough yet
    assert len(audit.read()) == 1


def test_auditing_is_off_unless_the_workspace_asks_for_it(tmp_path, monkeypatch):
    """An audit log nobody configured is a surprise file in someone's repository."""
    monkeypatch.chdir(tmp_path)
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    runtime.run(PromptFile.parse(PROMPT), {"name": "Ada"})
    assert not (tmp_path / ".assay" / "audit").exists()


def test_enabling_audit_writes_a_record(tmp_path):
    workspace = Workspace(root=tmp_path, config={"governance": {"audit": True}})
    runtime = Runtime(workspace=workspace, default_model="echo/echo")
    result = runtime.run(PromptFile.parse(PROMPT), {"name": "Ada"})

    entries = AuditLog(tmp_path / ".assay" / "audit").read()
    assert len(entries) == 1
    assert entries[0]["run_id"] == result.run_id
    assert entries[0]["environment"] == result.environment.fingerprint
    assert "content" not in entries[0]


@pytest.mark.asyncio
async def test_streaming_delivery_evidence_is_sealed_in_audit_record(tmp_path):
    workspace = Workspace(root=tmp_path, config={"governance": {"audit": True}})
    runtime = Runtime(workspace=workspace, default_model="echo/echo")
    prompt = PromptFile.parse(
        "---\npromptfile: 1\nid: gov/stream\nmodel: {primary: echo/echo}\n"
        "---\naudited stream"
    )

    events = [event async for event in runtime.astream(prompt)]
    log = AuditLog(tmp_path / ".assay" / "audit")
    records = log.read()

    assert events[-1].result.streaming["mode"] == "native"
    assert records[0]["streaming"] == events[-1].result.streaming
    assert log.verify_chain()["valid"] is True


def test_audit_record_names_configured_deployment(tmp_path):
    workspace = Workspace(
        root=tmp_path,
        config={"governance": {"audit": True, "deployment_id": "prod-sg"}},
    )
    Runtime(workspace=workspace, default_model="echo/echo").run(
        PromptFile.parse(PROMPT), {"name": "Ada"}
    )
    entry = AuditLog(tmp_path / ".assay" / "audit").read()[0]
    assert entry["deployment_id"] == "prod-sg"


def test_a_broken_audit_log_never_breaks_a_run(tmp_path):
    """Auditing is a side effect. Losing it must not lose the work."""
    workspace = Workspace(
        root=tmp_path,
        config={"governance": {"audit": True, "audit_root": "/proc/nonexistent/nope"}},
    )
    runtime = Runtime(workspace=workspace, default_model="echo/echo")
    result = runtime.run(PromptFile.parse(PROMPT), {"name": "Ada"})
    assert result.text                      # the run still succeeded


# ---------------------------------------------------------------------------
# Control mapping
# ---------------------------------------------------------------------------


def test_every_control_states_a_gap_not_just_evidence():
    """A mapping that only lists strengths is marketing, and assessors read it as such."""
    for entry in CONTROL_MAP:
        assert entry["gap"], f"{entry['control']} claims no gap at all"
        assert entry["evidence"]
        assert entry["status"] in {"supported", "partial", "missing"}


def test_no_control_is_claimed_as_fully_solved_when_it_is_not():
    """Security in particular must not be overstated."""
    security = next(e for e in CONTROL_MAP if "Art. 15" in e["control"])
    assert security["status"] == "partial"
    assert "80%" in security["gap"]


def test_report_carries_a_disclaimer(tmp_path):
    report = control_report(audit=AuditLog(tmp_path / "audit"))
    assert "not a compliance assessment" in report["disclaimer"]
    assert report["summary"]
    assert report["controls"]


def test_report_includes_audit_statistics(tmp_path):
    log = AuditLog(tmp_path / "audit")
    log.append(record())
    report = control_report(audit=log)
    assert report["audit_log"]["records"] == 1


def test_annex_iv_dossier_maps_all_nine_items_without_prompt_content(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    secret_body = "DO NOT EXPORT THIS PROMPT BODY"
    (prompts / "example.prompt.md").write_text(
        "---\npromptfile: 1\nid: gov/dossier\nname: Dossier example\n"
        "description: Evidence-safe inventory example\nversion: 3\nstatus: stable\n"
        "model: {primary: echo/echo}\n"
        "governance:\n  risk_class: high\n  owner: risk-team\n"
        "  human_oversight: A reviewer can stop tool execution.\n"
        "evals:\n  - id: c1\n    assert: [{type: contains, value: safe}]\n"
        f"---\n{secret_body}\n",
        encoding="utf-8",
    )
    workspace = Workspace(
        root=tmp_path,
        config={"name": "regulated-example", "prompts": "./prompts"},
    )
    log = AuditLog(tmp_path / ".assay" / "audit")
    log.append(record(artifact_id="gov/dossier", deployment_id="prod"))

    dossier = annex_iv_dossier(workspace, log)
    encoded = json.dumps(dossier)

    assert dossier["format"] == "assay-annex-iv-evidence-v1"
    assert [section["annex_item"] for section in dossier["sections"]] == [
        str(number) for number in range(1, 10)
    ]
    assert dossier["artifact_inventory"][0]["evals"]["cases"] == 1
    assert dossier["artifact_inventory"][0]["governance"]["risk_class"] == "high"
    assert secret_body not in encoded
    assert "not a legal opinion" in dossier["disclaimer"]
    assert next(item for item in dossier["sections"] if item["annex_item"] == "8")[
        "status"
    ] == "missing"
