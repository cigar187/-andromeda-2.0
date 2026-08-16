"""Andromeda API — reads today's event log (Pinnacle prop_snapshot + retail money_move_snapshot)
and serves the Andromeda card list expected by the RN AndromedaScreen.

Runs standalone (no container). Binds 127.0.0.1:8787 on droplet. Reach from Mac via
`ssh -L 8787:localhost:8787 root@138.197.27.37`, iOS simulator fetches http://localhost:8787/api/andromeda/today.

Design rules honored:
  - Rule 4 / no-skip: emits one card per Pinnacle-quoted (event, pitcher, line=main). Fields we
    don't have live (team names, real projection, sim floor/median/ceiling, NEWS stream, drivers
    from real engines) are set to honest placeholders — never fabricated engines running.
  - M1: card shape is the standard AndromedaScreen contract — swap engines behind this assembler,
    the app doesn't change.
  - A3: reads event log only. Imports no brain, no formula engine (pass-1 uses pure Pinnacle math).
"""
from __future__ import annotations

import hmac
import http.server
import json
import logging
import os
import socketserver
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVENT_LOG_ROOT = Path("/opt/trade-one/data/events")
LOG = logging.getLogger("andromeda_api")

MONEY_MOVE_BOOKS = {"draftkings", "betmgm", "hardrock", "fanduel"}
PINNACLE_BOOK = "pinnacle"

# Market-family → period_id mapping. Config-driven so future markets add
# without an RN change. New family added? Add one line here + a period label
# below. RN reads periods from the /api response.
FAMILY_TO_PERIOD = {
    "pitcher_strikeouts":              "full_game",
    "pitcher_hits_allowed":            "full_game",
    "pitcher_earned_runs":             "full_game",
    "pitcher_walks_allowed":           "full_game",
    "pitching_outs":                   "full_game",
    "batter_walks":                    "full_game",
    "team_total_runs_first_inning":    "first_inning",
    "team_total_runs_first_3_innings": "first_3",
    "team_total_runs_first_5_innings": "first_5",
    "team_total_runs_first_7_innings": "first_7",
    # NFL / cross-sport team markets — full game
    "team_moneyline":                  "full_game",
    "team_spread":                     "full_game",
    "team_total":                      "full_game",
}
# Period id → display label + sort order (lower = earlier in the pill strip)
PERIOD_META = {
    "full_game":    {"label": "FULL GAME", "order": 0},
    "first_inning": {"label": "1ST INN",   "order": 1},
    "first_3":      {"label": "F3",        "order": 2},
    "first_5":      {"label": "F5",        "order": 3},
    "first_7":      {"label": "F7",        "order": 4},
}

# ─── CHANGE 3 (2026-08-14): no-vig dead-zone band ────────────────────────────
# A Pinnacle no-vig sitting in [lower, upper] is the sharp market saying
# "coin flip — no edge." The card must surface this loudly through the existing
# conviction + driver fields so the operator cannot scroll past it.
# Config-driven defaults; env-var override for the operator.
NO_EDGE_LOWER = float(os.environ.get("ANDROMEDA_NO_EDGE_LOWER", "0.48"))
NO_EDGE_UPPER = float(os.environ.get("ANDROMEDA_NO_EDGE_UPPER", "0.52"))


def _decimal_to_implied(dec: float) -> float:
    return 1.0 / dec if dec and dec > 0 else 0.0


def _iso_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _load_events(kind: str, date: str) -> list[dict]:
    p = EVENT_LOG_ROOT / kind / f"{date}.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError as e:
                LOG.warning(f"skipping bad JSONL line in {p}: {e}")
    return out


def _edge_and_conviction(no_vig_side_prob: float) -> tuple[int, str, str]:
    """no_vig_side_prob = the fair prob on the side we're leaning (>0.5). Returns
    (edgeScore 0-100, edgeBand, conviction)."""
    delta_from_coin = max(0.0, no_vig_side_prob - 0.5)  # 0.0 ... 0.5
    score = int(round(delta_from_coin * 200))            # 0 ... 100
    if score < 20:
        return score, "LOW · weak", "thin"
    if score < 50:
        return score, "MODERATE", "moderate"
    return score, "STRONG", "sharp"


