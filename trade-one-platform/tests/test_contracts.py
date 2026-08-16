import unittest

from trade_one.pipeline import request_from_dict


def payload(mode="pregame"):
    return {
        "request_id": "r1",
        "mode": mode,
        "sport": "baseball",
        "league": "mlb",
        "game_id": "g1",
        "as_of": "2026-07-31T12:00:00Z" if mode == "pregame" else "2026-07-31T18:05:00Z",
        "event_start": "2026-07-31T18:00:00Z",
        "market": {
            "market_id": "m1",
            "sportsbook": "book",
            "market_family": "pitcher_strikeouts",
            "period": "full_game" if mode == "pregame" else "first_5",
            "side": "over",
            "line": 5.5,
            "decimal_odds": 1.91,
            "first_seen_at": "2026-07-31T11:59:00Z",
            "observed_at": "2026-07-31T11:59:30Z" if mode == "pregame" else "2026-07-31T18:04:59Z",
            "settlement_rule_version": "v1",
        },
        "numeric": {
            "baseline_projection": 6.0,
            "expected_batters_faced": 24,
            "matchup_k_rate": 0.25,
        },
    }


class ContractTests(unittest.TestCase):
    def test_pregame_rejects_post_start_cutoff(self):
        value = payload()
        value["as_of"] = "2026-07-31T18:01:00Z"
        value["market"]["observed_at"] = "2026-07-31T18:00:30Z"
        request = request_from_dict(value)
        with self.assertRaisesRegex(ValueError, "pregame request"):
            request.validate()

    def test_live_allows_post_start_cutoff(self):
        request = request_from_dict(payload("live"))
        request.validate()

    def test_future_quote_is_rejected(self):
        value = payload()
        value["market"]["observed_at"] = "2026-07-31T12:00:01Z"
        request = request_from_dict(value)
        with self.assertRaisesRegex(ValueError, "quote occurs after"):
            request.validate()


if __name__ == "__main__":
    unittest.main()

