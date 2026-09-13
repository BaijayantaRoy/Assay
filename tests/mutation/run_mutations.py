#!/usr/bin/env python3
"""Targeted mutation testing: break each claim, see whether the suite notices.

Coverage says which lines ran. It does not say whether anything would have *failed* had
those lines been wrong — a test that calls a function and asserts nothing scores the same
as one that checks the answer. This asks the question coverage cannot: **if we shipped
this bug, would anything go red?**

The mutations are hand-chosen, not random. Each one corresponds to a claim this project
makes in its README, its docs or its UI. Random operator mutation mostly turns up
equivalent mutants and dead branches; deliberately breaking a stated promise finds out
whether the promise is defended. A surviving mutant means *we could ship that bug today*.

Two correctness rules, both learned the hard way on this script's first run:

**Never mutate prose.** Version one replaced the first textual match anywhere in the file
and duly reported a "surviving mutant" that had edited nothing but a docstring. That is a
false finding — the precise failure mode this project exists to prevent — so anchors are
now rejected unless they land on real code, checked with :mod:`tokenize`.

**Stale anchors fail loudly.** They used to print SKIP and exit zero, which silently
shrinks the suite every time someone refactors. ``--check`` verifies every anchor still
resolves, runs in about a second, and is what CI gates on.

Usage::

    python tests/mutation/run_mutations.py --check    # anchors valid? (fast, CI gate)
    python tests/mutation/run_mutations.py --list     # what is measured, and why
    python tests/mutation/run_mutations.py            # full run (minutes)
    python tests/mutation/run_mutations.py 0 5        # a slice, for time-boxed runs

Exit code is 0 only when every mutation was killed and every anchor resolved.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "packages" / "assay-core" / "src" / "assay_core"
TESTS = "packages/assay-core/tests/"


@dataclass
class Mutation:
    """One deliberate bug, and the promise it breaks."""

    name: str
    claim: str
    path: Path
    old: str
    new: str
    #: Tests expected to catch it. Tried first; the whole suite is the fallback, because
    #: the honest question is whether *anything* notices — not whether the obvious file does.
    tests: list[str] = field(default_factory=list)


M = [
    # ------------------------------------------------------------------ security
    Mutation(
        "fence-marks-untrusted-as-trusted",
        "Tool output is fenced as UNTRUSTED by the harness before re-entering context.",
        SRC / "harness.py",
        'trust = provenance.TRUSTED if control.get("trust_tool_output") else provenance.UNTRUSTED',
        "trust = provenance.TRUSTED",
        [TESTS + "test_harness.py", TESTS + "test_disclosure_and_security.py"],
    ),
    Mutation(
        "scanner-never-flags",
        "Injection-associated patterns in tool output are detected and reported.",
        SRC / "provenance.py",
        "def scan(",
        "def scan(  # mutated\n    *_a, **_k):\n    return Report(suspicious=False, flags=[])\n\n\ndef _scan_real(",
        [TESTS + "test_disclosure_and_security.py"],
    ),
    Mutation(
        "adaptive-redteam-ignores-observed-state",
        "Adaptive attack stages wait for declared tool/result conditions before delivery.",
        SRC / "redteam.py",
        'if self.attack.strategy == "adaptive" and not self._matches(',
        "if False and not self._matches(",
        [TESTS + "test_redteam.py"],
    ),
    Mutation(
        "incomplete-redteam-delivery-counted-defended",
        "An attack whose stages were not delivered is withheld from every success-rate denominator.",
        SRC / "redteam.py",
        "if not delivery.complete:",
        "if False:",
        [TESTS + "test_redteam.py"],
    ),
    Mutation(
        "redteam-accepts-unknown-delivery-target",
        "A corpus entry cannot silently select an unsupported security delivery surface.",
        SRC / "redteam.py",
        'if target not in {"tool_output", "tool_description"}:',
        "if False:",
        [TESTS + "test_redteam.py"],
    ),
    Mutation(
        "redteam-coerces-string-expectation-to-true",
        "Security expectations require real booleans; truthy strings cannot change scoring semantics.",
        SRC / "redteam.py",
        'if field_name in expects and not isinstance(expects[field_name], bool):',
        "if False:",
        [TESTS + "test_redteam.py"],
    ),
    Mutation(
        "deny-list-ignored",
        "The controller blocks tool calls named in control.deny.",
        SRC / "builtins" / "controllers.py",
        'for pattern in config.get("deny") or []:',
        "for pattern in []:",
        [TESTS + "test_harness.py", TESTS + "test_redteam.py"],
    ),
    Mutation(
        "tool-result-guardrail-bypassed",
        "Declared tool-result guardrails run before untrusted content re-enters context.",
        SRC / "harness.py",
        "for plugin, spec in tool_result_guardrails:",
        "for plugin, spec in []:",
        [TESTS + "test_disclosure_and_security.py"],
    ),
    Mutation(
        "partial-tool-pins-accepted",
        "Once tool pinning is enabled, every live tool must have a matching pin.",
        SRC / "harness.py",
        "strict=strict",
        "strict=False",
        [TESTS + "test_disclosure_and_security.py"],
    ),
    # ------------------------------------------------------------------- honesty
    Mutation(
        "redteam-always-usable",
        "A red-team run where nothing executed refuses to report a success rate.",
        SRC / "redteam.py",
        "return bool(self.attacks)",
        "return True",
        [TESTS + "test_redteam.py"],
    ),
    Mutation(
        "unverified-cycle-claims-success",
        "A loop that verified nothing reports 'not checked', never a pass.",
        SRC / "loop.py",
        "cycle.goal_met = verified is True",
        "cycle.goal_met = verified is not False",
        [TESTS + "test_loop.py"],
    ),
    Mutation(
        "constant-series-correlates-perfectly",
        "A judge that always returns the same score cannot correlate at 1.0.",
        SRC / "stats.py",
        "if denominator == 0:",
        "if False:",
        [TESTS + "test_stats.py", TESTS + "test_calibration.py"],
    ),
    Mutation(
        "governance-gap-may-be-empty",
        "Every governance control states a gap beside its evidence.",
        SRC / "governance.py",
        '"gap":',
        '"_gap_disabled":',
        [TESTS + "test_governance.py"],
    ),
    Mutation(
        "remote-inference-called-deterministic",
        "Only offline inference is reported as deterministic.",
        SRC / "environment.py",
        'inference == "offline"',
        'inference in ("offline", "remote")',
        [TESTS + "test_governance.py"],
    ),
    Mutation(
        "eval-confidence-ignores-case-variation",
        "Eval score intervals resample whole cases and expose sample uncertainty.",
        SRC / "evaluation.py",
        "sampled = [usable[rng.randrange(len(usable))] for _ in usable]",
        "sampled = usable",
        [TESTS + "test_evaluation.py"],
    ),
    Mutation(
        "ab-winner-ignores-paired-uncertainty",
        "A/B comparison declares a winner only when the paired interval excludes zero.",
        SRC / "evaluation.py",
        "if low > 0:",
        "if point > 0:",
        [TESTS + "test_evaluation.py"],
    ),
    Mutation(
        "audit-hash-verification-trusts-stored-hash",
        "Audit verification recomputes record hashes and detects content tampering.",
        SRC / "governance.py",
        "expected = _record_hash(payload)",
        'expected = payload.get("record_hash")',
        [TESTS + "test_governance.py"],
    ),
    Mutation(
        "approval-evidence-drops-actor",
        "Human approval evidence records the caller-supplied approver identity.",
        SRC / "builtins" / "controllers.py",
        '"actor": actor or "unattributed", "reason": reason,',
        '"actor": "", "reason": reason,',
        [TESTS + "test_harness.py"],
    ),
    # ------------------------------------------------------------------- control
    Mutation(
        "stall-detection-disabled",
        "A loop whose output stops changing is reported as stalled, not merely failing.",
        SRC / "loop.py",
        'detect_stalls", True',
        'detect_stalls", False',
        [TESTS + "test_loop.py"],
    ),
    Mutation(
        "failed-step-does-not-stop-chain",
        "A failed handoff stops the chain at the step that broke.",
        SRC / "loop.py",
        'if outcome.get("failed") and policy == "stop":',
        "if False:",
        [TESTS + "test_loop.py"],
    ),
    Mutation(
        "golden-trajectory-order-is-ignored",
        "Golden trajectory accuracy measures the ordered matching path, not just call count.",
        SRC / "builtins" / "trajectory.py",
        "matched = lengths[-1][-1]",
        "matched = min(len(expected), len(actual))",
        [TESTS + "test_harness.py"],
    ),
    Mutation(
        "concurrent-fanout-serialised",
        "Concurrent loop steps actually overlap instead of only carrying a concurrent label.",
        SRC / "loop.py",
        "ThreadPoolExecutor(max_workers=workers)",
        "ThreadPoolExecutor(max_workers=1)",
        [TESTS + "test_loop.py"],
    ),
    Mutation(
        "bounded-eval-concurrency-collapsed",
        "Async eval cases overlap up to the declared ceiling instead of running serially.",
        SRC / "runtime.py",
        "active_limit = min(max_concurrency, max(len(resolved), 1))",
        "active_limit = 1",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "registry-scan-publishes-before-population",
        "Concurrent callers never observe plugin discovery as complete before inventory exists.",
        SRC / "registry.py",
        "        with self._scan_lock:\n"
        "            if self._scanned and not force:\n                return\n"
        "            if not self._autoload:\n"
        "                # Scoped registries (for example one isolated red-team attack) are\n"
        "                # populated explicitly. Re-scanning every installed distribution for\n"
        "                # each scope is both incorrect and prohibitively expensive on Windows.\n"
        "                self._scanned = True\n                return\n"
        "            if entry_points is None",
        "        if True:\n"
        "            if self._scanned and not force:\n                return\n"
        "            if not self._autoload:\n"
        "                # Scoped registries (for example one isolated red-team attack) are\n"
        "                # populated explicitly. Re-scanning every installed distribution for\n"
        "                # each scope is both incorrect and prohibitively expensive on Windows.\n"
        "                self._scanned = True\n                return\n"
        "            self._scanned = True\n            if entry_points is None",
        [TESTS + "test_registry_and_runtime.py"],
    ),
    Mutation(
        "rate-adaptation-retries-all-provider-errors",
        "Automatic retries apply only to explicit rate-limit responses, never generic failures.",
        SRC / "runtime.py",
        "except RateLimitError as exc:",
        "except ProviderError as exc:",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "retry-after-ignores-total-wait-cap",
        "Provider Retry-After values are capped by the declared total wait budget.",
        SRC / "runtime.py",
        "return min(requested, remaining), source",
        "return requested, source",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "streaming-bypasses-output-guardrail-buffer",
        "Streaming buffers before output controls so rejected partial text cannot leak.",
        SRC / "runtime.py",
        "if output_gates:",
        "if False:",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "streaming-output-limit-disabled",
        "Streamed output is bounded before the next oversized delta is delivered.",
        SRC / "runtime.py",
        "if output_bytes > MAX_STREAM_OUTPUT_BYTES:",
        "if False:",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "streamed-tool-call-fragments-discarded",
        "Fragmented streamed tool arguments assemble into the final auditable completion.",
        SRC / "runtime.py",
        "tool_calls = _merge_stream_tool_calls(chunks)",
        "tool_calls = []",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "harness-streamed-turns-silently-buffered",
        "A stream-enabled harness consumes provider chunks and retains per-step delivery evidence.",
        SRC / "harness.py",
        "if stream_model_calls:",
        "if False:",
        [TESTS + "test_harness.py"],
    ),
    Mutation(
        "stream-event-byte-limit-disabled",
        "Raw provider stream events are size-bounded before JSON parsing.",
        SRC / "builtins" / "providers.py",
        "if event_bytes > MAX_STREAM_EVENT_BYTES:",
        "if False:",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "stream-event-count-limit-disabled",
        "Ignored SSE/JSONL event lines cannot keep a provider stream alive indefinitely.",
        SRC / "builtins" / "providers.py",
        "if event_lines > MAX_STREAM_EVENTS:",
        "if False:",
        [TESTS + "test_async_runtime.py"],
    ),
    Mutation(
        "streaming-evidence-added-after-trace",
        "Streaming delivery evidence is attached before tracing and audit sealing.",
        SRC / "runtime.py",
        "streaming=dict(streaming or {}),",
        "streaming={},",
        [TESTS + "test_async_runtime.py", TESTS + "test_governance.py"],
    ),
    Mutation(
        "explicit-handoff-cycle-ignored",
        "A supervisor route that returns to an earlier agent stops before workers run.",
        SRC / "loop.py",
        "handoff_cycle = _find_handoff_cycle(cycle.route) if detect_handoffs else []",
        "handoff_cycle = []",
        [TESTS + "test_loop.py"],
    ),
    Mutation(
        "context-items-never-update-in-place",
        "Repeated tool work updates one stable context item instead of duplicating it.",
        SRC / "builtins" / "context.py",
        "items[item_id] = line",
        'items[f"{item_id}-{step.index}"] = line',
        [TESTS + "test_context.py"],
    ),
    Mutation(
        "selective-clear-keeps-hostile-body",
        "Selective clearing removes the old tool body while preserving surrounding reasoning.",
        SRC / "builtins" / "context.py",
        "cleared.append(Message(role=message.role, content=note))",
        "cleared.append(message)",
        [TESTS + "test_context.py"],
    ),
    Mutation(
        "optimizer-accepts-instruction-echo",
        "Reflective optimization refuses malformed model output before evaluation or write.",
        SRC / "builtins" / "optimizers.py",
        "payload = json.loads(text)",
        'payload = {"body": text, "rationale": "accepted malformed output"}',
        [TESTS + "test_optimizers.py"],
    ),
    Mutation(
        "sampling-makes-only-one-call",
        "model.params.samples is implemented as real repeated provider calls.",
        SRC / "runtime.py",
        "for _ in range(sample_count):",
        "for _ in range(1):",
        [TESTS + "test_sampling.py"],
    ),
    Mutation(
        "majority-selection-always-picks-first",
        "Majority selection chooses the most common normalized candidate.",
        SRC / "runtime.py",
        "selected_index = max(range(sample_count), key=lambda i: counts[keys[i]])",
        "selected_index = 0",
        [TESTS + "test_sampling.py"],
    ),
    Mutation(
        "sampling-cost-hides-extra-calls",
        "Sampled runs report the cost of every candidate and verifier call.",
        SRC / "runtime.py",
        "selected.cost_usd = sum(item.cost_usd for item in all_completions)",
        "selected.cost_usd = candidates[selected_index].cost_usd",
        [TESTS + "test_sampling.py"],
    ),
    # -------------------------------------------------------------------- format
    Mutation(
        "accepts-future-major-version",
        "Readers refuse a spec major version they do not implement.",
        SRC / "promptfile.py",
        "if major != SPEC_MAJOR:",
        "if False:",
        [TESTS + "test_promptfile.py"],
    ),
    Mutation(
        "duplicate-yaml-keys-silently-overwrite",
        "Readers reject ambiguous duplicate YAML keys instead of silently choosing one.",
        SRC / "promptfile.py",
        "duplicate = key in mapping",
        "duplicate = False",
        [TESTS + "test_cross_language_conformance.py", TESTS + "test_promptfile.py"],
    ),
    Mutation(
        "yaml-line-breaks-normalise-unknown-values",
        "YAML writers preserve every JSON-compatible unknown string exactly.",
        SRC / "promptfile.py",
        'if any(char in data for char in ("\\r", "\\x85", "\\u2028", "\\u2029")):',
        "if False:",
        [TESTS + "test_promptfile.py"],
    ),
    Mutation(
        "unknown-fields-dropped-on-write",
        "A conforming writer preserves keys it does not understand.",
        SRC / "promptfile.py",
        "ordered = self._ordered_data()",
        "ordered = {k: v for k, v in self._ordered_data().items() if k in FIELD_ORDER}",
        [TESTS + "test_promptfile.py"],
    ),
    Mutation(
        "eval-dataset-can-escape-workspace",
        "Dataset-backed evals cannot read files outside the workspace.",
        SRC / "evaluation.py",
        "candidate.relative_to(root)",
        "Path('.')",
        [TESTS + "test_evaluation.py"],
    ),
    # ------------------------------------------------------------------- ranking
    Mutation(
        "memory-entity-weight-flattened",
        "Entity matches outrank keyword overlap in hybrid recall.",
        SRC / "builtins" / "memory.py",
        '"entity": 3.0',
        '"entity": 0.1',
        [TESTS + "test_memory.py"],
    ),
]


# ---------------------------------------------------------------------------
# anchor validation
# ---------------------------------------------------------------------------


def _code_spans(source: str) -> list[tuple[int, int]]:
    """Character offsets of tokens that are real code — not strings, not comments.

    A mutation that only edits a docstring changes no behaviour and therefore survives
    every test, which reads as a coverage gap that does not exist.
    """
    spans: list[tuple[int, int]] = []
    offsets, running = [], 0
    for line in source.splitlines(keepends=True):
        offsets.append(running)
        running += len(line)

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            srow, scol = tok.start
            erow, ecol = tok.end
            if srow - 1 < len(offsets) and erow - 1 < len(offsets):
                spans.append((offsets[srow - 1] + scol, offsets[erow - 1] + ecol))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - malformed source
        return []
    return spans


def locate(m: Mutation) -> int:
    """Offset of the anchor within real code, or ``-1``.

    Scans every occurrence rather than taking the first, so an anchor appearing in both a
    docstring and the code below it still lands on the code.
    """
    source = m.path.read_text(encoding="utf-8")
    spans = _code_spans(source)
    start = source.find(m.old)
    while start != -1:
        end = start + len(m.old)
        if any(s <= start and end <= e for s, e in spans) or any(
            start <= s and e <= end for s, e in spans
        ):
            return start
        start = source.find(m.old, start + 1)
    return -1


def check() -> int:
    """Verify every anchor resolves to real code. Fast enough to gate every push."""
    problems = []
    for m in M:
        if not m.path.exists():
            problems.append(f"{m.name}: {m.path.name} does not exist")
        elif m.old not in m.path.read_text(encoding="utf-8"):
            problems.append(f"{m.name}: anchor not found in {m.path.name} — refactored away?")
        elif locate(m) == -1:
            problems.append(f"{m.name}: anchor matches only inside a string or comment")

    for problem in problems:
        print(f"STALE  {problem}")
    print(f"\n{len(M) - len(problems)}/{len(M)} anchors valid")
    if problems:
        print(
            "\nA stale anchor silently drops a mutation from the suite, so this is a "
            "failure rather than a warning. Re-point the anchor at the moved code, or "
            "delete the mutation on purpose."
        )
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


def run_tests(tests: list[str], timeout: int = 300) -> bool:
    """True if the suite passed — which means the mutant survived, which is bad."""
    existing = [t for t in tests if (REPO / t).exists()]
    if not existing:
        return True
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *existing, "-x", "-q", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode == 0


def main() -> int:
    if "--list" in sys.argv:
        for i, m in enumerate(M):
            print(f"{i:2d}  {m.name:38s} {m.claim}")
        return 0
    if "--check" in sys.argv:
        return check()

    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else len(M)

    survived, killed, stale = [], [], []
    for m in M[lo:hi]:
        offset = locate(m)
        if offset == -1:
            stale.append(m)
            print(f"STALE     {m.name} — anchor missing, or matches prose only")
            continue

        source = m.path.read_text(encoding="utf-8")
        m.path.write_text(
            source[:offset] + m.new + source[offset + len(m.old):], encoding="utf-8"
        )
        try:
            if run_tests(m.tests):
                alive = run_tests([TESTS.rstrip("/")])
                caught_by = "nothing"
            else:
                alive, caught_by = False, "its targeted tests"
        finally:
            # Restore even if pytest raised or the run timed out. Leaving a mutated
            # working tree behind would be worse than any result this produces.
            m.path.write_text(source, encoding="utf-8")

        if alive:
            survived.append(m)
            print(f"SURVIVED  {m.name}\n          {m.claim}")
        else:
            killed.append(m)
            print(f"killed    {m.name}  (by {caught_by})")

    total = len(survived) + len(killed)
    if total:
        print(f"\n{len(killed)}/{total} killed — {100 * len(killed) / total:.0f}% mutation score")
    if stale:
        print(f"{len(stale)} stale (counted as failures, not skips)")
    for m in survived:
        print(f"  GAP: {m.claim}")
    return 1 if (survived or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
