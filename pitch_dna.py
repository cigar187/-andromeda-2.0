"""Pitch DNA — per-pitcher per-date physical/kinematic reference vector.

Reusable feature module. V5B, MLB1, DNO can all consume it via a shared shape.
Everything is computed POINT-IN-TIME (rolling window strictly BEFORE game_date)
from the existing Baseball Savant per-pitch cache. No new data pull.

MEASURABLE variables ONLY per Rule 4 — no eye/neural claims, no bespoke physiology.
All quantities are directly derivable from Savant fields.

DNA vector (per pitcher, per as_of date):
  release_pos_x_mean, release_pos_z_mean, extension_mean            — release physics
  ff_velo_mean, ff_spin_mean, ff_ivb, ff_hb                          — fastball archetype
  primary_offspeed_type, offspeed_velo_mean, offspeed_ivb, offspeed_hb — primary offspeed
  velo_tunnel_delta, ivb_tunnel_delta, hb_tunnel_delta               — FB→OS gaps
  vaa_ff, vaa_offspeed                                                — kinematic VAA at plate
  n_pitches_window, n_fb_window, n_os_window                          — sample sizes

VAA calc (kinematic, from Savant pitch physics):
  vaa = atan2(vz_plate, vy_plate)   in degrees, at plate crossing
  where vy_plate = vy0 + ay * t_plate  and vz_plate solved similarly.
  See derive_vaa() below.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Any


DEFAULT_WINDOW_DAYS = 60
FASTBALL_TYPES = {"FF", "SI", "FC"}       # 4-seam + 2-seam + cutter
OFFSPEED_TYPES = {"CH", "SL", "CU", "KC", "FS", "ST", "SV"}
Y_PLATE = 17.0 / 12.0                     # plate crossing point in feet
Y_RELEASE = 50.0                          # Savant convention for release reference


def _fnum(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_date(s: str):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def load_pitches(cache_root: Path, pitcher_id: int, season: int) -> list[dict]:
    """Open with utf-8-sig so first-column BOM ('pitch_type') is stripped."""
    p = cache_root / str(season) / f"{pitcher_id}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def derive_vaa(pitch: dict) -> float | None:
    """Kinematic Vertical Approach Angle at plate crossing.

    Savant gives release-point velocities (vy0, vz0) and accelerations (ay, az)
    referenced from y=50 ft. We solve the y-equation for t at plate (y=Y_PLATE),
    then vz(t) = vz0 + az*t, vy(t) = vy0 + ay*t, and VAA = atan2(vz, vy) in deg.

    Returns None if physics fields missing or the y-quadratic has no real root.
    """
    vy0 = _fnum(pitch.get("vy0"))
    vz0 = _fnum(pitch.get("vz0"))
    ay = _fnum(pitch.get("ay"))
    az = _fnum(pitch.get("az"))
    if any(v is None for v in (vy0, vz0, ay, az)):
        return None
    # y(t) = Y_RELEASE + vy0*t + 0.5*ay*t^2 = Y_PLATE
    # 0.5*ay * t^2 + vy0 * t + (Y_RELEASE - Y_PLATE) = 0
    a = 0.5 * ay
    b = vy0
    c = Y_RELEASE - Y_PLATE
    disc = b * b - 4.0 * a * c
    if disc < 0 or a == 0:
        return None
    # positive root (t > 0, ball moving toward plate — vy0 is negative in Savant)
    t1 = (-b - math.sqrt(disc)) / (2.0 * a)
    t2 = (-b + math.sqrt(disc)) / (2.0 * a)
    t_plate = t1 if t1 > 0 else t2
    if t_plate <= 0:
        return None
    vz_plate = vz0 + az * t_plate
    vy_plate = vy0 + ay * t_plate
    if vy_plate == 0:
        return None
    # VAA convention: angle of the velocity vector below horizontal, from the batter's frame.
    # vy is negative (ball moving toward home = -y). Use |vy| for the horizontal magnitude,
    # signed vz for the vertical component. Downward ball → negative degrees (~-5° for FF).
    return math.degrees(math.atan(vz_plate / abs(vy_plate)))


def _agg_metric(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return mean(values)


def compute_dna(pitches: list[dict], as_of_date: str,
                window_days: int = DEFAULT_WINDOW_DAYS,
                min_pitches: int = 50) -> dict | None:
    """Compute a pitcher's DNA vector as of a target game_date.

    Filters PIT: pitches with game_date STRICTLY < as_of_date and within window_days.
    Returns None if fewer than min_pitches in window (Rule 4: no fabrication).
    """
    if not pitches:
        return None
    cutoff = _parse_date(as_of_date)
    if cutoff is None:
        return None
    window_start = cutoff - timedelta(days=window_days)

    kept = []
    for p in pitches:
        gd = _parse_date(p.get("game_date", ""))
        if gd is None:
            continue
        if gd >= cutoff or gd < window_start:
            continue
        kept.append(p)

    if len(kept) < min_pitches:
        return None

    # Release physics (all pitches)
    rel_x = [_fnum(p.get("release_pos_x")) for p in kept]
    rel_z = [_fnum(p.get("release_pos_z")) for p in kept]
    ext = [_fnum(p.get("release_extension")) for p in kept]

    # Group by pitch type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for p in kept:
        pt = (p.get("pitch_type") or "").upper().strip()
        if pt:
            by_type[pt].append(p)

    # Fastball archetype (prefer FF; fall back to SI/FC if FF absent)
    fb_pitches = []
    for pt in ("FF", "SI", "FC"):
        if pt in by_type and len(by_type[pt]) >= 10:
            fb_pitches = by_type[pt]
            fb_type_used = pt
            break
    else:
        fb_type_used = None

    ff_velo = _agg_metric([_fnum(p.get("release_speed")) for p in fb_pitches]) if fb_pitches else None
    ff_spin = _agg_metric([_fnum(p.get("release_spin_rate")) for p in fb_pitches]) if fb_pitches else None
    ff_ivb = _agg_metric([_fnum(p.get("pfx_z")) for p in fb_pitches]) if fb_pitches else None
    ff_hb = _agg_metric([_fnum(p.get("pfx_x")) for p in fb_pitches]) if fb_pitches else None
    ff_vaa = _agg_metric([derive_vaa(p) for p in fb_pitches]) if fb_pitches else None
    # inches conversion for reporting (pfx is feet)
    ff_ivb_in = ff_ivb * 12.0 if ff_ivb is not None else None
    ff_hb_in = ff_hb * 12.0 if ff_hb is not None else None

    # Primary offspeed = the offspeed pitch type with the most pitches
    os_counts = {pt: len(by_type[pt]) for pt in by_type if pt in OFFSPEED_TYPES}
    os_counts = {pt: n for pt, n in os_counts.items() if n >= 10}
    primary_os_type = max(os_counts, key=os_counts.get) if os_counts else None
    os_pitches = by_type.get(primary_os_type, []) if primary_os_type else []

    os_velo = _agg_metric([_fnum(p.get("release_speed")) for p in os_pitches]) if os_pitches else None
    os_ivb = _agg_metric([_fnum(p.get("pfx_z")) for p in os_pitches]) if os_pitches else None
    os_hb = _agg_metric([_fnum(p.get("pfx_x")) for p in os_pitches]) if os_pitches else None
    os_vaa = _agg_metric([derive_vaa(p) for p in os_pitches]) if os_pitches else None
    os_ivb_in = os_ivb * 12.0 if os_ivb is not None else None
    os_hb_in = os_hb * 12.0 if os_hb is not None else None

    # Tunneling deltas (FB - OS)
    velo_tunnel_delta = (ff_velo - os_velo) if (ff_velo is not None and os_velo is not None) else None
    ivb_tunnel_delta = (ff_ivb_in - os_ivb_in) if (ff_ivb_in is not None and os_ivb_in is not None) else None
    hb_tunnel_delta = (ff_hb_in - os_hb_in) if (ff_hb_in is not None and os_hb_in is not None) else None

    return {
        "as_of_date": as_of_date,
        "n_pitches_window": len(kept),
        "release_pos_x_mean": _agg_metric(rel_x),
        "release_pos_z_mean": _agg_metric(rel_z),
        "extension_mean": _agg_metric(ext),
        # Fastball archetype
        "ff_type_used": fb_type_used,
        "n_fb_window": len(fb_pitches),
        "ff_velo": ff_velo,
        "ff_spin": ff_spin,
        "ff_ivb_in": ff_ivb_in,
        "ff_hb_in": ff_hb_in,
        "ff_vaa": ff_vaa,
        # Primary offspeed
        "primary_offspeed_type": primary_os_type,
        "n_os_window": len(os_pitches),
        "offspeed_velo": os_velo,
        "offspeed_ivb_in": os_ivb_in,
        "offspeed_hb_in": os_hb_in,
        "offspeed_vaa": os_vaa,
        # Tunneling
        "velo_tunnel_delta": velo_tunnel_delta,
        "ivb_tunnel_delta_in": ivb_tunnel_delta,
        "hb_tunnel_delta_in": hb_tunnel_delta,
    }
