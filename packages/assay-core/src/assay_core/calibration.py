"""Judge calibration.

The problem
-----------
"Ask a model whether the output is good" produces a number between 0 and 1. That number
looks like a measurement, gets averaged, plotted, and used to gate deploys. Nothing in
the pipeline ever checks whether it tracks what a human would say.

An uncalibrated judge is not a weak measurement. It is an *unknown* measurement, and an
unknown measurement presented as a score is worse than no score, because it is acted on.

The protocol
------------
The field has converged on specific numbers (see ``docs/architecture/RESEARCH.md`` §3.1).
This module implements them as a **two-stage gate**, because the two stages diagnose
different faults:

**Stage 1 — is the rubric usable?**
    Measure agreement *between human raters* (Cohen's κ). If humans cannot agree with
    each other, the rubric is ambiguous. Calibrating a judge against an ambiguous rubric
    measures nothing. The cited action at κ < 0.6 is to fix the rubric — not the judge.

**Stage 2 — does the judge track humans?**
    Measure the judge against the human consensus (Spearman ρ, plus weighted κ on binned
    scores). The cited bar for production alignment is ρ ≥ 0.80.

A judge passing both is **certified**, and the certificate records the sample size, the
statistics, the thresholds and the date. A judge failing either is reported with the
specific reason, and the workspace policy may refuse to run it.

What this does not do
---------------------
It does not make a judge correct. It measures agreement with the humans who labelled
*this* dataset, on *this* rubric, at *this* moment. Distribution shift silently
invalidates a certificate, which is why certificates carry a date and a sample size and
why re-calibration is a maintenance task rather than a one-off.

The thresholds themselves are conventions from one research community, not physics. They
are cited, configurable, and reported alongside the raw numbers so a reader can disagree.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import stats
from .errors import AssayError

# --- Published thresholds. Cited, not invented; overridable per workspace. ---

#: Below this, inter-rater agreement is too weak to calibrate against — fix the rubric.
MIN_INTER_RATER_KAPPA = 0.60
#: Judge-vs-human rank correlation required for production use.
MIN_JUDGE_SPEARMAN = 0.80
#: Sample size below which aggregate metrics are not considered trustworthy.
MIN_SAMPLE_SIZE = 500
#: Below this, a report is refused outright rather than qualified.
ABSOLUTE_MIN_SAMPLE = 20

THRESHOLD_SOURCE = (
    "Thresholds from LLM-as-judge calibration practice surveyed in "
    "docs/architecture/RESEARCH.md §3.1. Conventions, not physical constants — "
    "override in assay.yaml under judge.thresholds."
)


class CalibrationError(AssayError):
    code = "assay.calibration"


# ---------------------------------------------------------------------------
# Label sets
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LabelledCase:
    """One item with human ratings, and optionally a judge score.

    ``ratings`` maps rater id → score. Two or more raters are required for stage 1;
    the protocol explicitly calls for independent double-rating.
    """

    id: str
    ratings: dict[str, float] = field(default_factory=dict)
    output: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    judge_score: float | None = None
    judge_reason: str = ""

    @property
    def consensus(self) -> float:
        """Human consensus. Mean of raters — the usual choice for ordinal rubrics."""
        return statistics.fmean(self.ratings.values()) if self.ratings else 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "LabelledCase":
        ratings = data.get("ratings") or {}
        if not ratings and "score" in data:
            ratings = {"rater1": float(data["score"])}
        return cls(
            id=str(data.get("id") or data.get("case_id") or ""),
            ratings={k: float(v) for k, v in ratings.items()},
            output=data.get("output", ""),
            input=data.get("input") or {},
            judge_score=data.get("judge_score"),
            judge_reason=data.get("judge_reason", ""),
        )


def load_labels(path: str | Path) -> list[LabelledCase]:
    """Read a ``*.labels.jsonl`` file.

    One JSON object per line::

        {"id": "c1", "output": "...", "ratings": {"alice": 4, "bob": 5}}
    """
    file = Path(path)
    if not file.is_file():
        raise CalibrationError(f"label file not found: {path}")

    cases: list[LabelledCase] = []
    for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            cases.append(LabelledCase.from_dict(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise CalibrationError(f"{path}:{number}: invalid JSON: {exc}") from exc
    if not cases:
        raise CalibrationError(f"{path} contains no labelled cases")
    return cases


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Thresholds:
    inter_rater_kappa: float = MIN_INTER_RATER_KAPPA
    judge_spearman: float = MIN_JUDGE_SPEARMAN
    sample_size: int = MIN_SAMPLE_SIZE

    @classmethod
    def from_config(cls, config: dict | None) -> "Thresholds":
        config = config or {}
        return cls(
            inter_rater_kappa=float(config.get("inter_rater_kappa", MIN_INTER_RATER_KAPPA)),
            judge_spearman=float(config.get("judge_spearman", MIN_JUDGE_SPEARMAN)),
            sample_size=int(config.get("sample_size", MIN_SAMPLE_SIZE)),
        )

    def to_dict(self) -> dict:
        return {
            "inter_rater_kappa": self.inter_rater_kappa,
            "judge_spearman": self.judge_spearman,
            "sample_size": self.sample_size,
        }


@dataclass
class CalibrationReport:
    """The verdict, and everything needed to disagree with it."""

    judge_id: str = ""
    n: int = 0
    thresholds: Thresholds = field(default_factory=Thresholds)

    # Stage 1 — rubric
    raters: list[str] = field(default_factory=list)
    inter_rater_kappa: stats.Interval | None = None
    inter_rater_weighted_kappa: float = 0.0
    inter_rater_agreement: float = 0.0
    pairwise_kappa: dict[str, float] = field(default_factory=dict)

    # Stage 2 — judge
    judge_spearman: stats.Interval | None = None
    judge_pearson: float = 0.0
    judge_kappa: float = 0.0
    judge_bias: float = 0.0

    human_scores: stats.Descriptives = field(default_factory=stats.Descriptives)
    judge_scores: stats.Descriptives = field(default_factory=stats.Descriptives)

    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""

    @property
    def rubric_ok(self) -> bool:
        return bool(self.inter_rater_kappa) and (
            self.inter_rater_kappa.point >= self.thresholds.inter_rater_kappa
        )

    @property
    def judge_ok(self) -> bool:
        return bool(self.judge_spearman) and (
            self.judge_spearman.point >= self.thresholds.judge_spearman
        )

    @property
    def certified(self) -> bool:
        """Both stages passed *and* nothing disqualifying was found."""
        return self.rubric_ok and self.judge_ok and not self.failures

    def to_dict(self) -> dict:
        return {
            "judge_id": self.judge_id,
            "certified": self.certified,
            "n": self.n,
            "created_at": self.created_at,
            "thresholds": self.thresholds.to_dict(),
            "threshold_source": THRESHOLD_SOURCE,
            "rubric": {
                "ok": self.rubric_ok,
                "raters": self.raters,
                "cohens_kappa": self.inter_rater_kappa.to_dict() if self.inter_rater_kappa else None,
                "weighted_kappa": round(self.inter_rater_weighted_kappa, 4),
                "percent_agreement": round(self.inter_rater_agreement, 4),
                "pairwise_kappa": {k: round(v, 4) for k, v in self.pairwise_kappa.items()},
                "interpretation": stats.kappa_label(
                    self.inter_rater_kappa.point if self.inter_rater_kappa else 0.0
                ),
            },
            "judge": {
                "ok": self.judge_ok,
                "spearman": self.judge_spearman.to_dict() if self.judge_spearman else None,
                "pearson": round(self.judge_pearson, 4),
                "weighted_kappa": round(self.judge_kappa, 4),
                "bias": round(self.judge_bias, 4),
            },
            "human_scores": self.human_scores.to_dict(),
            "judge_scores": self.judge_scores.to_dict(),
            "failures": self.failures,
            "warnings": self.warnings,
        }

    def certificate(self) -> dict:
        """Compact record for embedding in a PromptFile under ``calibration:``."""
        return {
            "certified": self.certified,
            "n": self.n,
            "date": self.created_at[:10],
            "inter_rater_kappa": round(self.inter_rater_kappa.point, 4) if self.inter_rater_kappa else None,
            "judge_spearman": round(self.judge_spearman.point, 4) if self.judge_spearman else None,
            "thresholds": self.thresholds.to_dict(),
        }


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


def _bin(value: float, scale: Sequence[float]) -> float:
    """Snap a continuous score onto the human rating scale, for κ.

    κ needs categories. Binning is a lossy step and is stated as such in the report,
    which is why Spearman — which needs no binning — is the primary judge statistic.
    """
    return min(scale, key=lambda s: abs(s - value))


def calibrate(
    cases: Sequence[LabelledCase],
    *,
    judge: Callable[[LabelledCase], tuple[float, str]] | None = None,
    judge_id: str = "",
    thresholds: Thresholds | None = None,
    resamples: int = 1000,
) -> CalibrationReport:
    """Run the two-stage protocol.

    ``judge`` is called for cases without a ``judge_score``. Supplying scores in the
    label file instead lets calibration run entirely offline.
    """
    thresholds = thresholds or Thresholds()
    report = CalibrationReport(
        judge_id=judge_id, n=len(cases), thresholds=thresholds,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if len(cases) < ABSOLUTE_MIN_SAMPLE:
        raise CalibrationError(
            f"{len(cases)} cases is too few to calibrate anything "
            f"(absolute minimum {ABSOLUTE_MIN_SAMPLE}, recommended {thresholds.sample_size})",
            n=len(cases),
        )

    # --- Stage 1: is the rubric usable? ---------------------------------

    rater_ids = sorted({r for case in cases for r in case.ratings})
    report.raters = rater_ids

    if len(rater_ids) < 2:
        report.warnings.append(
            "only one rater: inter-rater agreement cannot be measured, so the rubric is "
            "unvalidated. The protocol calls for at least two independent raters."
        )
        report.failures.append("rubric: fewer than two independent raters")
    else:
        complete = [c for c in cases if all(r in c.ratings for r in rater_ids[:2])]
        if len(complete) < ABSOLUTE_MIN_SAMPLE:
            report.failures.append(
                f"rubric: only {len(complete)} cases rated by both "
                f"{rater_ids[0]} and {rater_ids[1]}"
            )
        else:
            first = [c.ratings[rater_ids[0]] for c in complete]
            second = [c.ratings[rater_ids[1]] for c in complete]
            report.inter_rater_kappa = stats.bootstrap_ci(
                first, second, stats.cohens_kappa, resamples=resamples
            )
            report.inter_rater_weighted_kappa = stats.weighted_kappa(first, second)
            report.inter_rater_agreement = stats.percent_agreement(first, second)

            # All pairs, so a single dissenting rater is visible rather than averaged away.
            for i, a in enumerate(rater_ids):
                for b in rater_ids[i + 1:]:
                    both = [c for c in cases if a in c.ratings and b in c.ratings]
                    if len(both) >= ABSOLUTE_MIN_SAMPLE:
                        report.pairwise_kappa[f"{a}~{b}"] = stats.cohens_kappa(
                            [c.ratings[a] for c in both], [c.ratings[b] for c in both]
                        )

            if not report.rubric_ok:
                report.failures.append(
                    f"rubric: inter-rater κ {report.inter_rater_kappa.point:.3f} < "
                    f"{thresholds.inter_rater_kappa}. The rubric is ambiguous — refine it "
                    "before calibrating a judge against it."
                )

    # --- Stage 2: does the judge track humans? ---------------------------

    scored: list[LabelledCase] = []
    for case in cases:
        if case.judge_score is None and judge is not None:
            try:
                case.judge_score, case.judge_reason = judge(case)
            except Exception as exc:
                report.warnings.append(f"judge failed on case {case.id!r}: {exc}")
                continue
        if case.judge_score is not None:
            scored.append(case)

    if len(scored) < ABSOLUTE_MIN_SAMPLE:
        report.failures.append(
            f"judge: only {len(scored)} cases have judge scores "
            f"(minimum {ABSOLUTE_MIN_SAMPLE})"
        )
        return _finalise(report, cases, scored, thresholds)

    human = [c.consensus for c in scored]
    machine = [float(c.judge_score) for c in scored]

    report.judge_spearman = stats.bootstrap_ci(
        machine, human, stats.spearman, resamples=resamples
    )
    report.judge_pearson = stats.pearson(machine, human)
    report.judge_bias = statistics.fmean(machine) - statistics.fmean(human)

    scale = sorted({round(v) for v in human}) or [0, 1]
    report.judge_kappa = stats.weighted_kappa(
        [_bin(v, scale) for v in machine], [_bin(v, scale) for v in human]
    )

    if not report.judge_ok:
        report.failures.append(
            f"judge: Spearman ρ {report.judge_spearman.point:.3f} < "
            f"{thresholds.judge_spearman}. Its scores do not track human judgement "
            "closely enough to gate on."
        )

    return _finalise(report, cases, scored, thresholds)


def _finalise(report, cases, scored, thresholds) -> CalibrationReport:
    report.human_scores = stats.describe([c.consensus for c in cases if c.ratings])
    report.judge_scores = stats.describe([float(c.judge_score) for c in scored])

    if report.n < thresholds.sample_size:
        report.warnings.append(
            f"{report.n} cases is below the recommended {thresholds.sample_size} for "
            "trustworthy aggregates. Treat the interval width, not the point estimate, "
            "as the real result."
        )
    if report.judge_spearman and report.judge_spearman.width > 0.30:
        report.warnings.append(
            f"the Spearman interval spans {report.judge_spearman.width:.2f} — too wide to "
            "conclude much. More labelled cases will narrow it."
        )
    if abs(report.judge_bias) > 0.5:
        direction = "higher" if report.judge_bias > 0 else "lower"
        report.warnings.append(
            f"the judge scores {abs(report.judge_bias):.2f} points {direction} than humans "
            "on average. Rank correlation can still be high while absolute scores are "
            "systematically shifted."
        )
    if report.judge_scores.stdev < 0.05 and report.judge_scores.n > 0:
        report.failures.append(
            "judge: scores have almost no variance — it is returning the same value "
            "regardless of input, which correlates with nothing."
        )
    return report


# ---------------------------------------------------------------------------
# Chain-of-thought judging (the G-Eval result)
# ---------------------------------------------------------------------------

COT_JUDGE_TEMPLATE = """You are evaluating a response against a rubric. Reason before scoring.

