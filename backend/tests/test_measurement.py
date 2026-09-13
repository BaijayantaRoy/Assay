"""Tests for legacy measurement paths that must not fabricate assurance."""

from __future__ import annotations

import json

import pytest

from backend.api.routers.abtests import _compute_significance
from backend.api.routers.evaluations import _parse_judge_response


def _variant(up: int, down: int) -> dict:
    return {"thumbs_up": up, "thumbs_down": down}


def test_ab_significance_is_withheld_below_sample_floor():
    report = _compute_significance([_variant(9, 1), _variant(1, 9)])
    assert report["usable"] is False
    assert report["significant"] is None
    assert report["confidence"] is None
    assert report["p_value"] is None
    assert report["a_n"] == 10
    assert report["b_n"] == 10


def test_ab_significance_uses_exact_reference_case():
    report = _compute_significance([_variant(18, 2), _variant(8, 12)])
    assert report["usable"] is True
    assert report["method"] == "fisher_exact_two_sided"
    # Exact two-sided hypergeometric reference for [[18, 2], [8, 12]].
    assert report["p_value"] == pytest.approx(0.0022, abs=1e-6)
    assert report["significant"] is True
    assert report["difference"] == 50.0


def test_equal_ab_results_are_not_significant():
    report = _compute_significance([_variant(12, 8), _variant(12, 8)])
    assert report["usable"] is True
    assert report["p_value"] == 1.0
    assert report["significant"] is False


def test_judge_response_requires_a_real_bounded_score():
    assert _parse_judge_response('{"score": 0.8, "reasoning": "good"}') == (0.8, "good")
    for invalid in ('{}', '{"score": 1.2}', '{"score": "nan"}', 'not json'):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            _parse_judge_response(invalid)
