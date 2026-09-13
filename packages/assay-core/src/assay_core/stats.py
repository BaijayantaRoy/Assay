"""Agreement and correlation statistics.

Pure Python, no SciPy. Two reasons: ``assay-core`` stays dependency-light for a component
that must run in CI images and air-gapped environments, and these estimators are small
enough that a correct implementation is auditable in one screen.

Every function here is tested against hand-computed values in
``tests/test_calibration.py``. Statistics that decide whether a quality gate opens have
to be right, and "it looked plausible" is not a test.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def rank(values: Sequence[float]) -> list[float]:
    """Fractional ranks, averaging ties.

    Tie handling is not optional: with a 1–5 rubric most values are tied, and naive
    ordinal ranking silently inflates correlation.
    """
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position
        while end + 1 < len(indexed) and values[indexed[end + 1]] == values[indexed[position]]:
            end += 1
        average = (position + end) / 2 + 1  # ranks are 1-based
        for i in range(position, end + 1):
            ranks[indexed[i]] = average
        position = end + 1
    return ranks


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """Pearson product-moment correlation. Returns 0.0 when a series has no variance."""
    if len(x) != len(y):
        raise ValueError("series must be the same length")
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    dx = [xi - mean_x for xi in x]
    dy = [yi - mean_y for yi in y]
    numerator = sum(a * b for a, b in zip(dx, dy))
    denominator = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if denominator == 0:
        # A constant series has no rank information. Reporting 0 is honest; reporting
        # 1.0 (as some implementations do when both are constant) would certify a judge
        # that always says the same thing.
        return 0.0
    return numerator / denominator


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation — Pearson on fractional ranks."""
    return pearson(rank(x), rank(y))


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def cohens_kappa(a: Sequence, b: Sequence) -> float:
    """Cohen's κ for two raters over categorical labels.

    κ = (pₒ − pₑ) / (1 − pₑ), where pₒ is observed agreement and pₑ is the agreement
    expected from the raters' marginal distributions.

    Returns 1.0 when both raters used exactly one category and agreed on every item —
    perfect agreement is undefined under the formula (pₑ = 1) but is not a failure.
    """
    if len(a) != len(b):
        raise ValueError("rating series must be the same length")
    n = len(a)
    if n == 0:
        return 0.0

    categories = sorted({*a, *b}, key=str)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n

    expected = 0.0
    for category in categories:
        pa = sum(1 for x in a if x == category) / n
        pb = sum(1 for y in b if y == category) / n
        expected += pa * pb

    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def weighted_kappa(a: Sequence[float], b: Sequence[float], *, weights: str = "quadratic") -> float:
    """Weighted κ for *ordinal* ratings.

    Unweighted κ treats a 1-vs-5 disagreement identically to 4-vs-5, which is wrong for
    a graded rubric. Quadratic weighting is the usual default for ordinal scales.
    """
    if len(a) != len(b):
        raise ValueError("rating series must be the same length")
    n = len(a)
    if n == 0:
        return 0.0

    categories = sorted({*a, *b})
    k = len(categories)
    if k < 2:
        return 1.0 if all(x == y for x, y in zip(a, b)) else 0.0
    index = {c: i for i, c in enumerate(categories)}

    def weight(i: int, j: int) -> float:
        distance = abs(i - j) / (k - 1)
        return distance ** 2 if weights == "quadratic" else distance

    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1 / n

    marginal_a = [sum(1 for x in a if x == c) / n for c in categories]
    marginal_b = [sum(1 for y in b if y == c) / n for c in categories]

    numerator = sum(
        weight(i, j) * observed[i][j] for i in range(k) for j in range(k)
    )
    denominator = sum(
        weight(i, j) * marginal_a[i] * marginal_b[j] for i in range(k) for j in range(k)
    )
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return 1 - numerator / denominator


def percent_agreement(a: Sequence, b: Sequence) -> float:
    """Raw agreement. Reported alongside κ because it is intuitive — and because the gap
    between the two is what shows how much of the agreement was chance."""
    if not a:
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Interval:
    """A point estimate with a bootstrap confidence interval."""

    point: float
    low: float
    high: float
    level: float = 0.95
    n: int = 0

    @property
    def width(self) -> float:
        return self.high - self.low

    def to_dict(self) -> dict:
        return {
            "point": round(self.point, 4), "low": round(self.low, 4),
            "high": round(self.high, 4), "level": self.level,
            "width": round(self.width, 4), "n": self.n,
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"


def bootstrap_ci(
    x: Sequence,
    y: Sequence,
    statistic,
    *,
    resamples: int = 1000,
    level: float = 0.95,
    seed: int = 12345,
) -> Interval:
    """Percentile bootstrap CI for a paired statistic.

    Reported because a point estimate from 30 cases and one from 800 look identical
    otherwise. A wide interval is the honest way to say "this sample is too small",
    and it degrades more gracefully than a hard minimum-sample error.

    Seeded by default so a calibration report is reproducible.
    """
    n = len(x)
    point = statistic(x, y)
    if n < 3:
        return Interval(point=point, low=point, high=point, level=level, n=n)

    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        indices = [rng.randrange(n) for _ in range(n)]
        try:
            estimates.append(statistic([x[i] for i in indices], [y[i] for i in indices]))
        except Exception:
            continue
    if not estimates:
        return Interval(point=point, low=point, high=point, level=level, n=n)

    estimates.sort()
    tail = (1 - level) / 2
    low = estimates[max(0, int(tail * len(estimates)))]
    high = estimates[min(len(estimates) - 1, int((1 - tail) * len(estimates)))]
    return Interval(point=point, low=low, high=high, level=level, n=n)


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

#: Landis & Koch bands, the convention κ thresholds are usually quoted against.
#: Reported as a label, never as a verdict — a band is a convention, not a measurement.
KAPPA_BANDS: list[tuple[float, str]] = [
    (0.81, "almost perfect"),
    (0.61, "substantial"),
    (0.41, "moderate"),
    (0.21, "fair"),
    (0.01, "slight"),
    (float("-inf"), "poor / worse than chance"),
]


def kappa_label(value: float) -> str:
    for threshold, label in KAPPA_BANDS:
        if value >= threshold:
            return label
    return "poor"


@dataclass(slots=True)
class Descriptives:
    n: int = 0
    mean: float = 0.0
    stdev: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n": self.n, "mean": round(self.mean, 4), "stdev": round(self.stdev, 4),
            "min": self.minimum, "max": self.maximum, "distribution": self.distribution,
        }


def describe(values: Sequence[float]) -> Descriptives:
    if not values:
        return Descriptives()
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return Descriptives(
        n=n, mean=mean, stdev=math.sqrt(variance),
        minimum=min(values), maximum=max(values),
        distribution=dict(sorted(counts.items())),
    )
