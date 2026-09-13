#!/usr/bin/env python3
"""Synchronize canonical spec/security resources into the Python package.

Published sdists must be self-contained: a wheel rebuilt from an extracted sdist cannot
reach ``../../spec`` in the original repository. The copies below are generated package
data; ``--check`` is the CI/release drift gate that keeps the root files canonical.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "assay-core" / "src" / "assay_core"
RESOURCES = {
    ROOT / "spec" / "schemas" / "promptfile-v1.schema.json":
        PACKAGE / "schemas" / "promptfile-v1.schema.json",
    ROOT / "spec" / "redteam" / "corpus-v1.jsonl":
        PACKAGE / "redteam" / "corpus-v1.jsonl",
    ROOT / "spec" / "redteam" / "adaptive-v1.jsonl":
        PACKAGE / "redteam" / "adaptive-v1.jsonl",
    ROOT / "spec" / "promptfile-v1.md":
        PACKAGE / "spec" / "promptfile-v1.md",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale: list[str] = []
    for source, target in RESOURCES.items():
        expected = source.read_bytes()
        if args.check:
            if not target.is_file() or target.read_bytes() != expected:
                stale.append(str(target.relative_to(ROOT)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected)
        print(f"synced {source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    if stale:
        print("stale generated core resources:")
        for path in stale:
            print(f"  {path}")
        print("run: python scripts/sync_core_resources.py")
        return 1
    if args.check:
        print(f"{len(RESOURCES)} bundled core resources match canonical files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
