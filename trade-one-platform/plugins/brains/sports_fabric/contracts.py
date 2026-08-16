from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(slots=True)
class TextDocument:
    kind: str
    body: str
    published_at: str
    source: str
    source_reliability: float = 0.5

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TextDocument":
        return cls(
            kind=str(value.get("kind", "unknown")),
            body=str(value.get("body", "")),
            published_at=str(value["published_at"]),
            source=str(value.get("source", "unknown")),
            source_reliability=float(value.get("source_reliability", 0.5)),
        )


@dataclass(slots=True)
class CanonicalObservation:
    record_id: str
    as_of: str
    event_start: str
    sport: str
    league: str
    season: str
    event_id: str
    participant_id: str
    team_id: str
    opponent_id: str
    role: str
    market_family: str
    market_stat: str
    line: float
    over_odds: float
    under_odds: float
    numeric: dict[str, float] = field(default_factory=dict)
    categorical: dict[str, str] = field(default_factory=dict)
    text: list[TextDocument] = field(default_factory=list)
    incumbent_predictions: dict[str, float] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CanonicalObservation":
        required = ["record_id", "as_of", "event_start", "sport", "league", "season",
                    "event_id", "participant_id", "team_id", "opponent_id", "role",
                    "market_family", "market_stat", "line", "over_odds", "under_odds"]
        missing = [key for key in required if value.get(key) is None]
        if missing:
            raise ValueError(f"missing fields: {', '.join(missing)}")
        record = cls(
            **{key: value[key] for key in required},
            numeric={str(k): float(v) for k, v in value.get("numeric", {}).items() if v is not None},
            categorical={str(k): str(v) for k, v in value.get("categorical", {}).items() if v is not None},
            text=[TextDocument.from_dict(item) for item in value.get("text", [])],
            incumbent_predictions={str(k): float(v) for k, v in value.get("incumbent_predictions", {}).items()},
            labels=dict(value.get("labels", {})),
        )
        record.validate()
        return record

    def validate(self) -> None:
        cutoff = parse_time(self.as_of)
        if cutoff > parse_time(self.event_start):
            raise ValueError("as_of must not occur after event_start")
        future_docs = [doc for doc in self.text if parse_time(doc.published_at) > cutoff]
        if future_docs:
            raise ValueError("text document published after as_of cutoff")
        settled_at = self.labels.get("settled_at")
        if settled_at and parse_time(settled_at) < parse_time(self.event_start):
            raise ValueError("settled_at precedes event start")

    @property
    def route(self) -> str:
        return ":".join((self.sport, self.league, self.market_family, self.market_stat, self.role))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
