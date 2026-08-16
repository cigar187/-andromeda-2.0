"""V5B live store loader for the Andromeda card assembler.

Builds the {profiles, history, name_index} dict that V5B (sbc_engine_v5.py) needs:

  profiles[mlbam_id]       -> dict with csw_pct / whiff_pct / ip_baseline /
                              k_baseline_30 / leash_avg_ip (fields V5B reads)
  history[mlbam_id]        -> list[dict(game_date, k, ip, pitch_count)] sorted
                              desc by game_date (V5B calls _recent() on this)
  name_index[lower_name]   -> mlbam_id (join key for Rundown participant_name)

Sources (droplet paths, override via env vars):
  V5B_PROFILES_CSV  /opt/trade-one/data/clean/pitcher_profiles.csv     (220 rows)
  V5B_FEATURES_CSV  /opt/trade-one/v5c_build/data/features_v5c_2026.csv (2449 rows)

Rundown props carry participant_id as a Rundown-internal id (4-digit like 1729),
NOT MLBAM (6-digit like 666129). The name_index provides the join. Callers do:

    mlbam = resolve_pitcher(participant_name)
    if mlbam is None:
        log.error("v5b_store: no MLBAM match for name=%r — dropping card (Rule-4)")
        continue
    result = v5b_result_for_pitcher_night(get_store(), mlbam, game_date, line)
    if result is None:
        log.error("v5b: abstained for %s on %s — dropping card (Rule-4)")
        continue
    k_projected = result["k_projected"]
    grade = result["grade"]

Rule-4: never fabricates values. Missing profile / missing history / abstention
all return None; the caller decides (log ERROR + drop card, per project policy).
No stdlib-only deps — safe to import from server.py without extra sys.path setup.
"""
from __future__ import annotations

import csv
import logging
import os
import threading
from typing import Any

log = logging.getLogger("v5b_store")

PROFILES_CSV = os.environ.get(
    "V5B_PROFILES_CSV",
    "/opt/trade-one/data/clean/pitcher_profiles.csv",
)
FEATURES_CSV = os.environ.get(
    "V5B_FEATURES_CSV",
    "/opt/trade-one/v5c_build/data/features_v5c_2026.csv",
)

_lock = threading.Lock()
_store: dict[str, Any] | None = None


def _to_float(x: Any) -> float | None:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (ValueError, TypeError):
        return None
    return v


def _to_int(x: Any) -> int | None:
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return None


def _normalize_name(s: Any) -> str:
    return (s or "").strip().lower()


def _build_store() -> dict[str, Any]:
    """One-shot loader. Reads both CSVs into memory.

    Rule-4: fields that are literally missing/empty in the CSV land as None in the
    store — never substituted with a mean, default, or fabricated value. V5B's own
    silent defaults (put_whiff->0.24, ip_baseline->5.0) are blocked upstream by the
    wrapper's _validate_v5b_inputs guard.
    """
    profiles: dict[str, dict[str, Any]] = {}
    name_index: dict[str, str] = {}
    with open(PROFILES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mlbam = (row.get("pitcher_id") or "").strip()
            if not mlbam:
                continue
            nm = _normalize_name(row.get("pitcher_name"))
            if nm:
                name_index[nm] = mlbam
            profiles[mlbam] = {
                "pitcher_name": row.get("pitcher_name"),
                "csw_pct": _to_float(row.get("csw_pct")),
                "whiff_pct": _to_float(row.get("whiff_pct")),
                "put_whiff": _to_float(row.get("whiff_pct")),  # V5B reads put_whiff; use whiff_pct as its source
                "ip_baseline": _to_float(row.get("ip_baseline")),
                "k_baseline_30": _to_float(row.get("k_baseline_30")),
                "leash_avg_ip": _to_float(row.get("leash_avg_ip")),
            }

    # V5B expects history entries as tuples (game_date, k, ip, pitch_count) —
    # see sbc_engine_v5.py:200 (_recent) and :219-221 (unpacking). Any other shape
    # causes silent unpack-failure and V5B abstains as if history were empty.
    history: dict[str, list[tuple]] = {}
    with open(FEATURES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mlbam = (row.get("pitcher_id") or "").strip()
            if not mlbam:
                continue
            gd = row.get("game_date")
            k = _to_int(row.get("actual_ks"))
            ip = _to_float(row.get("actual_ip"))
            pc = _to_int(row.get("actual_pitch_count"))
            # Rule-4: only include starts with all four fields populated. Rows
            # missing any of them are dropped rather than substituted.
            if gd is None or k is None or ip is None or pc is None:
                continue
            history.setdefault(mlbam, []).append((gd, k, ip, pc))
    for mlbam in history:
        history[mlbam].sort(key=lambda r: r[0], reverse=True)

    log.info(
        "v5b_store loaded: %d profiles, %d pitchers with history, %d names indexed",
        len(profiles), len(history), len(name_index),
    )
    return {"profiles": profiles, "history": history, "name_index": name_index}


def get_store() -> dict[str, Any]:
    """Thread-safe singleton accessor. Builds on first call."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = _build_store()
    return _store


def resolve_pitcher(participant_name: Any) -> str | None:
    """Map a Rundown participant_name to MLBAM pitcher_id (str) via name lookup.
    Returns None if no match — caller must log ERROR and drop the card (Rule-4).
    """
    s = get_store()
    return s["name_index"].get(_normalize_name(participant_name))


def reload_store() -> dict[str, Any]:
    """Force a rebuild (e.g. after a data refresh). Returns the new store."""
    global _store
    with _lock:
        _store = _build_store()
    return _store
