"""Rundown props feed — pulls player-prop lines from therundown.io API and emits
one bus event per row the vendor returns. No pairing, no filtering, no skipping.

Design rules locked to project memory:
  - M1 (universal): EVERY vendor-mapping is a socket. All 5 tables + the line-value
    regex are DEFAULTS in this module and are override-mergeable from settings.
    Swapping Rundown → any other book/vendor is a config-only change.
  - Rule 4 / no-skip mandate: every row the vendor returns becomes one event on
    the bus. If a line value can't be parsed, if a market_id isn't mapped, if an
    affiliate isn't mapped — the row is still emitted with the RAW value preserved
    and a WARN log naming exactly what didn't map. NEVER dropped, NEVER guessed.
  - Rule 4 (key): API key is server-side ONLY (env var); NEVER hardcoded, NEVER
    printed or logged.
  - A3: this feed imports NO brain; NO brain imports this feed. Runs alongside M31.

Event routing:
  - Pinnacle (self.pinnacle_affiliate_id) rows → kind="prop_snapshot"          (LINE stream)
  - Every other affiliate row                 → kind="money_move_snapshot"     (MOVES stream)

Environment:
  ANDROMEDA_RUNDOWN_KEY — Rundown API key. Set on droplet only.

Settings (config/feeds.json). All override fields are dict-MERGED with defaults;
strings replace defaults:
  sports                       list[str]  — sport slugs (mlb, nfl, nba, nhl).
  market_ids                   list[int]  — Rundown market ids to pull. Default [19].
  base_url                     str        — default https://therundown.io/api/v2
  api_key_env                  str        — env var name (default ANDROMEDA_RUNDOWN_KEY)
  auth_header                  str        — default X-TheRundown-Key
  pinnacle_affiliate_id        int        — default 3
  http_timeout                 int        — default 30
  event_log_root               str        — default /opt/trade-one/data/events
  sport_id_map_override        dict       — {slug: rundown_sport_id}; merged with defaults.
  market_id_to_stat_override   dict       — {"<market_id_str>": neutral_stat}; merged (keys coerced to int).
  market_id_to_family_override dict       — {"<market_id_str>": neutral_family}; merged (keys coerced to int).
  affiliate_to_book_override   dict       — {"<affiliate_id_str>": neutral_book}; merged.
  line_value_regex             str        — regex STRING (case-insensitive). REPLACES default when set.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping

from trade_one.event_log import get_default_log
from trade_one.interfaces import ComponentManifest, FeedAdapter

log = logging.getLogger("feed.rundown_props")

# ─── DEFAULT socket tables (override in settings; see docstring) ───────────────

DEFAULT_SPORT_ID_MAP: dict[str, list[int]] = {
    "nfl": [2, 25],   # 2=NFL regular, 25=NFL preseason
    "mlb": [3, 30],   # 3=MLB regular, 30=MLB spring training
    "nba": [4, 23],   # 4=NBA regular, 23=NBA preseason
    "nhl": [6, 27],   # 6=NHL regular, 27=NHL preseason
}

DEFAULT_MARKET_ID_TO_STAT: dict[int, str] = {
    19: "strikeouts",
    47: "hits_allowed",
    967: "walks",
    973: "outs",
    1121: "earned_runs",
    1147: "walks_allowed",
    # Team-level partial-inning totals (period markets)
    766: "runs_1st",
    780: "runs_f5",
    1111: "runs_f3",
    1114: "runs_f7",
    # Standard cross-sport team markets — NFL preseason ships these
    1:   "moneyline",
    2:   "spread",
    3:   "total",
}
DEFAULT_MARKET_ID_TO_FAMILY: dict[int, str] = {
    19: "pitcher_strikeouts",
    47: "pitcher_hits_allowed",
    967: "batter_walks",
    973: "pitching_outs",
    1121: "pitcher_earned_runs",
    1147: "pitcher_walks_allowed",
    766: "team_total_runs_first_inning",
    780: "team_total_runs_first_5_innings",
    1111: "team_total_runs_first_3_innings",
    1114: "team_total_runs_first_7_innings",
    # NFL preseason ships these standard cross-sport team markets
    1:   "team_moneyline",
    2:   "team_spread",
    3:   "team_total",
}
# Period grouping — market_family → period_id (used by assembler to route cards
# into the right period pill in the RN app). Config-swappable: operators can
# add a new market and give it a period tag without any RN change.
DEFAULT_MARKET_FAMILY_TO_PERIOD: dict[str, str] = {
    "pitcher_strikeouts":               "full_game",
    "pitcher_hits_allowed":             "full_game",
    "pitcher_earned_runs":              "full_game",
    "pitcher_walks_allowed":            "full_game",
    "pitching_outs":                    "full_game",
    "batter_walks":                     "full_game",
    "team_total_runs_first_inning":     "first_inning",
    "team_total_runs_first_3_innings":  "first_3",
    "team_total_runs_first_5_innings":  "first_5",
    "team_total_runs_first_7_innings":  "first_7",
}
# Period display labels for the RN period pill strip.
DEFAULT_PERIOD_LABEL: dict[str, str] = {
    "full_game":    "FULL GAME",
    "first_inning": "1ST INN",
    "first_3":      "F3",
    "first_5":      "F5",
    "first_7":      "F7",
}
DEFAULT_AFFILIATE_TO_BOOK: dict[str, str] = {
    "2":  "bovada",
    "3":  "pinnacle",
    "6":  "betonline",
    "11": "lowvig",
    "12": "bodog",
    "16": "matchbook",
    "19": "draftkings",
    "21": "unibet",
    "22": "betmgm",
    "23": "fanduel",
    "24": "thescore",
    "25": "kalshi",
    "26": "polymarket",
    "27": "bet365",
    "28": "hardrock",
}
DEFAULT_LINE_VALUE_PATTERN: str = r"^\s*(over|under)\s+(-?\d+(?:\.\d+)?)\s*$"

# MLB team_id → mascot (fetched from Rundown /sports/3/teams on 2026-08-14 and
# baked in — teams don't change enough to warrant a runtime lookup). Overridable
# via settings.mlb_team_mascot_override for the operator (e.g. rebranding).
DEFAULT_MLB_TEAM_MASCOTS: dict[str, str] = {
    "31": "Braves",       "32": "Marlins",      "33": "Mets",
    "34": "Phillies",     "35": "Nationals",    "36": "Cubs",
    "37": "Reds",         "38": "Brewers",      "39": "Pirates",
    "40": "Cardinals",    "41": "Diamondbacks", "42": "Rockies",
    "43": "Dodgers",      "44": "Padres",       "45": "Giants",
    "46": "Orioles",      "47": "Red Sox",      "48": "Yankees",
    "49": "Rays",         "50": "Blue Jays",    "51": "White Sox",
    "52": "Guardians",    "53": "Tigers",       "54": "Royals",
    "55": "Twins",        "56": "Astros",       "57": "Angels",
    "58": "Athletics",    "59": "Mariners",     "60": "Rangers",
}
# NFL team_id → mascot (Rundown /sports/2/teams). All 32 teams.
DEFAULT_NFL_TEAM_MASCOTS: dict[str, str] = {
    "1":  "Cardinals",  "2":  "Falcons",     "3":  "Ravens",     "4":  "Bills",
    "5":  "Panthers",   "6":  "Bears",       "7":  "Bengals",    "8":  "Browns",
    "9":  "Cowboys",    "10": "Broncos",     "11": "Lions",      "12": "Packers",
    "13": "Texans",     "14": "Colts",       "15": "Jaguars",    "16": "Chiefs",
    "17": "Raiders",    "18": "Chargers",    "19": "Rams",       "20": "Dolphins",
    "21": "Vikings",    "22": "Patriots",    "23": "Saints",     "24": "Giants",
    "25": "Jets",       "26": "Eagles",      "27": "Steelers",   "28": "49ers",
    "29": "Seahawks",   "30": "Buccaneers",  "31": "Titans",     "32": "Commanders",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_int_keys(d: Mapping[Any, Any]) -> dict[int, Any]:
    """JSON dict keys are strings; coerce to int, skip any that don't parse (WARN)."""
    out: dict[int, Any] = {}
    for k, v in d.items():
        try:
            out[int(k)] = v
        except (ValueError, TypeError):
            log.warning(f"override map has non-integer key {k!r} — ignored")
    return out


