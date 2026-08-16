import json
import tempfile
import unittest
from pathlib import Path

from trade_one.config import load_pipelines
from trade_one.contracts import Mode
from trade_one.pipeline import request_from_dict


ROOT = Path(__file__).resolve().parents[1]


class EndToEndTests(unittest.TestCase):
    def config(self, directory: str) -> Path:
        value = json.loads((ROOT / "config/trade-one.json").read_text())
        value["components"]["formula.pregame"]["settings"]["path"] = str(
            ROOT / "plugins/formulas/baseball_strikeouts_template.py"
        )
        value["components"]["formula.live"]["settings"]["path"] = str(
            ROOT / "plugins/formulas/baseball_strikeouts_template.py"
        )
        value["components"]["repository.audit"]["settings"]["path"] = str(
            Path(directory) / "audit.jsonl"
        )
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(value))
        return path

    def test_pregame_and_live_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            _, pipelines = load_pipelines(self.config(directory))
            pregame = request_from_dict(json.loads((ROOT / "examples/pregame_request.json").read_text()))
            live = request_from_dict(json.loads((ROOT / "examples/live_request.json").read_text()))
            pregame_response = pipelines[Mode.PREGAME].evaluate(pregame)
            live_response = pipelines[Mode.LIVE].evaluate(live)
            self.assertEqual(pregame_response.mode, Mode.PREGAME)
            self.assertEqual(live_response.mode, Mode.LIVE)
            self.assertEqual(pregame_response.formula.explanation_codes, ("STRIKEOUT_FORMULA_APPLIED",))
            self.assertGreater(len(pregame_response.components), 5)
            self.assertNotEqual(pregame_response.trace_id, live_response.trace_id)
            self.assertEqual(len(Path(directory, "audit.jsonl").read_text().splitlines()), 2)

    def test_mode_mixing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, pipelines = load_pipelines(self.config(directory))
            live = request_from_dict(json.loads((ROOT / "examples/live_request.json").read_text()))
            with self.assertRaisesRegex(ValueError, "pregame pipeline"):
                pipelines[Mode.PREGAME].evaluate(live)


if __name__ == "__main__":
    unittest.main()