RUBRIC
{criteria}

SCALE
{scale}

{reference_block}RESPONSE TO EVALUATE
{response}

Work through this in order:
1. Restate what the rubric is actually asking for.
2. Identify specific evidence in the response for and against it. Quote it.
3. Note anything the rubric does *not* cover that you should therefore ignore.
4. Assign the score the evidence supports.

Reply with JSON only:
{{"reasoning": "<your step-by-step analysis>", "score": <number>, "confidence": <0.0-1.0>}}"""


def build_judge_prompt(
    criteria: str,
    response: str,
    *,
    scale: str = "0.0 to 1.0, where 1.0 fully satisfies the rubric",
    reference: str | None = None,
) -> str:
    """Chain-of-thought judge prompt.

    Forcing articulated reasoning before the score measurably improves alignment with
    human judgement (the G-Eval result) and mitigates several known judge biases. It
    costs more tokens, which is the trade this project makes by default — an unreliable
    cheap score is not a saving.
    """
    return COT_JUDGE_TEMPLATE.format(
        criteria=criteria.strip(),
        scale=scale,
        reference_block=f"REFERENCE ANSWER\n{reference}\n\n" if reference else "",
        response=response,
    )


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


def read_certificate(prompt: Any) -> dict | None:
    """Certificate stored on a judge PromptFile under ``calibration:``."""
    return (prompt.data.get("calibration") or None) if hasattr(prompt, "data") else None


def is_certified(prompt: Any, *, max_age_days: int | None = 180) -> tuple[bool, str]:
    """Whether a judge may be used under a workspace policy requiring calibration.

    Certificates expire. Agreement measured against last quarter's distribution is not
    evidence about this quarter's, and a certificate with no expiry would quietly become
    a rubber stamp.
    """
    certificate = read_certificate(prompt)
    if not certificate:
        return False, "no calibration certificate — run 'assay judge calibrate'"
    if not certificate.get("certified"):
        return False, "calibration was run and did not pass"
    if max_age_days:
        date = str(certificate.get("date") or "")
        try:
            age = (datetime.now(timezone.utc).date() - datetime.fromisoformat(date).date()).days
        except Exception:
            return False, f"certificate has an unreadable date: {date!r}"
        if age > max_age_days:
            return False, (
                f"certificate is {age} days old (limit {max_age_days}); "
                "re-calibrate against current data"
            )
    return True, f"certified on {certificate.get('date')} over n={certificate.get('n')}"
