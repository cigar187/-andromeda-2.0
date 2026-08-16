from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


def normalize(value: str) -> str:
    value = re.sub(r"[^a-z0-9 ]", " ", value.lower())
    return " ".join(token for token in value.split() if token not in {"jr", "sr", "ii", "iii", "iv"})


@dataclass(slots=True)
class Entity:
    canonical_id: str
    entity_type: str
    name: str
    aliases: set[str] = field(default_factory=set)
    team_id: str | None = None
    role: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(slots=True)
class Resolution:
    canonical_id: str | None
    confidence: float
    status: str
    candidates: list[tuple[str, float]]


class OntologyResolver:
    """Provider-aware resolver that quarantines ambiguity instead of guessing."""

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.provider_ids: dict[tuple[str, str], str] = {}

    def register(self, entity: Entity, provider_ids: dict[str, str] | None = None) -> None:
        self.entities[entity.canonical_id] = entity
        for provider, provider_id in (provider_ids or {}).items():
            self.provider_ids[(provider, provider_id)] = entity.canonical_id

    def resolve(self, provider: str, provider_id: str | None, name: str, team_id: str | None = None, role: str | None = None) -> Resolution:
        if provider_id and (provider, provider_id) in self.provider_ids:
            canonical_id = self.provider_ids[(provider, provider_id)]
            return Resolution(canonical_id, 1.0, "resolved_provider_id", [(canonical_id, 1.0)])
        target = normalize(name)
        candidates = []
        for entity in self.entities.values():
            names = {entity.name, *entity.aliases}
            score = max(SequenceMatcher(None, target, normalize(candidate)).ratio() for candidate in names)
            if team_id and entity.team_id == team_id:
                score += 0.08
            if role and entity.role == role:
                score += 0.05
            candidates.append((entity.canonical_id, min(score, 1.0)))
        candidates.sort(key=lambda item: item[1], reverse=True)
        if not candidates or candidates[0][1] < 0.84:
            return Resolution(None, candidates[0][1] if candidates else 0.0, "unresolved", candidates[:5])
        if len(candidates) > 1 and candidates[0][1] - candidates[1][1] < 0.05:
            return Resolution(None, candidates[0][1], "ambiguous", candidates[:5])
        return Resolution(candidates[0][0], candidates[0][1], "resolved_fuzzy", candidates[:5])
