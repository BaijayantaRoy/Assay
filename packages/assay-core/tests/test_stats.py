"""Statistics — the arithmetic behind every number the product reports.

These functions decide whether a judge gets certified, so a wrong answer here does not
crash anything; it quietly certifies a judge that should have been rejected. That makes
this the code where a silent bug is most expensive, and it had no dedicated test file:
it was covered only incidentally through ``test_calibration.py``, which exercises the
happy path and never touches the guards.

Mutation testing found the consequence. Deleting the constant-series guard in
``pearson`` — the one line standing between "this judge always answers 4" and a reported
correlation of 1.0 — changed no test outcome anywhere in the suite.

The degenerate inputs get most of the attention below, because they are where an
implementation quietly disagrees with the textbook and where a certification gate is
most likely to be fooled.
"""

from __future__ import annotations

import math

import pytest

from assay_core.stats import (
    bootstrap_ci,
    cohens_kappa,
    pearson,
    rank,
    spearman,
    weighted_kappa,
)


# ---------------------------------------------------------------------------
# Correlation — degenerate inputs first
# ---------------------------------------------------------------------------


def test_a_constant_series_correlates_at_zero_not_one():
    """The single most important line in this module.

    A judge that returns 4 for everything has no information in it. Some correlation
    implementations return 1.0 when both series are constant — division of zero by zero,
    resolved optimistically. Doing that here would certify a judge that says the same
    thing regardless of input, which is the exact opposite of what calibration is for.
    """
    assert pearson([4, 4, 4, 4], [1, 2, 3, 4]) == 0.0
    assert pearson([1, 2, 3, 4], [4, 4, 4, 4]) == 0.0
    assert pearson([4, 4, 4, 4], [4, 4, 4, 4]) == 0.0


def test_a_constant_judge_cannot_pass_the_spearman_gate():
    """The same guarantee at the level the certification gate actually uses."""
    assert spearman([3, 3, 3, 3, 3], [1, 2, 3, 4, 5]) == 0.0


def test_fewer_than_two_points_correlates_at_zero():
    """One point defines no relationship. Reporting anything else invents information."""
    assert pearson([], []) == 0.0
    assert pearson([1], [1]) == 0.0


def test_mismatched_lengths_raise_rather_than_truncate():
    """Silently zipping to the shorter series would score a subset and call it the whole."""
    with pytest.raises(ValueError):
        pearson([1, 2, 3], [1, 2])


# ---------------------------------------------------------------------------
# Correlation — known values
# ---------------------------------------------------------------------------


def test_perfect_positive_and_negative_correlation():
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_matches_a_hand_computed_value():
    """Anchored against an independently computed figure, not against our own output.

    Worked so a reader can check it rather than trust it::

        x  = [1, 2, 3, 4, 5]        mean 3      dx = [-2, -1, 0, 1, 2]
        y  = [2, 1, 4, 3, 5]        mean 3      dy = [-1, -2, 1, 0, 2]
        numerator   = 2 + 2 + 0 + 0 + 4 = 8
        denominator = sqrt(10 * 10)     = 10
        r           = 8 / 10            = 0.8
    """
    assert pearson([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8, abs=1e-9)


def test_spearman_is_pearson_on_ranks_and_ignores_monotone_scaling():
    """Rank correlation must not care that one rater used a wider scale."""
    human = [1, 2, 3, 4, 5]
    judge = [10, 20, 30, 40, 50]
    assert spearman(human, judge) == pytest.approx(1.0)


def test_spearman_detects_a_monotone_but_nonlinear_judge():
    """Exactly the case Spearman is chosen over Pearson for."""
    human = [1, 2, 3, 4, 5]
    judge = [1, 4, 9, 16, 25]
    assert spearman(human, judge) == pytest.approx(1.0)
    assert pearson(human, judge) < 1.0


# ---------------------------------------------------------------------------
# Ranking — ties are where implementations disagree
# ---------------------------------------------------------------------------


def test_ties_receive_fractional_average_ranks():
    """Integer ranks for ties would bias every correlation computed from them."""
    assert rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_all_values_tied_gives_every_item_the_same_rank():
    assert rank([5, 5, 5]) == [2.0, 2.0, 2.0]


def test_rank_of_an_empty_series_is_empty():
    assert rank([]) == []


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def test_total_agreement_is_kappa_one():
    assert cohens_kappa([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)


def test_chance_level_agreement_is_kappa_zero():
    """κ corrects for agreement that would happen by luck — the reason to prefer it
    over raw percent agreement, which would look respectable here."""
    a = [1, 1, 2, 2]
    b = [1, 2, 1, 2]
    assert cohens_kappa(a, b) == pytest.approx(0.0, abs=1e-9)


def test_systematic_disagreement_is_negative():
    assert cohens_kappa([1, 1, 2, 2], [2, 2, 1, 1]) < 0


def test_weighted_kappa_is_kinder_to_near_misses_than_plain_kappa():
    """Rating 4 when the human said 5 is a smaller error than rating 1, and on an
    ordinal rubric the metric should say so."""
    human = [1, 2, 3, 4, 5]
    near = [1, 2, 3, 4, 4]
    assert weighted_kappa(human, near) > cohens_kappa(human, near)


def test_weighted_kappa_still_punishes_a_large_miss():
    human = [1, 2, 3, 4, 5]
    far = [5, 4, 3, 2, 1]
    assert weighted_kappa(human, far) < 0


# ---------------------------------------------------------------------------
# Bootstrap intervals
# ---------------------------------------------------------------------------


def test_the_interval_brackets_the_point_estimate():
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [2, 1, 4, 3, 6, 5, 8, 7, 10, 9]
    interval = bootstrap_ci(x, y, pearson, resamples=200, seed=7)
    assert interval.low <= interval.point <= interval.high


def test_a_small_sample_produces_a_wide_interval():
    """The headline reason intervals are reported at all.

    A point estimate from five cases can look excellent; the interval is what tells the
    reader it means very little. If this ever stops holding, the certification gate is
    reporting false precision.
    """
    x_small, y_small = [1, 2, 3, 4, 5], [1, 3, 2, 5, 4]
    x_large = list(range(1, 41))
    y_large = [v + (1 if v % 3 else -1) for v in x_large]

    narrow = bootstrap_ci(x_large, y_large, pearson, resamples=200, seed=7)
    wide = bootstrap_ci(x_small, y_small, pearson, resamples=200, seed=7)
    assert wide.width > narrow.width


def test_the_interval_is_reproducible_for_a_given_seed():
    """Resampling is random; a certification result must not be."""
    x = [1, 2, 3, 4, 5, 6, 7, 8]
    y = [1, 3, 2, 4, 6, 5, 8, 7]
    first = bootstrap_ci(x, y, pearson, resamples=200, seed=42)
    second = bootstrap_ci(x, y, pearson, resamples=200, seed=42)
    assert (first.low, first.point, first.high) == (second.low, second.point, second.high)


def test_the_interval_reports_its_own_sample_size_and_level():
    x = [1, 2, 3, 4, 5, 6]
    y = [1, 2, 3, 4, 5, 6]
    interval = bootstrap_ci(x, y, pearson, resamples=100, seed=1)
    assert interval.n == 6
    assert 0 < interval.level < 1
    assert math.isfinite(interval.width)
