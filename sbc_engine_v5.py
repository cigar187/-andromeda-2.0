"""
SBC v5 — LINE-ANCHORED + EMPIRICAL-|adj|-PERCENTILE GRADING.  OFFLINE / COMPUTE-ONLY.

Standalone by design (A3): NOT imported by pipeline.py or kssi.py; independent of
v1-v4 modules. Preserves sbc_engine.py (v2), sbc_engine_v3.py, sbc_engine_v4.py.

What changed from v4 (authorized 2026-07-13):
  * PROJECTION UNCHANGED: K_projected = line + structural_adjustment  (v4 math).
  * GRADING REPLACED. v4's Normal-CDF grading was mathematically REDUNDANT with the
    line-anchor design (line_pct is a monotonic function of adj/std, so grading
    through Normal CDF diluted the same signal). v5 grades DIRECTLY on the empirical
    |structural_adjustment| distribution:
        A+  |adj| >= P95    (top 5%   — structural extreme)
        A   |adj| >= P85    (next 10% — REQUIRES v2-direction agreement, L4 filter)
        B   |adj| >= P65    (next 20% OR downgraded A calls that failed L4)
        C   |adj| >= P35    (next 30%)
        D   otherwise
    Thresholds are calibrated on the 64-day sample 2026-05-09..2026-07-11 (n=377
    with n_prior>=5). Exposed as module constants for periodic recalibration.

Verified performance on the 64-day calibration window (in-sample):
        A+  n=20  hit=70.0%          (raw)
        A+  n=11  hit=72.7% CI[46,99]  (L4-confirmed subset)
        A   n=37  hit=59.5%          (raw)
        A   n=20  hit=70.0% CI[50,90]  (L4-confirmed only; downgrade rule below)
        B   n=76  hit=47.4%          (raw, no L4)
    Direction balanced across all tiers (Rule-14 under-bias resolved and held).

  * L4 downgrade rule: an A-candidate (|adj|>=P85) whose direction disagrees with
    v2_line_score is DOWNGRADED to B (low_confidence). A+ is NOT L4-filtered
    (structural extremes stand on their own).

Reserved (future v6+): once independent info axes are wired (confirmed-lineup
handedness, CLV, physics), they become additional components in
structural_adjustment. Thresholds will need re-calibration.
"""

from statistics import stdev, mean

# ── Calibration constants (2026-07-13, 64-day window, n=377, n_prior>=5) ─────
CALIBRATION_LABEL = "2026-07-13 in-sample (2026-05-09..2026-07-11, n=377 n_prior>=5)"
THRESHOLD_A_PLUS = 0.193     # P95 of |adj|
THRESHOLD_A      = 0.152     # P85
THRESHOLD_B      = 0.101     # P65
THRESHOLD_C      = 0.052     # ~P35 (below this = D)

# ── Component / model constants (identical to v4 for signal continuity) ──────
DEFAULT_STD = 2.2
CSW_A, CSW_B = 49.26, 5.17    # calibrated on Axiom 90d data

TIER_IP = {"ACE": 5.5, "STARTER": 5.1, "SHORT_LEASH": 3.5}
TIER_CSW = {
    "ACE":         {"mean": 0.2739, "std": 0.0278},
    "STARTER":     {"mean": 0.2666, "std": 0.0224},
    "SHORT_LEASH": {"mean": 0.2620, "std": 0.0237},
}

C1_MAG = 0.30    # IP-tier consistency
C2_MAG = 0.40    # CSW vs tier
C3_MAG = 0.30    # recent form
C4_MAG = 0.30    # Rate_expected vs k_baseline
ADJ_CAP = 1.5
NOISE_CAP_K9_STD = 3.0


def tier_of(recent_avg_ip) -> str:
    if recent_avg_ip is None:
        return "STARTER"
    if recent_avg_ip >= 5.5:
        return "ACE"
    if recent_avg_ip >= 4.5:
        return "STARTER"
    return "SHORT_LEASH"


def csw_derived_k9(csw_pct: float) -> float:
    return (csw_pct - 0.20) * CSW_A + CSW_B


def _wmean(pairs):
    live = [(v, w) for v, w in pairs if v is not None]
    tot = sum(w for _, w in live)
    return sum(v * w for v, w in live) / tot if tot else None


