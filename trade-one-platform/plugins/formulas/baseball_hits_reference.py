"""Reference hits formula slot; must earn promotion before production use."""

FORMULA_ID = "tradeone.reference.baseball.hits"
FORMULA_VERSION = "0.1.0"
FORMULA_CONTRACT_VERSION = "1.0"
CAPABILITIES = ("baseball", "batter_hits", "pregame", "live", "reference_only")


def evaluate(context):
    plate_appearances = float(context.get("expected_plate_appearances", 0.0))
    hit_probability = float(context.get("hit_probability_per_pa", 0.0))
    if plate_appearances <= 0 or not 0 < hit_probability < 1:
        return {
            "projection": float(context.get("reference_line", 0.0)),
            "score": 0.0,
            "features": {"formula_available": 0.0},
            "flags": ["INSUFFICIENT_HITS_INPUTS"],
            "explanation_codes": ["FORMULA_ABSTAINED"],
        }
    projection = plate_appearances * hit_probability
    return {
        "projection": projection,
        "score": float(context.get("input_quality", 0.5)),
        "features": {
            "formula_available": 1.0,
            "formula_expected_plate_appearances": plate_appearances,
            "formula_hit_probability_per_pa": hit_probability,
        },
        "flags": ["REFERENCE_FORMULA_NOT_PROMOTED"],
        "explanation_codes": ["HITS_REFERENCE_FORMULA_APPLIED"],
    }


CONTRACT_EXAMPLES = (
    {"context": {"reference_line": 0.5, "expected_plate_appearances": 4.2,
                 "hit_probability_per_pa": 0.24}},
)

