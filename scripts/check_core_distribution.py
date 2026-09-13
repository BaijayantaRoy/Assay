#!/usr/bin/env python3
"""Prove an assay-core release contains and can load its canonical resources.

This check deliberately imports from an extracted wheel in an isolated subprocess whose
working directory is outside the repository.  A source checkout can therefore never
hide a missing package-data file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_MAP = {
    "assay_core/schemas/promptfile-v1.schema.json":
        ROOT / "spec" / "schemas" / "promptfile-v1.schema.json",
    "assay_core/redteam/corpus-v1.jsonl":
        ROOT / "spec" / "redteam" / "corpus-v1.jsonl",
    "assay_core/redteam/adaptive-v1.jsonl":
        ROOT / "spec" / "redteam" / "adaptive-v1.jsonl",
    "assay_core/spec/promptfile-v1.md": ROOT / "spec" / "promptfile-v1.md",
}


def _only(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one {pattern!r} in {directory}, found {len(matches)}"
        )
    return matches[0]


def _check_archives(wheel: Path, sdist: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        for member, canonical in RESOURCE_MAP.items():
            if member not in wheel_names:
                raise SystemExit(f"wheel is missing {member}")
            if archive.read(member) != canonical.read_bytes():
                raise SystemExit(f"wheel resource differs from canonical file: {member}")

    with tarfile.open(sdist) as archive:
        members = {member.name: member for member in archive.getmembers()}
        for relative, canonical in RESOURCE_MAP.items():
            suffix = f"/src/{relative}"
            matches = [name for name in members if name.endswith(suffix)]
            if len(matches) != 1:
                raise SystemExit(f"sdist must contain exactly one {suffix}, found {matches}")
            extracted = archive.extractfile(members[matches[0]])
            if extracted is None or extracted.read() != canonical.read_bytes():
                raise SystemExit(f"sdist resource differs from canonical file: {relative}")


def _check_isolated_import(wheel: Path) -> dict:
    smoke = r"""
import json
import sys
from pathlib import Path

target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))

import assay_core
from assay_core.promptfile import _schema_path, load_schema
from assay_core.redteam import corpus_path, load_corpus

package = Path(assay_core.__file__).resolve().parent
schema_path = _schema_path(1).resolve()
default_path = corpus_path().resolve()
adaptive_path = corpus_path("adaptive-v1.jsonl").resolve()
spec_path = (package / "spec" / "promptfile-v1.md").resolve()

for path in (schema_path, default_path, adaptive_path, spec_path):
    path.relative_to(package)
    if not path.is_file():
        raise AssertionError(f"missing installed resource: {path}")

schema = load_schema()
default = load_corpus(default_path)
adaptive = load_corpus(adaptive_path)
spec = spec_path.read_text(encoding="utf-8")
assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
assert default and adaptive
assert "promptfile: 1" in spec
print(json.dumps({
    "package": str(package),
    "default_attacks": len(default),
    "adaptive_attacks": len(adaptive),
    "spec_bytes": len(spec.encode("utf-8")),
}))
"""
    # Use the system temp root, which must be outside the source checkout. Extracting
    # below the repository could let the reader discover root ``spec/`` files and hide
    # missing wheel data—the exact packaging bug this gate exists to catch.
    with tempfile.TemporaryDirectory(prefix="assay-wheel-smoke-") as temp:
        target = Path(temp) / "installed"
        target.mkdir()
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(target)
        completed = subprocess.run(
            [sys.executable, "-I", "-c", smoke, str(target)],
            cwd=temp,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise SystemExit(
                "isolated wheel import failed:\n"
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path, help="directory containing assay-core wheel and sdist")
    args = parser.parse_args()
    directory = args.dist.resolve()
    wheel = _only(directory, "assay_core-*.whl")
    sdist = _only(directory, "assay_core-*.tar.gz")
    _check_archives(wheel, sdist)
    evidence = _check_isolated_import(wheel)
    print(
        "assay-core distribution verified: "
        f"4 exact resources; {evidence['default_attacks']} default and "
        f"{evidence['adaptive_attacks']} adaptive/sequence corpus cases load in isolation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
