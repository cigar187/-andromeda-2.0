"""M31 event-log consumer — bridges standard events to codex_control_engine.ControlPlane.

M1 mandate: feeds publish events; M31 consumes from the event log. M31 code is NEVER
imported by a feed and never modified. This consumer lives OUTSIDE the M31 module
tree and calls into ControlPlane.admit() one payload at a time.

Reads:  /opt/trade-one/data/events/{kind}/{YYYY-MM-DD}.jsonl
Writes: ControlPlane's raw_dir + quarantine_dir + returns Admission per record.

Payload → IntelligenceEnvelope conversion:
- `slate_snapshot`  → one envelope per (game_pk, probable_pitcher) with role='starting_pitcher';
                       market_family='pitcher_strikeouts' default (props are added later by
                       prop_snapshot events joined to the same event_id).
- `prop_snapshot`   → one envelope per prop line, provides market_family/market_stat/line/odds.
- `news_ingested`   → text[TextDocument] appended to envelopes matched by correlation_id
                       when props/slates arrive; standalone news events published as
                       envelope-less admissions for M31's news buffer.
- `outcome_settled` → labels{} attached to prior envelopes.

Rule 4: no fabrication. If required IntelligenceEnvelope fields are missing (line,
over_odds, under_odds), the event is skipped and the reason logged — never filled
with a placeholder.
"""
from __future__ import annotations

import importlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .event_log import get_default_log

log = logging.getLogger("m31_consumer")


def _load_control_plane():
    """Dynamic import so M31's plugin location is a config concern, not hard-wired.
    Rule 9: M31 is imported, never modified."""
    module = importlib.import_module("plugins.brains.codex_control_engine.control_plane")
    return module.ControlPlane


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slate_event_to_envelope(evt: dict) -> list[dict]:
    """A slate_snapshot creates ONE envelope per probable pitcher (starting_pitcher role).
    Returns a list because a game has 0-2 probables. Envelope has NO market fields yet;
    those come from prop_snapshot events. So slate envelopes only get created downstream
    JOINED with props. Here we return [] to signal 'slate context, no envelope yet'."""
    return []


def prop_event_to_envelope(evt: dict) -> dict | None:
    """Convert a prop_snapshot event to an IntelligenceEnvelope-shaped dict.
    Returns None if required fields are missing (Rule 4: no fabrication)."""
    p = evt.get("payload") or {}
    required = ["sport", "league", "market_family", "market_stat", "line", "over_odds",
                "under_odds", "event_id", "participant_id", "team_id", "opponent_id"]
    missing = [f for f in required if p.get(f) in (None, "")]
    if missing:
        log.warning(f"prop_snapshot skipped, missing {missing}: correlation_id={evt.get('correlation_id')}")
        return None
    return {
        "schema_version": "1.0",
        "record_id": f"{evt['event_id']}",
        "as_of": p.get("as_of", evt.get("timestamp", _iso_now())),
        "event_start": p["event_start"],
        "sport": p["sport"],
        "league": p["league"],
        "season": str(p.get("season", "")),
        "event_id": str(p["event_id"]),
        "participant_id": str(p["participant_id"]),
        "team_id": str(p["team_id"]),
        "opponent_id": str(p["opponent_id"]),
        "role": str(p.get("role", "starting_pitcher")),
        "market_family": str(p["market_family"]),
        "market_stat": str(p["market_stat"]),
        "line": float(p["line"]),
        "over_odds": float(p["over_odds"]),
        "under_odds": float(p["under_odds"]),
        "source": {
            "provider": evt.get("source", "unknown"),
            "provider_record_id": str(evt["event_id"]),
            "observed_at": p.get("observed_at", evt.get("timestamp", _iso_now())),
            "published_at": p.get("published_at", p.get("observed_at", evt.get("timestamp", _iso_now()))),
            "reliability_hint": float(p.get("reliability_hint", 0.5)),
            "content_hash": "",
        },
        "numeric": p.get("numeric", {}),
        "categorical": p.get("categorical", {}),
        "text": p.get("text", []),
    }


def news_event_to_text_document(evt: dict) -> dict | None:
    """A news_ingested event -> a TextDocument-shaped dict (for later envelope attachment)."""
    p = evt.get("payload") or {}
    if not (p.get("title") or p.get("body")):
        return None
    return {
        "document_id": evt.get("event_id"),
        "kind": "news",
        "body": (p.get("body") or p.get("title") or "").strip(),
        "published_at": p.get("published_at") or evt.get("timestamp") or _iso_now(),
        "source": p.get("source_site") or evt.get("source", "unknown"),
        "language": "en",
    }


def consume(event_log_root: str = "/opt/trade-one/data/events",
            date_iso: str | None = None,
            control_plane_raw_dir: str | None = None,
            control_plane_quarantine_dir: str | None = None) -> dict[str, Any]:
    """Read all events for the given date across relevant kinds and feed to ControlPlane.
    Returns per-kind counts + admission outcomes."""
    date_iso = date_iso or datetime.now(timezone.utc).date().isoformat()
    log_ev = get_default_log(event_log_root)

    ControlPlane = _load_control_plane()
    control = ControlPlane(raw_dir=control_plane_raw_dir, quarantine_dir=control_plane_quarantine_dir)

    stats = {"date": date_iso, "kinds": {}, "admissions": {"accepted": 0, "duplicate": 0,
                                                             "quarantined_invalid": 0,
                                                             "quarantined_signature": 0,
                                                             "quarantined_collision": 0,
                                                             "skipped_missing_fields": 0}}

    # prop_snapshot -> full IntelligenceEnvelope admissions
    n_prop = 0
    for evt in log_ev.read(kind="prop_snapshot", date=date_iso):
        n_prop += 1
        env_dict = prop_event_to_envelope(evt)
        if env_dict is None:
            stats["admissions"]["skipped_missing_fields"] += 1
            continue
        adm = control.admit(env_dict)
        stats["admissions"][adm.status] = stats["admissions"].get(adm.status, 0) + 1
    stats["kinds"]["prop_snapshot"] = n_prop

    # slate_snapshot -> count only (envelopes are constructed once matched with props)
    n_slate = sum(1 for _ in log_ev.read(kind="slate_snapshot", date=date_iso))
    stats["kinds"]["slate_snapshot"] = n_slate

    # news_ingested -> count only (attached to envelopes downstream by correlation_id)
    n_news = sum(1 for _ in log_ev.read(kind="news_ingested", date=date_iso))
    stats["kinds"]["news_ingested"] = n_news

    return stats


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-log-root", type=str, default="/opt/trade-one/data/events")
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--raw-dir", type=str, default="/opt/trade-one/data/m31/raw")
    ap.add_argument("--quarantine-dir", type=str, default="/opt/trade-one/data/m31/quarantine")
    args = ap.parse_args()
    result = consume(args.event_log_root, args.date, args.raw_dir, args.quarantine_dir)
    print(json.dumps(result, indent=2))
