#!/usr/bin/env python3
"""Verify that the release directory contains every intended publishable package."""

from __future__ import annotations

import argparse
import json
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_version(package: str) -> str:
    manifest = ROOT / "packages" / package / "pyproject.toml"
    return tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["version"]


def _npm_version(package: str) -> str:
    manifest = ROOT / "packages" / package / "package.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def _constant(relative: str, name: str) -> str:
    source = (ROOT / relative).read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", source, re.MULTILINE)
    if not match:
        raise SystemExit(f"{relative} does not declare {name}")
    return match.group(1)


def _versions() -> dict[str, str]:
    return {
        "packages/assay-core/pyproject.toml": _python_version("assay-core"),
        "packages/assay-cli/pyproject.toml": _python_version("assay-cli"),
        "packages/assay-mcp/pyproject.toml": _python_version("assay-mcp"),
        "packages/sdk-python/pyproject.toml": _python_version("sdk-python"),
        "packages/sdk-typescript/package.json": _npm_version("sdk-typescript"),
        "packages/promptfile-typescript/package.json": _npm_version("promptfile-typescript"),
        "assay_core.__version__": _constant(
            "packages/assay-core/src/assay_core/__init__.py", "__version__"
        ),
        "assay_cli.__version__": _constant(
            "packages/assay-cli/src/assay_cli/__init__.py", "__version__"
        ),
        "CLI_VERSION": _constant(
            "packages/assay-cli/src/assay_cli/__main__.py", "CLI_VERSION"
        ),
        "assay_mcp.__version__": _constant(
            "packages/assay-mcp/src/assay_mcp/__init__.py", "__version__"
        ),
        "SERVER_VERSION": _constant(
            "packages/assay-mcp/src/assay_mcp/server.py", "SERVER_VERSION"
        ),
        "assay client __version__": _constant(
            "packages/sdk-python/src/assay/__init__.py", "__version__"
        ),
        "backend VERSION": _constant("backend/main.py", "VERSION"),
    }


def _check_npm_tarball(path: Path, *, name: str, required: set[str]) -> None:
    with tarfile.open(path) as archive:
        members = {member.name: member for member in archive.getmembers()}
        missing = sorted(required - members.keys())
        if missing:
            raise SystemExit(f"{path.name} is missing published files: {missing}")
        package_json = archive.extractfile(members["package/package.json"])
        if package_json is None:
            raise SystemExit(f"{path.name} has no readable package.json")
        manifest = json.load(package_json)
        if manifest.get("name") != name:
            raise SystemExit(
                f"{path.name} contains npm package {manifest.get('name')!r}, expected {name!r}"
            )


def _check_wheel_license(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise SystemExit(f"{path.name} is missing its MIT LICENSE")


def _check_sdist_license(path: Path) -> None:
    with tarfile.open(path) as archive:
        if not any(member.name.endswith("/LICENSE") for member in archive.getmembers()):
            raise SystemExit(f"{path.name} is missing its MIT LICENSE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--expect-version")
    args = parser.parse_args()
    directory = args.dist.resolve()

    versions = _versions()
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        raise SystemExit(f"release versions disagree: {versions}")
    if args.expect_version and distinct[0] != args.expect_version:
        raise SystemExit(
            f"release version is {distinct[0]}, expected {args.expect_version}: {versions}"
        )

    core = _python_version("assay-core")
    cli = _python_version("assay-cli")
    mcp = _python_version("assay-mcp")
    sdk_py = _python_version("sdk-python")
    sdk_ts = _npm_version("sdk-typescript")
    reader = _npm_version("promptfile-typescript")
    expected = {
        f"assay_core-{core}-py3-none-any.whl",
        f"assay_core-{core}.tar.gz",
        f"assay_cli-{cli}-py3-none-any.whl",
        f"assay_cli-{cli}.tar.gz",
        f"assay_mcp-{mcp}-py3-none-any.whl",
        f"assay_mcp-{mcp}.tar.gz",
        f"assay_client-{sdk_py}-py3-none-any.whl",
        f"assay_client-{sdk_py}.tar.gz",
        f"assay-sdk-{sdk_ts}.tgz",
        f"assay-promptfile-{reader}.tgz",
    }
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise SystemExit(
            f"release inventory mismatch; missing={missing}, unexpected={unexpected}"
        )

    for path in sorted(directory.glob("*.whl")):
        _check_wheel_license(path)
    for path in sorted(directory.glob("*.tar.gz")):
        _check_sdist_license(path)

    _check_npm_tarball(
        directory / f"assay-sdk-{sdk_ts}.tgz",
        name="@assay/sdk",
        required={
            "package/package.json",
            "package/README.md",
            "package/LICENSE",
            "package/dist/index.js",
            "package/dist/index.d.ts",
        },
    )
    reader_tarball = directory / f"assay-promptfile-{reader}.tgz"
    _check_npm_tarball(
        reader_tarball,
        name="@assay/promptfile",
        required={
            "package/package.json",
            "package/README.md",
            "package/LICENSE",
            "package/dist/index.js",
            "package/dist/index.d.ts",
            "package/schema/promptfile-v1.schema.json",
        },
    )
    with tarfile.open(reader_tarball) as archive:
        bundled = archive.extractfile("package/schema/promptfile-v1.schema.json")
        canonical = ROOT / "spec" / "schemas" / "promptfile-v1.schema.json"
        if bundled is None or bundled.read() != canonical.read_bytes():
            raise SystemExit("published TypeScript schema differs from the canonical schema")

    print("release inventory verified: 4 Python wheels, 4 sdists, and 2 npm tarballs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
