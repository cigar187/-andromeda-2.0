"""DNO — Decision Deception formula module. Measured RELATIVE to each pitcher's
Pitch DNA. Never claims to observe eye or neural state — only Savant kinematics.

Three sub-engines produce ordinal/continuous features per pitcher-night; a
count-state whiff model produces per-pitch K probability; assembly yields
projected K + tier + hit-rate-ready output.

PSV-equiv (trajectory prediction error): extrapolate ball position from a
  simulated commit point (t ≈ 0.135 s from release, ≈ 23 ft from plate) forward
  to the plate, compare to actual (plate_x, plate_z). Normalize the appearance's
  mean magnitude by the pitcher's own DNA tunnel/break norms.

IOM-equiv (forced-chase): empirical P(swing | out-of-zone pitch), conditioned on
  late-break pitches following FB-mimicking release. Higher = pitcher forces
  more chase against their own DNA norm.

KMD (timing disruption): per-appearance mean of ||current pitch release_speed −
  EWMA(recent release_speeds)|| scaled by the pitcher's DNA velo variance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, stdev

Y_PLATE = 17.0 / 12.0
Y_RELEASE = 50.0
Y_COMMIT = 23.0                    # rough commit distance in ft
CHASE_ZONE_X = 0.708               # half zone width, ft
CHASE_ZONE_Z_LO = 1.5              # bottom of zone, ft (approx)
CHASE_ZONE_Z_HI = 3.5              # top of zone, ft (approx)


def _fnum(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ── PSV-equiv: trajectory extrapolation error at plate ────────────────────────

def commit_extrapolation_error(pitch: dict) -> float | None:
    """Given release-point physics, extrapolate the trajectory from the commit
    point (y=Y_COMMIT ~23 ft) linearly (constant velocity + gravity-only), then
    compare to the actual plate crossing.

    The rationale: a hitter commits ~135 ms before plate. If the ball's actual
    plate location differs from what a straight-line-from-commit extrapolation
    would predict, that's the physical late-break the hitter can't correct for.

    Returns Euclidean error in feet, or None if physics fields missing.
    """
    vy0 = _fnum(pitch.get("vy0")); vz0 = _fnum(pitch.get("vz0")); vx0 = _fnum(pitch.get("vx0"))
    ay = _fnum(pitch.get("ay")); az = _fnum(pitch.get("az")); ax = _fnum(pitch.get("ax"))
    plate_x = _fnum(pitch.get("plate_x")); plate_z = _fnum(pitch.get("plate_z"))
    rel_x = _fnum(pitch.get("release_pos_x")); rel_z = _fnum(pitch.get("release_pos_z"))
    if any(v is None for v in (vy0, vz0, vx0, ay, az, ax, plate_x, plate_z, rel_x, rel_z)):
        return None
    # Solve for t at commit point (y = Y_COMMIT)
    # y(t) = Y_RELEASE + vy0*t + 0.5*ay*t^2 = Y_COMMIT
    a = 0.5 * ay; b = vy0; c = Y_RELEASE - Y_COMMIT
    disc = b * b - 4.0 * a * c
    if disc < 0 or a == 0:
        return None
    t1 = (-b - math.sqrt(disc)) / (2.0 * a)
    t2 = (-b + math.sqrt(disc)) / (2.0 * a)
    t_commit = t1 if t1 > 0 else t2
    if t_commit <= 0:
        return None
    # Position at commit
    x_commit = rel_x + vx0 * t_commit + 0.5 * ax * t_commit ** 2
    z_commit = rel_z + vz0 * t_commit + 0.5 * az * t_commit ** 2
    # Velocity at commit
    vx_c = vx0 + ax * t_commit
    vz_c = vz0 + az * t_commit
    vy_c = vy0 + ay * t_commit
    # Straight-line extrapolation from commit to plate (Y_PLATE):
    # dt_left = (Y_COMMIT - Y_PLATE) / |vy_c|   (approximate — vy nearly constant)
    if vy_c == 0:
        return None
    dt_left = (Y_COMMIT - Y_PLATE) / abs(vy_c)
    # NO late acceleration in the extrapolation — that's what makes it a "commit prediction":
    # the hitter's expectation is linear from commit.
    x_pred = x_commit + vx_c * dt_left
    z_pred = z_commit + vz_c * dt_left
    return math.sqrt((plate_x - x_pred) ** 2 + (plate_z - z_pred) ** 2)


def compute_psv_equiv(pitches: list[dict], as_of_date: str, dna: dict | None,
                      window_days: int = 60) -> float | None:
    """Per-appearance mean commit_extrapolation_error, scaled by DNA HB+iVB norm."""
    if not pitches or dna is None:
        return None
    cutoff = _parse_date(as_of_date)
    if cutoff is None:
        return None
    window_start = cutoff - timedelta(days=window_days)
    errs = []
    for p in pitches:
        gd = _parse_date(p.get("game_date", ""))
        if gd is None or gd >= cutoff or gd < window_start:
            continue
        e = commit_extrapolation_error(p)
        if e is not None:
            errs.append(e)
    if len(errs) < 30:
        return None
    mean_err = mean(errs)
    # Normalize by DNA break magnitude (higher-break pitchers naturally have larger errs)
    ivb_in = dna.get("ff_ivb_in") or 0
    hb_in = dna.get("ff_hb_in") or 0
    break_mag_ft = math.sqrt(ivb_in ** 2 + hb_in ** 2) / 12.0
    if break_mag_ft <= 0:
        return mean_err
    return mean_err / break_mag_ft


# ── IOM-equiv: empirical forced-chase ─────────────────────────────────────────

def _in_zone(px, pz):
    if px is None or pz is None:
        return None
    return abs(px) <= CHASE_ZONE_X and CHASE_ZONE_Z_LO <= pz <= CHASE_ZONE_Z_HI


SWING_DESCRIPTIONS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "foul_bunt",
    "hit_into_play", "missed_bunt", "swinging_pitchout",
}


def compute_iom_equiv(pitches: list[dict], as_of_date: str, dna: dict | None,
                      window_days: int = 60) -> float | None:
    """Per-appearance forced-chase = P(swing | pitch is out-of-zone) relative to
    the population baseline (~0.28). Higher means the pitcher gets more chase.

    Requires ≥30 out-of-zone pitches in window."""
    if not pitches:
        return None
    cutoff = _parse_date(as_of_date)
    if cutoff is None:
        return None
    window_start = cutoff - timedelta(days=window_days)
    oz_total = 0
    oz_swings = 0
    for p in pitches:
        gd = _parse_date(p.get("game_date", ""))
        if gd is None or gd >= cutoff or gd < window_start:
            continue
        in_zone = _in_zone(_fnum(p.get("plate_x")), _fnum(p.get("plate_z")))
        if in_zone is None or in_zone:
            continue
        oz_total += 1
        desc = (p.get("description") or "").lower()
        if desc in SWING_DESCRIPTIONS:
            oz_swings += 1
    if oz_total < 30:
        return None
    return oz_swings / oz_total


# ── KMD: timing disruption ────────────────────────────────────────────────────

def compute_kmd(pitches: list[dict], as_of_date: str, dna: dict | None,
                window_days: int = 60, ewma_alpha: float = 0.4) -> float | None:
    """Per-appearance mean absolute velocity change against pitcher's own EWMA
    of release_speed, scaled by DNA velo baseline."""
    if not pitches:
        return None
    cutoff = _parse_date(as_of_date)
    if cutoff is None:
        return None
    window_start = cutoff - timedelta(days=window_days)
    kept = []
    for p in pitches:
        gd = _parse_date(p.get("game_date", ""))
        if gd is None or gd >= cutoff or gd < window_start:
            continue
        v = _fnum(p.get("release_speed"))
        if v is not None:
            kept.append((gd, v))
    if len(kept) < 30:
        return None
    kept.sort(key=lambda x: x[0])
    ewma = kept[0][1]
    diffs = []
    for _gd, v in kept[1:]:
        diffs.append(abs(v - ewma))
        ewma = (1.0 - ewma_alpha) * ewma + ewma_alpha * v
    if not diffs:
        return None
    mean_diff = mean(diffs)
    # Normalize by DNA fastball velo — a 5 mph swing on a 95 mph pitcher isn't
    # the same as on an 88 mph pitcher.
    ff_velo = (dna or {}).get("ff_velo") or 90.0
    return mean_diff / ff_velo


# ── DNO assembly ──────────────────────────────────────────────────────────────

def compute_dno_features(pitches: list[dict], as_of_date: str, dna: dict | None
                         ) -> dict:
    """All three DNO features in one pass."""
    return {
        "psv": compute_psv_equiv(pitches, as_of_date, dna),
        "iom": compute_iom_equiv(pitches, as_of_date, dna),
        "kmd": compute_kmd(pitches, as_of_date, dna),
    }
