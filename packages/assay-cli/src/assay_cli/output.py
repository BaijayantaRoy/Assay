"""Terminal output helpers.

Deliberately dependency-free: colour via raw ANSI, tables via ``str.ljust``. ``rich``
is an optional extra that improves rendering but is never required, so ``assay`` stays
installable in constrained environments (CI images, Alpine, air-gapped boxes).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterable

_COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREEN, RED, YELLOW, CYAN, MAGENTA = (
    "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[35m",
)

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


class _EncodingSafeStream:
    """Pre-sanitize text without reconfiguring a generated-launcher pipe.

    ``TextIOWrapper.reconfigure`` is correct for normal Python processes, but distlib's
    Windows ``*.exe`` console launcher can deadlock when the stream is a redirected pipe.
    Encoding first with replacement keeps the existing wrapper and descriptor intact,
    while making every later ``print`` total for that stream's actual encoding.
    """

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        encoding = getattr(self._stream, "encoding", None) or "utf-8"
        safe = str(text).encode(encoding, errors="backslashreplace").decode(encoding)
        return self._stream.write(safe)

    def writelines(self, lines):
        return self._stream.writelines(self._safe(line) for line in lines)

    def _safe(self, text):
        encoding = getattr(self._stream, "encoding", None) or "utf-8"
        return str(text).encode(encoding, errors="backslashreplace").decode(encoding)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def configure_console() -> None:
    """Make terminal output total: unsupported glyphs must never crash the CLI.

    Windows still commonly starts Python with a legacy console encoding.  Keeping the
    stream's chosen encoding while replacing only unrepresentable characters preserves
    redirected JSON and makes human output degrade legibly instead of raising
    ``UnicodeEncodeError``.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if isinstance(stream, _EncodingSafeStream):
            continue
        if not stream.isatty():
            setattr(sys, name, _EncodingSafeStream(stream))
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="backslashreplace")
            except (AttributeError, ValueError):
                # Test doubles and already-detached streams may reject reconfiguration.
                pass


def disable_color() -> None:
    global _COLOR, PASS, FAIL, WARN
    _COLOR = False


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}" if _COLOR else text


def heading(text: str) -> None:
    print(f"\n{_c(str(text).upper(), BOLD + CYAN)}")


def kv(key: str, value: Any) -> None:
    print(f"  {_c(str(key).ljust(14), DIM)} {value}")


def ok(text: str) -> None:
    print(_c(f"✔ {text}", GREEN))


def fail(text: str) -> None:
    print(_c(f"✘ {text}", RED))


def warn(text: str) -> None:
    print(_c(f"! {text}", YELLOW))


def dim(text: str) -> None:
    print(_c(text, DIM))


def die(message: str, code: int = 1) -> None:
    print(_c(f"✘ {message}", RED), file=sys.stderr)
    raise SystemExit(code)


def emit(args, payload: Any, *, force: bool = False) -> None:
    """Print JSON when ``--json`` is set (or forced). Otherwise stay silent."""
    if getattr(args, "json", False) or force:
        # Preserve readable Unicode in a terminal. Redirected output must stay encodable
        # even on legacy Windows pipes, where reconfiguring the generated console
        # launcher's stream can deadlock before the command starts.
        print(json.dumps(
            payload,
            indent=2,
            default=str,
            ensure_ascii=not sys.stdout.isatty(),
        ))


def table(rows: Iterable[dict], columns: list[str] | None = None) -> None:
    rows = list(rows)
    if not rows:
        return
    columns = columns or list(rows[0])
    columns = [c for c in columns if any(r.get(c) not in (None, "") for r in rows)]
    widths = {
        c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns
    }
    header = "  ".join(_c(c.ljust(widths[c]), BOLD) for c in columns)
    print(header)
    print(_c("  ".join("─" * widths[c] for c in columns), DIM))
    for row in rows:
        cells = []
        for c in columns:
            value = str(row.get(c, "") if row.get(c) is not None else "")
            if c in ("error",) and value:
                value = _c(value, RED)
                cells.append(value.ljust(widths[c] + len(RED) + len(RESET)))
            else:
                cells.append(value.ljust(widths[c]))
        print("  ".join(cells).rstrip())


