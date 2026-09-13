"""Build a deterministic, self-verifying benchmark operator kit."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "benchmark" / "assay-assurance-wedge-v1.zip"
DEFAULT_META = ROOT / "frontend" / "lib" / "benchmark-operator-kit.generated.json"
PREFIX = "assay-assurance-wedge-v1"

BASE_FILES = [
    "README.md",
    "protocol.json",
    "trial.schema.json",
    "score.py",
    "record_trial.py",
    "plan_trials.py",
    "plans/full-target-template.json",
    "trials/current.json",
    "fixtures/reporting-faults.json",
    "fixtures/portable-evidence.json",
]


def source_files() -> list[Path]:
    paths = [HERE / relative for relative in BASE_FILES]
    paths.extend(sorted((HERE / "fixtures" / "auditable-change").glob("*")))
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"operator-kit source missing: {missing[0]}")
    return paths


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build() -> tuple[bytes, dict[str, Any]]:
    payloads: list[tuple[str, bytes]] = []
    for path in source_files():
        relative = path.relative_to(HERE).as_posix()
        payloads.append((relative, path.read_bytes()))

    manifest = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in payloads
    ).encode()
    payloads.append(("SHA256SUMS", manifest))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in payloads:
            archive.writestr(_zip_info(f"{PREFIX}/{name}"), content)
    data = buffer.getvalue()
    metadata = {
        "file": f"/benchmark/{DEFAULT_OUTPUT.name}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "file_count": len(payloads),
        "format": "deterministic-uncompressed-zip",
        "evidence_status": "operator-inputs-not-trial-evidence",
    }
    return data, metadata


def render_metadata(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, indent=2, sort_keys=True) + "\n"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--metadata", type=Path, default=DEFAULT_META)
    result.add_argument("--check", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    data, metadata = build()
    rendered = render_metadata(metadata)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != data:
            raise SystemExit(f"operator kit drift: regenerate {args.output}")
        if not args.metadata.is_file() or args.metadata.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"operator kit metadata drift: regenerate {args.metadata}")
        print(f"operator kit valid: {metadata['file_count']} files, {metadata['sha256']}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(rendered, encoding="utf-8")
    print(json.dumps({"output": str(args.output), **metadata}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