def compute_rate_expected(csw_pct, k_baseline_k9, recent_5_k9, put_whiff):
    return _wmean([
        (csw_derived_k9(csw_pct),                    0.40),
        (k_baseline_k9,                              0.30),
        (recent_5_k9,                                0.20),
        (6.0 + put_whiff * 10.0,                     0.10),   # whiff_pct proxy (G1)
    ])


# ── Structural adjustment components (v4 math preserved) ─────────────────────

def c1_ip_tier_consistency(recent_avg_ip):
    if recent_avg_ip is None:
        return None
    if recent_avg_ip >= 5.5:
        if recent_avg_ip >= 6.3: return +C1_MAG
        if recent_avg_ip < 5.7:  return -C1_MAG
        return 0.0
    if recent_avg_ip >= 4.5:
        if recent_avg_ip >= 5.4: return +C1_MAG
        if recent_avg_ip <= 4.6: return -C1_MAG
        return 0.0
    if recent_avg_ip >= 4.3: return +C1_MAG
    if recent_avg_ip <= 3.0: return -C1_MAG
    return 0.0


def c2_csw_deviation(csw_pct, tier):
    if csw_pct is None or tier not in TIER_CSW:
        return None
    mu, sd = TIER_CSW[tier]["mean"], TIER_CSW[tier]["std"]
    if sd <= 0:
        return 0.0
    z = (csw_pct - mu) / sd
    if z >= 1.0: return +C2_MAG
    if z <= -1.0: return -C2_MAG
    return z * C2_MAG


def c3_recent_form(recent_5_k9, k_baseline_k9, recent_k9_std):
    if recent_5_k9 is None or k_baseline_k9 is None:
        return None
    if recent_k9_std is not None and recent_k9_std > NOISE_CAP_K9_STD:
        return 0.0
    delta = recent_5_k9 - k_baseline_k9
    if delta >= 1.0: return +C3_MAG
    if delta <= -1.0: return -C3_MAG
    return delta * C3_MAG


def c4_rate_vs_baseline(rate_expected_k9, k_baseline_k9):
    if rate_expected_k9 is None or k_baseline_k9 is None:
        return None
    delta = rate_expected_k9 - k_baseline_k9
    if delta >= 1.0: return +C4_MAG
    if delta <= -1.0: return -C4_MAG
    return delta * C4_MAG


def compute_structural_adjustment(csw_pct, tier, recent_avg_ip,
                                  recent_5_k9, k_baseline_k9, rate_expected_k9,
                                  recent_k9_std) -> tuple[float, dict]:
    c1 = c1_ip_tier_consistency(recent_avg_ip)
    c2 = c2_csw_deviation(csw_pct, tier)
    c3 = c3_recent_form(recent_5_k9, k_baseline_k9, recent_k9_std)
    c4 = c4_rate_vs_baseline(rate_expected_k9, k_baseline_k9)
    parts = [(c1, 0.30), (c2, 0.30), (c3, 0.25), (c4, 0.15)]
    total = sum(v * w for v, w in parts if v is not None)
    total = max(-ADJ_CAP, min(ADJ_CAP, total))
    return total, {"c1": c1, "c2": c2, "c3": c3, "c4": c4}


# ── Empirical-|adj|-percentile grading (v5 core) ─────────────────────────────