def _money_stream(book_deltas: dict[str, int], direction: str) -> tuple[float, str, int, int]:
    """Returns (fill 0-1, read string, num_agree, den) across the 4 money-move books."""
    den = len(MONEY_MOVE_BOOKS)
    num_agree = 0
    total_toward = 0
    for book in MONEY_MOVE_BOOKS:
        d = book_deltas.get(book)
        if d is None:
            continue
        # over side "agrees" if the OVER got more expensive (delta < 0 in American on the OVER row)
        # We record d as the delta on the SAME side as `direction`.
        if d < 0:
            num_agree += 1
            total_toward += abs(d)
    fill = min(1.0, total_toward / 100.0)
    if num_agree >= 3:
        read = "bought up"
    elif num_agree >= 2:
        read = "leaning"
    elif num_agree >= 1:
        read = "early move"
    else:
        read = "quiet"
    return fill, read, num_agree, den


def _books_label(num: int, den: int) -> str:
    if num == 0:
        return "no agree"
    if num == 1:
        return "early move"
    if num >= den - 1:
        return "consensus"
    return "leaning"


def assemble_cards_for_sport(sport: str, date: str) -> list[dict]:
    props = _load_events("prop_snapshot", date)
    moves = _load_events("money_move_snapshot", date)

    # index Pinnacle prop rows by (event_id, participant_id, line, side)
    pin_by_key: dict[tuple, dict] = {}
    for e in props:
        p = e.get("payload", {})
        if p.get("sport") != sport:
            continue
        m = p.get("market", {})
        if m.get("sportsbook") != PINNACLE_BOOK:
            continue
        side = m.get("side")
        line = m.get("line")
        # Skip rows the adapter couldn't parse into a clean side/line — they're on
        # the bus for audit (raw_line_value preserved on the event) but can't be
        # paired into an over/under card. Not a Rule-4 skip: the data is intact
        # in the bus; the ASSEMBLER just can't render an unparseable row.
        if side not in ("over", "under") or line is None:
            continue
        # Two market shapes:
        #   PITCHER PROPS (family starts pitcher_/batter_): participants = 1 per
        #     player; Over+Under live under SAME participant_id. Pair by participant.
        #   TEAM-TOTAL PROPS (team_total_*): "Over" and "Under" are SEPARATE
        #     participants. Pair by (event, family, line) — no participant in key.
        family_p = (p.get("market_family") or "")
        is_team_total = family_p.startswith("team_")
        if is_team_total:
            key = (p.get("event_id"), family_p, line, side)
        else:
            key = (p.get("event_id"), p.get("participant_id"), line, side)
        pin_by_key[key] = e

    # index money-move rows the same way (pitcher-vs-team keying)
    move_by_key: dict[tuple, dict] = {}
    for e in moves:
        p = e.get("payload", {})
        if p.get("sport") != sport:
            continue
        m = p.get("market", {})
        side = m.get("side")
        line = m.get("line")
        if side not in ("over", "under") or line is None:
            continue
        family_p = (p.get("market_family") or "")
        is_team_total = family_p.startswith("team_")
        if is_team_total:
            key = (p.get("event_id"), family_p, line, side, m.get("sportsbook"))
        else:
            key = (p.get("event_id"), p.get("participant_id"), line, side, m.get("sportsbook"))
        move_by_key[key] = e

    # Pair Pinnacle over/under per (event, pitcher, line) — main-line only (is_main_line=True)
    paired: dict[tuple, dict] = {}
    for (event_id, participant_id, line, side), e in pin_by_key.items():
        p = e["payload"]
        m = p["market"]
        if not m.get("is_main_line"):
            continue
        pk = (event_id, participant_id, line)
        d = paired.setdefault(pk, {"payload": p, "over": None, "under": None})
        d[side] = m
    # If NO Pinnacle main-line for a prop, fall back to whatever Pinnacle line we have
    for (event_id, participant_id, line, side), e in pin_by_key.items():
        pk = (event_id, participant_id, line)
        if pk in paired:
            continue
        p = e["payload"]
        m = p["market"]
        d = paired.setdefault(pk, {"payload": p, "over": None, "under": None})
        if d[side] is None:
            d[side] = m

    # PREGAME-ONLY DISPLAY FILTER (2026-08-15, Robert-flagged bug).
    # Rundown's /sports/3/events/<UTC_date> returns games with event_start between
    # UTC midnight–midnight, which straddles ET evening: e.g. yesterday's 8pm EDT
    # games (00:00 UTC today) come back on today's response. Pregame product mandate
    # (project_axiom_purpose.md) says we don't show already-started games. The bus
    # keeps every row (Rule 4 no-skip); the assembler chooses not to render games
    # whose event_start is in the past. Configurable grace window via env var.
    now_utc = datetime.now(timezone.utc)
    grace_min = int(os.environ.get("ANDROMEDA_LOCK_MINUTES_BEFORE_START", "10"))
    def _is_pregame(event_start_iso: str) -> bool:
        try:
            ev = datetime.fromisoformat(event_start_iso.replace("Z", "+00:00"))
        except Exception:
            return True  # unparseable — surface it, don't silently drop
        # Card renders until N minutes BEFORE first pitch; after that, it's "live" (out of scope)
        return (ev - now_utc).total_seconds() > grace_min * 60

    cards = []
    for (event_id, participant_id, line), rec in paired.items():
        payload = rec["payload"]
        over_m = rec["over"]
        under_m = rec["under"]

        # Pregame filter — drop from CARD render if game already started (or within grace).
        # Bus still contains all rows for audit / M31 / grader.
        if not _is_pregame(payload.get("event_start", "")):
            continue

        # Compute no-vig fair on whichever sides we have
        pin_over_dec = (over_m or {}).get("decimal_odds")
        pin_under_dec = (under_m or {}).get("decimal_odds")
        if pin_over_dec and pin_under_dec:
            o_imp = _decimal_to_implied(pin_over_dec)
            u_imp = _decimal_to_implied(pin_under_dec)
            total = o_imp + u_imp
            no_vig_over = o_imp / total if total else 0.5
        elif pin_over_dec:
            no_vig_over = min(0.9, _decimal_to_implied(pin_over_dec))
        elif pin_under_dec:
            no_vig_over = 1.0 - min(0.9, _decimal_to_implied(pin_under_dec))
        else:
            continue  # no Pinnacle price on either side; skip THIS prop only (still emit others)

        direction = "over" if no_vig_over > 0.5 else "under"
        side_prob = no_vig_over if direction == "over" else (1 - no_vig_over)
        edge_score, edge_band, conviction = _edge_and_conviction(side_prob)

        # Money-move stream: aggregate deltas per book on the SIDE we're leaning.
        # Key shape mirrors the pin_by_key routing above (team-totals differ).
        _family_here = (payload.get("market_family") or "")
        _is_team = _family_here.startswith("team_")
        book_deltas: dict[str, int] = {}
        for book in MONEY_MOVE_BOOKS:
            if _is_team:
                k = (event_id, _family_here, line, direction, book)
            else:
                k = (event_id, participant_id, line, direction, book)
            mv = move_by_key.get(k)
            if mv:
                d = mv["payload"]["market"].get("price_delta_american")
                if d is not None:
                    book_deltas[book] = int(d)
        money_fill, money_read, num_agree, den = _money_stream(book_deltas, direction)

        # STATS fill: reflects edge from the no-vig line (pure market view since real engines aren't wired yet)
        stats_fill = min(1.0, edge_score / 100.0)
        stats_read = "strong" if edge_score >= 60 else "moderate" if edge_score >= 30 else "weak"

        # ─── CHANGE 2 (2026-08-14): honest driver chip ─────────────────────
        # No stats engine is wired today; every projection is derived from the
        # Pinnacle no-vig line. STATS-LED would be provably false and must NEVER
        # appear on a card until a stats engine is genuinely producing the verdict.
        # Driver chip reflects what actually drove the number:
        #   - retail money moved with real conviction → MONEY-LED
        #   - otherwise → SHARP MARKET (Pinnacle no-vig is the driver)
        drivers = []
        if num_agree >= 2 and money_fill >= 0.3:
            drivers.append({"key": "DRIVER · MONEY-LED", "tone": "driver-money"})
            drivers.append({"key": "MARKET AGREES", "tone": "driver-market"})
        else:
            drivers.append({"key": "DRIVER · SHARP MARKET", "tone": "driver-market"})
            if num_agree == 0:
                drivers.append({"key": "MONEY QUIET", "tone": "money"})
            elif num_agree == 1:
                drivers.append({"key": "MONEY EARLY MOVE", "tone": "money"})
            elif num_agree >= 2:
                drivers.append({"key": "MONEY LEANING", "tone": "money"})

        # ─── CHANGE 3 (2026-08-14): no-vig dead-zone flag ──────────────────
        # Pinnacle's no-vig-over inside [NO_EDGE_LOWER, NO_EDGE_UPPER] means the
        # sharp market is calling this a coin flip. Surface it loudly through the
        # conviction field (RN already renders this) and prepend a warn-tone chip
        # to the driver row. Applied to every qualifying card — no skipping.
        is_dead_zone = NO_EDGE_LOWER <= no_vig_over <= NO_EDGE_UPPER
        if is_dead_zone:
            drivers.insert(0, {"key": "COIN FLIP · NO EDGE", "tone": "warn"})

        # Team / opponent identifier resolution.
        # Every prop_snapshot carries up to THREE independent identifiers for each
        # side (Rundown provides all three at ingest when we've mapped that sport):
        #   - mascot  ("Angels", "Yankees")            — sport-specific mapping table
        #   - name    ("Los Angeles", "New York")      — city string from Rundown
        #   - team_id ("57", "48")                     — Rundown internal id
        # None of these is a failure mode; each is a REAL identifier at a different
        # specificity level. The card picks the most specific identifier present
        # and records which tier we matched at, so the UI can surface data quality
        # ("angels" match_level=mascot vs "team_57" match_level=id) if it wants.
        team_id = payload.get("team_id") or ""
        opp_id = payload.get("opponent_id") or ""
        team_mascot_real = (payload.get("team_mascot") or "").strip()
        opp_mascot_real = (payload.get("opponent_mascot") or "").strip()
        team_name_real = (payload.get("team_name") or "").strip()
        opp_name_real = (payload.get("opponent_name") or "").strip()

        def _resolve_team(mascot: str, name: str, id_: str) -> tuple[str, str]:
            """Return (display, match_level) where match_level ∈
            {'mascot','name','id','none'} — reports which identifier was matched."""
            if mascot:
                return mascot, "mascot"
            if name:
                return name, "name"
            if id_:
                return f"team_{id_}", "id"
            return "team ?", "none"
        team_str, team_match_level = _resolve_team(team_mascot_real, team_name_real, team_id)
        opp_str, opp_match_level = _resolve_team(opp_mascot_real, opp_name_real, opp_id)

        # PRODUCT FILTER (Robert 2026-08-14): starters only.
        # The Rundown adapter sets team_id ONLY when participant_id matches the event's
        # announced pitcher_home or pitcher_away. Non-starters (relievers, spot-K props
        # for position players) have empty team_id. Sportsbooks price them but they're
        # not real bet targets. This is a product-defined filter, not a Rule 4 skip:
        # the row is in the bus, we're just choosing not to card it. To see non-starters
        # in the future, add a ?starters_only=false query param and thread it here.
        # Starter filter applies only to PITCHER-level props (family starts pitcher_/batter_).
        # Team-total markets (F5/F3/F7/1st inning runs) have no pitcher affiliation by design;
        # they're team-vs-team props and must render regardless of team_id.
        if not team_id and not (payload.get("market_family") or "").startswith("team_"):
            continue
        # (team_str + team_match_level computed above by _resolve_team)

        # kProj — market-inferred estimate (line + small nudge from no-vig).
        # NOT a real engine projection. Labeled as "market" in sub-text.
        k_proj = round(line + (no_vig_over - 0.5) * 2.0, 2)

        # Lead: one-liner
        lead = (
            f"Pinnacle no-vig **{side_prob:.0%}** on the {direction}. "
            f"Market-inferred projection **{k_proj:.2f}** vs line {line}."
        )
        # Brief: expandable plain-English. Customer-facing text ONLY — no engine
        # names, no model names, no internal architecture references. Describes
        # what the card is showing in market terms the end user recognizes.
        brief = (
            f"Sharp market prices this at a fair {{{{k:{side_prob:.0%}}}}} on the "
            f"{{{{{'up' if direction == 'over' else 'dn'}:{direction}}}}}, "
            f"projection {{{{k:{k_proj:.2f}}}}} against line {{{{k:{line}}}}}. "
            f"Retail books moving that way: {{{{k:{num_agree} of {den}}}}} — {money_read}."
        )

        # Period tag — assembler routes each card into the right pill via family lookup.
        family = payload.get("market_family") or ""
        stat = payload.get("market_stat") or ""
        period = FAMILY_TO_PERIOD.get(family, "other")

        # TEAM-TOTAL card shape: no player attached. Read the event-level home/away
        # info the adapter now embeds on every payload (v0.8+). This works even
        # when a game has NO pitcher events on the bus (Sunday morning pre-lineups).
        is_team_card = family.startswith("team_")
        if is_team_card:
            home_mascot_evt = (payload.get("event_home_mascot") or "").strip()
            away_mascot_evt = (payload.get("event_away_mascot") or "").strip()
            home_name_evt = (payload.get("event_home_name") or "").strip()
            away_name_evt = (payload.get("event_away_name") or "").strip()
            home_id_evt = (payload.get("event_home_id") or "").strip()
            away_id_evt = (payload.get("event_away_id") or "").strip()
            # Use most-specific team identifier available (mascot > city > id).
            team_str_card = home_mascot_evt or home_name_evt or (f"team_{home_id_evt}" if home_id_evt else "home")
            opp_str_card = away_mascot_evt or away_name_evt or (f"team_{away_id_evt}" if away_id_evt else "away")
            display_name = f"{team_str_card} vs {opp_str_card}"
            display_team = team_str_card
            display_opp = opp_str_card
        else:
            display_name = payload.get("participant_name") or "unknown"
            display_team = team_str
            display_opp = opp_str

        card = {
            "id": f"{sport}:{event_id}:{participant_id}:{stat}:{line}",
            "period": period,
            "card_type": "game" if is_team_card else "player",
            "market_family": family,
            "is_team_card": is_team_card,
            "pitcherName": display_name,
            "team": display_team,
            "opponent": display_opp,
            "team_match_level": team_match_level,
            "opponent_match_level": opp_match_level,
            # Nicer labels for common stats — customer-facing text.
            "statCategory": {
                "strikeouts":    "Strikeouts",
                "hits_allowed":  "Hits Allowed",
                "runs_1st":      "1st Inn Total Runs",
                "runs_f3":       "F3 Total Runs",
                "runs_f5":       "F5 Total Runs",
                "runs_f7":       "F7 Total Runs",
                "moneyline":     "Moneyline",
                "spread":        "Spread",
                "total":         ("Total Runs" if sport == "mlb" else "Total Points"),
            }.get(stat, (stat.replace("_", " ").title() if stat else "Strikeouts")),
            "line": line,
            "direction": direction,
            # Change 3: in the dead-zone, replace the conviction string with a
            # loud "COIN FLIP" marker so the RN app's existing conviction render
            # displays it prominently. Outside the dead-zone, unchanged.
            "conviction": (
                f"COIN FLIP · no edge · {no_vig_over:.2f}"
                if is_dead_zone
                else f"{conviction} · {side_prob:.2f}"
            ),
            "no_edge_dead_zone": is_dead_zone,
            "no_vig_over_prob": no_vig_over,
            "drivers": drivers,
            "regressionWarn": False,  # no data source yet
            "lead": lead,
            "kProj": k_proj,
            "edgeScore": edge_score,
            "edgeBand": edge_band,
            "booksAgreeNum": num_agree,
            "booksAgreeDen": den,
            "booksLabel": _books_label(num_agree, den),
            # Sim floor/median/ceiling — NOT WIRED (no SIM engine). Omitted so the block hides.
            "brief": brief,
            "stats": {"fill": stats_fill, "read": stats_read},
            "money": {"fill": money_fill, "read": money_read},
            # NEWS stream — no news engine wired. Omitted so the row hides.
            "isAlert": edge_score >= 60 or (num_agree >= 3 and money_fill >= 0.5),
        }
        cards.append(card)

    # sort: alerts first, then by edge desc
    cards.sort(key=lambda c: (not c["isAlert"], -c["edgeScore"]))
    return cards


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_bearer_auth(self) -> bool:
        """Bearer-token gate on /api/* paths. /health stays open for uptime probes.
        Rule 4: no fallback to open access. If ANDROMEDA_API_TOKEN is not set,
        main() refuses to start the server — so at request time we can trust it
        is set. Token is compared with hmac.compare_digest to defeat timing oracles.
        Token value is NEVER logged."""
        if not self.path.startswith("/api/"):
            return True
        required = os.environ.get("ANDROMEDA_API_TOKEN", "").strip()
        # main() gate makes this defensive-only; if we ever get here without a
        # token, refuse loudly rather than silently allow.
        if not required:
            self._send_json(500, {"error": "server misconfigured"})
            return False
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "missing bearer token"})
            return False
        presented = auth[7:].strip()
        if not hmac.compare_digest(presented, required):
            self._send_json(401, {"error": "invalid token"})
            return False
        return True

    def do_GET(self):
        if not self._check_bearer_auth():
            return
        # /api/andromeda/today[?sport=mlb]
        if self.path.startswith("/api/andromeda/today"):
            sport = "mlb"
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for pair in qs.split("&"):
                    if pair.startswith("sport="):
                        sport = pair.split("=", 1)[1].lower()
            date = _iso_today()
            cards = assemble_cards_for_sport(sport, date)
            # Build per-type period lists that ONLY include periods actually
            # present for that (sport, type) combination. Prevents Player Props
            # from showing game-only periods (1ST INN / F3 / F5) or Football
            # from showing MLB-only periods.
            periods_by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for c in cards:
                periods_by_type[c.get("card_type", "other")][c.get("period", "other")] += 1
            # Also expose card_types (player/game) counts so the RN app can
            # build a Player-Props vs Game-Props toggle dynamically. New types
            # auto-appear here if we ever tag additional card_types on the server.
            type_counts: dict[str, int] = defaultdict(int)
            for c in cards:
                type_counts[c.get("card_type", "other")] += 1
            TYPE_META = {
                "player": {"label": "PLAYER PROPS", "order": 0},
                "game":   {"label": "GAME PROPS",   "order": 1},
            }
            # Nested types → each type carries its own scoped periods list.
            # Only periods actually present for that type are included, so
            # PLAYER PROPS won't show inning pills, and Football won't show
            # MLB inning pills.
            def _periods_for_type(tid: str) -> list[dict]:
                per = periods_by_type.get(tid, {})
                out = []
                for pid, n in per.items():
                    meta = PERIOD_META.get(pid, {"label": pid.upper(), "order": 99})
                    out.append({"id": pid, "label": meta["label"], "order": meta["order"], "count": n})
                out.sort(key=lambda p: (p["order"], p["id"]))
                return out
            card_types = []
            for tid, meta in TYPE_META.items():
                card_types.append({
                    "id": tid, "label": meta["label"], "order": meta["order"],
                    "count": type_counts.get(tid, 0),
                    "periods": _periods_for_type(tid),
                })
            for tid, n in type_counts.items():
                if tid not in TYPE_META:
                    card_types.append({
                        "id": tid, "label": tid.upper(), "order": 99, "count": n,
                        "periods": _periods_for_type(tid),
                    })
            card_types.sort(key=lambda t: (t["order"], t["id"]))
            self._send_json(200, {
                "date": date, "sport": sport,
                # `periods` kept at top level for backward-compat with older clients
                # (build 11 and earlier). New clients should read card_types[t].periods.
                "periods": [p for t in card_types for p in t["periods"]],
                "card_types": card_types,
                "verdicts": cards,
            })
            return
        if self.path == "/health":
            self._send_json(200, {"ok": True, "date": _iso_today()})
            return
        self._send_json(404, {"error": "not found", "path": self.path})

    def log_message(self, fmt, *args):
        LOG.info(f"{self.address_string()} - {fmt % args}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s | %(message)s")
    # Rule 4 gate: refuse to start without an auth token (no open-access fallback).
    if not os.environ.get("ANDROMEDA_API_TOKEN", "").strip():
        LOG.error(
            "ANDROMEDA_API_TOKEN env var is not set. Refusing to start — no open-access fallback."
        )
        sys.exit(1)
    port = int(os.environ.get("ANDROMEDA_API_PORT", "8787"))
    host = os.environ.get("ANDROMEDA_API_HOST", "127.0.0.1")  # bind loopback; caddy fronts HTTPS
    with socketserver.ThreadingTCPServer((host, port), Handler) as srv:
        LOG.info(f"Andromeda API listening on {host}:{port} — auth: bearer-token required (value not logged)")
        srv.serve_forever()


if __name__ == "__main__":
    main()
