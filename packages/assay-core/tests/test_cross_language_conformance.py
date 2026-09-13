"""Python implementation against the corpus shared with the independent TS reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assay_core import PromptFile
from assay_core.errors import ParseError, UnsupportedSpecVersion, ValidationError

ROOT = Path(__file__).resolve().parents[3] / "spec" / "conformance"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def _at_path(value, path: str):
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


@pytest.mark.parametrize("fixture", MANIFEST["valid"], ids=lambda item: item["file"])
def test_python_reader_matches_shared_valid_corpus(fixture):
    source = (ROOT / fixture["file"]).read_text(encoding="utf-8")
    parsed = PromptFile.parse(source, fmt=fixture["format"])
    assert not parsed.validate(strict=False)
    assert parsed.id == fixture["id"]
    assert fixture["body_contains"] in parsed.body
    for path, expected in fixture["unknown"].items():
        assert _at_path(parsed.data, path) == expected

    serialized = parsed.to_text(fmt=fixture["format"])
    reparsed = PromptFile.parse(serialized, fmt=fixture["format"])
    assert reparsed.to_dict() == parsed.to_dict()
    assert reparsed.to_text(fmt=fixture["format"]) == serialized


@pytest.mark.parametrize("fixture", MANIFEST["invalid"], ids=lambda item: item["file"])
def test_python_reader_matches_shared_invalid_corpus(fixture):
    source = (ROOT / fixture["file"]).read_text(encoding="utf-8")
    if fixture["error"] == "unsupported_version":
        with pytest.raises(UnsupportedSpecVersion):
            PromptFile.parse(source, fmt=fixture["format"])
    elif fixture["error"] == "parse":
        with pytest.raises(ParseError):
            PromptFile.parse(source, fmt=fixture["format"])
    else:
        parsed = PromptFile.parse(source, fmt=fixture["format"])
        assert parsed.validate(strict=False)