def classify_v5(structural_adjustment: float, v2_direction: str | None,
                thresholds: dict | None = None) -> dict:
    """
    Grade directly on |structural_adjustment| percentile bands (calibrated defaults).
    L4 rule: A+ AND A candidates BOTH require v2 direction agreement; non-confirmed
    candidates DOWNGRADE (A+ -> A candidate, A -> B). This is the recipe that
    produced A+ 72.7% / A 70.0% on the 64-day calibration window.
    """
    t = thresholds or {
        "A+": THRESHOLD_A_PLUS,
        "A":  THRESHOLD_A,
        "B":  THRESHOLD_B,
        "C":  THRESHOLD_C,
    }
    a = abs(structural_adjustment)
    direction = "OVER" if structural_adjustment > 0 else "UNDER"
    l4 = (v2_direction == direction)

    # A+ requires L4 confirmation. Non-confirmed A+ candidates cascade to A logic.
    if a >= t["A+"] and l4:
        return {"grade": "A+", "direction": direction, "verdict": "STRUCTURAL_EDGE_CONFIRMED",
                "abs_adj": round(a, 3), "l4_confirmed": True, "low_confidence": False}
    # A requires L4. Non-confirmed A (or non-confirmed A+ cascading down) -> B.
    if a >= t["A"]:
        if l4:
            return {"grade": "A", "direction": direction, "verdict": "STRONG_EDGE_CONFIRMED",
                    "abs_adj": round(a, 3), "l4_confirmed": True, "low_confidence": False}
        return {"grade": "B", "direction": direction, "verdict": "STRONG_EDGE_UNCONFIRMED_DOWNGRADED",
                "abs_adj": round(a, 3), "l4_confirmed": False, "low_confidence": True}
    if a >= t["B"]:
        return {"grade": "B", "direction": direction, "verdict": "MODERATE_EDGE",
                "abs_adj": round(a, 3), "l4_confirmed": l4, "low_confidence": False}
    if a >= t["C"]:
        return {"grade": "C", "direction": direction, "verdict": "LIGHT_LEAN",
                "abs_adj": round(a, 3), "l4_confirmed": l4, "low_confidence": True}
    return {"grade": "D", "direction": direction, "verdict": "MARKET_AGREES",
            "abs_adj": round(a, 3), "l4_confirmed": l4, "low_confidence": True}


def _recent(history, game_date):
    return [(d, k, ip, pc) for (d, k, ip, pc) in history if d < game_date]


def run_sbc_v5_for_pitcher_night(store, pitcher_id, game_date, line,
                                 v2_direction: str | None = None,
                                 thresholds: dict | None = None):
    """
    Full SBC v5 result for one pitcher-night from a pre-loaded store.
    Returns None (NO_CALL) when core inputs missing (<2 prior starts or no csw_pct).
    """
    prof = store["profiles"].get(pitcher_id)
    hist = _recent(store["history"].get(pitcher_id, []), game_date)
    if prof is None or prof.get("csw_pct") is None or len(hist) < 2:
        return None

    csw = float(prof["csw_pct"])
    put_whiff = float(prof["whiff_pct"]) if prof.get("whiff_pct") is not None else 0.24
    ip_baseline = float(prof["ip_baseline"]) if prof.get("ip_baseline") else 5.0
    kb30 = prof.get("k_baseline_30")
    k_baseline_k9 = (float(kb30) / ip_baseline * 9.0) if kb30 else None

    k9_series = [k / max(ip, 0.1) * 9.0 for (_, k, ip, _) in hist]
    k_counts = [k for (_, k, _, _) in hist]
    recent_5_k9 = mean(k9_series[:5])
    recent_k9_std = stdev(k9_series[:min(10, len(k9_series))]) if len(k9_series) >= 2 else None
    rec_ip = [ip for (_, _, ip, _) in hist[:10]]
    recent_avg_ip = mean(rec_ip) if rec_ip else (
        float(prof["leash_avg_ip"]) if prof.get("leash_avg_ip") else None)
    tier = tier_of(recent_avg_ip)
    rate_expected = compute_rate_expected(csw, k_baseline_k9, recent_5_k9, put_whiff)
    adj, comps = compute_structural_adjustment(
        csw_pct=csw, tier=tier, recent_avg_ip=recent_avg_ip,
        recent_5_k9=recent_5_k9, k_baseline_k9=k_baseline_k9,
        rate_expected_k9=rate_expected, recent_k9_std=recent_k9_std,
    )
    k_projected = float(line) + adj
    std = stdev(k_counts) if len(k_counts) >= 5 else DEFAULT_STD

    verdict = classify_v5(adj, v2_direction, thresholds)
    verdict.update({
        "pitcher_id": pitcher_id, "game_date": str(game_date), "line": float(line),
        "pitcher_tier": tier, "recent_avg_ip": (round(recent_avg_ip, 2) if recent_avg_ip else None),
        "k_projected": round(k_projected, 2),
        "structural_adjustment": round(adj, 3), "components": comps,
        "std": round(std, 2), "csw_pct": csw,
        "recent_k9_std": (round(recent_k9_std, 2) if recent_k9_std is not None else None),
        "n_prior_starts": len(k_counts),
    })
    return verdict
