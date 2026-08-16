from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .contracts import CanonicalObservation
from .features import add_temporal_features, to_frame
from .training import IntelligenceTrainer, ModelBundle


class IntelligenceEngine:
    def __init__(self, artifact_dir: str | Path) -> None:
        self.bundle: ModelBundle = joblib.load(Path(artifact_dir) / "model.joblib")

    def predict(self, records: list[CanonicalObservation]) -> list[dict]:
        frame = add_temporal_features(to_frame(records))
        expert_predictions = np.column_stack([
            self.bundle.experts[name].predict_proba(frame)[:, 1]
            for name in self.bundle.expert_order
        ])
        meta_features = np.column_stack([expert_predictions, IntelligenceTrainer._routing_matrix(frame)])
        probability = self.bundle.meta_model.predict_proba(meta_features)[:, 1]
        distributions = self._distribution(frame)
        results = []
        for index, record in enumerate(records):
            p = float(probability[index])
            result = {
                "record_id": record.record_id,
                "event_id": record.event_id,
                "participant_id": record.participant_id,
                "market_stat": record.market_stat,
                "line": record.line,
                "probability_over": round(p, 5),
                "probability_under": round(1 - p, 5),
                "decision": "over" if p >= 0.5 else "under",
                "confidence": "high" if abs(p - 0.5) >= 0.24 else "medium" if abs(p - 0.5) >= 0.12 else "low",
                "expert_probabilities": {name: round(float(expert_predictions[index, j]), 5) for j, name in enumerate(self.bundle.expert_order)},
                "model_route": record.route,
            }
            threshold = self.bundle.conformal_threshold
            labels = []
            if 1 - p <= threshold:
                labels.append("over")
            if p <= threshold:
                labels.append("under")
            result["conformal_set"] = labels
            result["conformal_alpha"] = 0.15
            result.update({key: round(float(values[index]), 4) for key, values in distributions.items()})
            results.append(result)
        return results

    def _distribution(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        output = {}
        for name, payload in self.bundle.quantile_models.items():
            columns, model = payload
            X = frame.reindex(columns=columns).apply(pd.to_numeric, errors="coerce").fillna(0)
            output[name] = model.predict(X)
        if not output:
            line = frame["line"].to_numpy(float)
            output = {"floor": line * 0.78, "median": line, "ceiling": line * 1.22}
        return output