class RundownPropsFeed(FeedAdapter):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.sports = [s.lower() for s in settings.get("sports", ["mlb"])]
        self.market_ids = [int(m) for m in settings.get("market_ids", [19])]
        self.base_url = settings.get("base_url", "https://therundown.io/api/v2").rstrip("/")
        self.api_key_env = settings.get("api_key_env", "ANDROMEDA_RUNDOWN_KEY")
        self.auth_header = settings.get("auth_header", "X-TheRundown-Key")
        self.pinnacle_affiliate_id = str(settings.get("pinnacle_affiliate_id", 3))
        # Affiliate-ID filter passed to Rundown as a URL param to reduce response
        # payload. Default = the 5 books the assembler actually consumes (Pinnacle
        # for the LINE stream + DK/BetMGM/HardRock/FanDuel for money moves). Cuts
        # per-call bytes by ~60% vs pulling all ~15 books. Not a skip — Rundown
        # returns fewer records because we ASKED for fewer; we emit everything
        # it returns. Set to [] to disable the filter and fetch every affiliate.
        self.affiliate_ids_filter = [
            int(a) for a in settings.get("affiliate_ids_filter", [3, 19, 22, 23, 28])
        ]
        self.http_timeout = int(settings.get("http_timeout", 30))
        self.event_log = get_default_log(
            settings.get("event_log_root", "/opt/trade-one/data/events")
        )

        # ── SOCKETS (M1): defaults + settings-merge overrides ────────────────
        def _coerce_ids(v: Any) -> list[int]:
            if isinstance(v, (list, tuple)):
                return [int(x) for x in v]
            return [int(v)]
        self.sport_id_map: dict[str, list[int]] = {
            **{k: list(v) for k, v in DEFAULT_SPORT_ID_MAP.items()},
            **{str(k).lower(): _coerce_ids(v) for k, v in settings.get("sport_id_map_override", {}).items()},
        }
        self.market_id_to_stat: dict[int, str] = {
            **DEFAULT_MARKET_ID_TO_STAT,
            **_coerce_int_keys(settings.get("market_id_to_stat_override", {})),
        }
        self.market_id_to_family: dict[int, str] = {
            **DEFAULT_MARKET_ID_TO_FAMILY,
            **_coerce_int_keys(settings.get("market_id_to_family_override", {})),
        }
        self.affiliate_to_book: dict[str, str] = {
            **DEFAULT_AFFILIATE_TO_BOOK,
            **{str(k): str(v) for k, v in settings.get("affiliate_to_book_override", {}).items()},
        }
        self.mlb_team_mascots: dict[str, str] = {
            **DEFAULT_MLB_TEAM_MASCOTS,
            **{str(k): str(v) for k, v in settings.get("mlb_team_mascot_override", {}).items()},
        }
        self.nfl_team_mascots: dict[str, str] = {
            **DEFAULT_NFL_TEAM_MASCOTS,
            **{str(k): str(v) for k, v in settings.get("nfl_team_mascot_override", {}).items()},
        }
        pattern = settings.get("line_value_regex", DEFAULT_LINE_VALUE_PATTERN)
        try:
            self.line_value_re = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            log.error(
                f"line_value_regex compile failed ({e!r}); falling back to DEFAULT_LINE_VALUE_PATTERN"
            )
            self.line_value_re = re.compile(DEFAULT_LINE_VALUE_PATTERN, re.IGNORECASE)

        self._version = "0.7.0"

    @property
    def manifest(self) -> ComponentManifest:
        return ComponentManifest(
            component_id="feed.rundown.props",
            version=self._version,
            contract_version="1.0",
            kind="feed_adapter",
            capabilities=("props", "money_moves", "multi_sport", *self.sports),
        )

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _get_key(self) -> str | None:
        key = os.environ.get(self.api_key_env)
        if not key:
            log.error(
                f"env var {self.api_key_env} not set — cannot call Rundown API. "
                f"Set it on the droplet before running this feed."
            )
            return None
        return key

    def _get_json(self, path: str, key: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        req = urllib.request.Request(url, headers={
            self.auth_header: key,
            "Accept": "application/json",
            "User-Agent": "andromeda-feed-rundown/0.4",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.http_timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            log.error(f"GET {path} → HTTP {e.code} {e.reason}")
            return None
        except urllib.error.URLError as e:
            log.error(f"GET {path} → URL error {e.reason!r}")
            return None
        except TimeoutError:
            log.error(f"GET {path} → timeout")
            return None
        except json.JSONDecodeError as e:
            log.error(f"GET {path} → non-JSON: {e!r}")
            return None

    # ── polling ──────────────────────────────────────────────────────────────

    def _fetch_events(self, sport_id: int, market_id: int, key: str) -> list[dict]:
        today = datetime.now(timezone.utc).date().isoformat()
        params: dict[str, Any] = {"market_ids": market_id}
        # Filter response to only the affiliates the assembler actually consumes.
        # Cuts token burn ~60%. Set settings.affiliate_ids_filter=[] to disable.
        if self.affiliate_ids_filter:
            params["affiliate_ids"] = ",".join(str(a) for a in self.affiliate_ids_filter)
        payload = self._get_json(
            f"/sports/{sport_id}/events/{today}", key, params=params,
        )
        if payload is None:
            return []
        return payload.get("events", []) if isinstance(payload, dict) else (payload or [])

    def _emit_for_market(self, sport_slug: str, sport_id: int, market_id: int, key: str) -> dict[str, int]:
        events = self._fetch_events(sport_id, market_id, key)
        counts = {"prop_snapshot": 0, "money_move_snapshot": 0, "raw_line_preserved": 0,
                  "raw_market_preserved": 0, "raw_affiliate_preserved": 0}
        if not events:
            log.error(f"sport={sport_slug} market_id={market_id}: 0 events")
            return counts

        # Neutral names for this market_id — raw-preserve if unmapped.
        stat_mapped = market_id in self.market_id_to_stat
        family_mapped = market_id in self.market_id_to_family
        stat = self.market_id_to_stat.get(market_id, f"raw_market_{market_id}")
        family = self.market_id_to_family.get(market_id, f"raw_market_{market_id}")
        if not stat_mapped:
            log.warning(
                f"market_id={market_id} not in market_id_to_stat map — "
                f"emitting with stat='{stat}' and raw_market_id preserved in payload. "
                f"Add via settings.market_id_to_stat_override."
            )
            counts["raw_market_preserved"] += 1
        if not family_mapped:
            log.warning(
                f"market_id={market_id} not in market_id_to_family map — "
                f"emitting with family='{family}' and raw_market_id preserved. "
                f"Add via settings.market_id_to_family_override."
            )

        for evt in events:
            event_id = str(evt.get("event_id") or evt.get("id") or "")
            if not event_id:
                continue
            event_start = evt.get("event_date") or _iso_now()
            teams_norm = evt.get("teams_normalized") or []
            home_team = next((t for t in teams_norm if t.get("is_home")), None)
            away_team = next((t for t in teams_norm if t.get("is_away")), None)
            if home_team is None and len(teams_norm) > 1:
                home_team = teams_norm[1]
            if away_team is None and teams_norm:
                away_team = teams_norm[0]
            home_id = str((home_team or {}).get("team_id") or (home_team or {}).get("id") or "")
            away_id = str((away_team or {}).get("team_id") or (away_team or {}).get("id") or "")
            home_name = str((home_team or {}).get("name") or "")
            away_name = str((away_team or {}).get("name") or "")

            pitcher_home = evt.get("pitcher_home") or {}
            pitcher_away = evt.get("pitcher_away") or {}

            for m in evt.get("markets", []) or []:
                if int(m.get("market_id") or -1) != market_id:
                    continue
                for participant in m.get("participants", []) or []:
                    player_id = str(participant.get("id") or "")
                    player_name = str(participant.get("name") or "")

                    team_id = ""
                    opponent_id = ""
                    team_name = ""
                    opponent_name = ""
                    if pitcher_home.get("id") and str(pitcher_home["id"]) == player_id:
                        team_id, opponent_id = home_id, away_id
                        team_name, opponent_name = home_name, away_name
                    elif pitcher_away.get("id") and str(pitcher_away["id"]) == player_id:
                        team_id, opponent_id = away_id, home_id
                        team_name, opponent_name = away_name, home_name

                    # Mascot lookup — sport-specific. MLB + NFL wired; others fall through.
                    if sport_slug == "mlb":
                        team_mascot = self.mlb_team_mascots.get(team_id, "")
                        opponent_mascot = self.mlb_team_mascots.get(opponent_id, "")
                    elif sport_slug == "nfl":
                        team_mascot = self.nfl_team_mascots.get(team_id, "")
                        opponent_mascot = self.nfl_team_mascots.get(opponent_id, "")
                    else:
                        team_mascot = ""
                        opponent_mascot = ""

                    # Event-level home/away mascots — always populated regardless
                    # of participant type (so team-total cards can render Phillies
                    # vs Blue Jays without needing a pitcher event for that game).
                    if sport_slug == "mlb":
                        _lookup = self.mlb_team_mascots
                    elif sport_slug == "nfl":
                        _lookup = self.nfl_team_mascots
                    else:
                        _lookup = {}
                    event_home_mascot = _lookup.get(home_id, "")
                    event_away_mascot = _lookup.get(away_id, "")

                    for line_obj in participant.get("lines", []) or []:
                        raw_value = line_obj.get("value")
                        raw_value_str = str(raw_value) if raw_value is not None else ""

                        match = self.line_value_re.match(raw_value_str) if raw_value_str else None
                        side: str | None = None
                        line_num: float | None = None
                        if match:
                            # Player-prop shape: value = "Over 4.5" / "Under 4.5"
                            side = match.group(1).lower()
                            try:
                                line_num = float(match.group(2))
                            except ValueError:
                                side, line_num = None, None
                                counts["raw_line_preserved"] += 1
                        else:
                            # Team-totals shape: value is JUST a number (e.g. "0.5", "4.5", "3")
                            # and the SIDE lives on the PARTICIPANT NAME ("Over" / "Under").
                            # Handle it inline — not a fallback, this is the second known vendor shape.
                            pname_lower = player_name.strip().lower()
                            if pname_lower in ("over", "under"):
                                try:
                                    line_num = float(raw_value_str)
                                    side = pname_lower
                                except ValueError:
                                    counts["raw_line_preserved"] += 1
                            else:
                                counts["raw_line_preserved"] += 1

                        prices = line_obj.get("prices") or {}
                        if not isinstance(prices, dict):
                            log.warning(
                                f"line prices field is {type(prices).__name__} (expected dict) — "
                                f"emitting single event with raw prices object preserved"
                            )
                            # Still emit one event so nothing is silently dropped
                            self._emit_row(
                                sport_slug=sport_slug, event_id=event_id, event_start=event_start,
                                player_id=player_id, player_name=player_name,
                                team_id=team_id, opponent_id=opponent_id, team_name=team_name, opponent_name=opponent_name, team_mascot=team_mascot, opponent_mascot=opponent_mascot, event_home_name=home_name, event_away_name=away_name, event_home_mascot=event_home_mascot, event_away_mascot=event_away_mascot, event_home_id=home_id, event_away_id=away_id,
                                market_id=market_id, stat=stat, family=family,
                                stat_mapped=stat_mapped, family_mapped=family_mapped,
                                aff_id_raw="__no_prices__", american=None, decimal=None,
                                price_delta=None, is_main=False, updated_at=_iso_now(),
                                side=side, line_num=line_num, raw_value_str=raw_value_str,
                                raw_prices=prices, counts=counts,
                            )
                            continue

                        for aff_id, price_obj in prices.items():
                            aff_id_str = str(aff_id)
                            if not isinstance(price_obj, dict):
                                log.warning(
                                    f"price_obj for aff={aff_id_str} is {type(price_obj).__name__} "
                                    f"(expected dict) — emitting with raw price preserved"
                                )
                                self._emit_row(
                                    sport_slug=sport_slug, event_id=event_id, event_start=event_start,
                                    player_id=player_id, player_name=player_name,
                                    team_id=team_id, opponent_id=opponent_id, team_name=team_name, opponent_name=opponent_name, team_mascot=team_mascot, opponent_mascot=opponent_mascot, event_home_name=home_name, event_away_name=away_name, event_home_mascot=event_home_mascot, event_away_mascot=event_away_mascot, event_home_id=home_id, event_away_id=away_id,
                                    market_id=market_id, stat=stat, family=family,
                                    stat_mapped=stat_mapped, family_mapped=family_mapped,
                                    aff_id_raw=aff_id_str, american=None, decimal=None,
                                    price_delta=None, is_main=False, updated_at=_iso_now(),
                                    side=side, line_num=line_num, raw_value_str=raw_value_str,
                                    raw_price_obj=price_obj, counts=counts,
                                )
                                continue

                            american = price_obj.get("price")
                            decimal_odds = _american_to_decimal(american) if american is not None else None
                            price_delta = price_obj.get("price_delta")
                            is_main = bool(price_obj.get("is_main_line"))
                            updated_at = price_obj.get("updated_at") or _iso_now()

                            self._emit_row(
                                sport_slug=sport_slug, event_id=event_id, event_start=event_start,
                                player_id=player_id, player_name=player_name,
                                team_id=team_id, opponent_id=opponent_id, team_name=team_name, opponent_name=opponent_name, team_mascot=team_mascot, opponent_mascot=opponent_mascot, event_home_name=home_name, event_away_name=away_name, event_home_mascot=event_home_mascot, event_away_mascot=event_away_mascot, event_home_id=home_id, event_away_id=away_id,
                                market_id=market_id, stat=stat, family=family,
                                stat_mapped=stat_mapped, family_mapped=family_mapped,
                                aff_id_raw=aff_id_str, american=american, decimal=decimal_odds,
                                price_delta=price_delta, is_main=is_main, updated_at=updated_at,
                                side=side, line_num=line_num, raw_value_str=raw_value_str,
                                counts=counts,
                            )
        return counts

    def _emit_row(self, *, sport_slug: str, event_id: str, event_start: str,
                  player_id: str, player_name: str, team_id: str, opponent_id: str,
                  team_name: str, opponent_name: str,
                  team_mascot: str, opponent_mascot: str,
                  event_home_name: str = "", event_away_name: str = "",
                  event_home_mascot: str = "", event_away_mascot: str = "",
                  event_home_id: str = "", event_away_id: str = "",
                  market_id: int, stat: str, family: str,
                  stat_mapped: bool, family_mapped: bool,
                  aff_id_raw: str, american: Any, decimal: float | None,
                  price_delta: Any, is_main: bool, updated_at: str,
                  side: str | None, line_num: float | None, raw_value_str: str,
                  counts: dict[str, int],
                  raw_prices: Any = None, raw_price_obj: Any = None) -> None:
        """Emit ONE bus event for ONE (event × participant × line × side × affiliate) row.
        Never skips. Raw-preserves anything that didn't parse or didn't map."""
        # Neutral book name; raw-preserve if unmapped
        book_mapped = aff_id_raw in self.affiliate_to_book
        sportsbook = self.affiliate_to_book.get(aff_id_raw, aff_id_raw)
        if not book_mapped and aff_id_raw not in ("__no_prices__",):
            log.warning(
                f"affiliate_id={aff_id_raw} not in affiliate_to_book map — "
                f"sportsbook field kept as raw '{sportsbook}'. "
                f"Add via settings.affiliate_to_book_override."
            )
            counts["raw_affiliate_preserved"] += 1

        is_pinnacle = aff_id_raw == self.pinnacle_affiliate_id
        kind = "prop_snapshot" if is_pinnacle else "money_move_snapshot"

        # stable_prop_id uses NEUTRAL fields — vendor-neutral per M1
        stable_prop_id = (
            f"{sport_slug}:{event_id}:{stat}:{player_id}:"
            f"{line_num if line_num is not None else 'RAW:' + raw_value_str}"
        )
        side_tag = side if side is not None else f"raw:{raw_value_str}"
        side_id = f"{stable_prop_id}:{side_tag}"
        now = _iso_now()

        market_block: dict[str, Any] = {
            "market_id": side_id,
            "sportsbook": sportsbook,
            "affiliate_id": aff_id_raw,
            "market_family": family,
            "period": "full_game",
            "side": side,
            "line": line_num,
            "american_odds": american,
            "decimal_odds": decimal,
            "price_delta_american": price_delta,
            "is_main_line": is_main,
            "first_seen_at": updated_at,
            "observed_at": now,
            "status": "open",
            "settlement_rule_version": f"{sport_slug}-2026-v1",
            "prop_id": stable_prop_id,
        }
        # Raw-preserve fields: only present when something didn't map / didn't parse
        if side is None or line_num is None:
            market_block["raw_line_value"] = raw_value_str
        if not book_mapped:
            market_block["raw_affiliate_id"] = aff_id_raw
        if not stat_mapped or not family_mapped:
            market_block["raw_market_id"] = market_id
        if raw_prices is not None:
            market_block["raw_prices_field"] = raw_prices
        if raw_price_obj is not None:
            market_block["raw_price_obj"] = raw_price_obj

        payload = {
            "sport": sport_slug,
            "league": sport_slug,
            "market_family": family,
            "market_stat": stat,
            "period": "full_game",
            "event_id": event_id,
            "participant_id": player_id,
            "participant_name": player_name,
            "team_id": team_id,
            "opponent_id": opponent_id,
            "team_name": team_name,
            "opponent_name": opponent_name,
            "team_mascot": team_mascot,
            "opponent_mascot": opponent_mascot,
            # Event-level (game-wide) team info — always populated regardless of
            # whether this row is a pitcher prop or a team-total prop. Lets team-total
            # cards render "Phillies vs Blue Jays" without needing a pitcher event.
            "event_home_id": event_home_id,
            "event_away_id": event_away_id,
            "event_home_name": event_home_name,
            "event_away_name": event_away_name,
            "event_home_mascot": event_home_mascot,
            "event_away_mascot": event_away_mascot,
            "as_of": now,
            "event_start": event_start,
            "prop_id": stable_prop_id,
            "market": market_block,
        }

        self.event_log.emit(
            kind=kind,
            source=self.manifest.component_id,
            payload=payload,
            component_version=f"{self.manifest.component_id}:{self._version}",
            correlation_id=f"{kind}:{sport_slug}:{event_id}:{stat}:{player_id}:{line_num}:{side_tag}:{aff_id_raw}",
        )
        counts[kind] += 1

    def poll(self) -> int:
        key = self._get_key()
        if not key:
            return 0
        total = 0
        for sport in self.sports:
            sport_ids = self.sport_id_map.get(sport)
            if not sport_ids:
                log.error(
                    f"sport slug '{sport}' not in sport_id_map — "
                    f"cannot fetch. Add via settings.sport_id_map_override."
                )
                continue
            for sport_id in sport_ids:
                for market_id in self.market_ids:
                    c = self._emit_for_market(sport, sport_id, market_id, key)
                    log.info(
                        f"sport={sport} sport_id={sport_id} market_id={market_id}: "
                        f"prop_snapshot={c['prop_snapshot']} money_move_snapshot={c['money_move_snapshot']} "
                        f"raw_line_preserved={c['raw_line_preserved']} "
                        f"raw_market_preserved={c['raw_market_preserved']} "
                        f"raw_affiliate_preserved={c['raw_affiliate_preserved']}"
                    )
                    total += c["prop_snapshot"] + c["money_move_snapshot"]
        return total


def _american_to_decimal(price: Any) -> float | None:
    try:
        p = int(price)
    except (ValueError, TypeError):
        try:
            f = float(price)
            return f if f > 1.0 else None
        except (ValueError, TypeError):
            return None
    if p > 0:
        return 1.0 + p / 100.0
    if p < 0:
        return 1.0 + 100.0 / abs(p)
    return None


def rundown_props(settings: dict) -> RundownPropsFeed:
    return RundownPropsFeed(settings)
