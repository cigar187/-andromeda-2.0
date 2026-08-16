from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(slots=True)
class Source:
    provider: str
    provider_record_id: str
    observed_at: str
    published_at: str
    reliability_hint: float = 0.5
    content_hash: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Source":
        source = cls(
            provider=str(value["provider"]),
            provider_record_id=str(value["provider_record_id"]),
            observed_at=str(value["observed_at"]),
            published_at=str(value.get("published_at", value["observed_at"])),
            reliability_hint=float(value.get("reliability_hint", 0.5)),
            content_hash=str(value.get("content_hash", "")),
        )
        if not 0 <= source.reliability_hint <= 1:
            raise ValueError("source reliability_hint must be between zero and one")
        parse_time(source.observed_at)
        parse_time(source.published_at)
        return source


@dataclass(slots=True)
class TextDocument:
    document_id: str
    kind: str
    body: str
    published_at: str
    source: str
    language: str = "en"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TextDocument":
        return cls(
            document_id=str(value["document_id"]), kind=str(value.get("kind", "report")),
            body=str(value.get("body", "")), published_at=str(value["published_at"]),
            source=str(value.get("source", "unknown")), language=str(value.get("language", "en")),
        )


@dataclass(slots=True)
class IntelligenceEnvelope:
    schema_version: str
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
    source: Source
    numeric: dict[str, float] = field(default_factory=dict)
    categorical: dict[str, str] = field(default_factory=dict)
    text: list[TextDocument] = field(default_factory=list)
    incumbent_predictions: dict[str, float] = field(default_factory=dict)
    temporal_history: list[dict[str, float]] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)
    signature: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "IntelligenceEnvelope":
        required = ["schema_version", "record_id", "as_of", "event_start", "sport", "league",
                    "season", "event_id", "participant_id", "team_id", "opponent_id", "role",
                    "market_family", "market_stat", "line", "over_odds", "under_odds", "source"]
        missing = [key for key in required if value.get(key) is None]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        payload = {key: value[key] for key in required if key != "source"}
        record = cls(
            **payload,
            source=Source.from_dict(value["source"]),
            numeric={str(k): float(v) for k, v in value.get("numeric", {}).items() if v is not None},
            categorical={str(k): str(v) for k, v in value.get("categorical", {}).items() if v is not None},
            text=[TextDocument.from_dict(item) for item in value.get("text", [])],
            incumbent_predictions={str(k): float(v) for k, v in value.get("incumbent_predictions", {}).items()},
            temporal_history=[{str(k): float(v) for k, v in item.items() if v is not None} for item in value.get("temporal_history", [])],
            labels=dict(value.get("labels", {})), signature=value.get("signature"),
        )
        record.validate()
        return record

    def validate(self) -> None:
        cutoff, start = parse_time(self.as_of), parse_time(self.event_start)
        if cutoff > start:
            raise ValueError("as_of occurs after event_start")
        if parse_time(self.source.published_at) > cutoff:
            raise ValueError("source published after the point-in-time cutoff")
        if parse_time(self.source.observed_at) > cutoff:
            raise ValueError("source observed after the point-in-time cutoff")
        if any(parse_time(document.published_at) > cutoff for document in self.text):
            raise ValueError("text document published after the point-in-time cutoff")
        settled_at = self.labels.get("settled_at")
        if settled_at and parse_time(settled_at) < start:
            raise ValueError("outcome settled before event start")
        if not self.record_id or not self.source.provider_record_id:
            raise ValueError("record identifiers may not be empty")

    @property
    def route(self) -> str:
        return ":".join((self.sport.lower(), self.league.lower(), self.market_family.lower(), self.market_stat.lower(), self.role.lower()))

    @property
    def payload_hash(self) -> str:
        value = self.to_dict()
        value.pop("signature", None)
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
