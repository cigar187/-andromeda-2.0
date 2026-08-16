"""
SBC v5c — decision-deception hybrid with soft saturation + probability calibration.

NEW in v5c vs V5B (all additive; V5B is preserved untouched per Rule 9):
  - T5:  soft saturation (tanh) replaces the hard ADJ_CAP clamp
  - T6:  dd_sequence_shift — pitch-to-pitch sequence surprise from Savant per-pitch data
  - T11: dd_command_uncertainty — pitcher's location Var from Savant per-pitch data
  - T1:  calibrated P(over) via isotonic regression (artifact loaded at runtime)

ANCHOR (per DESIGN GUARD): k_projected = baseline + structural_adjustment
where baseline = k_baseline_season * ip_baseline_season / 9 — the pitcher's own
season-to-date K/9 * their typical IP, expressed as expected K per typical start.
This is data-derived (statsapi gameLog PIT), NOT market-line anchored — so v5c
is validatable across the full 2023-2026 window regardless of market availability.

The decision-deception (dd_*) features are MEASURABLE stand-ins for the intuition
Codex called DNO. They never claim to observe neural or eye state — only pitch
kinematics from Baseball Savant.

sbc_engine_v5.py IS NEVER MODIFIED. Component functions c1-c4 are imported.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Any, Iterable

from sbc_engine_v5 import (
    ADJ_CAP,
    C1_MAG,
    C2_MAG,
    C3_MAG,
    C4_MAG,
    DEFAULT_STD,
    c1_ip_tier_consistency,
    c2_csw_deviation,
    c3_recent_form,
    c4_rate_vs_baseline,
    compute_rate_expected,
    tier_of,
)

# Decision-deception component magnitudes — same scale as existing c1-c4
DD_SEQ_MAG = 0.30
DD_CMD_MAG = 0.30

# Weight vector (c1..c4 preserve their relative ratios; dd_* added at parity)
# Original V5B: [0.30, 0.30, 0.25, 0.15] summing to 1.00
# v5c:           [0.25, 0.25, 0.20, 0.10, 0.10, 0.10] summing to 1.00
V5C_WEIGHTS = (
    ("c1", 0.25),
    ("c2", 0.25),
    ("c3", 0.20),
    ("c4", 0.10),
    ("c5_dd_seq", 0.10),
    ("c6_dd_cmd", 0.10),
)

# Calibrator loaded from disk; None means P(over) will return None
_CALIBRATOR: dict | None = None


# ── T5: soft saturation replaces hard clamp ───────────────────────────────────

def soft_cap(x: float, cap: float = ADJ_CAP) -> float:
    """Smooth saturation preserving marginal signal above ±cap.
    Asymptote unchanged (±cap), continuous derivative — no cliff at boundary."""
    return cap * math.tanh(x / cap)


# ── T6: dd_sequence_shift ────────────────────────────────────────────────────

def compute_dd_sequence_shift(pitches: list[dict], cutoff_date: str,
                              ewma_alpha: float = 0.5) -> float | None:
    """T6: mean per-pitch surprise = ||pitch_vec_t − EWMA_α(prior pitches)||.

    pitch_vec = (release_speed, pfx_x, pfx_z, release_pos_x, release_pos_z).
    Normalized by pitcher's own std of pitch-vec magnitude so different pitchers
    are on comparable scales.

    Filtered PIT to pitches with game_date STRICTLY LESS than cutoff, within a
    60-day trailing window. Returns None if fewer than 30 prior pitches — no
    fabrication (Rule 4)."""
    if not pitches:
        return None
    try:
        cutoff = datetime.strptime(cutoff_date[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    window_start = cutoff - timedelta(days=60)

    kept = []
    for p in pitches:
        gd_raw = (p.get("game_date") or "")[:10]
        if not gd_raw:
            continue
        try:
            gd = datetime.strptime(gd_raw, "%Y-%m-%d")
        except ValueError:
            continue
        if gd >= cutoff or gd < window_start:
            continue
        try:
            vec = (
                float(p.get("release_speed") or 0),
                float(p.get("pfx_x") or 0),
                float(p.get("pfx_z") or 0),
                float(p.get("release_pos_x") or 0),
                float(p.get("release_pos_z") or 0),
            )
        except (ValueError, TypeError):
            continue
        kept.append((gd, vec))

    if len(kept) < 30:
        return None

    kept.sort(key=lambda item: item[0])
    ewma = kept[0][1]
    surprises = []
    for _gd, vec in kept[1:]:
        diff_sq = sum((vec[i] - ewma[i]) ** 2 for i in range(len(vec)))
        surprises.append(math.sqrt(diff_sq))
        ewma = tuple(
            ewma[i] * (1.0 - ewma_alpha) + vec[i] * ewma_alpha
            for i in range(len(vec))
        )

    if not surprises:
        return None
    magnitudes = [math.sqrt(sum(x * x for x in vec)) for _, vec in kept]
    mag_std = stdev(magnitudes) if len(magnitudes) >= 2 else 0.0
    if mag_std <= 0:
        return None
    return mean(surprises) / mag_std


# ── T11: dd_command_uncertainty ──────────────────────────────────────────────

def compute_dd_command_uncertainty(pitches: list[dict], cutoff_date: str
                                   ) -> float | None:
    """T11: mean over pitch-types of the pitcher's location variance.

    variance_pt = Var(release_pos_x) + Var(release_pos_z) + Var(plate_x) + Var(plate_z)
    for that pitch_type over the pitcher's prior 60d. Higher variance → less
    command → typically lower K rate.

    Returns None if fewer than 30 prior pitches total or no pitch_type has ≥10
    pitches — no fabrication (Rule 4)."""
    if not pitches:
        return None
    try:
        cutoff = datetime.strptime(cutoff_date[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    window_start = cutoff - timedelta(days=60)

    by_type: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    total_kept = 0
    for p in pitches:
        gd_raw = (p.get("game_date") or "")[:10]
        if not gd_raw:
            continue
        try:
            gd = datetime.strptime(gd_raw, "%Y-%m-%d")
        except ValueError:
            continue
        if gd >= cutoff or gd < window_start:
            continue
        pt = (p.get("pitch_type") or "").upper()
        if not pt:
            continue
        try:
            rec = (
                float(p.get("release_pos_x") or 0),
                float(p.get("release_pos_z") or 0),
                float(p.get("plate_x") or 0),
                float(p.get("plate_z") or 0),
            )
        except (ValueError, TypeError):
            continue
        by_type[pt].append(rec)
        total_kept += 1

    if total_kept < 30:
        return None

    variances = []
    for _pt, recs in by_type.items():
        if len(recs) < 10:
            continue
        pt_var = 0.0
        for dim in range(4):
            vals = [r[dim] for r in recs]
            m = mean(vals)
            pt_var += sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
        variances.append(pt_var)

    if not variances:
        return None
    return mean(variances)


# ── Z-score → component contribution helpers ─────────────────────────────────

def c5_dd_sequence(dd_seq: float | None, ref_mean: float, ref_std: float
                   ) -> float | None:
    """Higher-than-expected sequence surprise → higher K rate → positive contribution."""
    if dd_seq is None or ref_std <= 0:
        return None
    z = (dd_seq - ref_mean) / ref_std
    if z >= 1.0:
        return +DD_SEQ_MAG
    if z <= -1.0:
        return -DD_SEQ_MAG
    return z * DD_SEQ_MAG


def c6_dd_command(dd_cmd: float | None, ref_mean: float, ref_std: float
                  ) -> float | None:
    """Higher command uncertainty → LOWER K rate → negative contribution.
    Sign inverted from c5 by design (higher uncertainty = worse pitcher)."""
    if dd_cmd is None or ref_std <= 0:
        return None
    z = (dd_cmd - ref_mean) / ref_std
    if z >= 1.0:
        return -DD_CMD_MAG
    if z <= -1.0:
        return +DD_CMD_MAG
    return -z * DD_CMD_MAG


# ── Structural adjustment (V5B c1-c4 imported, dd_* added, soft cap) ─────────

def compute_structural_adjustment_v5c(
    csw_pct, tier, recent_avg_ip,
    recent_5_k9, k_baseline_k9, rate_expected_k9,
    recent_k9_std,
    dd_seq, dd_seq_ref,
    dd_cmd, dd_cmd_ref,
) -> tuple[float, dict]:
    """v5c structural adjustment. dd_*_ref = (mean, std) for that season's z-score."""
    c1 = c1_ip_tier_consistency(recent_avg_ip)
    c2 = c2_csw_deviation(csw_pct, tier)
    c3 = c3_recent_form(recent_5_k9, k_baseline_k9, recent_k9_std)
    c4 = c4_rate_vs_baseline(rate_expected_k9, k_baseline_k9)
    c5 = c5_dd_sequence(dd_seq, *dd_seq_ref) if dd_seq_ref else None
    c6 = c6_dd_command(dd_cmd, *dd_cmd_ref) if dd_cmd_ref else None

    values = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5_dd_seq": c5, "c6_dd_cmd": c6}
    total = sum(values[name] * weight for name, weight in V5C_WEIGHTS
                if values[name] is not None)
    total = soft_cap(total, ADJ_CAP)
    return total, values


