from __future__ import annotations

import hashlib
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

from .contracts import CONTRACT_VERSION, FormulaOutput
from .interfaces import ComponentManifest, FormulaEngine


class FormulaContractError(RuntimeError):
    pass


class PythonFormulaPlugin(FormulaEngine):
    """Loads an owned formula file behind the stable FormulaEngine contract."""

    def __init__(self, path: str | Path, settings: Mapping[str, Any] | None = None) -> None:
        self.path = Path(path).resolve()
        self.settings = dict(settings or {})
        if not self.path.is_file():
            raise FormulaContractError(f"formula file not found: {self.path}")
        self._hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self._module = self._load_module()
        self._evaluate = self._resolve_evaluator(self._module)
        self._validate_examples()

    def _load_module(self) -> ModuleType:
        # Compile the exact bytes instead of using importlib's timestamp-based
        # bytecode cache. Formula identity is content-addressed and a rapid
        # same-size replacement must never execute stale code.
        module = ModuleType(f"trade_one_formula_{self._hash[:12]}")
        module.__file__ = str(self.path)
        source = self.path.read_text(encoding="utf-8")
        exec(compile(source, str(self.path), "exec"), module.__dict__)
        declared = str(getattr(module, "FORMULA_CONTRACT_VERSION", ""))
        if declared.split(".", 1)[0] != CONTRACT_VERSION.split(".", 1)[0]:
            raise FormulaContractError(
                f"formula contract {declared or 'missing'} is incompatible with {CONTRACT_VERSION}"
            )
        return module

    @staticmethod
    def _resolve_evaluator(module: ModuleType) -> Callable[[Mapping[str, Any]], Any]:
        evaluator = getattr(module, "evaluate", None)
        if not callable(evaluator):
            raise FormulaContractError("formula module must define evaluate(context)")
        return evaluator

    @property
    def manifest(self) -> ComponentManifest:
        return ComponentManifest(
            component_id=str(getattr(self._module, "FORMULA_ID", "owner.formula")),
            version=str(getattr(self._module, "FORMULA_VERSION", "0.0.0")),
            contract_version=CONTRACT_VERSION,
            kind="formula",
            capabilities=tuple(getattr(self._module, "CAPABILITIES", ())),
            artifact_hash=self._hash,
        )

    def evaluate(self, context: Mapping[str, Any]) -> FormulaOutput:
        result = self._evaluate(dict(context) | {"formula_settings": dict(self.settings)})
        if isinstance(result, FormulaOutput):
            output = result
        elif isinstance(result, Mapping):
            output = FormulaOutput(
                projection=float(result["projection"]),
                score=float(result.get("score", 0.0)),
                features={str(k): float(v) for k, v in result.get("features", {}).items()},
                flags=tuple(map(str, result.get("flags", ()))),
                explanation_codes=tuple(map(str, result.get("explanation_codes", ()))),
            )
        else:
            raise FormulaContractError("evaluate() must return FormulaOutput or a mapping")
        if not -1_000_000 < output.projection < 1_000_000:
            raise FormulaContractError("formula projection is outside safety bounds")
        if not -1_000_000 < output.score < 1_000_000:
            raise FormulaContractError("formula score is outside safety bounds")
        return output

    def _validate_examples(self) -> None:
        examples = getattr(self._module, "CONTRACT_EXAMPLES", ())
        for index, example in enumerate(examples):
            try:
                self.evaluate(example["context"])
            except Exception as error:
                raise FormulaContractError(f"formula contract example {index} failed") from error


def python_formula(settings: dict[str, Any]) -> PythonFormulaPlugin:
    path = settings.pop("path")
    return PythonFormulaPlugin(path, settings)
