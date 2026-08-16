from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp, wasserstein_distance


@dataclass
class DriftMetric:
    name: str
    value: float
    threshold: float
    breached: bool
    severity: str


@dataclass
class DriftReport:
    scope: str
    metrics: list[DriftMetric]
    action: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DriftBaseline:
    """Persisted reference distributions for input, semantic, and prediction drift."""

    def __init__(self) -> None:
        self.numeric: dict[str, list[float]] = {}
        self.categorical: dict[str, dict[str, float]] = {}
        self.embedding_centroid: list[float] = []
        self.embedding_scale: float = 1.0
        self.predictions: list[float] = []
        self.quality: dict[str, float] = {}

    def fit(self, numeric: dict[str, list[float]], categorical: dict[str, list[str]],
            embeddings: np.ndarray | None = None, predictions: list[float] | None = None,
            quality: dict[str, float] | None = None) -> "DriftBaseline":
        self.numeric = {key: list(map(float, values[-10000:])) for key, values in numeric.items()}
        self.categorical = {}
        for key, values in categorical.items():
            unique, counts = np.unique(values, return_counts=True)
            total = counts.sum() or 1
            self.categorical[key] = {str(name): float(count / total) for name, count in zip(unique, counts)}
        if embeddings is not None and len(embeddings):
            centroid = embeddings.mean(axis=0)
            self.embedding_centroid = centroid.tolist()
            self.embedding_scale = float(np.linalg.norm(embeddings - centroid, axis=1).mean()) or 1.0
        self.predictions = list(map(float, (predictions or [])[-10000:]))
        self.quality = dict(quality or {})
        return self

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.__dict__, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> "DriftBaseline":
        baseline = cls(); baseline.__dict__.update(json.loads(Path(path).read_text())); return baseline


class DriftDiscipline:
    def __init__(self, baseline: DriftBaseline) -> None:
        self.baseline = baseline

    def evaluate(self, scope: str, numeric: dict[str, list[float]], categorical: dict[str, list[str]],
                 embeddings: np.ndarray | None = None, predictions: list[float] | None = None,
                 quality: dict[str, float] | None = None) -> DriftReport:
        metrics: list[DriftMetric] = []
        for key, current in numeric.items():
            reference = self.baseline.numeric.get(key)
            if reference and len(current) >= 20:
                ks = float(ks_2samp(reference, current).statistic)
                water = float(wasserstein_distance(reference, current) / (np.std(reference) or 1))
                metrics.extend((self._metric(f"numeric.{key}.ks", ks, 0.20), self._metric(f"numeric.{key}.wasserstein", water, 0.35)))
        for key, current in categorical.items():
            reference = self.baseline.categorical.get(key)
            if reference and current:
                categories = sorted(set(reference) | set(map(str, current)))
                unique, counts = np.unique(list(map(str, current)), return_counts=True)
                current_map = {str(name): count / counts.sum() for name, count in zip(unique, counts)}
                p = np.array([reference.get(category, 1e-8) for category in categories]); p /= p.sum()
                q = np.array([current_map.get(category, 1e-8) for category in categories]); q /= q.sum()
                metrics.append(self._metric(f"categorical.{key}.js", float(jensenshannon(p, q)), 0.18))
        if embeddings is not None and len(embeddings) and self.baseline.embedding_centroid:
            distance = float(np.linalg.norm(embeddings.mean(axis=0) - np.array(self.baseline.embedding_centroid)) / self.baseline.embedding_scale)
            metrics.append(self._metric("semantic.embedding_centroid", distance, 0.40))
        if predictions and self.baseline.predictions:
            metrics.append(self._metric("prediction.wasserstein", float(wasserstein_distance(self.baseline.predictions, predictions)), 0.10))
        for key, value in (quality or {}).items():
            reference = self.baseline.quality.get(key)
            if reference is not None:
                relative = abs(value - reference) / max(abs(reference), 0.01)
                metrics.append(self._metric(f"quality.{key}", relative, 0.30))
        severe = [metric for metric in metrics if metric.breached and metric.severity == "critical"]
        breached = [metric for metric in metrics if metric.breached]
        action = "quarantine" if severe else "degrade_confidence" if len(breached) >= 3 else "warn" if breached else "continue"
        return DriftReport(scope, metrics, action, [metric.name for metric in breached])

    @staticmethod
    def _metric(name: str, value: float, threshold: float) -> DriftMetric:
        ratio = value / threshold if threshold else 0
        severity = "critical" if ratio >= 2 else "high" if ratio >= 1.35 else "medium" if ratio >= 1 else "normal"
        return DriftMetric(name, value, threshold, value >= threshold, severity)
