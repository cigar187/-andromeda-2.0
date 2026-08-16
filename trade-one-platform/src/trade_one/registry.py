from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import CONTRACT_VERSION
from .interfaces import Component


class CompatibilityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PluginSpec:
    slot: str
    factory: str
    settings: dict[str, Any]


def contract_major(value: str) -> str:
    return value.split(".", 1)[0]


class ComponentRegistry:
    """Composition root. Pipelines depend on interfaces, never concrete brains."""

    def __init__(self, expected_contract: str = CONTRACT_VERSION) -> None:
        self.expected_contract = expected_contract
        self._components: dict[str, Component] = {}

    def load(self, spec: PluginSpec) -> Component:
        module_name, attribute = spec.factory.split(":", 1)
        factory = getattr(importlib.import_module(module_name), attribute)
        component = factory(dict(spec.settings))
        if not isinstance(component, Component):
            raise CompatibilityError(f"{spec.factory} did not create a Component")
        actual = component.manifest.contract_version
        if contract_major(actual) != contract_major(self.expected_contract):
            raise CompatibilityError(
                f"slot {spec.slot} requires contract {self.expected_contract}; "
                f"component {component.manifest.component_id} provides {actual}"
            )
        if spec.slot in self._components:
            raise CompatibilityError(f"duplicate component slot: {spec.slot}")
        self._components[spec.slot] = component
        return component

    def get(self, slot: str, expected_type: type[Any]) -> Any:
        try:
            component = self._components[slot]
        except KeyError as error:
            raise CompatibilityError(f"missing required component slot: {slot}") from error
        if not isinstance(component, expected_type):
            raise CompatibilityError(
                f"slot {slot} contains {type(component).__name__}, expected {expected_type.__name__}"
            )
        return component

    def doctor(self) -> list[dict[str, Any]]:
        return [
            {"slot": slot, "manifest": asdict(component.manifest), "health": dict(component.health())}
            for slot, component in sorted(self._components.items())
        ]
