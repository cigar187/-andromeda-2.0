from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import (
    ComponentRef,
    FormulaOutput,
    IntelligenceRequest,
    MarketView,
    Opportunity,
    OutcomeDistribution,
)


@dataclass(frozen=True, slots=True)
class ComponentManifest:
    component_id: str
    version: str
    contract_version: str
    kind: str
    capabilities: tuple[str, ...] = ()
    artifact_hash: str = ""

    def ref(self) -> ComponentRef:
        return ComponentRef(self.component_id, self.version, self.contract_version, self.artifact_hash)


class Component(ABC):
    @property
    @abstractmethod
    def manifest(self) -> ComponentManifest: ...

    def health(self) -> Mapping[str, Any]:
        return {"status": "ok", "component": self.manifest.component_id}


class ControlEngine(Component):
    @abstractmethod
    def normalize(self, request: IntelligenceRequest) -> IntelligenceRequest: ...


class SportAdapter(Component):
    @abstractmethod
    def enrich(self, request: IntelligenceRequest) -> Mapping[str, Any]: ...

    @abstractmethod
    def validate_market(self, request: IntelligenceRequest) -> tuple[str, ...]: ...


class FormulaEngine(Component):
    @abstractmethod
    def evaluate(self, context: Mapping[str, Any]) -> FormulaOutput: ...


class GroundTruthModel(Component):
    @abstractmethod
    def predict(self, request: IntelligenceRequest, features: Mapping[str, Any],
                formula: FormulaOutput) -> OutcomeDistribution: ...


class MarketModel(Component):
    @abstractmethod
    def price(self, request: IntelligenceRequest, features: Mapping[str, Any]) -> MarketView: ...


class Calibrator(Component):
    @abstractmethod
    def calibrate_distribution(self, distribution: OutcomeDistribution,
                               route: str) -> OutcomeDistribution: ...

    @abstractmethod
    def calibrate_market(self, market: MarketView, route: str) -> MarketView: ...


class OpportunityGrader(Component):
    @abstractmethod
    def grade(self, request: IntelligenceRequest, distribution: OutcomeDistribution,
              market: MarketView, validation_reasons: tuple[str, ...]) -> Opportunity: ...


class AuditRepository(Component):
    @abstractmethod
    def record(self, response: Mapping[str, Any]) -> None: ...


class DeliveryAdapter(Component):
    @abstractmethod
    def publish(self, response: Mapping[str, Any]) -> None: ...


class FeedAdapter(Component):
    """Ingestion feed. Publishes standard events to the event log; NEVER called by any
    brain directly (M1 mandate). Nested sub-sources (individual news sites, individual
    scout targets) follow the same law inside the parent adapter."""
    @abstractmethod
    def poll(self) -> int: ...

