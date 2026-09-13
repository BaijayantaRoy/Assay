"""Quality gates for every PromptFile shipped in ``packs/``.

Pack count is not a quality metric. These tests make the useful promises measurable:
the files conform, run without a paid provider, carry real checks, and those checks can
detect a broken template rather than passing regardless of the artifact under test.
"""

from __future__ import annotations

import copy
from pathlib import Path

import jsonschema
import pytest

from assay_core import PromptFile, Runtime, Workspace

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_FILES = sorted((REPO_ROOT / "packs").glob("*/*.prompt.*"))


@pytest.fixture(scope="module")
def pack_runtime(tmp_path_factory) -> Runtime:
    workspace = Workspace.init(tmp_path_factory.mktemp("pack-quality"), name="pack-quality")
    return Runtime(workspace=workspace)


def _broken_template(prompt: PromptFile) -> PromptFile:
    data = copy.deepcopy(prompt.data)
    if data.get("messages"):
        data["messages"] = [
            {**message, "content": ""} for message in data["messages"]
        ]
    return PromptFile(data=data, body="", path=prompt.path)


def test_pack_catalog_is_not_empty_and_ids_are_unique():
    assert len(PACK_FILES) >= 200, "the curated catalog coverage baseline is 200 artifacts"
    ids = [PromptFile.load(path).id for path in PACK_FILES]
    assert len(ids) == len(set(ids)), "pack artifact ids must be globally unique"


@pytest.mark.parametrize("path", PACK_FILES, ids=lambda path: path.stem)
def test_pack_artifact_has_a_runnable_mutation_sensitive_contract(path, pack_runtime):
    prompt = PromptFile.load(path)

    assert prompt.validate(strict=True) == []
    assert prompt.status == "stable"
    assert prompt.model_ref and prompt.model_ref.startswith("echo/"), (
        "shipped pack evals must run offline; users may change the model after install"
    )
    assert prompt.evals, "a stable pack artifact without evals is unverified"
    assert len(prompt.body.strip()) >= 80, "starter bodies must teach a substantive pattern"

    schema = prompt.input_schema or {}
    required = set(schema.get("required") or [])
    declared = set((schema.get("properties") or {}).keys())
    assert required <= declared
    assert required <= prompt.template_variables(), (
        "every required input must affect the rendered artifact"
    )
    for case in prompt.evals:
        jsonschema.Draft202012Validator(schema).validate(case.get("input") or {})

    report = pack_runtime.evaluate(prompt)
    assert report["passed"] is True
    assert report["usable"] is True
    assert report["total_assertions"] > 0

    mutant = pack_runtime.evaluate(_broken_template(prompt))
    assert mutant["passed"] is False, (
        "the embedded evals still pass after deleting the template; add a positive, "
        "artifact-sensitive assertion"
    )
