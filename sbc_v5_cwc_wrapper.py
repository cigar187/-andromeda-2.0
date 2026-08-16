"""V5B -> EngineDistribution wrapper (CWC-facing).

Sits BESIDE sbc_engine_v5.py; V5B itself is not modified. The wrapper takes V5B's point
projection + std and discretizes Normal(k_projected, std) onto integer K support [0..20]
using continuity correction, then renormalizes so the support-truncated distribution sums
to 1.0.

Absence is honest (Rule 4):
- V5B abstains (csw_pct missing OR n_prior_starts < 2) -> wrapper returns None.
- Missing required inputs at the CALLER layer (put_whiff, ip_baseline, insufficient
  prior starts for a real std) -> wrapper RAISES with ERROR log rather than allowing
  V5B's internal silent defaults (0.24 / 5.0 / DEFAULT_STD=2.2) to fire.
- No flat/uniform fake distribution is ever fabricated.

Engine identity carried to the EngineDistribution:
- engine_id       = "sbc_v5b"
- engine_version  = the CALIBRATION_LABEL constant published by sbc_engine_v5.py itself
                    (single source of truth — never invented here).

Full V5B output preserved (Rule 4 / grade-signal integrity):
- v5b_for_pitcher_night_full() returns a tuple (EngineDistribution|None, dict|None)
  where the dict carries grade, l4_confirmed, direction, components, k_projected,
  std, and adjustment. Callers that only need the distribution can use
  v5b_for_pitcher_night(); callers that need grading (e.g. Andromeda card
  assembler) must use the _full variant to avoid the earlier signal-drop bug
  (grade/l4_confirmed/direction/components were being discarded).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

# Wrapper imports the engine as a read-only reference — never mutates it (Rule 9 / A3).
import sbc_engine_v5
from sbc_engine_v5 import CALIBRATION_LABEL, run_sbc_v5_for_pitcher_night

from trade_one.contracts import EngineDistribution

log = logging.getLogger("sbc_v5_cwc_wrapper")

# Minimum prior starts required for V5B to produce a real std from data. Below this
# threshold sbc_engine_v5 silently falls back to DEFAULT_STD=2.2 (Rule-4 violation).
# The wrapper enforces the same threshold sbc_engine_v5.py uses internally (>= 5)
# and raises rather than allowing the substitute std through.
MIN_PRIOR_STARTS_FOR_STD = 5


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

    NOTE: this function returns ONLY the distribution. Grade/l4_confirmed/direction/
    components are dropped by design here — call v5b_for_pitcher_night_full() when
    those fields are needed downstream (e.g. card assembler / grader).
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


def _validate_v5b_inputs(store: dict[str, Any], pitcher_id: Any, game_date: Any) -> None:
    """Raise ValueError (with ERROR log) if the store lacks values V5B would silently
    default. Rule-4: no fallbacks — a missing input is a hard failure, not a fabricated
    substitute. Keeps sbc_engine_v5.py untouched (Rule-9) while blocking its internal
    put_whiff->0.24 / ip_baseline->5.0 / std->2.2 defaults from ever firing.
    """
    profiles = store.get("profiles") if isinstance(store, dict) else None
    if profiles is None:
        msg = f"V5B input missing: store has no 'profiles' key (pitcher={pitcher_id!r}, date={game_date!r})"
        log.error(msg)
        raise ValueError(msg)
    prof = profiles.get(pitcher_id) if isinstance(profiles, dict) else None
    if prof is None:
        msg = f"V5B input missing: no profile for pitcher_id={pitcher_id!r} (date={game_date!r})"
        log.error(msg)
        raise ValueError(msg)
    if prof.get("put_whiff") is None:
        msg = f"V5B input missing: put_whiff is None for pitcher_id={pitcher_id!r} (date={game_date!r})"
        log.error(msg)
        raise ValueError(msg)
    if prof.get("ip_baseline") is None:
        msg = f"V5B input missing: ip_baseline is None for pitcher_id={pitcher_id!r} (date={game_date!r})"
        log.error(msg)
        raise ValueError(msg)
    history = store.get("history") if isinstance(store, dict) else None
    hist_rows = history.get(pitcher_id, []) if isinstance(history, dict) else []
    # V5B's own MIN_STARTS_FOR_STD is 5 (sbc_engine_v5.py:236). Below it, V5B substitutes
    # DEFAULT_STD=2.2. Wrapper refuses rather than allow that substitution.
    prior_starts = sum(
        1 for r in hist_rows
        if r.get("game_date") is not None and str(r["game_date"]) < str(game_date)
    )
    if prior_starts < MIN_PRIOR_STARTS_FOR_STD:
        msg = (
            f"V5B input insufficient: only {prior_starts} prior starts for pitcher_id={pitcher_id!r} "
            f"before {game_date!r} (need >= {MIN_PRIOR_STARTS_FOR_STD} for a real std; "
            f"V5B would otherwise substitute DEFAULT_STD=2.2 — Rule-4 refuses)"
        )
        log.error(msg)
        raise ValueError(msg)


def v5b_for_pitcher_night(store: dict[str, Any], pitcher_id: Any, game_date: Any, line: float,
                          v2_direction: str | None = None,
                          thresholds: dict | None = None) -> EngineDistribution | None:
    """End-to-end: run V5B against the given store + inputs, return an EngineDistribution
    (or None if V5B abstained on this pitcher-night). Wrapper only — V5B is untouched.

    Rule-4: pre-flight validates required inputs and RAISES on missing values rather
    than allowing V5B's silent internal defaults to substitute (see _validate_v5b_inputs).

    NOTE: returns only the distribution. If you need grade/l4_confirmed/direction/
    components (e.g. for card grading), use v5b_for_pitcher_night_full() instead.
    """
    _validate_v5b_inputs(store, pitcher_id, game_date)
    result = run_sbc_v5_for_pitcher_night(
        store, pitcher_id, game_date, line, v2_direction=v2_direction, thresholds=thresholds,
    )
    correlation_id = f"{pitcher_id}:{game_date}" if result is not None else None
    return v5b_result_to_distribution(result, correlation_id=correlation_id)


def v5b_for_pitcher_night_full(store: dict[str, Any], pitcher_id: Any, game_date: Any, line: float,
                               v2_direction: str | None = None,
                               thresholds: dict | None = None
                               ) -> tuple[EngineDistribution | None, dict[str, Any] | None]:
    """End-to-end + FULL result: returns (EngineDistribution, v5b_result_dict).

    The dict carries every field V5B produces — grade, l4_confirmed, direction, components,
    k_projected, std, adjustment, verdict, etc. — so callers (Andromeda card assembler,
    grader, calibrator) can consume V5B's grade signal without the earlier drop bug.

    Returns (None, None) when V5B abstains. Rule-4: validates inputs; raises on missing.
    """
    _validate_v5b_inputs(store, pitcher_id, game_date)
    result = run_sbc_v5_for_pitcher_night(
        store, pitcher_id, game_date, line, v2_direction=v2_direction, thresholds=thresholds,
    )
    if result is None:
        return (None, None)
    correlation_id = f"{pitcher_id}:{game_date}"
    dist = v5b_result_to_distribution(result, correlation_id=correlation_id)
    return (dist, result)
