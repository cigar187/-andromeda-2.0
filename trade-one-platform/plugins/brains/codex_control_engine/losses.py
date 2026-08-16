from __future__ import annotations

import torch
from torch import Tensor, nn


def pinball(prediction: Tensor, target: Tensor, quantile: float) -> Tensor:
    error = target - prediction
    return torch.maximum(quantile * error, (quantile - 1) * error).mean()


class MultitaskControlLoss(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.binary = nn.BCEWithLogitsLoss()
        self.multiclass = nn.CrossEntropyLoss()

    def forward(self, outputs: dict[str, Tensor], targets: dict[str, Tensor]) -> tuple[Tensor, dict[str, float]]:
        pieces = {
            "event": self.multiclass(outputs["event_logits"], targets["event_class"]),
            "relevance": self.binary(outputs["relevance_logit"].squeeze(-1), targets["relevance"].float()),
            "direction": self.multiclass(outputs["direction_logits"], targets["direction"]),
            "certainty": torch.nn.functional.mse_loss(outputs["certainty"].squeeze(-1), targets["certainty"].float()),
            "over": self.binary(outputs["over_logit"].squeeze(-1), targets["over_hit"].float()),
            "floor": pinball(outputs["quantiles"][:, 0], targets["actual_value"], 0.15),
            "median": pinball(outputs["quantiles"][:, 1], targets["actual_value"], 0.50),
            "ceiling": pinball(outputs["quantiles"][:, 2], targets["actual_value"], 0.85),
            "route": self.multiclass(outputs["route_logits"], targets["best_expert"]),
        }
        weighted = pieces["event"] * 0.8 + pieces["relevance"] * 0.4 + pieces["direction"] * 0.4 + pieces["certainty"] * 0.2 + pieces["over"] + pieces["floor"] * 0.3 + pieces["median"] * 0.4 + pieces["ceiling"] * 0.3 + pieces["route"] * 0.5
        return weighted, {name: float(value.detach()) for name, value in pieces.items()}
