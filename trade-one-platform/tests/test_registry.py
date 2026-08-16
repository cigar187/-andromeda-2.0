import unittest

from trade_one.builtin import deterministic_control
from trade_one.interfaces import FormulaEngine
from trade_one.registry import CompatibilityError, ComponentRegistry, PluginSpec


class RegistryTests(unittest.TestCase):
    def test_wrong_component_kind_is_rejected_when_resolved(self):
        registry = ComponentRegistry()
        registry.load(PluginSpec("formula.pregame", "trade_one.builtin:deterministic_control", {}))
        with self.assertRaisesRegex(CompatibilityError, "expected FormulaEngine"):
            registry.get("formula.pregame", FormulaEngine)

    def test_duplicate_slot_is_rejected(self):
        registry = ComponentRegistry()
        spec = PluginSpec("control", "trade_one.builtin:deterministic_control", {})
        registry.load(spec)
        with self.assertRaisesRegex(CompatibilityError, "duplicate"):
            registry.load(spec)


if __name__ == "__main__":
    unittest.main()

