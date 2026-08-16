from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from .contracts import IntelligenceEnvelope, parse_time
from .tokenizer import SportsTokenizer


@dataclass
class FeatureSchema:
    numeric_names: list[str] = field(default_factory=list)
    incumbent_names: list[str] = field(default_factory=list)
    temporal_names: list[str] = field(default_factory=list)
    numeric_mean: dict[str, float] = field(default_factory=dict)
    numeric_std: dict[str, float] = field(default_factory=dict)
    categorical_dimensions: int = 128
    maximum_history: int = 32
    event_classes: list[str] = field(default_factory=lambda: ["none", "injury", "restriction", "role_change", "lineup", "weather", "market", "availability", "tactical", "other"])

    @classmethod
    def fit(cls, records: list[IntelligenceEnvelope], categorical_dimensions: int = 128, maximum_history: int = 32) -> "FeatureSchema":
        numeric_names = sorted({key for record in records for key in record.numeric})
        incumbent_names = sorted({key for record in records for key in record.incumbent_predictions})
        temporal_names = sorted({key for record in records for state in record.temporal_history for key in state})
        temporal_names = temporal_names or ["line", "over_odds", "under_odds", "source_velocity", "consensus", "contradiction"]
        means, stds = {}, {}
        for name in numeric_names:
            values = [record.numeric[name] for record in records if name in record.numeric]
            means[name] = float(np.mean(values)) if values else 0.0
            stds[name] = float(np.std(values)) or 1.0
        return cls(numeric_names, incumbent_names, temporal_names, means, stds, categorical_dimensions, maximum_history)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> "FeatureSchema":
        return cls(**json.loads(Path(path).read_text()))


class Tensorizer:
    def __init__(self, tokenizer: SportsTokenizer, schema: FeatureSchema) -> None:
        self.tokenizer = tokenizer
        self.schema = schema

    def inputs(self, record: IntelligenceEnvelope) -> dict[str, torch.Tensor]:
        text = " [SEP] ".join(f"[{document.kind}] [{document.source}] {document.body}" for document in record.text)
        token_ids, attention_mask = self.tokenizer.encode(text)
        numeric = [(record.numeric.get(name, self.schema.numeric_mean[name]) - self.schema.numeric_mean[name]) / self.schema.numeric_std[name] for name in self.schema.numeric_names]
        categorical = np.zeros(self.schema.categorical_dimensions, dtype=np.float32)
        categorical_values = {
            "sport": record.sport, "league": record.league, "season": record.season,
            "role": record.role, "market_family": record.market_family,
            "market_stat": record.market_stat, "team_id": record.team_id,
            "opponent_id": record.opponent_id, **record.categorical,
        }
        for key, value in categorical_values.items():
            digest = hashlib.blake2b(f"{key}:{value}".lower().encode(), digest_size=8).digest()
            integer = int.from_bytes(digest)
            categorical[integer % len(categorical)] += 1 if integer & 1 else -1
        incumbent = [record.incumbent_predictions.get(name, 0.5) for name in self.schema.incumbent_names]
        sequence = np.zeros((self.schema.maximum_history, len(self.schema.temporal_names)), dtype=np.float32)
        mask = np.zeros(self.schema.maximum_history, dtype=np.float32)
        history = record.temporal_history[-self.schema.maximum_history:]
        for row_index, state in enumerate(history):
            mask[row_index] = 1
            for column_index, name in enumerate(self.schema.temporal_names):
                sequence[row_index, column_index] = state.get(name, 0.0)
        if not history:
            mask[0] = 1
        over_implied = self._implied(record.over_odds)
        under_implied = self._implied(record.under_odds)
        hours = max(0.0, (parse_time(record.event_start) - parse_time(record.as_of)).total_seconds() / 3600)
        market = [record.line, over_implied, under_implied, min(hours, 336) / 336, record.source.reliability_hint, min(len(record.text), 20) / 20]
        return {
            "token_ids": torch.tensor(token_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.bool),
            "numeric": torch.tensor(numeric, dtype=torch.float32),
            "categorical": torch.tensor(categorical, dtype=torch.float32),
            "incumbent": torch.tensor(incumbent, dtype=torch.float32),
            "temporal_sequence": torch.tensor(sequence, dtype=torch.float32),
            "temporal_mask": torch.tensor(mask, dtype=torch.bool),
            "market": torch.tensor(market, dtype=torch.float32),
        }

    def targets(self, record: IntelligenceEnvelope) -> dict[str, torch.Tensor]:
        labels = record.labels
        event_name = str(labels.get("event_class", "none"))
        event_index = self.schema.event_classes.index(event_name) if event_name in self.schema.event_classes else self.schema.event_classes.index("other")
        direction = {"negative": 0, "neutral": 1, "positive": 2}.get(str(labels.get("direction", "neutral")), 1)
        incumbent_losses = labels.get("incumbent_losses", {})
        if self.schema.incumbent_names and incumbent_losses:
            best_expert = min(range(len(self.schema.incumbent_names)), key=lambda index: float(incumbent_losses.get(self.schema.incumbent_names[index], 1e9)))
        else:
            best_expert = 0
        # A4: over_hit and actual_value are the primary targets — no defaults,
        # no coercion. If either is missing, this record should have been
        # excluded upstream by ControlTrainer._is_trainable; a KeyError here
        # is a loud signal that an unlabeled record leaked into the tensor
        # path.
        return {
            "event_class": torch.tensor(event_index, dtype=torch.long),
            "relevance": torch.tensor(float(labels.get("relevance", 1.0))),
            "direction": torch.tensor(direction, dtype=torch.long),
            "certainty": torch.tensor(float(labels.get("certainty", 0.5))),
            "over_hit": torch.tensor(float(labels["over_hit"])),
            "actual_value": torch.tensor(float(labels["actual_value"])),
            "best_expert": torch.tensor(best_expert, dtype=torch.long),
        }

    @staticmethod
    def _implied(odds: float) -> float:
        return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)
