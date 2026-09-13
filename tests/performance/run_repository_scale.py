#!/usr/bin/env python3
"""Deterministic large-repository discovery and render budget.

This benchmark creates 1,000 small PromptFiles outside the checkout, then measures the
real file store and renderer. File creation is excluded. The budgets are conservative
cross-platform regression ceilings, not a claim about competitor speed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from assay_core import Runtime, Workspace
from assay_core.builtins.stores import FileStore

ARTIFACTS = 1_000
REPETITIONS = 3
MAX_INDEX_MEDIAN_MS = 5_000
MAX_LOAD_RENDER_MEDIAN_MS = 5_000


def seed(root: Path) -> None:
    for index in range(ARTIFACTS):
        namespace = root / f"domain-{index % 20:02d}"
        namespace.mkdir(exist_ok=True)
        (namespace / f"prompt-{index:04d}.prompt.md").write_text(
            "---\n"
            "promptfile: 1\n"
            f"id: scale/domain-{index % 20:02d}/prompt-{index:04d}\n"
            f"name: Scale prompt {index:04d}\n"
            "model: {primary: echo/echo}\n"
            f"x-scale: {{ordinal: {index}, cohort: {index % 7}}}\n"
            "---\n"
            "Render {{ value }} without losing future metadata.\n",
            encoding="utf-8",
        )


def measure(root: Path) -> dict:
    store = FileStore(root)
    runtime = Runtime(workspace=Workspace(root=root), default_model="echo/echo")
    index_ms: list[float] = []
    render_ms: list[float] = []
    expected_ids = [
        f"scale/domain-{index % 20:02d}/prompt-{index:04d}"
        for index in range(ARTIFACTS)
    ]

    for _ in range(REPETITIONS):
        started = time.perf_counter()
        index = store.reindex()
        index_ms.append((time.perf_counter() - started) * 1000)
        if set(index) != set(expected_ids):
            raise AssertionError(f"indexed {len(index)} ids; expected {ARTIFACTS}")

        started = time.perf_counter()
        first_text = last_text = ""
        for position, prompt_id in enumerate(expected_ids):
            prompt = store.get(prompt_id)
            rendered = runtime.render(prompt, {"value": prompt_id})
            if prompt.data["x-scale"]["ordinal"] != position:
                raise AssertionError(f"unknown metadata changed for {prompt_id}")
            if position == 0:
                first_text = rendered.text
            elif position == ARTIFACTS - 1:
                last_text = rendered.text
        render_ms.append((time.perf_counter() - started) * 1000)
        if expected_ids[0] not in first_text or expected_ids[-1] not in last_text:
            raise AssertionError("rendered edge artifacts do not contain their input")

    index_median = statistics.median(index_ms)
    render_median = statistics.median(render_ms)
    return {
        "benchmark": "promptfile-repository-scale-v1",
        "artifacts": ARTIFACTS,
        "namespaces": 20,
        "repetitions": REPETITIONS,
        "index_ms": [round(value, 3) for value in index_ms],
        "load_render_ms": [round(value, 3) for value in render_ms],
        "index_median_ms": round(index_median, 3),
        "load_render_median_ms": round(render_median, 3),
        "targets": {
            "index_median_ms_at_most": MAX_INDEX_MEDIAN_MS,
            "load_render_median_ms_at_most": MAX_LOAD_RENDER_MEDIAN_MS,
        },
        "semantic_checks": {
            "all_ids_indexed": True,
            "edge_inputs_rendered": True,
            "unknown_metadata_preserved": True,
        },
        "passed": index_median <= MAX_INDEX_MEDIAN_MS and render_median <= MAX_LOAD_RENDER_MEDIAN_MS,
        "limitations": [
            "Files are small and generated on one local filesystem.",
            "The time to create the fixture is excluded.",
            "The ceilings are regression budgets, not competitor or hosted-service evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--temp-root",
        type=Path,
        default=None,
        help="parent directory for the disposable fixture (defaults to the system temp directory)",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="assay-scale-", dir=args.temp_root) as directory:
        root = Path(directory)
        seed(root)
        result = measure(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.check and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
