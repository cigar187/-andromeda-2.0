"""Scoring harness — grade any discrete predictive distribution against a realized outcome.

Reused by forward validation and by every engine's calibration report. Consumes the same
vector shape that convergence.py operates on: (support, probabilities) — so an
EngineDistribution feeds in via its .to_vectors() adapter without any coupling here.

Formulas (all nats/absolute-units; support may be integer counts or floats):
------------------------------------------------------------------------------
CRPS (discrete):     CRPS = sum_i (F(x_i) - 1{x_i >= actual})^2 * dx_i
                     for a discrete distribution with support x_0 < ... < x_{N-1}, we use
                     the trapezoidal spacing dx_i = (x_{i+1} - x_{i-1}) / 2 with edge cases
                     dx_0 = (x_1 - x_0), dx_{N-1} = (x_{N-1} - x_{N-2}).
                     Equivalent to the continuous CRPS applied to the step CDF.
PIT value:           F(actual) — the predictive CDF evaluated at the realized outcome. For
                     a well-calibrated model the PIT values across many samples are ~U[0,1].
                     Ties handled by taking F strictly at or below actual (right-continuous).
Interval coverage:   The central `level` interval [q_lo, q_hi] with lo = (1-level)/2 and
                     hi = 1-lo. Returns True iff actual is inside [q_lo, q_hi].
Point error:         mean = sum_i support_i * p_i; abs_err = |mean - actual|; sq_err = err^2.
Bootstrap CI:        resample `values` with replacement `n_boot` times, apply `statistic`,
                     return (percentile lo, percentile hi) at the 2.5 / 97.5 quantiles.
                     `seed` is REQUIRED — no unseeded RNG (Rule 4 reproducibility).

Every function raises ValueError on malformed input. No None/abstain returns.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np


_ZERO_TOL = 1e-12
_SUM_TOL = 1e-6


def _validate_dist(support: Sequence[float], probabilities: Sequence[float]
                   ) -> tuple[np.ndarray, np.ndarray]:
    sup = np.asarray(support, dtype=float)
    probs = np.asarray(probabilities, dtype=float)
    if sup.ndim != 1 or sup.size < 1 or sup.shape != probs.shape:
        raise ValueError("support and probabilities must be equal-length 1-D and non-empty")
    if not np.all(np.isfinite(sup)) or not np.all(np.isfinite(probs)):
        raise ValueError("support/probabilities contain non-finite values")
    if np.any(probs < -_ZERO_TOL):
        raise ValueError("probabilities contain negative values")
    if np.any(np.diff(sup) <= 0):
        raise ValueError("support must be strictly ascending")
    probs = np.clip(probs, 0.0, None)
    total = float(probs.sum())
    if abs(total - 1.0) > _SUM_TOL:
        raise ValueError(f"probabilities must sum to 1 (got {total:.6f})")
    return sup, probs / total


def crps(support: Sequence[float], probabilities: Sequence[float], actual: float) -> float:
    """CRPS of a discrete predictive distribution vs a scalar outcome. Zero when the
    distribution is a point mass at `actual`; grows as mass moves away from `actual`."""
    if not math.isfinite(actual):
        raise ValueError("actual must be finite")
    sup, probs = _validate_dist(support, probabilities)
    cdf = np.cumsum(probs)
    step = (sup >= actual).astype(float)
    # Trapezoidal width per support point (edges get single-sided width).
    n = sup.size
    if n == 1:
        return float((cdf[0] - step[0]) ** 2 * 0.0)
    dx = np.empty(n)
    dx[0] = sup[1] - sup[0]
    dx[-1] = sup[-1] - sup[-2]
    if n >= 3:
        dx[1:-1] = (sup[2:] - sup[:-2]) / 2.0
    return float(((cdf - step) ** 2 * dx).sum())


def pit_value(support: Sequence[float], probabilities: Sequence[float], actual: float) -> float:
    """Predictive CDF at the realized outcome — F(actual) in [0, 1]."""
    if not math.isfinite(actual):
        raise ValueError("actual must be finite")
    sup, probs = _validate_dist(support, probabilities)
    below = probs[sup <= actual].sum()
    return float(min(max(below, 0.0), 1.0))


def interval_coverage(support: Sequence[float], probabilities: Sequence[float],
                      actual: float, level: float) -> bool:
    """Is `actual` inside the central `level` predictive interval?"""
    if not (0.0 < level < 1.0):
        raise ValueError("level must be in (0, 1)")
    if not math.isfinite(actual):
        raise ValueError("actual must be finite")
    sup, probs = _validate_dist(support, probabilities)
    cdf = np.cumsum(probs)
    lo_q = (1.0 - level) / 2.0
    hi_q = 1.0 - lo_q
    lo_idx = int(np.searchsorted(cdf, lo_q, side="left"))
    hi_idx = int(np.searchsorted(cdf, hi_q, side="left"))
    lo_idx = min(lo_idx, sup.size - 1)
    hi_idx = min(hi_idx, sup.size - 1)
    return bool(sup[lo_idx] <= actual <= sup[hi_idx])


def point_error(support: Sequence[float], probabilities: Sequence[float], actual: float
                ) -> tuple[float, float]:
    """(abs_err, sq_err) between the distribution mean and the realized outcome."""
    if not math.isfinite(actual):
        raise ValueError("actual must be finite")
    sup, probs = _validate_dist(support, probabilities)
    mean = float((sup * probs).sum())
    err = mean - float(actual)
    return abs(err), err * err


def bootstrap_ci(values: Sequence[float], statistic: Callable[[np.ndarray], float],
                 n_boot: int, seed: int, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI on `statistic(sample)` at central `level`.

    `seed` is REQUIRED. `values` must be non-empty. `n_boot` must be a positive int.
    """
    if not isinstance(n_boot, int) or n_boot < 1:
        raise ValueError("n_boot must be a positive int")
    if not (0.0 < level < 1.0):
        raise ValueError("level must be in (0, 1)")
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("values must be a non-empty 1-D sequence")
    if not np.all(np.isfinite(arr)):
        raise ValueError("values contain non-finite entries")
    rng = np.random.default_rng(seed)
    n = arr.size
    stats = np.empty(n_boot)
    for b in range(n_boot):
        sample = arr[rng.integers(0, n, size=n)]
        stats[b] = float(statistic(sample))
    lo_q = (1.0 - level) / 2.0
    hi_q = 1.0 - lo_q
    return float(np.quantile(stats, lo_q)), float(np.quantile(stats, hi_q))
