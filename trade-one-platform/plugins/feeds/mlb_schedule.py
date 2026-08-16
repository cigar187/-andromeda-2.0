"""MLB slate + probable pitchers feed — public statsapi.mlb.com.

Publishes `slate_snapshot` events per game. Publishes `prop_snapshot` STUB-FREE:
this feed does NOT invent prop lines; a separate props-source feed publishes those.

Rule 4: on any HTTP error the game is skipped and logged; no fabricated data.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from trade_one.event_log import get_default_log
from trade_one.interfaces import ComponentManifest, FeedAdapter

log = logging.getLogger("feed.mlb_schedule")

BASE = "https://statsapi.mlb.com/api/v1"
UA = "trade-one-feeds/0.1"


def _get_json(url: str, timeout: int = 30) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log.error(f"GET {url} failed: {e!r}")
        return None


class MlbScheduleFeed(FeedAdapter):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.lookahead_days = int(settings.get("lookahead_days", 3))
        self.event_log = get_default_log(settings.get("event_log_root", "/opt/trade-one/data/events"))
        self._version = "0.1.0"

    @property
    def manifest(self) -> ComponentManifest:
        return ComponentManifest(
            component_id="feed.mlb.schedule",
            version=self._version,
            contract_version="1.0",
            kind="feed_adapter",
            capabilities=("mlb", "slate", "probable_pitchers"),
        )

    def poll(self) -> int:
        today = datetime.now(timezone.utc).date()
        # statsapi from droplet ONLY accepts simple `?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher`
        # (no parameter args, no commas, no compound paths — else 406). Iterate per-day.
        all_buckets = []
        for d_offset in range(self.lookahead_days + 1):
            day = today + timedelta(days=d_offset)
            url = f"{BASE}/schedule?sportId=1&date={day.isoformat()}&hydrate=probablePitcher"
            payload = _get_json(url)
            if not payload:
                continue
            all_buckets.extend(payload.get("dates", []))

        if not all_buckets:
            log.error("schedule fetch returned nothing across all dates")
            return 0

        n_emitted = 0
        for date_bucket in all_buckets:
            game_date = date_bucket.get("date")
            for game in date_bucket.get("games", []):
                game_pk = game.get("gamePk")
                if not game_pk:
                    continue
                teams = game.get("teams", {})
                home = teams.get("home", {})
                away = teams.get("away", {})
                venue = game.get("venue", {})
                self.event_log.emit(
                    kind="slate_snapshot",
                    source=self.manifest.component_id,
                    payload={
                        "sport": "mlb", "league": "mlb", "sport_id": 1,
                        "game_pk": game_pk, "game_date": game_date,
                        "game_start_utc": game.get("gameDate"),
                        "status": (game.get("status") or {}).get("abstractGameState"),
                        "home_team_id": (home.get("team") or {}).get("id"),
                        "home_team_name": (home.get("team") or {}).get("name"),
                        "away_team_id": (away.get("team") or {}).get("id"),
                        "away_team_name": (away.get("team") or {}).get("name"),
                        "venue_id": venue.get("id"),
                        "venue_name": venue.get("name"),
                        "home_probable_pitcher_id": ((home.get("probablePitcher") or {}).get("id")),
                        "home_probable_pitcher_name": ((home.get("probablePitcher") or {}).get("fullName")),
                        "away_probable_pitcher_id": ((away.get("probablePitcher") or {}).get("id")),
                        "away_probable_pitcher_name": ((away.get("probablePitcher") or {}).get("fullName")),
                    },
                    component_version=f"{self.manifest.component_id}:{self._version}",
                    correlation_id=f"game:mlb:{game_pk}",
                )
                n_emitted += 1
        return n_emitted


def mlb_schedule(settings: dict) -> MlbScheduleFeed:
    return MlbScheduleFeed(settings)
