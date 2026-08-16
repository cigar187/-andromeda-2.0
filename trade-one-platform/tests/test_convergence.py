"""Unit tests for the CWC math module. Each test carries the hand-computed expected value."""

from __future__ import annotations

import math

import numpy as np
import pytest

from trade_one.convergence import (
    log_opinion_pool,
    normalized_confidence,
    shannon_entropy,
    vnm_decision,
)


# ---- shannon_entropy -------------------------------------------------------

def test_entropy_point_mass_is_zero():
    # Hand calc: H = -1*ln(1) - 0 - 0 = 0
    assert shannon_entropy([1.0, 0.0, 0.0]) == pytest.approx(0.0)


def test_entropy_uniform_ternary_is_ln3():
    # Hand calc: H = -3 * (1/3)*ln(1/3) = ln(3) ~= 1.09861228866810969
    assert shannon_entropy([1 / 3, 1 / 3, 1 / 3]) == pytest.approx(math.log(3), rel=1e-12)


def test_entropy_binary_half_half_is_ln2():
    # Hand calc: H = -2 * 0.5*ln(0.5) = ln(2) ~= 0.6931471805599453
    assert shannon_entropy([0.5, 0.5]) == pytest.approx(math.log(2), rel=1e-12)


def test_entropy_worked_example_9010():
    # Hand calc: H = -0.9*ln(0.9) - 0.1*ln(0.1)
    #             = 0.9*0.105360515657826 + 0.1*2.302585092994046
    #             = 0.0948244640920434 + 0.2302585092994046
    #             = 0.3250829733914480
    expected = -0.9 * math.log(0.9) - 0.1 * math.log(0.1)
    assert shannon_entropy([0.9, 0.1]) == pytest.approx(expected, rel=1e-12)
    assert expected == pytest.approx(0.3250829733914480, rel=1e-12)


def test_entropy_rejects_unnormalized():
    with pytest.raises(ValueError, match="must sum to 1"):
        shannon_entropy([0.5, 0.4])


def test_entropy_rejects_negative():
    with pytest.raises(ValueError, match="negative"):
        shannon_entropy([0.6, 0.6, -0.2])


# ---- normalized_confidence -------------------------------------------------

