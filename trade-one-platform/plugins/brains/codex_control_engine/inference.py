from __future__ import annotations

from pathlib import Path

import torch

from .contracts import IntelligenceEnvelope
from .calibration import CalibrationState
from .model import CodexControlModel, ModelConfig
from .tensorizer import FeatureSchema, Tensorizer
from .tokenizer import SportsTokenizer


class ControlInference:
    def __init__(self, artifact_dir: str | Path, device: str = "cpu") -> None:
        artifact_dir = Path(artifact_dir)
        payload = torch.load(artifact_dir / "model.pt", map_location=device, weights_only=True)
        self.model = CodexControlModel(ModelConfig(**payload["config"]))
        self.model.load_state_dict(payload["state_dict"])
        self.model.to(device).eval()
        self.device = device
        self.tensorizer = Tensorizer(SportsTokenizer.load(artifact_dir / "tokenizer.json"), FeatureSchema.load(artifact_dir / "feature_schema.json"))
        self.calibration = CalibrationState.load(artifact_dir / "calibration.json") if (artifact_dir / "calibration.json").exists() else CalibrationState()

    def predict(self, records: list[IntelligenceEnvelope]) -> list[dict]:
        results = []
        with torch.inference_mode():
            for record in records:
                inputs = {key: value.unsqueeze(0).to(self.device) for key, value in self.tensorizer.inputs(record).items()}
                output = self.model(**inputs)
                event_index = int(output["event_logits"].argmax(-1))
                direction_index = int(output["direction_logits"].argmax(-1))
                over = self.calibration.probability(float(output["over_logit"][0, 0]))
                route_weights = torch.softmax(output["route_logits"], -1)[0].cpu().tolist()
                results.append({
                    "record_id": record.record_id, "event_id": record.event_id,
                    "participant_id": record.participant_id, "route": record.route,
                    "event_class": self.tensorizer.schema.event_classes[event_index],
                    "relevance": round(float(torch.sigmoid(output["relevance_logit"])[0, 0]), 5),
                    "direction": ["negative", "neutral", "positive"][direction_index],
                    "certainty": round(float(output["certainty"][0, 0]), 5),
                    "probability_over": round(over, 5),
                    "probability_under": round(1 - over, 5),
                    "floor": round(float(output["quantiles"][0, 0]) - self.calibration.interval_padding, 4),
                    "median": round(float(output["quantiles"][0, 1]), 4),
                    "ceiling": round(float(output["quantiles"][0, 2]) + self.calibration.interval_padding, 4),
                    "conformal_set": self.calibration.prediction_set(over),
                    "conformal_alpha": self.calibration.alpha,
                    "epistemic_uncertainty": round(float(output["uncertainty"][0, 0]), 5),
                    "expert_route_weights": {name: round(route_weights[index], 5) for index, name in enumerate(self.tensorizer.schema.incumbent_names)},
                    "payload_hash": record.payload_hash,
                })
        return results
