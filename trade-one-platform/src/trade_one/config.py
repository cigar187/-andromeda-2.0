from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import CONTRACT_VERSION, Mode
from .pipeline import IntelligencePipeline
from .registry import ComponentRegistry, PluginSpec


def load_registry(path: str | Path) -> ComponentRegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    registry = ComponentRegistry(str(payload.get("contract_version", CONTRACT_VERSION)))
    for slot, value in payload["components"].items():
        registry.load(PluginSpec(slot, str(value["factory"]), dict(value.get("settings", {}))))
    return registry


def load_pipelines(path: str | Path) -> tuple[ComponentRegistry, dict[Mode, IntelligencePipeline]]:
    registry = load_registry(path)
    return registry, {
        Mode.PREGAME: IntelligencePipeline(registry, Mode.PREGAME),
        Mode.LIVE: IntelligencePipeline(registry, Mode.LIVE),
    }

