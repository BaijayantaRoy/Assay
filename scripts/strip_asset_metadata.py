#!/usr/bin/env python3
"""Remove and detect generator/provenance metadata in published visual assets."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets"
MARKERS = (b"c2pa", b"manifest-store", b"anthropic", b"claude provided")
SVG_METADATA = re.compile(rb"\s*<metadata\b.*?</metadata>\s*", re.IGNORECASE | re.DOTALL)
SVG_C2PA_NAMESPACE = re.compile(rb"\s+xmlns:c2pa=(?:\"[^\"]*\"|'[^']*')", re.IGNORECASE)


def contaminated(path: Path) -> bool:
    payload = path.read_bytes().lower()
    return any(marker in payload for marker in MARKERS) or (
        path.suffix.lower() == ".svg" and b"<metadata" in payload
    )


def clean_svg(path: Path) -> None:
    original = path.read_bytes()
    cleaned, metadata_count = SVG_METADATA.subn(b"\n", original)
    cleaned, namespace_count = SVG_C2PA_NAMESPACE.subn(b"", cleaned)
    if metadata_count or namespace_count:
        path.write_bytes(cleaned)


def clean_raster(path: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - only needed by the maintenance command
        raise SystemExit("Cleaning raster metadata requires Pillow") from exc

    with Image.open(path) as source:
        source.load()
        image = source.convert("RGBA")
        expected_size = image.size
        expected_pixels = hashlib.sha256(image.tobytes()).digest()
        temporary = path.with_name(f".{path.stem}.metadata-clean{path.suffix}")
        if path.suffix.lower() == ".ico":
            image.save(temporary, format="ICO", sizes=[image.size])
        else:
            image.save(temporary, format="PNG", optimize=True)
        with Image.open(temporary) as cleaned:
            actual = cleaned.convert("RGBA")
            if actual.size != expected_size or hashlib.sha256(actual.tobytes()).digest() != expected_pixels:
                temporary.unlink(missing_ok=True)
                raise SystemExit(f"metadata cleaning changed visible pixels: {path}")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if published assets still contain generator/provenance metadata",
    )
    args = parser.parse_args()

    assets = sorted(
        path
        for path in ASSET_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".svg", ".png", ".ico"}
    )
    dirty = [path for path in assets if contaminated(path)]
    if args.check:
        if dirty:
            relative = ", ".join(str(path.relative_to(ROOT)) for path in dirty)
            raise SystemExit(f"asset metadata contamination found: {relative}")
        print(f"asset metadata check passed: {len(assets)} files")
        return 0

    for path in dirty:
        if path.suffix.lower() == ".svg":
            clean_svg(path)
        else:
            clean_raster(path)

    remaining = [path for path in assets if contaminated(path)]
    if remaining:
        relative = ", ".join(str(path.relative_to(ROOT)) for path in remaining)
        raise SystemExit(f"metadata remains after cleaning: {relative}")
    print(f"cleaned {len(dirty)} assets; verified {len(assets)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
