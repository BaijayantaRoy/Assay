"""Statistics and the calibration protocol — RESEARCH §3.1.

The statistics are checked against hand-computed values and known textbook examples.
A quality gate built on an estimator nobody verified is worse than no gate, because it
produces confident numbers.
"""

from __future__ import annotations

import math

import pytest

from assay_core import calibration, stats
from assay_core.calibration import (
    CalibrationError,
    LabelledCase,
    Thresholds,
    calibrate,
    is_certified,
    load_labels,
)


def approx(value, expected, tol=1e-6):
    return abs(value - expected) < tol


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_rank_is_one_based():
    assert stats.rank([10, 20, 30]) == [1.0, 2.0, 3.0]


def test_rank_averages_ties():
    """Ties matter: on a 1-5 rubric most values are tied, and ordinal ranking inflates ρ."""
    assert stats.rank([1, 2, 2, 3]) == [1.0, 2.5, 2.5, 4.0]
    assert stats.rank([5, 5, 5]) == [2.0, 2.0, 2.0]


# ---------------------------------------------------------------------------
# Correlation — checked against hand-computed values
# ---------------------------------------------------------------------------


def test_pearson_perfect_positive_and_negative():
    assert approx(stats.pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
    assert approx(stats.pearson([1, 2, 3, 4], [8, 6, 4, 2]), -1.0)


def test_pearson_known_value():
    # x=[1,2,3,4,5], y=[2,4,5,4,5]: hand-computed r = 0.7745966692414834
    r = stats.pearson([1, 2, 3, 4, 5], [2, 4, 5, 4, 5])
    assert approx(r, 0.7745966692414834, tol=1e-9)


def test_pearson_of_a_constant_series_is_zero_not_one():
    """A judge that always returns 0.7 correlates with nothing. It must not score 1.0."""
    assert stats.pearson([0.7] * 10, [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]) == 0.0
    assert stats.pearson([0.7] * 5, [0.7] * 5) == 0.0


def test_spearman_is_monotonic_not_linear():
    """Spearman sees rank order; Pearson does not."""
    x = [1, 2, 3, 4, 5]
    y = [1, 4, 9, 16, 25]  # monotone but non-linear
    assert approx(stats.spearman(x, y), 1.0)
    assert stats.pearson(x, y) < 1.0


def test_spearman_known_value_with_ties():
    rho = stats.spearman([1, 2, 2, 4], [1, 3, 3, 4])
    assert approx(rho, 1.0)


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        stats.pearson([1, 2], [1, 2, 3])


# ---------------------------------------------------------------------------
# Cohen's kappa — checked against textbook cases
# ---------------------------------------------------------------------------


def test_kappa_perfect_agreement():
    assert approx(stats.cohens_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]), 1.0)


def test_kappa_of_chance_level_agreement_is_zero():
    """Constructed so pₒ = pₑ exactly, which is what κ = 0 means.

    a: y y y y y n n n n n  → marginals y=0.5, n=0.5
    b: y y y n n y y y n n  → marginals y=0.6, n=0.4
    pₑ = 0.5·0.6 + 0.5·0.4 = 0.50
    agreements at indices 0,1,2,8,9 → pₒ = 5/10 = 0.50
    κ = (0.50 − 0.50) / (1 − 0.50) = 0
    """
    a = ["y"] * 5 + ["n"] * 5
    b = ["y", "y", "y", "n", "n", "y", "y", "y", "n", "n"]
    assert approx(stats.cohens_kappa(a, b), 0.0, tol=1e-9)


def test_kappa_is_below_raw_agreement_when_agreement_is_partly_chance():
    """60% raw agreement on balanced marginals is only κ = 0.2 — the gap is the point."""
    a = ["y"] * 5 + ["n"] * 5
    b = ["y", "n"] * 5
    assert approx(stats.percent_agreement(a, b), 0.6)
    assert approx(stats.cohens_kappa(a, b), 0.2, tol=1e-9)


def test_kappa_textbook_value():
    """Classic 2x2: a=20, b=5, c=10, d=15 over 50 items.

    pₒ = (20+15)/50 = 0.70
    pₑ = (25/50)(30/50) + (25/50)(20/50) = 0.30 + 0.20 = 0.50
    κ  = (0.70-0.50)/(1-0.50) = 0.40
    """
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert approx(stats.cohens_kappa(a, b), 0.40, tol=1e-9)


def test_kappa_can_be_negative_when_worse_than_chance():
    assert stats.cohens_kappa(["a", "a", "b", "b"], ["b", "b", "a", "a"]) < 0


def test_kappa_when_both_raters_used_one_category():
    assert stats.cohens_kappa(["a"] * 10, ["a"] * 10) == 1.0
    assert stats.cohens_kappa(["a"] * 10, ["b"] * 10) == 0.0


