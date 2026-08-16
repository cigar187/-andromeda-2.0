from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar


@dataclass
class CalibrationState:
    temperature: float = 1.0
    classification_nonconformity: float = 1.0
    interval_padding: float = 0.0
    alpha: float = 0.15

    def probability(self, logit: float) -> float:
        scaled = np.clip(logit / max(self.temperature, 1e-3), -35, 35)
        return float(1 / (1 + np.exp(-scaled)))

    def prediction_set(self, probability_over: float) -> list[str]:
        labels = []
        if 1 - probability_over <= self.classification_nonconformity: labels.append("over")
        if probability_over <= self.classification_nonconformity: labels.append("under")
        return labels

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationState":
        return cls(**json.loads(Path(path).read_text()))


def fit_calibration(logits: np.ndarray, labels: np.ndarray, floors: np.ndarray,
                    ceilings: np.ndarray, actual: np.ndarray, alpha: float = 0.15) -> CalibrationState:
    def objective(temperature: float) -> float:
        probability = 1 / (1 + np.exp(-np.clip(logits / temperature, -35, 35)))
        return float(-np.mean(labels * np.log(probability + 1e-9) + (1 - labels) * np.log(1 - probability + 1e-9)))
    result = minimize_scalar(objective, bounds=(0.05, 10), method="bounded")
    temperature = float(result.x)
    probability = 1 / (1 + np.exp(-np.clip(logits / temperature, -35, 35)))
    true_probability = np.where(labels == 1, probability, 1 - probability)
    nonconformity = float(np.quantile(1 - true_probability, 1 - alpha, method="higher"))
    misses = np.maximum(floors - actual, actual - ceilings)
    padding = float(max(0, np.quantile(misses, 1 - alpha, method="higher")))
    return CalibrationState(temperature, nonconformity, padding, alpha)
