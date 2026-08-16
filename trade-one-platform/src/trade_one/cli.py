from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .config import load_pipelines, load_registry
from .contracts import Mode
from .pipeline import request_from_dict


def main() -> None:
    parser = argparse.ArgumentParser(prog="trade-one")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pregame", "live"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--input", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--config", required=True)
    args = parser.parse_args()

    if args.command == "doctor":
        print(json.dumps(load_registry(args.config).doctor(), indent=2, default=str))
        return
    _, pipelines = load_pipelines(args.config)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    request = request_from_dict(payload)
    expected = Mode(args.command)
    if request.mode != expected:
        raise SystemExit(f"input mode is {request.mode.value}, expected {expected.value}")
    print(json.dumps(pipelines[expected].evaluate(request).to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()