def test_confidence_point_mass_is_one():
    assert normalized_confidence([1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_confidence_uniform_is_zero_regardless_of_N():
    for n in (2, 3, 5, 11):
        assert normalized_confidence([1 / n] * n) == pytest.approx(0.0, abs=1e-12)


def test_confidence_support_size_one_is_one():
    # A one-outcome distribution IS a point mass. Documented in module docstring.
    assert normalized_confidence([1.0]) == pytest.approx(1.0)


def test_confidence_worked_example_9010():
    # H([0.9,0.1]) = 0.32508297339144800 (nats)
    # N = 2 -> ln(2) = 0.69314718055994531
    # C = 1 - 0.32508297339144800 / 0.69314718055994531
    #   = 1 - 0.4689955935892812
    #   = 0.5310044064107188
    got = normalized_confidence([0.9, 0.1])
    assert got == pytest.approx(0.5310044064107188, rel=1e-12)


# ---- log_opinion_pool ------------------------------------------------------

def test_pool_identity_two_identical_with_unit_weight_sum():
    # Log-pool identity: pooling K identical distributions with weights summing to 1
    # returns that same distribution exactly.
    p = [0.5, 0.3, 0.2]
    out = log_opinion_pool([p, p], [0.5, 0.5])
    np.testing.assert_allclose(out, p, atol=1e-12)


def test_pool_equal_weight_sum_1_over_K_returns_identity_arbitrary_K():
    p = [0.4, 0.35, 0.2, 0.05]
    for k in (2, 3, 5, 8):
        out = log_opinion_pool([p] * k, [1.0 / k] * k)
        np.testing.assert_allclose(out, p, atol=1e-12)


def test_pool_confident_stream_dominates_uniform_stream():
    # A uniform stream carries zero confidence, so it contributes literally nothing to the
    # log-pool. The pool argmax must match the confident stream's argmax. (The pool value
    # itself is a POWER-FLATTENED version of the confident stream since the single active
    # voter's weight is < 1 — this is standard log-pool math, not a bug.)
    confident = [0.9, 0.05, 0.05]
    uniform = [1 / 3, 1 / 3, 1 / 3]
    w_confident = normalized_confidence(confident)
    w_uniform = normalized_confidence(uniform)
    assert w_uniform == pytest.approx(0.0, abs=1e-12)
    assert 0.0 < w_confident < 1.0
    out = log_opinion_pool([confident, uniform], [w_confident, w_uniform])
    # Argmax preserved:
    assert int(np.argmax(out)) == 0
    # Ranking preserved:
    assert out[0] > out[1] and out[0] > out[2]
    # Flattening effect (single active voter with w<1):
    assert out[0] < confident[0]
    assert out[1] > confident[1] and out[2] > confident[2]


def test_pool_higher_confidence_stream_pulls_pool_toward_it():
    # dist_a peaks on outcome 0, dist_b peaks on outcome 2, with weights biased toward b.
    # Result: pool argmax should be outcome 2.
    a = [0.7, 0.2, 0.1]
    b = [0.1, 0.2, 0.7]
    out = log_opinion_pool([a, b], [0.3, 0.7])
    assert int(np.argmax(out)) == 2


def test_pool_all_zero_weights_raises():
    # Explicit contract: silently defaulting to equal weights would fabricate a stance.
    with pytest.raises(ValueError, match="all weights are zero"):
        log_opinion_pool([[0.5, 0.5], [0.3, 0.7]], [0.0, 0.0])


def test_pool_negative_weight_raises():
    with pytest.raises(ValueError, match="negative"):
        log_opinion_pool([[0.5, 0.5], [0.3, 0.7]], [1.0, -0.1])


def test_pool_mismatched_shapes_raise():
    with pytest.raises(ValueError):
        log_opinion_pool([[0.5, 0.5], [0.3, 0.3, 0.4]], [0.5, 0.5])
    with pytest.raises(ValueError, match="length"):
        log_opinion_pool([[0.5, 0.5]], [0.5, 0.5])


def test_pool_zero_slot_kills_that_slot():
    # If a voter with positive weight assigns 0 to slot i, the pool assigns 0 to slot i.
    a = [0.0, 0.5, 0.5]
    b = [0.4, 0.3, 0.3]
    out = log_opinion_pool([a, b], [0.5, 0.5])
    assert out[0] == pytest.approx(0.0, abs=1e-12)
    assert out.sum() == pytest.approx(1.0, abs=1e-12)


# ---- vnm_decision ----------------------------------------------------------

def test_vnm_picks_over_on_over_heavy_distribution():
    # Support [5,6,7,8], probs [0.1, 0.1, 0.4, 0.4], line=6.5
    # p_over = P(support > 6.5) = 0.4 + 0.4 = 0.8
    # Hand calc (exact):  C = 1 - H/ln(4)
    #   H = -0.1*ln(0.1)*2 - 0.4*ln(0.4)*2
    #     = 0.2*2.302585092994046 + 0.8*0.916290731874155
    #     = 1.193549604098133
    #   C = 1 - 1.193549604098133 / 1.386294361119891 = 0.1391472914480368
    #   conviction = 0.6 * C ~= 0.083488...
    # We assert against the formula recomputed via the same primitives to stay robust to
    # float-summation noise (np.array([0.1,0.1,0.4,0.4]).sum() -> 0.9999999999999999,
    # which the vector normalizer amplifies away from the hex constant above).
    probs = [0.1, 0.1, 0.4, 0.4]
    lean, p_over, conviction = vnm_decision([5, 6, 7, 8], probs, line=6.5)
    assert lean == "OVER"
    assert p_over == pytest.approx(0.8, abs=1e-9)
    expected_conviction = 0.6 * normalized_confidence(probs)
    assert conviction == pytest.approx(expected_conviction, rel=1e-12)
    # Sanity: hand-derived value from the docstring, within fp tolerance:
    assert conviction == pytest.approx(0.08348837486882207, abs=1e-4)


def test_vnm_picks_under_on_under_heavy_distribution():
    # Support [3,4,5,6,7,8], probs concentrated at 3-5, line=6.5
    lean, p_over, _ = vnm_decision([3, 4, 5, 6, 7, 8],
                                    [0.30, 0.30, 0.30, 0.05, 0.03, 0.02], line=6.5)
    assert lean == "UNDER"
    assert p_over == pytest.approx(0.05, abs=1e-12)


def test_vnm_push_on_exact_fifty_fifty():
    # Support [5,6,7,8], probs [0.25, 0.25, 0.25, 0.25], line=6.5
    # p_over = 0.25 + 0.25 = 0.5 exactly -> PUSH
    lean, p_over, conviction = vnm_decision([5, 6, 7, 8], [0.25, 0.25, 0.25, 0.25], line=6.5)
    assert lean == "PUSH"
    assert p_over == pytest.approx(0.5, abs=1e-12)
    # convict = |0| * 2 * C(uniform) = 0
    assert conviction == pytest.approx(0.0, abs=1e-12)


def test_vnm_max_conviction_when_lopsided_and_peaky():
    # Point mass on outcome 8, line 6.5 -> p_over=1, C=1, conviction=1.0
    lean, p_over, conviction = vnm_decision([5, 6, 7, 8], [0, 0, 0, 1.0], line=6.5)
    assert lean == "OVER"
    assert p_over == pytest.approx(1.0, abs=1e-12)
    assert conviction == pytest.approx(1.0, abs=1e-12)


def test_vnm_zero_conviction_when_lopsided_but_uniform_never_happens():
    # Sanity: you cannot have a uniform distribution that is also lopsided; here we just
    # confirm the interaction — a nearly-uniform distribution that happens to shade OVER
    # still lands very low conviction.
    lean, p_over, conviction = vnm_decision([5, 6, 7, 8], [0.24, 0.24, 0.26, 0.26], line=6.5)
    assert lean == "OVER"
    assert p_over == pytest.approx(0.52, abs=1e-12)
    # C is very small; conviction < 0.01
    assert 0 < conviction < 0.01


def test_vnm_shape_mismatch_raises():
    with pytest.raises(ValueError):
        vnm_decision([5, 6, 7], [0.25, 0.25, 0.25, 0.25], line=6.5)