# ── Full projection ──────────────────────────────────────────────────────────

def run_sbc_v5c(store: dict, pitcher_id: Any, game_date: str,
                pitches: list[dict] | None = None,
                dd_seq_ref: tuple[float, float] | None = None,
                dd_cmd_ref: tuple[float, float] | None = None,
                ) -> dict | None:
    """Full v5c pitcher-night projection. Returns None if V5B-style inputs missing."""
    prof = store["profiles"].get(pitcher_id)
    hist = [
        (d, k, ip, pc) for (d, k, ip, pc)
        in store["history"].get(pitcher_id, [])
        if d < game_date
    ]
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
    recent_k9_std = (stdev(k9_series[:min(10, len(k9_series))])
                     if len(k9_series) >= 2 else None)
    rec_ip = [ip for (_, _, ip, _) in hist[:10]]
    recent_avg_ip = (mean(rec_ip) if rec_ip
                     else (float(prof["leash_avg_ip"]) if prof.get("leash_avg_ip") else None))
    tier = tier_of(recent_avg_ip)
    rate_expected = compute_rate_expected(csw, k_baseline_k9, recent_5_k9, put_whiff)

    dd_seq = compute_dd_sequence_shift(pitches, game_date) if pitches else None
    dd_cmd = compute_dd_command_uncertainty(pitches, game_date) if pitches else None

    adj, comps = compute_structural_adjustment_v5c(
        csw_pct=csw, tier=tier, recent_avg_ip=recent_avg_ip,
        recent_5_k9=recent_5_k9, k_baseline_k9=k_baseline_k9,
        rate_expected_k9=rate_expected, recent_k9_std=recent_k9_std,
        dd_seq=dd_seq, dd_seq_ref=dd_seq_ref,
        dd_cmd=dd_cmd, dd_cmd_ref=dd_cmd_ref,
    )

    if k_baseline_k9 is None:
        return None
    baseline = k_baseline_k9 * ip_baseline / 9.0

    k_projected = baseline + adj
    std = stdev(k_counts) if len(k_counts) >= 5 else DEFAULT_STD

    return {
        "pitcher_id": pitcher_id,
        "game_date": str(game_date),
        "pitcher_tier": tier,
        "baseline": round(baseline, 3),
        "structural_adjustment": round(adj, 4),
        "components": comps,
        "k_projected": round(k_projected, 3),
        "std": round(std, 3),
        "csw_pct": csw,
        "dd_sequence_shift": round(dd_seq, 4) if dd_seq is not None else None,
        "dd_command_uncertainty": round(dd_cmd, 6) if dd_cmd is not None else None,
        "n_prior_starts": len(k_counts),
    }


