from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "benchmarks" / "assurance-wedge" / "record_trial.py"
SPEC = importlib.util.spec_from_file_location("record_trial", PATH)
assert SPEC and SPEC.loader
RECORD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECORD)


def args(**changes):
    values = {
        "id": "assay-faults-001",
        "product_id": "assay",
        "product_version": "1.0.0",
        "metric_id": "false-assurance-miss-rate",
        "task_id": "zero-usable-sample",
        "operator_id": "operator-a",
        "task_author_id": "task-author",
        "os": "windows",
        "runtime": "python-3.12",
        "clean_setup": True,
        "usable": True,
        "completed": True,
        "measurement": ["delivered_faults=4", "detected_faults=4"],
    }
    values.update(changes)
    return argparse.Namespace(**values)


def test_measurements_are_numeric_and_duplicate_keys_are_rejected():
    assert RECORD.parse_measurements(["count=4", "minutes=2.5"]) == {"count": 4, "minutes": 2.5}
    with pytest.raises(ValueError, match="duplicated"):
        RECORD.parse_measurements(["count=4", "count=5"])
    with pytest.raises(ValueError, match="not numeric"):
        RECORD.parse_measurements(["count=four"])


def test_trial_builder_preserves_explicit_evidence_states():
    trial = RECORD.build_trial(
        args(usable=False, completed=False),
        [{"uri": "raw/evidence.json", "sha256": "a" * 64}],
    )
    assert trial["usable"] is False
    assert trial["completed"] is False
    assert trial["environment"]["clean_setup"] is True
    assert trial["measurement"] == {"delivered_faults": 4, "detected_faults": 4}


def test_trial_ids_are_safe_relative_path_components():
    with pytest.raises(ValueError, match="trial id"):
        RECORD.build_trial(args(id="../escape"), [])
