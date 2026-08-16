"""V5B -> EngineDistribution wrapper (CWC-facing).

Sits BESIDE sbc_engine_v5.py; V5B itself is not modified. The wrapper takes V5B's point
projection + std and discretizes Normal(k_projected, std) onto integer K support [0..20]
using continuity correction, then renormalizes so the support-truncated distribution sums
to 1.0.

Absence is honest:
- V5B returns None (csw_pct missing OR n_prior_starts < 2) -> wrapper returns None.
- No flat/uniform fake distribution is ever fabricated (Rule 4).

Engine identity carried to the EngineDistribution:
- engine_id       = "sbc_v5b"
- engine_version  = the CALIBRATION_LABEL constant published by sbc_engine_v5.py itself
                    (single source of truth — never invented here).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Wrapper imports the engine as a read-only reference — never mutates it (Rule 9 / A3).
import sbc_engine_v5
from sbc_engine_v5 import CALIBRATION_LABEL, run_sbc_v5_for_pitcher_night

from trade_one.contracts import EngineDistribution


ENGINE_ID = "sbc_v5b"
ENGINE_VERSION = CALIBRATION_LABEL
OUTCOME_FAMILY = "pitcher_strikeouts"
SUPPORT_MIN = 0
SUPPORT_MAX = 20
SUPPORT: tuple[float, ...] = tuple(float(k) for k in range(SUPPORT_MIN, SUPPORT_MAX + 1))


def _phi(z: float) -> float:
    """Standard-normal CDF via erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def discretize_normal(mean: float, std: float,
                      support_min: int = SUPPORT_MIN,
                      support_max: int = SUPPORT_MAX) -> tuple[float, ...]:
    """Discretize Normal(mean, std) onto integer support [support_min .. support_max] using
    continuity correction: P(K=k) proportional to Phi((k+0.5-mean)/std) - Phi((k-0.5-mean)/std)
    for k = support_min..support_max, with the leftmost bin absorbing mass at k <= support_min-0.5
    and the rightmost bin absorbing mass at k >= support_max+0.5. Result is renormalized to sum
    to 1 so the truncated distribution is a proper probability vector.

    Requires std > 0; raises ValueError otherwise.
    """
    if not (std > 0 and math.isfinite(std)):
        raise ValueError(f"std must be positive and finite (got {std!r})")
    if not math.isfinite(mean):
        raise ValueError(f"mean must be finite (got {mean!r})")
    if support_max < support_min:
        raise ValueError("support_max must be >= support_min")

    n = support_max - support_min + 1
    probs = [0.0] * n
    for i, k in enumerate(range(support_min, support_max + 1)):
        lo = -math.inf if k == support_min else (k - 0.5 - mean) / std
        hi = math.inf if k == support_max else (k + 0.5 - mean) / std
        p_lo = 0.0 if lo == -math.inf else _phi(lo)
        p_hi = 1.0 if hi == math.inf else _phi(hi)
        probs[i] = p_hi - p_lo
    total = sum(probs)
    if total <= 0.0 or not math.isfinite(total):
        raise ValueError(f"discretization produced non-positive mass ({total!r})")
    return tuple(p / total for p in probs)


def v5b_result_to_distribution(v5b_result: dict[str, Any] | None,
                               correlation_id: str | None = None) -> EngineDistribution | None:
    """Convert one V5B result dict into an EngineDistribution over pitcher-K support [0..20].

    v5b_result is either the dict returned by run_sbc_v5_for_pitcher_night, or None (no-call).
    None in -> None out; no fake distribution is ever fabricated.
    """
    if v5b_result is None:
        return None
    k_projected = float(v5b_result["k_projected"])
    std = float(v5b_result["std"])
    probs = discretize_normal(k_projected, std)
    dist = EngineDistribution(
        engine_id=ENGINE_ID,
        engine_version=ENGINE_VERSION,
        outcome_family=OUTCOME_FAMILY,
        support=SUPPORT,
        probabilities=probs,
        as_of=str(v5b_result.get("game_date", "")),
        correlation_id=correlation_id,
    )
    dist.validate()
    return dist


def v5b_for_pitcher_night(store: dict[str, Any], pitcher_id: Any, game_date: Any, line: float,
                          v2_direction: str | None = None,
                          thresholds: dict | None = None) -> EngineDistribution | None:
    """End-to-end: run V5B against the given store + inputs, return an EngineDistribution
    (or None if V5B abstained on this pitcher-night). Wrapper only — V5B is untouched.
    """
    result = run_sbc_v5_for_pitcher_night(
        store, pitcher_id, game_date, line, v2_direction=v2_direction, thresholds=thresholds,
    )
    correlation_id = f"{pitcher_id}:{game_date}" if result is not None else None
    return v5b_result_to_distribution(result, correlation_id=correlation_id)