def render_attack(result) -> None:
    """One attack, as it completes."""
    marks = {
        "defended": _c("defended ", GREEN),
        "compromised": _c("COMPROMISED", RED + BOLD),
        "clean": _c("clean    ", GREEN),
        "false_positive": _c("false-pos", YELLOW),
        "error": _c("error    ", YELLOW),
    }
    detail = []
    if result.detected:
        detail.append("detected: " + ", ".join(result.detection_flags[:3]))
    if result.blocked_by_policy:
        detail.append(f"{len(result.blocked_by_policy)} blocked by policy")
    if result.canary_leaked:
        detail.append(_c("canary leaked", RED))
    if result.compliance_reason:
        detail.append(result.compliance_reason)
    suffix = f"  ({'; '.join(detail)})" if detail else ""
    print(f"  {marks.get(result.outcome, result.outcome)}  "
          f"{result.attack.id:<12} {result.attack.category:<22}{suffix}")


def _one_line(text: str, limit: int = 100) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_step(step) -> None:
    """One agent step, printed as it completes: what it did, and what came back."""
    cost = step.completion.cost_usd if step.completion else 0.0
    print(f"  {_c(f'step {step.index}', BOLD)}  "
          + _c(f"{step.context_tokens} ctx tokens  ${cost:.6f}", DIM))
    if step.context_action:
        dim(f"    context: {step.context_action}")
    results = list(step.tool_results)
    for i, call in enumerate(step.tool_calls):
        result = next(
            (r for r in results if r.call is call or (call.id and r.call.id == call.id)),
            results[i] if i < len(results) else None,
        )
        if result is None:
            mark = _c("pending", DIM)
        elif result.denied:
            mark = _c("denied", YELLOW)
        elif result.is_error:
            mark = _c("error", RED)
        else:
            mark = _c("ok", GREEN)
        args = _one_line(json.dumps(call.arguments, default=str), 60)
        print(f"    → {call.name}({args})  {mark}")
        if result is not None and result.denied and result.denied_reason:
            dim(f"      {_one_line(result.denied_reason)}")
        elif result is not None and result.is_error:
            print(f"      {_c(_one_line(result.content), RED)}")
    if step.text and not step.tool_calls:
        print(f"    {_one_line(step.text)}")


def render_trajectory_summary(trajectory) -> None:
    """The whole run: outcome, spend, and anything that went wrong on the way."""
    heading("Agent run")
    kv("harness", trajectory.harness_id)
    kv("model", trajectory.model or "default")
    status = trajectory.status
    kv("status", _c(status, GREEN) if status == "completed" else _c(status, RED))
    if trajectory.stop_reason:
        kv("stop reason", trajectory.stop_reason)
    kv("iterations", trajectory.iterations)
    kv("tool calls", len(trajectory.tool_call_names))
    kv("cost", f"${trajectory.cost_usd:.6f}")
    kv("tokens", trajectory.total_tokens)
    kv("wallclock", f"{trajectory.wallclock_s:.2f}s")

    # Tri-state on purpose: None means nothing checked the result, which is not a pass.
    if trajectory.verified is True:
        kv("verified", _c("yes", GREEN))
    elif trajectory.verified is False:
        kv("verified", _c("no", RED))
    else:
        kv("verified", _c("not checked", YELLOW))
    if trajectory.verification_detail:
        dim(f"  {trajectory.verification_detail}")

    if trajectory.tool_errors:
        warn(f"{len(trajectory.tool_errors)} tool call(s) failed")
    if trajectory.denied_calls:
        warn(f"{len(trajectory.denied_calls)} tool call(s) denied by policy")

    if trajectory.output:
        heading("Output")
        print(trajectory.output)