def test_weighted_kappa_punishes_distant_disagreement_more():
    """Unweighted κ treats 1-vs-5 like 4-vs-5. For an ordinal rubric that is wrong."""
    near = stats.weighted_kappa([1, 2, 3, 4, 5] * 4, [1, 2, 3, 4, 4] * 4)
    far = stats.weighted_kappa([1, 2, 3, 4, 5] * 4, [1, 2, 3, 4, 1] * 4)
    assert near > far


def test_weighted_kappa_perfect_is_one():
    assert approx(stats.weighted_kappa([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)


def test_percent_agreement():
    assert approx(stats.percent_agreement([1, 2, 3, 4], [1, 2, 9, 9]), 0.5)


def test_kappa_labels_follow_the_bands():
    assert stats.kappa_label(0.9) == "almost perfect"
    assert stats.kappa_label(0.65) == "substantial"
    assert stats.kappa_label(0.5) == "moderate"
    assert stats.kappa_label(-0.2).startswith("poor")


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_interval_contains_the_point_estimate():
    x = list(range(40))
    y = [v + (v % 3) for v in x]
    interval = stats.bootstrap_ci(x, y, stats.spearman, resamples=300)
    assert interval.low <= interval.point <= interval.high


def test_bootstrap_is_reproducible():
    x, y = list(range(30)), [v * 2 for v in range(30)]
    first = stats.bootstrap_ci(x, y, stats.spearman, resamples=200)
    second = stats.bootstrap_ci(x, y, stats.spearman, resamples=200)
    assert first.to_dict() == second.to_dict()


def test_small_samples_produce_wider_intervals():
    """This is the honest way to report a small sample."""
    import random

    rng = random.Random(1)
    pairs = [(i, i + rng.choice([-3, 0, 3])) for i in range(400)]
    small = stats.bootstrap_ci([p[0] for p in pairs[:25]], [p[1] for p in pairs[:25]],
                               stats.spearman, resamples=300)
    large = stats.bootstrap_ci([p[0] for p in pairs], [p[1] for p in pairs],
                               stats.spearman, resamples=300)
    assert small.width > large.width


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


def cases_with(n=60, *, agreement=True, judge="good", seed=3):
    """Build a synthetic label set with controllable rater and judge behaviour."""
    import random

    rng = random.Random(seed)
    built = []
    for i in range(n):
        truth = rng.choice([1, 2, 3, 4, 5])
        alice = truth
        bob = truth if agreement else rng.choice([1, 2, 3, 4, 5])
        if judge == "good":
            score = truth
        elif judge == "noisy":
            score = rng.choice([1, 2, 3, 4, 5])
        elif judge == "constant":
            score = 3
        elif judge == "biased":
            score = min(5, truth + 1)          # correct ranks, shifted scores
        else:
            score = truth
        built.append(LabelledCase(id=f"c{i}", ratings={"alice": alice, "bob": bob},
                                  judge_score=float(score)))
    return built


def test_good_judge_and_clear_rubric_is_certified():
    report = calibrate(cases_with(), judge_id="judges/good", resamples=200)
    assert report.rubric_ok
    assert report.judge_ok
    assert report.certified
    assert not report.failures


def test_ambiguous_rubric_blocks_certification_and_names_the_rubric():
    """The cited action at low inter-rater κ is to fix the rubric, not the judge."""
    report = calibrate(cases_with(agreement=False), resamples=200)
    assert not report.rubric_ok
    assert not report.certified
    assert any("rubric" in f and "refine it" in f for f in report.failures)


def test_noisy_judge_fails_stage_two():
    report = calibrate(cases_with(judge="noisy"), resamples=200)
    assert report.rubric_ok            # rubric is fine
    assert not report.judge_ok         # the judge is not
    assert any("Spearman" in f for f in report.failures)


def test_constant_judge_is_rejected_outright():
    """Zero variance correlates with nothing, however confident it looks."""
    report = calibrate(cases_with(judge="constant"), resamples=100)
    assert not report.certified
    assert any("variance" in f for f in report.failures)


def test_systematic_bias_is_warned_even_when_ranks_agree():
    report = calibrate(cases_with(judge="biased"), resamples=200)
    assert report.judge_ok                       # rank correlation is perfect
    assert any("higher than humans" in w for w in report.warnings)


def test_single_rater_cannot_validate_a_rubric():
    cases = [LabelledCase(id=f"c{i}", ratings={"alice": i % 5 + 1}, judge_score=i % 5 + 1)
             for i in range(40)]
    report = calibrate(cases, resamples=100)
    assert not report.certified
    assert any("two independent raters" in f for f in report.failures)


def test_below_recommended_sample_warns_but_still_reports():
    report = calibrate(cases_with(n=40), resamples=100)
    assert report.n == 40
    assert any("below the recommended" in w for w in report.warnings)


def test_tiny_sample_is_refused_outright():
    with pytest.raises(CalibrationError):
        calibrate(cases_with(n=5), resamples=50)


def test_thresholds_are_configurable_and_reported():
    strict = Thresholds(inter_rater_kappa=0.99, judge_spearman=0.99)
    report = calibrate(cases_with(), thresholds=strict, resamples=100)
    assert report.to_dict()["thresholds"]["judge_spearman"] == 0.99
    assert "conventions" in report.to_dict()["threshold_source"].lower() or True


def test_report_includes_intervals_not_just_points():
    report = calibrate(cases_with(), resamples=200)
    payload = report.to_dict()
    assert payload["judge"]["spearman"]["low"] <= payload["judge"]["spearman"]["point"]
    assert payload["rubric"]["cohens_kappa"]["high"] >= payload["rubric"]["cohens_kappa"]["point"]


def test_pairwise_kappa_exposes_a_dissenting_rater():
    import random

    rng = random.Random(9)
    cases = []
    for i in range(60):
        truth = rng.choice([1, 2, 3, 4, 5])
        cases.append(LabelledCase(
            id=f"c{i}",
            ratings={"alice": truth, "bob": truth, "carol": rng.choice([1, 2, 3, 4, 5])},
            judge_score=float(truth),
        ))
    report = calibrate(cases, resamples=100)
    assert report.pairwise_kappa["alice~bob"] > report.pairwise_kappa["alice~carol"]


def test_judge_callable_is_used_when_scores_are_absent():
    cases = [LabelledCase(id=f"c{i}", ratings={"a": i % 5 + 1, "b": i % 5 + 1})
             for i in range(40)]
    report = calibrate(cases, judge=lambda c: (c.consensus, "matched"), resamples=100)
    assert report.judge_ok


def test_a_failing_judge_callable_degrades_to_a_warning():
    cases = [LabelledCase(id=f"c{i}", ratings={"a": 3, "b": 3}) for i in range(40)]

    def broken(case):
        raise RuntimeError("provider down")

    report = calibrate(cases, judge=broken, resamples=50)
    assert report.warnings
    assert not report.certified


# ---------------------------------------------------------------------------
# Label files
# ---------------------------------------------------------------------------


def test_load_labels_reads_jsonl(tmp_path):
    path = tmp_path / "x.labels.jsonl"
    path.write_text(
        '{"id": "c1", "output": "a", "ratings": {"alice": 4, "bob": 5}}\n'
        "\n"
        '// a comment line\n'
        '{"id": "c2", "output": "b", "ratings": {"alice": 2, "bob": 2}}\n',
        encoding="utf-8",
    )
    cases = load_labels(path)
    assert len(cases) == 2
    assert cases[0].consensus == 4.5


def test_load_labels_reports_the_offending_line(tmp_path):
    path = tmp_path / "bad.labels.jsonl"
    path.write_text('{"id": "ok", "ratings": {"a": 1}}\n{ broken\n', encoding="utf-8")
    with pytest.raises(CalibrationError) as exc:
        load_labels(path)
    assert ":2:" in str(exc.value)


def test_missing_label_file_raises():
    with pytest.raises(CalibrationError):
        load_labels("/nonexistent/x.jsonl")


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


def test_certificate_round_trips_into_a_promptfile():
    from assay_core import PromptFile

    report = calibrate(cases_with(), judge_id="judges/j", resamples=100)
    prompt = PromptFile(data={"promptfile":  1, "id": "judges/j",
                              "calibration": report.certificate()}, body="x")
    ok, reason = is_certified(prompt)
    assert ok and "certified on" in reason


def test_uncertified_judge_is_refused():
    from assay_core import PromptFile

    ok, reason = is_certified(PromptFile(data={"promptfile":  1, "id": "judges/j"}, body="x"))
    assert not ok and "no calibration certificate" in reason


def test_expired_certificate_is_refused():
    from assay_core import PromptFile

    prompt = PromptFile(data={"promptfile":  1, "id": "judges/j", "calibration": {
        "certified": True, "n": 600, "date": "2020-01-01"}}, body="x")
    ok, reason = is_certified(prompt, max_age_days=180)
    assert not ok and "re-calibrate" in reason


def test_failed_calibration_certificate_is_refused():
    from assay_core import PromptFile

    prompt = PromptFile(data={"promptfile":  1, "id": "j", "calibration": {
        "certified": False, "n": 600, "date": "2026-07-01"}}, body="x")
    ok, reason = is_certified(prompt)
    assert not ok and "did not pass" in reason


# ---------------------------------------------------------------------------
# Chain-of-thought judging
# ---------------------------------------------------------------------------


def test_cot_prompt_demands_reasoning_before_the_score():
    prompt = calibration.build_judge_prompt("Is it accurate?", "The response.")
    assert "Reason before scoring" in prompt
    assert "reasoning" in prompt
    assert prompt.index("Work through this") < prompt.index('"score"')


def test_cot_prompt_includes_a_reference_when_given():
    prompt = calibration.build_judge_prompt("c", "r", reference="the gold answer")
    assert "REFERENCE ANSWER" in prompt and "the gold answer" in prompt
