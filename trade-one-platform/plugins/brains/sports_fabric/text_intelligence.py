from __future__ import annotations

import math
import re
from collections import Counter
from datetime import timezone

from .contracts import CanonicalObservation, parse_time


NEGATION = re.compile(r"\b(no|not|never|without|unlikely|denies|ruled out)\b", re.I)
UNCERTAINTY = re.compile(r"\b(may|might|could|questionable|uncertain|expected|possible|monitor)\b", re.I)
LIMITATION = re.compile(r"\b(limit|restriction|pitch count|minutes cap|managed workload|short leash)\b", re.I)
POSITIVE_ROLE = re.compile(r"\b(full go|no restriction|cleared|starting|promoted|first unit|top line)\b", re.I)
INJURY = re.compile(r"\b(injury|sore|tightness|sprain|illness|concussion|day-to-day)\b", re.I)


def document_text(record: CanonicalObservation) -> str:
    return " \n ".join(f"__{doc.kind}__ __source_{doc.source}__ {doc.body}" for doc in record.text)


def event_features(record: CanonicalObservation) -> dict[str, float]:
    cutoff = parse_time(record.as_of).astimezone(timezone.utc)
    output: Counter[str] = Counter()
    normalized_bodies: Counter[str] = Counter()
    for doc in record.text:
        body = " ".join(doc.body.lower().split())
        normalized_bodies[body] += 1
        age_hours = max(0.0, (cutoff - parse_time(doc.published_at)).total_seconds() / 3600)
        decay = math.exp(-age_hours / 12) * doc.source_reliability
        output["text_count"] += 1
        output["text_weight"] += decay
        output["negation"] += decay * bool(NEGATION.search(body))
        output["uncertainty"] += decay * bool(UNCERTAINTY.search(body))
        output["limitation"] += decay * bool(LIMITATION.search(body))
        output["positive_role"] += decay * bool(POSITIVE_ROLE.search(body))
        output["injury"] += decay * bool(INJURY.search(body))
    output["duplicate_ratio"] = (
        1 - len(normalized_bodies) / max(1, sum(normalized_bodies.values()))
    )
    output["source_consensus"] = min(1.0, len({doc.source for doc in record.text}) / 4)
    return dict(output)
