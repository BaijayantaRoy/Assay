"""Append one evidence-backed operator trial to the benchmark ledger.

The command copies raw artifacts beneath the ledger, hashes their content, validates the
prospective full ledger with the canonical scorer, and replaces the ledger atomically. It refuses
implicit usable/completed states and never overwrites an existing trial or raw-evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
DEFAULT_LEDGER = HERE / "trials" / "current.json"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


def load_scorer():
    spec = importlib.util.spec_from_file_location("assurance_wedge_score", HERE / "score.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load benchmark scorer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_measurements(values: list[str]) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"measurement must be key=value: {value}")
        key, raw = value.split("=", 1)
        if not key or key in result:
            raise ValueError(f"measurement key is empty or duplicated: {key}")
        try:
            number = float(raw) if "." in raw else int(raw)
        except ValueError as exc:
            raise ValueError(f"measurement is not numeric: {value}") from exc
        result[key] = number
    return result


def build_trial(args: argparse.Namespace, artifacts: list[dict[str, str]]) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(args.id):
        raise ValueError("trial id must be 3-128 lowercase letters, numbers, dots, dashes, or underscores")
    return {
        "id": args.id,
        "product_id": args.product_id,
        "product_version": args.product_version,
        "metric_id": args.metric_id,
        "task_id": args.task_id,
        "operator_id": args.operator_id,
        "task_author_id": args.task_author_id,
        "environment": {
            "os": args.os,
            "runtime": args.runtime,
            "clean_setup": args.clean_setup,
        },
        "usable": args.usable,
        "completed": args.completed,
        "measurement": parse_measurements(args.measurement),
        "raw_artifacts": artifacts,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    result.add_argument("--id", required=True)
    result.add_argument("--product-id", required=True)
    result.add_argument("--product-version", required=True)
    result.add_argument("--metric-id", required=True)
    result.add_argument("--task-id", required=True)
    result.add_argument("--operator-id", required=True)
    result.add_argument("--task-author-id", required=True)
    result.add_argument("--os", required=True)
    result.add_argument("--runtime", required=True)
    result.add_argument("--clean-setup", action=argparse.BooleanOptionalAction, required=True)
    usable = result.add_mutually_exclusive_group(required=True)
    usable.add_argument("--usable", action="store_true", dest="usable")
    usable.add_argument("--not-usable", action="store_false", dest="usable")
    completed = result.add_mutually_exclusive_group(required=True)
    completed.add_argument("--completed", action="store_true", dest="completed")
    completed.add_argument("--not-completed", action="store_false", dest="completed")
    result.add_argument("--measurement", action="append", required=True, metavar="KEY=NUMBER")
    result.add_argument("--artifact", action="append", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    ledger = args.ledger.resolve()
    if not ledger.is_file():
        raise SystemExit(f"ledger does not exist: {ledger}")
    document = json.loads(ledger.read_text(encoding="utf-8"))
    if any(trial.get("id") == args.id for trial in document.get("trials", [])):
        raise SystemExit(f"trial id already exists: {args.id}")

    raw_root = ledger.parent / "raw" / args.id
    if raw_root.exists():
        raise SystemExit(f"raw evidence directory already exists: {raw_root}")
    sources = [path.resolve() for path in args.artifact]
    if any(not source.is_file() for source in sources):
        raise SystemExit("every --artifact must name an existing file")
    names = [source.name for source in sources]
    if len(names) != len(set(names)):
        raise SystemExit("raw artifact basenames must be unique within a trial")

    raw_root.mkdir(parents=True)
    try:
        artifacts = []
        for source in sources:
            destination = raw_root / source.name
            shutil.copyfile(source, destination)
            artifacts.append({
                "uri": destination.relative_to(ledger.parent).as_posix(),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            })
        prospective = {**document, "trials": [*document["trials"], build_trial(args, artifacts)]}
        scorer = load_scorer()
        protocol = scorer.load_json(PROTOCOL_PATH)
        scorer.validate_trials(protocol, prospective, artifact_root=ledger.parent)
        temporary = ledger.with_suffix(ledger.suffix + ".tmp")
        temporary.write_text(json.dumps(prospective, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, ledger)
    except Exception:
        shutil.rmtree(raw_root, ignore_errors=True)
        raise

    print(json.dumps({"recorded": args.id, "ledger": str(ledger), "artifacts": artifacts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
