from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import Tensor, nn


@dataclass(slots=True)
class ModelConfig:
    vocabulary_size: int
    numeric_features: int
    categorical_features: int
    incumbent_features: int
    event_classes: int
    hidden_size: int = 192
    text_layers: int = 3
    text_heads: int = 6
    temporal_features: int = 16
    temporal_layers: int = 2
    dropout: float = 0.12
    max_length: int = 192
    modality_tokens: int = 4


class PositionalEncoding(nn.Module):
    def __init__(self, maximum: int, hidden: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(maximum, hidden)

    def forward(self, inputs: Tensor) -> Tensor:
        positions = torch.arange(inputs.size(1), device=inputs.device)
        return inputs + self.embedding(positions)[None, :, :]


class SportsTextEncoder(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.embedding = nn.Embedding(config.vocabulary_size, config.hidden_size, padding_idx=0)
        self.position = PositionalEncoding(config.max_length, config.hidden_size)
        layer = nn.TransformerEncoderLayer(
            d_model=config.hidden_size, nhead=config.text_heads,
            dim_feedforward=config.hidden_size * 4, dropout=config.dropout,
            activation="gelu", batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, config.text_layers)
        self.norm = nn.LayerNorm(config.hidden_size)

    def forward(self, token_ids: Tensor, attention_mask: Tensor) -> Tensor:
        hidden = self.position(self.embedding(token_ids))
        hidden = self.encoder(hidden, src_key_padding_mask=~attention_mask.bool())
        return self.norm(hidden[:, 0])


class TabularGatedEncoder(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        input_size = config.numeric_features + config.categorical_features + config.incumbent_features
        self.value = nn.Sequential(nn.Linear(input_size, config.hidden_size * 2), nn.GELU(), nn.Dropout(config.dropout), nn.Linear(config.hidden_size * 2, config.hidden_size))
        self.gate = nn.Sequential(nn.Linear(input_size, config.hidden_size), nn.Sigmoid())
        self.norm = nn.LayerNorm(config.hidden_size)

    def forward(self, numeric: Tensor, categorical: Tensor, incumbent: Tensor) -> Tensor:
        combined = torch.cat((numeric, categorical, incumbent), dim=-1)
        return self.norm(self.value(combined) * self.gate(combined))


class TemporalStateEncoder(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.input = nn.Linear(config.temporal_features, config.hidden_size)
        self.gru = nn.GRU(config.hidden_size, config.hidden_size, config.temporal_layers, dropout=config.dropout if config.temporal_layers > 1 else 0, batch_first=True)
        self.change_gate = nn.Sequential(nn.Linear(config.temporal_features, config.hidden_size), nn.Sigmoid())
        self.norm = nn.LayerNorm(config.hidden_size)

    def forward(self, sequence: Tensor, sequence_mask: Tensor) -> Tensor:
        encoded, _ = self.gru(self.input(sequence))
        lengths = sequence_mask.sum(dim=1).long().clamp(min=1) - 1
        last = encoded[torch.arange(encoded.size(0), device=encoded.device), lengths]
        delta = sequence[:, -1] - sequence[:, 0]
        return self.norm(last * self.change_gate(delta))


class CrossModalFusion(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.market = nn.Sequential(nn.Linear(6, config.hidden_size), nn.GELU(), nn.LayerNorm(config.hidden_size))
        self.attention = nn.MultiheadAttention(config.hidden_size, config.text_heads, dropout=config.dropout, batch_first=True)
        self.feedforward = nn.Sequential(nn.LayerNorm(config.hidden_size), nn.Linear(config.hidden_size, config.hidden_size * 3), nn.GELU(), nn.Dropout(config.dropout), nn.Linear(config.hidden_size * 3, config.hidden_size))
        self.norm = nn.LayerNorm(config.hidden_size)

    def forward(self, text: Tensor, tabular: Tensor, temporal: Tensor, market: Tensor) -> tuple[Tensor, Tensor]:
        tokens = torch.stack((text, tabular, temporal, self.market(market)), dim=1)
        attended, weights = self.attention(tokens, tokens, tokens, need_weights=True, average_attn_weights=False)
        fused = self.norm(tokens + attended + self.feedforward(tokens + attended)).mean(dim=1)
        return fused, weights


class CodexControlModel(nn.Module):
    """Small owned multimodal model; no generative language head."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.text = SportsTextEncoder(config)
        self.tabular = TabularGatedEncoder(config)
        self.temporal = TemporalStateEncoder(config)
        self.fusion = CrossModalFusion(config)
        hidden = config.hidden_size
        self.event_head = nn.Linear(hidden, config.event_classes)
        self.relevance_head = nn.Linear(hidden, 1)
        self.direction_head = nn.Linear(hidden, 3)
        self.certainty_head = nn.Linear(hidden, 1)
        self.over_head = nn.Linear(hidden, 1)
        self.quantile_head = nn.Linear(hidden, 3)
        self.uncertainty_head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, 1), nn.Softplus())
        self.route_head = nn.Linear(hidden, max(1, config.incumbent_features))

    def forward(self, token_ids: Tensor, attention_mask: Tensor, numeric: Tensor, categorical: Tensor,
                incumbent: Tensor, temporal_sequence: Tensor, temporal_mask: Tensor, market: Tensor) -> dict[str, Tensor]:
        text = self.text(token_ids, attention_mask)
        tabular = self.tabular(numeric, categorical, incumbent)
        temporal = self.temporal(temporal_sequence, temporal_mask)
        fused, attention = self.fusion(text, tabular, temporal, market)
        raw_quantiles = self.quantile_head(fused)
        floor = raw_quantiles[:, :1]
        median = floor + torch.nn.functional.softplus(raw_quantiles[:, 1:2])
        ceiling = median + torch.nn.functional.softplus(raw_quantiles[:, 2:3])
        return {
            "event_logits": self.event_head(fused),
            "relevance_logit": self.relevance_head(fused),
            "direction_logits": self.direction_head(fused),
            "certainty": torch.sigmoid(self.certainty_head(fused)),
            "over_logit": self.over_head(fused),
            "quantiles": torch.cat((floor, median, ceiling), dim=1),
            "uncertainty": self.uncertainty_head(fused),
            "route_logits": self.route_head(fused),
            "modality_attention": attention,
            "embedding": fused,
        }

    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    def configuration(self) -> dict:
        return asdict(self.config)
