from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    CONTRACT_VERSION,
    FormulaOutput,
    IntelligenceRequest,
    MarketView,
    Mode,
    Opportunity,
    OpportunityStatus,
    OutcomeDistribution,
    utc,
)
from .interfaces import (
    AuditRepository,
    Calibrator,
    ComponentManifest,
    ControlEngine,
    DeliveryAdapter,
    FormulaEngine,
    GroundTruthModel,
    MarketModel,
    OpportunityGrader,
    SportAdapter,
)


def manifest(identifier: str, kind: str, version: str = "0.1.0",
             capabilities: tuple[str, ...] = ()) -> ComponentManifest:
    return ComponentManifest(identifier, version, CONTRACT_VERSION, kind, capabilities)


class DeterministicControl(ControlEngine):
    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.control.deterministic", "control", capabilities=("pregame", "live"))

    def normalize(self, request: IntelligenceRequest) -> IntelligenceRequest:
        request.validate()
        return replace(
            request,
            sport=request.sport.strip().lower(),
            league=request.league.strip().lower(),
            categorical={str(key): str(value).strip().lower() for key, value in request.categorical.items()},
            numeric={str(key): float(value) for key, value in request.numeric.items()},
        )


class BaseballAdapter(SportAdapter):
    PERIODS = {
        "inning_1", "inning_2", "inning_3", "inning_4", "inning_5",
        "first_3", "first_5", "full_game", "plate_appearance",
    }

    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.sport.baseball", "sport_adapter", capabilities=("mlb", "pregame", "live"))

    def enrich(self, request: IntelligenceRequest) -> Mapping[str, Any]:
        values: dict[str, Any] = dict(request.numeric) | dict(request.categorical)
        values.update({
            "mode": request.mode.value,
            "period": request.market.period,
            "market_family": request.market.market_family,
            "reference_line": request.market.line,
            "reference_decimal_odds": request.market.decimal_odds,
            "history_length": len(request.history),
            "state_revision": request.state_revision,
        })
        if request.mode == Mode.LIVE:
            values["live_state_present"] = float(bool(request.history or request.numeric.get("inning")))
        return values

    def validate_market(self, request: IntelligenceRequest) -> tuple[str, ...]:
        reasons: list[str] = []
        if request.sport != "baseball":
            reasons.append("UNSUPPORTED_SPORT")
        if request.market.period not in self.PERIODS:
            reasons.append("UNSUPPORTED_PERIOD")
        if request.market.status != "open":
            reasons.append("MARKET_NOT_OPEN")
        if request.market.settlement_rule_version == "unknown":
            reasons.append("SETTLEMENT_RULE_UNVERIFIED")
        return tuple(reasons)


class EmptyFormula(FormulaEngine):
    """Safe default slot. Replace with the owner's proprietary formula plugin."""

    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.formula.empty", "formula", capabilities=("safe_default",))

    def evaluate(self, context: Mapping[str, Any]) -> FormulaOutput:
        baseline = float(context.get("baseline_projection", context.get("reference_line", 0.0)))
        return FormulaOutput(
            projection=baseline,
            score=0.0,
            features={"formula_available": 0.0},
            flags=("FORMULA_NOT_INSTALLED",),
            explanation_codes=("BASELINE_ONLY",),
        )


class ReferenceDistributionModel(GroundTruthModel):
    """Executable structural placeholder, not a trained production brain."""

    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.settings = dict(settings)

    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.brain.reference_distribution", "ground_truth_model",
                        capabilities=("distribution", "pregame", "live", "cpu"))

    def predict(self, request: IntelligenceRequest, features: Mapping[str, Any],
                formula: FormulaOutput) -> OutcomeDistribution:
        baseline = float(features.get("baseline_projection", request.market.line))
        weight = float(self.settings.get("formula_weight", 0.35))
        mean = baseline * (1 - weight) + formula.projection * weight
        scale = max(float(features.get("projection_sd", self.settings.get("default_sd", 1.5))), 0.25)
        z = (mean - request.market.line) / scale
        probability_over = 1.0 / (1.0 + math.exp(-1.7 * z))
        if request.market.side.lower() in {"under", "no"}:
            selected = 1.0 - probability_over
        else:
            selected = probability_over
        output = OutcomeDistribution(
            outcome=f"{request.market.side}:{request.market.line}",
            mean=mean,
            quantiles={"q05": mean - 1.645 * scale, "q50": mean, "q95": mean + 1.645 * scale},
            event_probabilities={"selected": selected, "over": probability_over, "under": 1 - probability_over},
            uncertainty=scale,
        )
        output.validate()
        return output


