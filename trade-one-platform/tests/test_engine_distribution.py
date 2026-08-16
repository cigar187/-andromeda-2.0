"""Unit tests for EngineDistribution.validate() + to_vectors() adapter."""

from __future__ import annotations

import math

import pytest

from trade_one.contracts import EngineDistribution


def _valid(**overrides):
    kwargs = dict(
        engine_id="test",
        engine_version="1.0.0",
        outcome_family="pitcher_strikeouts",
        support=(0.0, 1.0, 2.0),
        probabilities=(0.2, 0.5, 0.3),
        as_of="2026-08-06T00:00:00Z",
    )
    kwargs.update(overrides)
    return EngineDistribution(**kwargs)


def test_valid_distribution_passes():
    _valid().validate()


def test_to_vectors_returns_support_and_probs_unchanged():
    d = _valid()
    sup, probs = d.to_vectors()
    assert sup == d.support and probs == d.probabilities


def test_empty_rejected():
    d = _valid(support=(), probabilities=())
    with pytest.raises(ValueError, match="non-empty"):
        d.validate()


def test_length_mismatch_rejected():
    d = _valid(support=(0.0, 1.0), probabilities=(0.5, 0.3, 0.2))
    with pytest.raises(ValueError, match="equal length"):
        d.validate()


def test_bad_sum_rejected():
    d = _valid(probabilities=(0.2, 0.5, 0.2))
    with pytest.raises(ValueError, match="sum to 1"):
        d.validate()


def test_negative_probability_rejected():
    d = _valid(probabilities=(0.6, 0.6, -0.2))
    with pytest.raises(ValueError, match="negative"):
        d.validate()


def test_nan_probability_rejected():
    d = _valid(probabilities=(0.2, float("nan"), 0.8))
    with pytest.raises(ValueError, match="non-finite"):
        d.validate()


def test_inf_probability_rejected():
    d = _valid(probabilities=(0.2, float("inf"), 0.8))
    with pytest.raises(ValueError, match="non-finite"):
        d.validate()


def test_support_not_strictly_ascending_rejected():
    d_dup = _valid(support=(0.0, 1.0, 1.0), probabilities=(0.2, 0.5, 0.3))
    with pytest.raises(ValueError, match="strictly ascending"):
        d_dup.validate()
    d_desc = _valid(support=(2.0, 1.0, 0.0), probabilities=(0.2, 0.5, 0.3))
    with pytest.raises(ValueError, match="strictly ascending"):
        d_desc.validate()


def test_single_outcome_support_ok():
    d = _valid(support=(5.0,), probabilities=(1.0,))
    d.validate()
    sup, probs = d.to_vectors()
    assert sup == (5.0,) and probs == (1.0,)


def test_boundary_sum_within_tolerance():
    # sum == 1 - 1e-7 -> ok (within 1e-6 tol)
    d = _valid(probabilities=(0.2, 0.5, 0.3 - 1e-7))
    d.validate()
    # sum off by 1e-5 -> rejected
    d_bad = _valid(probabilities=(0.2, 0.5, 0.3 - 1e-5))
    with pytest.raises(ValueError, match="sum to 1"):
        d_bad.validate()
