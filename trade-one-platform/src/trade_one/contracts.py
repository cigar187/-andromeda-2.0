from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


CONTRACT_VERSION = "1.0"


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def require_probability(value: float, name: str) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


class Mode(StrEnum):
    PREGAME = "pregame"
    LIVE = "live"


class OpportunityStatus(StrEnum):
    READY = "READY"
    WATCH = "WATCH"
    PASS = "PASS"
    STALE = "STALE"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class ComponentRef:
    component_id: str
    version: str
    contract_version: str = CONTRACT_VERSION
    artifact_hash: str = ""


@dataclass(frozen=True, slots=True)
class SourceClock:
    provider: str
    provider_record_id: str
    published_at: str
    received_at: str
    observed_at: str | None = None

    def validate(self, cutoff: str) -> None:
        limit = utc(cutoff)
        if utc(self.published_at) > limit or utc(self.received_at) > limit:
            raise ValueError("source was not available at the decision cutoff")
        if self.observed_at and utc(self.observed_at) > limit:
            raise ValueError("source observation occurs after the decision cutoff")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    market_id: str
    sportsbook: str
    market_family: str
    period: str
    side: str
    line: float
    decimal_odds: float
    first_seen_at: str
    observed_at: str
    status: str = "open"
    settlement_rule_version: str = "unknown"
    prop_id: str | None = None

    def validate(self, cutoff: str) -> None:
        if self.decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be greater than 1")
        if utc(self.observed_at) > utc(cutoff):
            raise ValueError("market quote occurs after the decision cutoff")


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    request_id: str
    mode: Mode
    sport: str
    league: str
    game_id: str
    as_of: str
    event_start: str
    market: MarketQuote
    opposite_market: MarketQuote | None = None
    numeric: dict[str, float] = field(default_factory=dict)
    categorical: dict[str, str] = field(default_factory=dict)
    history: tuple[dict[str, Any], ...] = ()
    text_signals: tuple[dict[str, Any], ...] = ()
    source_clocks: tuple[SourceClock, ...] = ()
    state_revision: int = 0

    def validate(self) -> None:
        utc(self.as_of)
        utc(self.event_start)
        if self.mode == Mode.PREGAME and utc(self.as_of) > utc(self.event_start):
            raise ValueError("pregame request occurs after event start")
        self.market.validate(self.as_of)
        for clock in self.source_clocks:
            clock.validate(self.as_of)
        if not self.request_id or not self.game_id:
            raise ValueError("request_id and game_id are required")


@dataclass(frozen=True, slots=True)
class EngineDistribution:
    engine_id: str
    engine_version: str
    outcome_family: str
    support: tuple[float, ...]
    probabilities: tuple[float, ...]
    as_of: str
    correlation_id: str | None = None

    def validate(self) -> None:
        n = len(self.support)
        if n < 1 or n != len(self.probabilities):
            raise ValueError("support and probabilities must be non-empty and equal length")
        prev = float("-inf")
        for value in self.support:
            fv = float(value)
            if fv <= prev:
                raise ValueError("support must be strictly ascending")
            prev = fv
        total = 0.0
        for value in self.probabilities:
            fv = float(value)
            if fv != fv or fv in (float("inf"), float("-inf")):
                raise ValueError("probabilities contain non-finite values")
            if fv < 0.0:
                raise ValueError("probabilities contain negative values")
            total += fv
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"probabilities must sum to 1 (got {total:.6f})")

    def to_vectors(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return self.support, self.probabilities


@dataclass(frozen=True, slots=True)
class FormulaOutput:
    projection: float
    score: float
    features: dict[str, float] = field(default_factory=dict)
    flags: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutcomeDistribution:
    outcome: str
    mean: float
    quantiles: dict[str, float]
    event_probabilities: dict[str, float]
    uncertainty: float

    def validate(self) -> None:
        if self.uncertainty < 0:
            raise ValueError("uncertainty cannot be negative")
        for name, value in self.event_probabilities.items():
            require_probability(value, name)
        ordered = [self.quantiles[key] for key in ("q05", "q50", "q95") if key in self.quantiles]
        if ordered and ordered != sorted(ordered):
            raise ValueError("quantiles must not cross")


@dataclass(frozen=True, slots=True)
class MarketView:
    no_vig_probability: float | None
    price_probability: float
    uncertainty: float
    reference_decimal_odds: float

    def validate(self) -> None:
        if self.no_vig_probability is not None:
            require_probability(self.no_vig_probability, "no_vig_probability")
        require_probability(self.price_probability, "price_probability")


@dataclass(frozen=True, slots=True)
class Opportunity:
    status: OpportunityStatus
    probability: float
    market_probability: float | None
    raw_divergence: float | None
    adjusted_divergence: float | None
    expected_value: float
    confidence: float
    expires_at: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    contract_version: str
    request_id: str
    mode: Mode
    as_of: str
    game_id: str
    market_id: str
    distribution: OutcomeDistribution
    market_view: MarketView
    opportunity: Opportunity
    formula: FormulaOutput
    components: tuple[ComponentRef, ...]
    trace_id: str
    state_revision: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

