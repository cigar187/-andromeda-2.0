from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .contracts import IntelligenceEnvelope, parse_time
from .calibration import fit_calibration
from .losses import MultitaskControlLoss
from .model import CodexControlModel, ModelConfig
from .tensorizer import FeatureSchema, Tensorizer
from .tokenizer import SportsTokenizer


class RecordDataset(Dataset):
    def __init__(self, records: list[IntelligenceEnvelope], tensorizer: Tensorizer) -> None:
        self.records, self.tensorizer = records, tensorizer

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        record = self.records[index]
        return self.tensorizer.inputs(record), self.tensorizer.targets(record)


@dataclass
class TrainingResult:
    best_validation_loss: float
    epochs_completed: int
    parameter_count: int
    training_rows: int
    validation_rows: int
    routes: int
    artifact_dir: str
    input_rows: int = 0
    excluded_unsettled: int = 0
    excluded_push: int = 0


def _is_trainable(record: IntelligenceEnvelope) -> bool:
    """A record is trainable iff its labels bag carries a clean over_hit
    ∈ {0, 1} AND an actual_value AND is not flagged as a push. Missing
    over_hit/actual_value is UNLABELED — never coerced to 0 or record.line.
    Push (actual == line) is not a clean over/under example and is excluded.
    Enforced under A4 (no fallbacks): if the emitter didn't grade this row,
    it doesn't train.
    """
    labels = record.labels
    if labels.get("push") is True:
        return False
    over_hit = labels.get("over_hit")
    if over_hit not in (0, 1, 0.0, 1.0):
        return False
    if labels.get("actual_value") is None:
        return False
    return True


class ControlTrainer:
    def __init__(self, seed: int = 187) -> None:
        self.seed = seed
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)

    def train(self, records: list[IntelligenceEnvelope], artifact_dir: str | Path, epochs: int = 20,
              batch_size: int = 32, hidden_size: int = 192, device: str | None = None) -> TrainingResult:
        input_rows = len(records)
        push_records = [r for r in records if r.labels.get("push") is True]
        eligible = [r for r in records if _is_trainable(r)]
        excluded_push = len(push_records)
        excluded_unsettled = input_rows - len(eligible) - excluded_push
        if len(eligible) < 40:
            raise ValueError(
                f"at least 40 labeled point-in-time records are required "
                f"(input={input_rows} eligible={len(eligible)} "
                f"excluded_unsettled={excluded_unsettled} excluded_push={excluded_push})"
            )
        ordered = sorted(eligible, key=lambda record: parse_time(record.as_of))
        split = max(1, int(len(ordered) * 0.8))
        train_records, validation_records = ordered[:split], ordered[split:]
        if len({int(record.labels["over_hit"]) for record in train_records}) < 2:
            raise ValueError("training partition requires both target classes")
        documents = [document.body for record in train_records for document in record.text]
        tokenizer = SportsTokenizer(max_length=192).fit(documents, vocabulary_size=32000, min_frequency=2)
        schema = FeatureSchema.fit(train_records)
        tensorizer = Tensorizer(tokenizer, schema)
        config = ModelConfig(
            vocabulary_size=len(tokenizer), numeric_features=len(schema.numeric_names),
            categorical_features=schema.categorical_dimensions,
            incumbent_features=max(1, len(schema.incumbent_names)), event_classes=len(schema.event_classes),
            hidden_size=hidden_size, temporal_features=len(schema.temporal_names), max_length=tokenizer.max_length,
        )
        # Preserve a route channel even when no incumbent prediction is present.
        if not schema.incumbent_names:
            schema.incumbent_names = ["no_incumbent"]
        model = CodexControlModel(config)
        device = device or ("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        training_loader = DataLoader(RecordDataset(train_records, tensorizer), batch_size=batch_size, shuffle=True)
        validation_loader = DataLoader(RecordDataset(validation_records, tensorizer), batch_size=batch_size)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=0.02, betas=(0.9, 0.98))
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
        criterion = MultitaskControlLoss()
        best_loss, best_state, patience = math.inf, None, 5
        epochs_completed = 0
        for epoch in range(epochs):
            model.train()
            for inputs, targets in training_loader:
                inputs = {key: value.to(device) for key, value in inputs.items()}
                targets = {key: value.to(device) for key, value in targets.items()}
                optimizer.zero_grad(set_to_none=True)
                outputs = model(**inputs)
                loss, _ = criterion(outputs, targets)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            scheduler.step()
            validation_loss = self._evaluate(model, validation_loader, criterion, device)
            epochs_completed = epoch + 1
            if validation_loss < best_loss - 1e-4:
                best_loss = validation_loss
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                patience = 5
            else:
                patience -= 1
                if patience <= 0:
                    break
        if best_state is None:
            raise RuntimeError("training did not produce a valid checkpoint")
        model.load_state_dict(best_state)
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        torch.save({"state_dict": best_state, "config": asdict(config)}, artifact_dir / "model.pt")
        logits, labels, floors, ceilings, actual = self._calibration_values(model, validation_loader, device)
        fit_calibration(logits, labels, floors, ceilings, actual).save(artifact_dir / "calibration.json")
        tokenizer.save(artifact_dir / "tokenizer.json")
        schema.save(artifact_dir / "feature_schema.json")
        result = TrainingResult(
            best_validation_loss=float(best_loss),
            epochs_completed=epochs_completed,
            parameter_count=model.parameter_count(),
            training_rows=len(train_records),
            validation_rows=len(validation_records),
            routes=len({record.route for record in eligible}),
            artifact_dir=str(artifact_dir),
            input_rows=input_rows,
            excluded_unsettled=excluded_unsettled,
            excluded_push=excluded_push,
        )
        (artifact_dir / "training_manifest.json").write_text(json.dumps(asdict(result), indent=2, sort_keys=True))
        return result

    @staticmethod
    def _evaluate(model, loader, criterion, device) -> float:
        model.eval(); losses = []
        with torch.no_grad():
            for inputs, targets in loader:
                outputs = model(**{key: value.to(device) for key, value in inputs.items()})
                loss, _ = criterion(outputs, {key: value.to(device) for key, value in targets.items()})
                losses.append(float(loss))
        return float(np.mean(losses)) if losses else math.inf

    @staticmethod
    def _calibration_values(model, loader, device):
        model.eval(); logits=[]; labels=[]; floors=[]; ceilings=[]; actual=[]
        with torch.no_grad():
            for inputs, targets in loader:
                output=model(**{key:value.to(device) for key,value in inputs.items()})
                logits.extend(output["over_logit"].squeeze(-1).cpu().tolist())
                labels.extend(targets["over_hit"].tolist())
                floors.extend(output["quantiles"][:,0].cpu().tolist())
                ceilings.extend(output["quantiles"][:,2].cpu().tolist())
                actual.extend(targets["actual_value"].tolist())
        return tuple(np.asarray(values,dtype=float) for values in (logits,labels,floors,ceilings,actual))