class QuoteMarketModel(MarketModel):
    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.market.quote", "market_model", capabilities=("sportsbook_quote",))

    def price(self, request: IntelligenceRequest, features: Mapping[str, Any]) -> MarketView:
        raw = min(max(1.0 / request.market.decimal_odds, 0.001), 0.999)
        opposite = request.opposite_market
        if opposite is not None and opposite.decimal_odds > 1.0:
            q_this = 1.0 / request.market.decimal_odds
            q_opp = 1.0 / opposite.decimal_odds
            no_vig: float | None = min(max(q_this / (q_this + q_opp), 0.001), 0.999)
        else:
            no_vig = None
        view = MarketView(no_vig, raw, float(features.get("market_uncertainty", 0.02)),
                          request.market.decimal_odds)
        view.validate()
        return view


class IdentityCalibrator(Calibrator):
    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.calibration.identity", "calibrator", capabilities=("unfitted",))

    def calibrate_distribution(self, distribution: OutcomeDistribution,
                               route: str) -> OutcomeDistribution:
        return distribution

    def calibrate_market(self, market: MarketView, route: str) -> MarketView:
        return market


class ConservativeGrader(OpportunityGrader):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.minimum_edge = float(settings.get("minimum_edge", 0.04))
        self.watch_edge = float(settings.get("watch_edge", 0.015))
        self.uncertainty_penalty = float(settings.get("uncertainty_penalty", 0.02))
        self.maximum_quote_age_seconds = float(settings.get("maximum_quote_age_seconds", 300))

    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.opportunity.conservative", "opportunity_grader",
                        capabilities=("read_only", "abstention"))

    def grade(self, request: IntelligenceRequest, distribution: OutcomeDistribution,
              market: MarketView, validation_reasons: tuple[str, ...]) -> Opportunity:
        probability = distribution.event_probabilities["selected"]
        quote_age = (utc(request.as_of) - utc(request.market.observed_at)).total_seconds()
        reasons = list(validation_reasons)
        if quote_age > self.maximum_quote_age_seconds:
            reasons.append("STALE_QUOTE")
        if market.no_vig_probability is None:
            reasons.append("NO_VIG_UNAVAILABLE")
            raw = None
            adjusted = None
            status = OpportunityStatus.STALE if "STALE_QUOTE" in reasons else OpportunityStatus.PASS
        else:
            raw = probability - market.no_vig_probability
            adjusted = raw - self.uncertainty_penalty * (distribution.uncertainty + market.uncertainty)
            if reasons:
                status = OpportunityStatus.STALE if "STALE_QUOTE" in reasons else OpportunityStatus.PASS
            elif adjusted >= self.minimum_edge:
                status = OpportunityStatus.READY
            elif adjusted >= self.watch_edge:
                status = OpportunityStatus.WATCH
            else:
                status = OpportunityStatus.PASS
                reasons.append("EDGE_BELOW_THRESHOLD")
        expected_value = probability * (request.market.decimal_odds - 1.0) - (1.0 - probability)
        expiry = min(utc(request.event_start), utc(request.as_of) + timedelta(seconds=self.maximum_quote_age_seconds))
        return Opportunity(
            status=status,
            probability=probability,
            market_probability=market.no_vig_probability,
            raw_divergence=raw,
            adjusted_divergence=adjusted,
            expected_value=expected_value,
            confidence=max(0.0, min(1.0, 1.0 - distribution.uncertainty / 10.0)),
            expires_at=expiry.isoformat().replace("+00:00", "Z"),
            reasons=tuple(sorted(set(reasons))),
        )


class JsonlAuditRepository(AuditRepository):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.path = Path(str(settings.get("path", "data/audit/intelligence.jsonl")))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.repository.jsonl", "audit_repository", capabilities=("local", "append_only"))

    def record(self, response: Mapping[str, Any]) -> None:
        line = json.dumps(response, sort_keys=True, separators=(",", ":"), default=str)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


class NullDelivery(DeliveryAdapter):
    @property
    def manifest(self) -> ComponentManifest:
        return manifest("tradeone.delivery.null", "delivery", capabilities=("read_only",))

    def publish(self, response: Mapping[str, Any]) -> None:
        return None


def deterministic_control(settings: dict[str, Any]) -> DeterministicControl:
    return DeterministicControl()


def baseball_adapter(settings: dict[str, Any]) -> BaseballAdapter:
    return BaseballAdapter()


def empty_formula(settings: dict[str, Any]) -> EmptyFormula:
    return EmptyFormula()


def reference_distribution(settings: dict[str, Any]) -> ReferenceDistributionModel:
    return ReferenceDistributionModel(settings)


def quote_market(settings: dict[str, Any]) -> QuoteMarketModel:
    return QuoteMarketModel()


def identity_calibrator(settings: dict[str, Any]) -> IdentityCalibrator:
    return IdentityCalibrator()


def conservative_grader(settings: dict[str, Any]) -> ConservativeGrader:
    return ConservativeGrader(settings)


def jsonl_repository(settings: dict[str, Any]) -> JsonlAuditRepository:
    return JsonlAuditRepository(settings)


def null_delivery(settings: dict[str, Any]) -> NullDelivery:
    return NullDelivery()

