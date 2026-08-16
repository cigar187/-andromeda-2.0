import tempfile
import textwrap
import unittest
from pathlib import Path

from trade_one.formula_sdk import FormulaContractError, PythonFormulaPlugin


def formula_source(version="1.0", projection="7.0"):
    return textwrap.dedent(f'''\
        FORMULA_ID = "test.formula"
        FORMULA_VERSION = "1.0.0"
        FORMULA_CONTRACT_VERSION = "{version}"
        CAPABILITIES = ("test",)
        def evaluate(context):
            return {{"projection": {projection}, "score": 0.5, "features": {{"x": 1}}}}
        CONTRACT_EXAMPLES = ({{"context": {{}}}},)
    ''')


class FormulaPluginTests(unittest.TestCase):
    def test_formula_is_loaded_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "formula.py")
            path.write_text(formula_source())
            first = PythonFormulaPlugin(path)
            first_hash = first.manifest.artifact_hash
            self.assertEqual(first.evaluate({}).projection, 7.0)
            path.write_text(formula_source(projection="8.0"))
            second = PythonFormulaPlugin(path)
            self.assertNotEqual(first_hash, second.manifest.artifact_hash)
            self.assertEqual(second.evaluate({}).projection, 8.0)

    def test_incompatible_formula_fails_at_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "formula.py")
            path.write_text(formula_source(version="2.0"))
            with self.assertRaisesRegex(FormulaContractError, "incompatible"):
                PythonFormulaPlugin(path)


if __name__ == "__main__":
    unittest.main()

