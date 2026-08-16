from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss


@dataclass
class ChallengerScore:
    rows: int
    log_loss: float
    brier: float
    expected_calibration_error: float
    closing_line_value: float
    quantile_coverage: float
    scored_at: str


def calibration_error(labels: np.ndarray, probabilities: np.ndarray, bins: int = 15) -> float:
    edges = np.linspace(0, 1, bins + 1); total = len(labels); error = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (probabilities >= lower) & (probabilities < upper if upper < 1 else probabilities <= upper)
        if mask.any():
            error += mask.mean() * abs(labels[mask].mean() - probabilities[mask].mean())
    return float(error)


def score_challenger(labels: list[int], probabilities: list[float], closing_probabilities: list[float],
                     actual_values: list[float], floors: list[float], ceilings: list[float]) -> ChallengerScore:
    y, p, closing = np.asarray(labels), np.asarray(probabilities), np.asarray(closing_probabilities)
    actual, floor, ceiling = np.asarray(actual_values), np.asarray(floors), np.asarray(ceilings)
    return ChallengerScore(
        rows=len(y), log_loss=float(log_loss(y, p)), brier=float(brier_score_loss(y, p)),
        expected_calibration_error=calibration_error(y, p),
        closing_line_value=float(np.mean(np.abs(closing - y) - np.abs(p - y))),
        quantile_coverage=float(np.mean((actual >= floor) & (actual <= ceiling))),
        scored_at=datetime.now(timezone.utc).isoformat(),
    )
