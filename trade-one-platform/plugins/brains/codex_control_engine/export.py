from __future__ import annotations

from pathlib import Path

import torch
from torch import nn

from .model import CodexControlModel, ModelConfig


class ExportWrapper(nn.Module):
    def __init__(self, model: CodexControlModel) -> None:
        super().__init__(); self.model = model

    def forward(self, token_ids, attention_mask, numeric, categorical, incumbent, temporal_sequence, temporal_mask, market):
        output = self.model(token_ids, attention_mask, numeric, categorical, incumbent, temporal_sequence, temporal_mask, market)
        return (output["event_logits"], output["relevance_logit"], output["direction_logits"], output["certainty"],
                output["over_logit"], output["quantiles"], output["uncertainty"], output["route_logits"], output["embedding"])


def export_onnx(artifact_dir: str | Path, output_path: str | Path, quantize: bool = True) -> Path:
    artifact_dir, output_path = Path(artifact_dir), Path(output_path)
    payload = torch.load(artifact_dir / "model.pt", map_location="cpu", weights_only=True)
    config = ModelConfig(**payload["config"]); model = CodexControlModel(config); model.load_state_dict(payload["state_dict"]); model.eval()
    batch, history = 1, 32
    inputs = (
        torch.zeros(batch, config.max_length, dtype=torch.long), torch.ones(batch, config.max_length, dtype=torch.bool),
        torch.zeros(batch, config.numeric_features), torch.zeros(batch, config.categorical_features),
        torch.zeros(batch, config.incumbent_features), torch.zeros(batch, history, config.temporal_features),
        torch.ones(batch, history, dtype=torch.bool), torch.zeros(batch, 6),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(ExportWrapper(model), inputs, output_path, input_names=["token_ids","attention_mask","numeric","categorical","incumbent","temporal_sequence","temporal_mask","market"],
                      output_names=["event_logits","relevance_logit","direction_logits","certainty","over_logit","quantiles","uncertainty","route_logits","embedding"],
                      dynamic_axes={name: {0: "batch"} for name in ["token_ids","attention_mask","numeric","categorical","incumbent","temporal_sequence","temporal_mask","market"]},
                      opset_version=18, dynamo=False)
    if quantize:
        try:
            from onnxruntime.quantization import QuantType, quantize_dynamic
            quantized = output_path.with_name(output_path.stem + ".int8.onnx")
            quantize_dynamic(output_path, quantized, weight_type=QuantType.QInt8)
            return quantized
        except ImportError:
            pass
    return output_path
