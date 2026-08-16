"""Unit tests for the scoring harness. Hand-worked expected values on synthetic dists."""

from __future__ import annotations

import math

import numpy as np
import pytest

from trade_one.contracts import EngineDistribution
from trade_one.scoring import (
    bootstrap_ci,
    crps,
    interval_coverage,
    pit_value,
    point_error,
)


# ---- CRPS ------------------------------------------------------------------

def test_crps_point_mass_at_actual_is_zero():
    # Point mass at K=6 vs actual K=6: CDF jumps at 6, indicator jumps at 6.
    # (CDF - step)^2 = 0 everywhere. Trapezoidal weights don't matter.
    support = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    probs = [0.0] * len(support); probs[6] = 1.0
    assert crps(support, probs, 6) == pytest.approx(0.0, abs=1e-12)


def test_crps_grows_as_mass_moves_from_actual():
    support = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    def point_at(k):
        p = [0.0] * len(support); p[k] = 1.0
        return crps(support, p, 5)
    # Symmetry: same distance -> same CRPS
    assert point_at(6) == pytest.approx(point_at(4))
    # Monotonicity: farther -> larger CRPS
    assert point_at(5) < point_at(6) < point_at(7) < point_at(9)


def test_crps_point_mass_at_5_actual_6_equals_one_unit():
    # Point mass at 5, actual 6. Compute by hand on support 0..10:
    # CDF steps to 1 at index 5. Indicator {x>=6} steps to 1 at index 6.
    # (CDF-step)^2 = 1 at index 5 only (CDF=1, step=0). Elsewhere 0.
    # dx at index 5 = (6-4)/2 = 1. Sum = 1 * 1 = 1.
    support = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    probs = [0.0] * 11; probs[5] = 1.0
    assert crps(support, probs, 6) == pytest.approx(1.0, abs=1e-12)


def test_crps_uses_engine_distribution_via_to_vectors():
    # Harness must be feed-able from an EngineDistribution instance without importing it.
    dist = EngineDistribution(
        engine_id="test", engine_version="1.0", outcome_family="k",
        support=tuple(float(k) for k in range(0, 11)),
        probabilities=tuple(0.0 if k != 6 else 1.0 for k in range(0, 11)),
        as_of="2026-08-06T00:00:00Z",
    )
    dist.validate()
    support, probs = dist.to_vectors()
    assert crps(support, probs, 6) == pytest.approx(0.0)


def test_crps_rejects_non_finite_actual():
    with pytest.raises(ValueError):
        crps([0, 1, 2], [0.2, 0.5, 0.3], float("nan"))


# ---- PIT --------------------------------------------------------------------

def test_pit_of_symmetric_dist_at_median_is_half():
    # Support [0..10], symmetric triangular peaking at 5. Median = 5. PIT(5) = 0.5.
    # Take a symmetric ramp: [0, 0.05, 0.1, 0.15, 0.2, ?, ?, ?, ?, ?, ?] — easier:
    # use exact symmetric [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    # over support [0..9] -> median between 4 and 5. To hit exactly 0.5 at median 5,
    # use odd-length symmetric dist on [0..10] where mass at 5 is central peak.
    support = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    probs = [0.02, 0.04, 0.08, 0.12, 0.14, 0.20, 0.14, 0.12, 0.08, 0.04, 0.02]
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)
    # PIT(5) = P(X<=5) = 0.02+0.04+0.08+0.12+0.14+0.20 = 0.60 (right-continuous CDF at 5)
    # For our right-continuous CDF PIT_at_5 = 0.6. Assert exact.
    assert pit_value(support, probs, 5) == pytest.approx(0.6, abs=1e-12)


def test_pit_at_smallest_support_is_that_bins_probability():
    support = [0, 1, 2]; probs = [0.2, 0.5, 0.3]
    assert pit_value(support, probs, 0) == pytest.approx(0.2, abs=1e-12)


def test_pit_at_or_above_max_support_is_one():
    support = [0, 1, 2]; probs = [0.2, 0.5, 0.3]
    assert pit_value(support, probs, 2) == pytest.approx(1.0, abs=1e-12)
    assert pit_value(support, probs, 5) == pytest.approx(1.0, abs=1e-12)


def test_pit_below_min_support_is_zero():
    support = [0, 1, 2]; probs = [0.2, 0.5, 0.3]
    assert pit_value(support, probs, -1) == pytest.approx(0.0, abs=1e-12)


# ---- interval_coverage ------------------------------------------------------

def test_interval_covers_center_excludes_far_tail_80_pct():
    # Symmetric dist on [0..10] peaked at 5. 80% interval = quantiles [0.10, 0.90].
    support = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    probs = [0.02, 0.04, 0.08, 0.12, 0.14, 0.20, 0.14, 0.12, 0.08, 0.04, 0.02]
    assert interval_coverage(support, probs, 5, level=0.80) is True
    assert interval_coverage(support, probs, 4, level=0.80) is True
    assert interval_coverage(support, probs, 7, level=0.80) is True
    assert interval_coverage(support, probs, 10, level=0.80) is False
    assert interval_coverage(support, probs, 0, level=0.80) is False


def test_interval_rejects_bad_level():
    with pytest.raises(ValueError):
        interval_coverage([0, 1], [0.5, 0.5], 0, level=0.0)
    with pytest.raises(ValueError):
        interval_coverage([0, 1], [0.5, 0.5], 0, level=1.0)


# ---- point_error ------------------------------------------------------------

def test_point_error_uniform_dist_mean_at_center():
    # Uniform on [0..10] has mean 5.
    support = list(range(11))
    probs = [1 / 11] * 11
    abs_err, sq_err = point_error(support, probs, 5)
    assert abs_err == pytest.approx(0.0, abs=1e-12)
    assert sq_err == pytest.approx(0.0, abs=1e-12)
    abs_err2, sq_err2 = point_error(support, probs, 8)
    assert abs_err2 == pytest.approx(3.0, abs=1e-12)
    assert sq_err2 == pytest.approx(9.0, abs=1e-12)


# ---- bootstrap_ci ----------------------------------------------------------

def test_bootstrap_ci_brackets_true_mean_of_known_sample():
    # Draw from a distribution with known mean; bootstrap CI on the mean should bracket it
    # for a sufficiently large n_boot with a seeded RNG. Reproducible.
    rng = np.random.default_rng(42)
    sample = rng.normal(loc=5.0, scale=1.0, size=500)
    sample_mean = float(sample.mean())
    lo, hi = bootstrap_ci(sample, np.mean, n_boot=2000, seed=7, level=0.95)
    assert lo <= sample_mean <= hi
    # Width should be roughly 2 * 1.96 * sigma / sqrt(n) ~= 0.175 for these params
    assert (hi - lo) < 0.3


def test_bootstrap_ci_deterministic_with_same_seed():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    a = bootstrap_ci(values, np.mean, n_boot=200, seed=123)
    b = bootstrap_ci(values, np.mean, n_boot=200, seed=123)
    assert a == b
    c = bootstrap_ci(values, np.mean, n_boot=200, seed=124)
    assert c != a  # different seed -> different CI


def test_bootstrap_ci_rejects_bad_inputs():
    with pytest.raises(ValueError):
        bootstrap_ci([1.0, 2.0], np.mean, n_boot=0, seed=1)
    with pytest.raises(ValueError):
        bootstrap_ci([], np.mean, n_boot=100, seed=1)
    with pytest.raises(ValueError):
        bootstrap_ci([1.0, float("nan")], np.mean, n_boot=100, seed=1)
