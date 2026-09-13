"""Deterministic serial-vs-bounded-concurrency evaluation benchmark.

This measures scheduler overhead and overlap using an artificial fixed-latency provider. It
does not measure model quality, vendor latency, or competitor performance. ``--check`` gates
the narrow claim that four-worker evaluation takes at most half the serial wall time while
returning the same ordered evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from assay_core import Completion, PromptFile, Registry, Runtime, Usage, Workspace
from assay_core.contracts import CONTRACT_VERSION, RenderedPrompt

CASE_COUNT = 12
DELAY_SECONDS = 0.03
WORKERS = 4
REPETITIONS = 3
MAX_TIME_RATIO = 0.5


class FixedLatencyProvider:
    id = "fixed_latency"
    contract_version = CONTRACT_VERSION

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    def capabilities(self, model: str) -> frozenset[str]:
        return frozenset({"text"})

    def list_models(self):
        return []

    def _result(self, prompt: RenderedPrompt) -> Completion:
        label = str(prompt.variables["label"])
        return Completion(
            text=label,
            model=prompt.model or "model",
            provider=self.id,
            usage=Usage(input_tokens=1, output_tokens=1),
            latency_ms=round(DELAY_SECONDS * 1000),
        )

    def complete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        time.sleep(DELAY_SECONDS)
        return self._result(prompt)

    async def acomplete(self, prompt: RenderedPrompt, **kwargs) -> Completion:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(DELAY_SECONDS)
            return self._result(prompt)
        finally:
            self.active -= 1


def prompt() -> PromptFile:
    cases = [
        {
            "id": f"case-{index:02d}",
            "input": {"label": f"value-{index:02d}"},
            "assert": [{"type": "contains", "value": f"value-{index:02d}"}],
        }
        for index in range(CASE_COUNT)
    ]
    return PromptFile(
        data={
            "promptfile": 1,
            "id": "benchmark/eval-throughput",
            "model": {"primary": "fixed_latency/model"},
            "evals": cases,
        },
        body="{{ label }}",
    )


def comparable(report: dict) -> dict:
    """Remove timing/mode metadata before semantic equality comparison."""
    return {
        "passed": report["passed"],
        "score": report["score"],
        "usable": report["usable"],
        "total_assertions": report["total_assertions"],
        "failed_assertions": report["failed_assertions"],
        "cases": [
            {
                "id": case["id"],
                "passed": case["passed"],
                "score": case.get("score"),
                "output": case.get("output"),
                "results": case.get("results"),
            }
            for case in report["cases"]
        ],
    }


def measure(runtime: Runtime, artifact: PromptFile, provider: FixedLatencyProvider) -> dict:
    serial_ms: list[float] = []
    concurrent_ms: list[float] = []
    semantic_parity = True

    # Pay plugin discovery and interpreter warm-up outside the measured repetitions.
    warmup = [artifact.evals[0]]
    runtime.evaluate(artifact, cases=warmup)
    asyncio.run(runtime.aevaluate(artifact, cases=warmup, max_concurrency=1))
    provider.peak = 0

    for _ in range(REPETITIONS):
        started = time.perf_counter()
        serial = runtime.evaluate(artifact)
        serial_ms.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        concurrent = asyncio.run(runtime.aevaluate(
            artifact, max_concurrency=WORKERS
        ))
        concurrent_ms.append((time.perf_counter() - started) * 1000)
        semantic_parity = semantic_parity and comparable(serial) == comparable(concurrent)

    serial_median = statistics.median(serial_ms)
    concurrent_median = statistics.median(concurrent_ms)
    ratio = concurrent_median / serial_median if serial_median else None
    return {
        "benchmark": "fixed-latency-eval-throughput-v1",
        "scope": "Assay serial runtime versus Assay bounded-concurrency runtime",
        "cases": CASE_COUNT,
        "provider_delay_ms": round(DELAY_SECONDS * 1000),
        "max_concurrency": WORKERS,
        "repetitions": REPETITIONS,
        "warmup_cases": 1,
        "serial_ms": [round(value, 3) for value in serial_ms],
        "bounded_concurrent_ms": [round(value, 3) for value in concurrent_ms],
        "serial_median_ms": round(serial_median, 3),
        "bounded_concurrent_median_ms": round(concurrent_median, 3),
        "time_ratio": round(ratio, 6) if ratio is not None else None,
        "speedup": round(1 / ratio, 6) if ratio else None,
        "peak_active_calls": provider.peak,
        "semantic_parity": semantic_parity,
        "target": {
            "bounded_time_at_most_fraction_of_serial": MAX_TIME_RATIO,
            "meaning": "at least 50% lower median wall time on this synthetic workload",
        },
        "passed": bool(
            semantic_parity
            and provider.peak == WORKERS
            and ratio is not None
            and ratio <= MAX_TIME_RATIO
        ),
        "limitations": [
            "The provider is synthetic and fixed-latency.",
            "This does not measure a hosted model, rate limiting, quality, or a competitor.",
            "Wall-clock results depend on the machine and scheduler; raw repetitions are retained.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    registry = Registry()
    provider = FixedLatencyProvider()
    registry.register("assay.providers", provider.id, provider)
    runtime = Runtime(
        workspace=Workspace(root=Path.cwd()),
        registry=registry,
        default_model="fixed_latency/model",
    )
    result = measure(runtime, prompt(), provider)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.check and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
