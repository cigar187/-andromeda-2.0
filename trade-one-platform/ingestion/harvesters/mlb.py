"""MLB harvester for the M31 training store.

Public source: statsapi.mlb.com (official MLB Advanced Media endpoint).
No API key required. Rate-limited politely at ~3 req/sec with retry/backoff.
Writes idempotent per-game raw JSON + append-only canonical JSONL.
Missing field on a record -> null in the row + line in the missing-field log,
never fabricated.

Grain: game-line. One row per pitcher-appearance per game, one row per batter
who came to the plate. NOT pitch-by-pitch.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"
SPORT_MLB = 1
REGULAR_AND_PLAYOFF_GAME_TYPES = {"R", "F", "D", "L", "W"}
FINAL_STATUSES = {"Final", "Completed Early", "Game Over"}
USER_AGENT = "trade-one-mlb-harvester/0.1"
DEFAULT_SLEEP_SECONDS = 0.35

log = logging.getLogger("mlb_harvester")


def _get(url: str, sleep_after: float = DEFAULT_SLEEP_SECONDS, retries: int = 8) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            time.sleep(sleep_after)
            return data
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                back = min(60.0, 2.0 ** attempt)
                log.warning("HTTP %s on %s, retry %d in %.1fs", error.code, url, attempt + 1, back)
                time.sleep(back)
                continue
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionResetError) as error:
            # Transient network-layer failures — retry with exponential backoff.
            if attempt < retries - 1:
                back = min(60.0, 2.0 ** attempt)
                log.warning("network error on %s (%s), retry %d in %.1fs", url, error, attempt + 1, back)
                time.sleep(back)
                continue
            raise
    raise RuntimeError(f"retries exhausted for {url}")


def fetch_schedule(season: int) -> list[dict]:
    start, end = f"{season}-02-01", f"{season}-12-01"
    params = urllib.parse.urlencode({"sportId": SPORT_MLB, "startDate": start, "endDate": end})
    payload = _get(f"{STATSAPI_BASE}/schedule?{params}")
    out: list[dict] = []
    for date_block in payload.get("dates", []):
        for game in date_block.get("games", []):
            if game.get("gameType") in REGULAR_AND_PLAYOFF_GAME_TYPES:
                out.append(game)
    return out


def fetch_boxscore(gamePk: int) -> dict:
    return _get(f"{STATSAPI_BASE}/game/{gamePk}/boxscore")


def _record_missing(missing_log_path: Path, kind: str, ident: str, field: str) -> None:
    missing_log_path.parent.mkdir(parents=True, exist_ok=True)
    with missing_log_path.open("a") as stream:
        stream.write(
            json.dumps(
                {"kind": kind, "ident": ident, "field": field,
                 "at": datetime.now(timezone.utc).isoformat()}
            )
            + "\n"
        )


def _team_meta(boxscore: dict, side: str) -> dict:
    team_block = boxscore.get("teams", {}).get(side, {}) or {}
    team = team_block.get("team", {}) or {}
    return {
        "side_block": team_block,
        "team_id": team.get("id"),
        "team_abbr": team.get("abbreviation"),
        "team_name": team.get("name"),
    }


def normalize_pitcher_lines(
    boxscore: dict, game_meta: dict, missing_log_path: Path
) -> Iterator[dict]:
    gamePk = game_meta["gamePk"]
    game_date = game_meta.get("officialDate") or game_meta.get("gameDate")
    season = game_meta.get("season")
    for side in ("home", "away"):
        meta = _team_meta(boxscore, side)
        opp_meta = _team_meta(boxscore, "away" if side == "home" else "home")
        team_block = meta["side_block"]
        pitcher_ids = team_block.get("pitchers", []) or []
        for order, pid in enumerate(pitcher_ids):
            player = team_block.get("players", {}).get(f"ID{pid}", {}) or {}
            pitching = (player.get("stats", {}) or {}).get("pitching", {}) or {}
            person = player.get("person", {}) or {}
            row = {
                "source": "statsapi.mlb.com",
                "gamePk": gamePk,
                "game_date": game_date,
                "season": season,
                "home_away": side,
                "team_id": meta["team_id"],
                "team_abbr": meta["team_abbr"],
                "opponent_id": opp_meta["team_id"],
                "opponent_abbr": opp_meta["team_abbr"],
                "pitcher_id": person.get("id"),
                "pitcher_name": person.get("fullName"),
                "pitch_hand": (person.get("pitchHand") or {}).get("code"),
                "position": (player.get("position") or {}).get("abbreviation"),
                "appearance_order": order,
                "is_starter": order == 0,
                # counts: null (not zero) if missing
                "strikeOuts": pitching.get("strikeOuts"),
                "battersFaced": pitching.get("battersFaced"),
                "inningsPitched": pitching.get("inningsPitched"),
                "outs": pitching.get("outs"),
                "hits": pitching.get("hits"),
                "earnedRuns": pitching.get("earnedRuns"),
                "runs": pitching.get("runs"),
                "walks": pitching.get("baseOnBalls"),
                "intentionalWalks": pitching.get("intentionalWalks"),
                "hitBatsmen": pitching.get("hitBatsmen"),
                "homeRuns": pitching.get("homeRuns"),
                "pitches": pitching.get("numberOfPitches"),
                "strikes": pitching.get("strikes"),
                "wildPitches": pitching.get("wildPitches"),
                "balks": pitching.get("balks"),
                "harvested_at": datetime.now(timezone.utc).isoformat(),
            }
            for identity in ("pitcher_id", "team_id", "opponent_id"):
                if row[identity] is None:
                    _record_missing(missing_log_path, "pitcher_line", str(gamePk), identity)
            yield row


def normalize_batter_lines(
    boxscore: dict, game_meta: dict, missing_log_path: Path
) -> Iterator[dict]:
    gamePk = game_meta["gamePk"]
    game_date = game_meta.get("officialDate") or game_meta.get("gameDate")
    season = game_meta.get("season")
    for side in ("home", "away"):
        meta = _team_meta(boxscore, side)
        opp_meta = _team_meta(boxscore, "away" if side == "home" else "home")
        team_block = meta["side_block"]
        batter_ids = team_block.get("batters", []) or []
        for order, bid in enumerate(batter_ids):
            player = team_block.get("players", {}).get(f"ID{bid}", {}) or {}
            batting = (player.get("stats", {}) or {}).get("batting", {}) or {}
            person = player.get("person", {}) or {}
            plate_appearances = batting.get("plateAppearances")
            if not plate_appearances:
                # batter did not come to the plate; skip
                continue
            row = {
                "source": "statsapi.mlb.com",
                "gamePk": gamePk,
                "game_date": game_date,
                "season": season,
                "home_away": side,
                "team_id": meta["team_id"],
                "team_abbr": meta["team_abbr"],
                "opponent_id": opp_meta["team_id"],
                "opponent_abbr": opp_meta["team_abbr"],
                "batter_id": person.get("id"),
                "batter_name": person.get("fullName"),
                "bat_side": (person.get("batSide") or {}).get("code"),
                "position": (player.get("position") or {}).get("abbreviation"),
                "batting_order": order,
                "plateAppearances": plate_appearances,
                "atBats": batting.get("atBats"),
                "hits": batting.get("hits"),
                "doubles": batting.get("doubles"),
                "triples": batting.get("triples"),
                "homeRuns": batting.get("homeRuns"),
                "walks": batting.get("baseOnBalls"),
                "intentionalWalks": batting.get("intentionalWalks"),
                "strikeOuts": batting.get("strikeOuts"),
                "hitByPitch": batting.get("hitByPitch"),
                "sacFlies": batting.get("sacFlies"),
                "sacBunts": batting.get("sacBunts"),
                "rbi": batting.get("rbi"),
                "leftOnBase": batting.get("leftOnBase"),
                "harvested_at": datetime.now(timezone.utc).isoformat(),
            }
            for identity in ("batter_id", "team_id", "opponent_id"):
                if row[identity] is None:
                    _record_missing(missing_log_path, "batter_line", str(gamePk), identity)
            yield row


def _boxscore_path(out_dir: Path, season: int, gamePk: int) -> Path:
    return out_dir / "raw" / "boxscores" / str(season) / f"{gamePk}.json"


def _write_schedule(out_dir: Path, season: int, games: list[dict]) -> Path:
    dst = out_dir / "raw" / "schedules" / f"{season}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        json.dumps(
            {
                "season": season,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "statsapi.mlb.com",
                "count": len(games),
                "games": games,
            }
        )
    )
    return dst


def harvest_season(out_dir: Path, season: int, max_games: int | None = None) -> dict:
    logger = logging.getLogger("mlb_harvester")
    logger.info("harvest_season %s starting", season)
    missing_log_path = out_dir / "logs" / f"missing_{season}.jsonl"
    manifest_path = out_dir / "manifest.json"

    games = fetch_schedule(season)
    _write_schedule(out_dir, season, games)
    logger.info("season %s schedule: %d total games", season, len(games))

    finals = [g for g in games if g.get("status", {}).get("detailedState") in FINAL_STATUSES]
    logger.info("season %s finals: %d", season, len(finals))
    if max_games is not None:
        finals = finals[:max_games]
        logger.info("season %s CAPPED to %d games (test mode)", season, len(finals))

    pitcher_out = out_dir / "canonical" / f"pitcher_lines_{season}.jsonl"
    batter_out = out_dir / "canonical" / f"batter_lines_{season}.jsonl"
    pitcher_out.parent.mkdir(parents=True, exist_ok=True)
    pitcher_out.write_text("")
    batter_out.write_text("")

    fetched = cached = 0
    pitcher_rows = batter_rows = 0
    for i, game in enumerate(finals, 1):
        gamePk = game["gamePk"]
        boxscore_path = _boxscore_path(out_dir, season, gamePk)
        if boxscore_path.exists():
            boxscore = json.loads(boxscore_path.read_text())
            cached += 1
        else:
            boxscore = fetch_boxscore(gamePk)
            boxscore_path.parent.mkdir(parents=True, exist_ok=True)
            boxscore_path.write_text(json.dumps(boxscore))
            fetched += 1

        with pitcher_out.open("a") as pfh:
            for row in normalize_pitcher_lines(boxscore, game, missing_log_path):
                pfh.write(json.dumps(row) + "\n")
                pitcher_rows += 1
        with batter_out.open("a") as bfh:
            for row in normalize_batter_lines(boxscore, game, missing_log_path):
                bfh.write(json.dumps(row) + "\n")
                batter_rows += 1

        if i % 100 == 0 or i == len(finals):
            logger.info(
                "season %s progress: %d/%d (fetched=%d cached=%d rows P=%d B=%d)",
                season, i, len(finals), fetched, cached, pitcher_rows, batter_rows,
            )

    result = {
        "season": season,
        "games_scheduled": len(games),
        "games_final": len(finals),
        "boxscores_fetched": fetched,
        "boxscores_cached": cached,
        "pitcher_rows": pitcher_rows,
        "batter_rows": batter_rows,
        "pitcher_lines_path": str(pitcher_out),
        "batter_lines_path": str(batter_out),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"source": "statsapi.mlb.com", "seasons": {}}
    )
    manifest["seasons"][str(season)] = result
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("harvest_season %s complete: %s", season, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="mlb_harvester")
    parser.add_argument("--out", required=True, help="output directory for the training store")
    parser.add_argument("--seasons", required=True, help="comma-separated seasons e.g. 2022,2023,2024,2025")
    parser.add_argument("--max-games", type=int, default=None, help="cap games per season (test mode)")
    parser.add_argument("--log-file", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    for season in [int(s) for s in args.seasons.split(",")]:
        harvest_season(out_dir, season, max_games=args.max_games)


if __name__ == "__main__":
    main()
