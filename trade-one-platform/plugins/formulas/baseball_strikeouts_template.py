"""Replace only the math inside evaluate(). Keep this interface stable."""

FORMULA_ID = "owner.baseball.strikeouts"
FORMULA_VERSION = "0.1.0"
FORMULA_CONTRACT_VERSION = "1.0"
CAPABILITIES = ("baseball", "pitcher_strikeouts", "pregame", "live")

REQUIRED_INPUTS = (
    "baseline_projection",
    "expected_batters_faced",
    "matchup_k_rate",
)


def evaluate(context):
    missing = [name for name in REQUIRED_INPUTS if context.get(name) is None]
    if missing:
        return {
            "projection": float(context.get("reference_line", 0.0)),
            "score": 0.0,
            "features": {"formula_available": 0.0},
            "flags": ["MISSING_INPUT:" + name for name in missing],
            "explanation_codes": ["FORMULA_ABSTAINED"],
        }

    # PROPRIETARY FORMULA INSERTION POINT
    # Replace this reference math with the owner's formula. The rest of the
    # platform, API, tests, audit lineage, and engine chain do not change.
    batters = float(context["expected_batters_faced"])
    rate = float(context["matchup_k_rate"])
    workload = float(context.get("workload_multiplier", 1.0))
    projection = max(0.0, batters * rate * workload)

    return {
        "projection": projection,
        "score": min(1.0, max(0.0, float(context.get("input_quality", 0.5)))),
        "features": {
            "formula_available": 1.0,
            "formula_expected_batters_faced": batters,
            "formula_matchup_k_rate": rate,
            "formula_workload_multiplier": workload,
        },
        "flags": [],
        "explanation_codes": ["STRIKEOUT_FORMULA_APPLIED"],
    }


CONTRACT_EXAMPLES = (
    {
        "context": {
            "baseline_projection": 6.0,
            "reference_line": 5.5,
            "expected_batters_faced": 24.0,
            "matchup_k_rate": 0.25,
            "workload_multiplier": 1.0,
        }
    },
)