# ── T1: calibrated P(over) — isotonic wrapper ────────────────────────────────

def load_calibrator(path: str) -> None:
    """Load an isotonic calibrator artifact from disk. Format:
      {"per_tier": {"A+": [[raw_p, calibrated_p, ci_lo, ci_hi], ...], ...},
       "trained_at": "...", "n_train": N}
    Must be called once before p_over_calibrated()."""
    global _CALIBRATOR
    with open(path, "r") as fh:
        _CALIBRATOR = json.load(fh)


def raw_p_over_normal(k_projected: float, k_line: float, std: float) -> float:
    """Untuned P(over) assuming Normal(k_projected, std)."""
    z = (k_projected - k_line) / max(std, 0.1)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _interp(x: float, table: list) -> tuple[float, float, float]:
    """Linear interpolate calibrator table. Returns (cal_p, ci_lo, ci_hi)."""
    if not table:
        return x, max(0.0, x - 0.15), min(1.0, x + 0.15)
    if x <= table[0][0]:
        return table[0][1], table[0][2], table[0][3]
    if x >= table[-1][0]:
        return table[-1][1], table[-1][2], table[-1][3]
    for i in range(len(table) - 1):
        x0 = table[i][0]
        x1 = table[i + 1][0]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return (
                table[i][1] + t * (table[i + 1][1] - table[i][1]),
                table[i][2] + t * (table[i + 1][2] - table[i][2]),
                table[i][3] + t * (table[i + 1][3] - table[i][3]),
            )
    return x, max(0.0, x - 0.15), min(1.0, x + 0.15)


def p_over_calibrated(k_projected: float, k_line: float, std: float, tier: str
                      ) -> tuple[float, tuple[float, float]] | None:
    """T1: calibrated P(over) with 95% CI band. Returns None if calibrator not
    loaded (Rule 4: no fabricated probability without a fitted model)."""
    if _CALIBRATOR is None:
        return None
    raw = raw_p_over_normal(k_projected, k_line, std)
    per_tier = _CALIBRATOR.get("per_tier", {})
    table = per_tier.get(tier) or per_tier.get("ALL")
    if not table:
        return None
    cal, lo, hi = _interp(raw, table)
    return cal, (lo, hi)
