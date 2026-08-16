from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Evaluation:
    log_loss: float
    brier: float
    calibration_error: float
    quantile_coverage: float
    closing_line_value: float
    availability: float
    p95_latency_ms: float
    critical_integrity_failures: int
    segment_regressions: int
    drift_coverage: float


@dataclass
class PromotionDecision:
    approved: bool
    status: str
    failures: list[str]
    comparisons: dict[str, float]


class PromotionPolicy:
    """A challenger earns promotion; elapsed test time never promotes it."""

    def decide(self, challenger: Evaluation, champion: Evaluation) -> PromotionDecision:
        failures = []
        comparisons = {
            "log_loss_lift": champion.log_loss - challenger.log_loss,
            "brier_lift": champion.brier - challenger.brier,
            "calibration_lift": champion.calibration_error - challenger.calibration_error,
            "clv_lift": challenger.closing_line_value - champion.closing_line_value,
        }
        if challenger.critical_integrity_failures:
            failures.append("critical data-integrity failure")
        if challenger.availability < 0.999:
            failures.append("availability below 99.9%")
        if challenger.p95_latency_ms > 250:
            failures.append("p95 latency above 250ms")
        if challenger.segment_regressions:
            failures.append("one or more protected segments regressed")
        if challenger.drift_coverage < 0.98:
            failures.append("drift monitoring coverage below 98%")
        if comparisons["log_loss_lift"] <= 0:
            failures.append("no out-of-sample log-loss improvement")
        if comparisons["brier_lift"] <= 0:
            failures.append("no Brier-score improvement")
        if challenger.quantile_coverage < 0.82 or challenger.quantile_coverage > 0.88:
            failures.append("quantile coverage outside required band")
        return PromotionDecision(not failures, "approved" if not failures else "rejected", failures, comparisons)


class LocalModelRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists(): self.path.write_text(json.dumps({"models": []}))

    def register(self, version: str, artifact_uri: str, metrics: dict[str, Any], status: str = "challenger") -> None:
        payload = json.loads(self.path.read_text())
        payload["models"] = [model for model in payload["models"] if model["version"] != version]
        payload["models"].append({"version": version, "artifact_uri": artifact_uri, "metrics": metrics, "status": status})
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def promote(self, version: str) -> None:
        payload = json.loads(self.path.read_text())
        found = False
        for model in payload["models"]:
            if model["version"] == version:
                model["status"] = "champion"; found = True
            elif model["status"] == "champion":
                model["status"] = "retired"
        if not found: raise KeyError(version)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))
