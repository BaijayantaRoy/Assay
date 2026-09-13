from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORT_PATH = ROOT / "benchmarks" / "assurance-wedge" / "export_operator_kit.py"
SPEC = importlib.util.spec_from_file_location("assurance_wedge_operator_kit", EXPORT_PATH)
assert SPEC and SPEC.loader
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


def test_operator_kit_manifest_verifies_every_payload():
    data, metadata = EXPORTER.build()
    assert metadata["evidence_status"] == "operator-inputs-not-trial-evidence"
    assert metadata["sha256"] == hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        manifest_name = f"{EXPORTER.PREFIX}/SHA256SUMS"
        assert manifest_name in names
        lines = archive.read(manifest_name).decode().splitlines()
        assert len(lines) == metadata["file_count"] - 1
        for line in lines:
            digest, relative = line.split("  ", 1)
            assert hashlib.sha256(
                archive.read(f"{EXPORTER.PREFIX}/{relative}")
            ).hexdigest() == digest


def test_checked_in_operator_kit_is_byte_for_byte_reproducible():
    data, metadata = EXPORTER.build()
    assert EXPORTER.DEFAULT_OUTPUT.read_bytes() == data
    assert EXPORTER.DEFAULT_META.read_text(encoding="utf-8") == EXPORTER.render_metadata(metadata)