def render_redteam_summary(report) -> None:
    payload = report.to_dict()

    heading("Red team")
    kv("harness", payload["harness_id"])
    kv("model", payload["model"])
    kv("mode", payload["mode"])
    kv("attacks", payload["attacks_run"])
    kv("benign controls", payload["benign_controls"])

    if payload.get("errored"):
        heading("Errors")
        fail(f"{payload['errored']} attack(s) did not run at all:")
        for e in payload.get("errors", [])[:5]:
            print(f"    {e['id']}: {e['error']}")
        dim("  Rates below exclude these, so they do not describe a defended system.")

    if not payload.get("usable", True):
        heading("Verdict")
        fail("NO ATTACKS RAN — the rates below are meaningless, not good news.")
        dim("  Fix the errors above and re-run. A 0% attack success rate produced by "
            "nothing executing is exactly the false green this tool exists to prevent.")
        return

    heading("Rates")
    asr = payload["attack_success_rate"]
    (ok if asr == 0 else fail)(f"attack success rate  {asr:.1%}  (lower is better)")
    dim(f"  detection rate       {payload['detection_rate']:.1%}  "
        "(detection is not prevention)")
    false_positive_rate = payload["false_positive_rate"]
    if false_positive_rate is None:
        dim("  false positive rate  not checked  (no benign controls ran)")
    else:
        dim(f"  false positive rate  {false_positive_rate:.1%}  "
            "(benign text wrongly flagged)")

    if payload["by_category"]:
        heading("By category")
        table(
            [{"category": name, "attacks": v["total"],
              "compromised": v["compromised"], "detected": v["detected"]}
             for name, v in sorted(payload["by_category"].items())],
            ["category", "attacks", "compromised", "detected"],
        )

    if payload["compromised"]:
        heading("Compromised")
        for entry in payload["compromised"]:
            fail(f"{entry['id']} ({entry['category']}, {entry['severity']}): "
                 f"{entry['compliance_reason']}")

    heading("Verdict")
    if report.passed:
        ok(f"no attack in this corpus succeeded ({payload['attacks_run']} attempted)")
    else:
        fail(f"{len(payload['compromised'])} of {payload['attacks_run']} attacks succeeded")
    dim("\n" + payload["mode_note"])
    dim("A clean result covers the payloads in this corpus and nothing else. Published "
        "attack success rates against current defences exceed 80% — treat this as a "
        "regression gate, not a safety guarantee.")


def render_calibration(report) -> None:
    """Two-stage verdict, with the numbers a reader needs to disagree with it."""
    payload = report.to_dict()
    rubric, judge = payload["rubric"], payload["judge"]

    heading("Stage 1 — is the rubric usable?")
    if rubric["cohens_kappa"]:
        interval = rubric["cohens_kappa"]
        kv("inter-rater κ", f"{interval['point']:.3f} "
                            f"[{interval['low']:.3f}, {interval['high']:.3f}] "
                            f"· {rubric['interpretation']}")
        kv("weighted κ", f"{rubric['weighted_kappa']:.3f}")
        kv("raw agreement", f"{rubric['percent_agreement']:.1%}")
        kv("raters", ", ".join(rubric["raters"]))
        if rubric["pairwise_kappa"]:
            for pair, value in sorted(rubric["pairwise_kappa"].items()):
                kv(f"  {pair}", f"{value:.3f}")
    else:
        warn("inter-rater agreement could not be measured")
    (ok if rubric["ok"] else fail)(
        f"rubric {'passes' if rubric['ok'] else 'fails'} "
        f"(threshold κ ≥ {payload['thresholds']['inter_rater_kappa']})"
    )

    heading("Stage 2 — does the judge track humans?")
    if judge["spearman"]:
        interval = judge["spearman"]
        kv("Spearman ρ", f"{interval['point']:.3f} "
                         f"[{interval['low']:.3f}, {interval['high']:.3f}] (n={interval['n']})")
        kv("Pearson r", f"{judge['pearson']:.3f}")
        kv("weighted κ", f"{judge['weighted_kappa']:.3f}")
        kv("mean bias", f"{judge['bias']:+.3f}")
    else:
        warn("judge agreement could not be measured")
    (ok if judge["ok"] else fail)(
        f"judge {'passes' if judge['ok'] else 'fails'} "
        f"(threshold ρ ≥ {payload['thresholds']['judge_spearman']})"
    )

    heading("Verdict")
    if payload["certified"]:
        ok(f"CERTIFIED over n={payload['n']}")
    else:
        fail(f"NOT CERTIFIED over n={payload['n']}")
    for problem in payload["failures"]:
        print(f"    ✗ {problem}")
    for note in payload["warnings"]:
        warn(f"  {note}")
    dim(f"\n{payload['threshold_source']}")


def print_diff(diff_text: str) -> None:
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(_c(line, BOLD))
        elif line.startswith("@@"):
            print(_c(line, MAGENTA))
        elif line.startswith("+"):
            print(_c(line, GREEN))
        elif line.startswith("-"):
            print(_c(line, RED))
        else:
            print(line)
