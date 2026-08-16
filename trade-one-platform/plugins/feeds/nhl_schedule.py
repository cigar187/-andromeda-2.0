"""NHL slate feed — public api-web.nhle.com.

Publishes `slate_snapshot` events per game. Handles 307 redirects properly.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from trade_one.event_log import get_default_log
from trade_one.interfaces import ComponentManifest, FeedAdapter

log = logging.getLogger("feed.nhl_schedule")
BASE = "https://api-web.nhle.com"
UA = "trade-one-feeds/0.1"


def _get_json(url: str, timeout: int = 30) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log.error(f"GET {url} failed: {e!r}")
        return None


class NhlScheduleFeed(FeedAdapter):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.lookahead_days = int(settings.get("lookahead_days", 3))
        self.event_log = get_default_log(settings.get("event_log_root", "/opt/trade-one/data/events"))
        self._version = "0.1.0"

    @property
    def manifest(self) -> ComponentManifest:
        return ComponentManifest(
            component_id="feed.nhl.schedule",
            version=self._version,
            contract_version="1.0",
            kind="feed_adapter",
            capabilities=("nhl", "slate"),
        )

    def poll(self) -> int:
        today = datetime.now(timezone.utc).date()
        n_emitted = 0
        for d_offset in range(self.lookahead_days + 1):
            day = today + timedelta(days=d_offset)
            url = f"{BASE}/v1/schedule/{day.isoformat()}"
            payload = _get_json(url)
            if not payload:
                continue
            for week_day in payload.get("gameWeek", []):
                gd = week_day.get("date")
                if gd != day.isoformat():
                    continue
                for game in week_day.get("games", []):
                    game_id = game.get("id")
                    if not game_id:
                        continue
                    home = game.get("homeTeam", {})
                    away = game.get("awayTeam", {})
                    venue = game.get("venue", {})
                    self.event_log.emit(
                        kind="slate_snapshot",
                        source=self.manifest.component_id,
                        payload={
                            "sport": "nhl", "league": "nhl",
                            "game_id": game_id, "game_date": gd,
                            "game_start_utc": game.get("startTimeUTC"),
                            "status": game.get("gameState"),
                            "home_team_id": home.get("id"),
                            "home_team_name": (home.get("commonName") or {}).get("default"),
                            "away_team_id": away.get("id"),
                            "away_team_name": (away.get("commonName") or {}).get("default"),
                            "venue_name": (venue or {}).get("default"),
                        },
                        component_version=f"{self.manifest.component_id}:{self._version}",
                        correlation_id=f"game:nhl:{game_id}",
                    )
                    n_emitted += 1
        return n_emitted


def nhl_schedule(settings: dict) -> NhlScheduleFeed:
    return NhlScheduleFeed(settings)
