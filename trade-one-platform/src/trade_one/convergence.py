"""Confidence-Weighted Convergence (CWC) — pure math for fusing multi-stream distributions.

Each engine emits a discrete probability distribution over an outcome (e.g. pitcher-K count).
Confidence in each stream is derived from the entropy of that stream's own distribution
(1 - H/ln(N)). Streams fuse via a log-opinion pool weighted by their confidence. A single
directional decision + conviction is then read off the fused distribution.

Uncertainty becomes a WEIGHT, never a veto. A stream with high entropy contributes little; a
stream with low entropy dominates. This is distinct from thresholded voting (which throws away
uncertain votes) and from arithmetic averaging (which lets confident streams get diluted by
uncertain ones).

Formulas (nats throughout)
--------------------------
Shannon entropy:      H(p) = -Sigma_i p_i * ln(p_i),  with p_i = 0 contributing 0.
Normalized conf:      C(p) = 1 - H(p) / ln(N),  N = support size.
                      Uniform -> 0. Point mass -> 1. N = 1 defined as 1 (a one-outcome
                      distribution IS a point mass).
Log-opinion pool:     combined_i proportional to Prod_k p_k[i]^{w_k}
                      equivalently:  log combined_i = Sigma_k w_k * log p_k[i], then softmax-
                      normalize. Weights that sum to 1 give the identity property (pooling K
                      identical distributions returns that distribution); weights that sum > 1
                      sharpen; weights that sum < 1 flatten.
                      All-zero-weight input is REJECTED (raises ValueError). Silently defaulting
                      to equal weight would fabricate a stance we do not have (Rule 4: no
                      fabrication).

No function returns None or an abstain sentinel. Every function returns a real value or raises.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


_ZERO_TOL = 1e-12
_SUM_TOL = 1e-6


def _as_prob_vector(p: Sequence[float], name: str = "p") -> np.ndarray:
    """Validate + normalize a probability vector. Raises ValueError on any violation."""
    arr = np.asarray(p, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D sequence")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
    if np.any(arr < -_ZERO_TOL):
        raise ValueError(f"{name} contains negative values")
    arr = np.clip(arr, 0.0, None)
    total = float(arr.sum())
    if abs(total - 1.0) > _SUM_TOL:
        raise ValueError(f"{name} must sum to 1 (got {total:.6f})")
    return arr / total


def shannon_entropy(p: Sequence[float]) -> float:
    """H(p) = -Sigma p_i * ln p_i (nats). Slots with p_i = 0 contribute 0."""
    arr = _as_prob_vector(p, "p")
    mask = arr > 0
    return float(-(arr[mask] * np.log(arr[mask])).sum())


def normalized_confidence(p: Sequence[float]) -> float:
    """C(p) = 1 - H(p) / ln(N). Uniform -> 0; point mass -> 1; support size 1 -> 1."""
    arr = _as_prob_vector(p, "p")
    n = arr.size
    if n == 1:
        return 1.0
    return float(1.0 - shannon_entropy(arr) / math.log(n))


def log_opinion_pool(dists: Sequence[Sequence[float]], weights: Sequence[float]) -> np.ndarray:
    """Weighted log-opinion pool over K distributions sharing an N-outcome support.

    combined_i proportional to Prod_k dist_k[i]^{w_k}, then normalized to sum to 1.

    Raises ValueError if:
      - dists is empty
      - dists have differing support size
      - len(weights) != len(dists)
      - any weight is negative or non-finite
      - all weights are zero (would require an equal-weight fabrication)
      - the pool degenerates (every outcome has log-sum = -inf under positively-weighted voters)
    """
    if len(dists) == 0:
        raise ValueError("dists must be non-empty")
    if len(weights) != len(dists):
        raise ValueError(f"weights length {len(weights)} != dists length {len(dists)}")
    w = np.asarray(weights, dtype=float)
    if not np.all(np.isfinite(w)):
        raise ValueError("weights contain non-finite values")
    if np.any(w < 0):
        raise ValueError("weights contain negative values")
    if float(w.sum()) <= _ZERO_TOL:
        raise ValueError("all weights are zero; refusing to fabricate an equal-weight fallback")

    prob_matrix = np.stack([_as_prob_vector(d, f"dists[{i}]") for i, d in enumerate(dists)])
    with np.errstate(divide="ignore"):
        log_p = np.log(prob_matrix)
    log_combined = (w[:, None] * log_p).sum(axis=0)
    if not np.any(np.isfinite(log_combined)):
        raise ValueError("pool degenerate: every outcome has zero mass under some positively-weighted voter")
    finite_max = float(log_combined[np.isfinite(log_combined)].max())
    shifted = log_combined - finite_max
    exp = np.exp(shifted)
    total = float(exp.sum())
    if total <= _ZERO_TOL or not math.isfinite(total):
        raise ValueError("pool degenerate: normalizer is zero or non-finite")
    return exp / total


def vnm_decision(support: Sequence[float], probabilities: Sequence[float], line: float
                 ) -> tuple[str, float, float]:
    """Read a directional decision from a discrete distribution over outcome values.

    p_over = sum of probabilities at support indices where support_i > line.
    lean   = 'OVER' if p_over > 0.5 + eps
             'UNDER' if p_over < 0.5 - eps
             'PUSH' otherwise
    conviction = |p_over - 0.5| * 2 * normalized_confidence(probabilities), in [0, 1].
                 High only when the vote is BOTH lopsided AND the fused dist is peaky.

    Raises ValueError if support and probabilities have different shapes.
    """
    sup = np.asarray(support, dtype=float)
    probs = _as_prob_vector(probabilities, "probabilities")
    if sup.shape != probs.shape:
        raise ValueError(f"support shape {sup.shape} != probabilities shape {probs.shape}")
    p_over = float(probs[sup > line].sum())
    edge = abs(p_over - 0.5)
    eps = 1e-9
    if p_over > 0.5 + eps:
        lean = "OVER"
    elif p_over < 0.5 - eps:
        lean = "UNDER"
    else:
        lean = "PUSH"
    conviction = float(edge * 2.0 * normalized_confidence(probs))
    return lean, p_over, conviction
