from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

from .contracts import CONTRACT_VERSION, IntelligenceRequest, IntelligenceResponse, Mode
from .interfaces import (
    AuditRepository,
    Calibrator,
    ControlEngine,
    DeliveryAdapter,
    FormulaEngine,
    GroundTruthModel,
    MarketModel,
    OpportunityGrader,
    SportAdapter,
)
from .registry import ComponentRegistry


class IntelligencePipeline:
    """Stable orchestration shell around replaceable components."""

    def __init__(self, registry: ComponentRegistry, mode: Mode) -> None:
        self.mode = mode
        prefix = mode.value
        self.control = registry.get("control", ControlEngine)
        self.sport = registry.get(f"sport.{prefix}", SportAdapter)
        self.formula = registry.get(f"formula.{prefix}", FormulaEngine)
        self.brain = registry.get(f"brain.{prefix}", GroundTruthModel)
        self.market = registry.get(f"market.{prefix}", MarketModel)
        self.calibrator = registry.get(f"calibrator.{prefix}", Calibrator)
        self.grader = registry.get(f"grader.{prefix}", OpportunityGrader)
        self.repository = registry.get("repository.audit", AuditRepository)
        self.delivery = registry.get("delivery", DeliveryAdapter)

    def evaluate(self, request: IntelligenceRequest) -> IntelligenceResponse:
        if request.mode != self.mode:
            raise ValueError(f"{self.mode.value} pipeline cannot process {request.mode.value} request")
        normalized = self.control.normalize(request)
        features = dict(self.sport.enrich(normalized))
        validation = self.sport.validate_market(normalized)
        formula = self.formula.evaluate(features)
        distribution = self.brain.predict(normalized, features, formula)
        market = self.market.price(normalized, features)
        route = ":".join((normalized.mode.value, normalized.sport, normalized.league,
                          normalized.market.market_family, normalized.market.period))
        distribution = self.calibrator.calibrate_distribution(distribution, route)
        market = self.calibrator.calibrate_market(market, route)
        distribution.validate()
        market.validate()
        opportunity = self.grader.grade(normalized, distribution, market, validation)
        components = tuple(component.manifest.ref() for component in (
            self.control, self.sport, self.formula, self.brain, self.market,
            self.calibrator, self.grader, self.repository, self.delivery,
        ))
        trace_material = json.dumps({
            "request": normalized.request_id,
            "state_revision": normalized.state_revision,
            "components": [asdict(component) for component in components],
        }, sort_keys=True, separators=(",", ":"))
        trace_id = hashlib.sha256(trace_material.encode()).hexdigest()[:24]
        response = IntelligenceResponse(
            contract_version=CONTRACT_VERSION,
            request_id=normalized.request_id,
            mode=normalized.mode,
            as_of=normalized.as_of,
            game_id=normalized.game_id,
            market_id=normalized.market.market_id,
            distribution=distribution,
            market_view=market,
            opportunity=opportunity,
            formula=formula,
            components=components,
            trace_id=trace_id,
            state_revision=normalized.state_revision,
        )
        payload = response.to_dict()
        self.repository.record(payload)
        self.delivery.publish(payload)
        return response


def request_from_dict(payload: dict[str, Any]) -> IntelligenceRequest:
    from .contracts import MarketQuote, SourceClock

    market = MarketQuote(**payload["market"])
    opposite_market = MarketQuote(**payload["opposite_market"]) if payload.get("opposite_market") else None
    clocks = tuple(SourceClock(**item) for item in payload.get("source_clocks", []))
    return IntelligenceRequest(
        request_id=str(payload.get("request_id") or uuid.uuid4()),
        mode=Mode(payload["mode"]),
        sport=str(payload["sport"]),
        league=str(payload["league"]),
        game_id=str(payload["game_id"]),
        as_of=str(payload["as_of"]),
        event_start=str(payload["event_start"]),
        market=market,
        opposite_market=opposite_market,
        numeric={str(k): float(v) for k, v in payload.get("numeric", {}).items()},
        categorical={str(k): str(v) for k, v in payload.get("categorical", {}).items()},
        history=tuple(payload.get("history", [])),
        text_signals=tuple(payload.get("text_signals", [])),
        source_clocks=clocks,
        state_revision=int(payload.get("state_revision", 0)),
    )

