"""Unit tests for the V5B -> EngineDistribution wrapper.

The wrapper lives at Trade One Package root (beside sbc_engine_v5.py), so we insert that
directory on sys.path for these tests.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_PKG_ROOT = str(Path(__file__).resolve().parents[2])
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from sbc_v5_cwc_wrapper import (  # noqa: E402
    ENGINE_ID,
    ENGINE_VERSION,
    OUTCOME_FAMILY,
    SUPPORT,
    SUPPORT_MAX,
    SUPPORT_MIN,
    discretize_normal,
    v5b_result_to_distribution,
)


# ---- discretize_normal ------------------------------------------------------

def test_discretize_sums_to_one():
    probs = discretize_normal(6.4, 2.2)
    assert len(probs) == SUPPORT_MAX - SUPPORT_MIN + 1
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)


def test_discretize_all_nonnegative():
    probs = discretize_normal(6.4, 2.2)
    assert all(p >= 0.0 for p in probs)


def test_discretize_centered_at_projection_mode_near_integer_mean():
    # Normal(6.0, 2.2) discretized: the bin at K=6 should be the mode.
    probs = discretize_normal(6.0, 2.2)
    argmax_index = probs.index(max(probs))
    argmax_k = SUPPORT_MIN + argmax_index
    assert argmax_k == 6


def test_discretize_mass_no_leakage_below_support_min():
    # There is no support below 0; leftmost bin is the ONLY holder of P(K<=0.5).
    # Truncation lives in the leftmost bin; total still sums to 1.
    probs = discretize_normal(6.4, 2.2)
    assert probs[0] >= 0.0
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)


def test_discretize_rejects_zero_or_negative_std():
    with pytest.raises(ValueError, match="std must be positive"):
        discretize_normal(6.4, 0.0)
    with pytest.raises(ValueError, match="std must be positive"):
        discretize_normal(6.4, -1.0)


def test_discretize_rejects_non_finite():
    with pytest.raises(ValueError):
        discretize_normal(float("nan"), 2.2)
    with pytest.raises(ValueError):
        discretize_normal(6.4, float("inf"))


def test_discretize_narrow_std_concentrates_mass_at_mean():
    # std=0.4 around mean=7.0 -> almost all mass on K=7
    probs = discretize_normal(7.0, 0.4)
    assert probs[7] > 0.75  # bulk of the density
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)


# ---- v5b_result_to_distribution --------------------------------------------

def _mock_v5b_result(k_projected=6.4, std=2.2, game_date="2026-08-06"):
    # Only the fields the wrapper reads are required. Match the shape V5B emits.
    return {
        "grade": "A",
        "direction": "OVER",
        "verdict": "STRONG_EDGE_CONFIRMED",
        "abs_adj": 0.152,
        "l4_confirmed": True,
        "low_confidence": False,
        "pitcher_id": 543037,
        "game_date": game_date,
        "line": 6.5,
        "pitcher_tier": "STARTER",
        "recent_avg_ip": 5.1,
        "k_projected": k_projected,
        "structural_adjustment": -0.1,
        "components": {"c1": 0.0, "c2": 0.0, "c3": 0.0, "c4": 0.0},
        "std": std,
        "csw_pct": 0.28,
        "recent_k9_std": 1.5,
        "n_prior_starts": 8,
    }


def test_none_in_none_out():
    assert v5b_result_to_distribution(None) is None


def test_result_to_distribution_returns_valid_engine_distribution():
    dist = v5b_result_to_distribution(_mock_v5b_result(k_projected=6.4, std=2.2),
                                       correlation_id="543037:2026-08-06")
    assert dist is not None
    dist.validate()
    assert dist.engine_id == ENGINE_ID
    assert dist.engine_version == ENGINE_VERSION
    assert dist.outcome_family == OUTCOME_FAMILY
    assert dist.support == SUPPORT
    assert len(dist.probabilities) == len(SUPPORT)
    assert sum(dist.probabilities) == pytest.approx(1.0, abs=1e-12)
    assert dist.correlation_id == "543037:2026-08-06"


def test_distribution_centered_near_projection():
    dist = v5b_result_to_distribution(_mock_v5b_result(k_projected=6.4, std=2.2))
    assert dist is not None
    argmax = dist.probabilities.index(max(dist.probabilities))
    # k_projected=6.4 -> mode should be 6 or 7 (rounded to nearest bin center)
    assert argmax in (6, 7)


def test_as_of_carries_game_date():
    dist = v5b_result_to_distribution(_mock_v5b_result(game_date="2026-05-14"))
    assert dist is not None
    assert dist.as_of == "2026-05-14"


def test_engine_version_matches_v5b_calibration_label():
    # The wrapper must pull the identity string from V5B itself, not invent one.
    from sbc_engine_v5 import CALIBRATION_LABEL
    assert ENGINE_VERSION == CALIBRATION_LABEL
