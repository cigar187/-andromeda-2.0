from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .contracts import IntelligenceEnvelope
from .api_client import CursorFile, OwnedApiConsumer
from .control_plane import ControlPlane
from .export import export_onnx
from .inference import ControlInference
from .training import ControlTrainer


# The consumer name persisted to control_replay_cursors when running in
# database-authoritative mode. Kept explicit so multiple pulls (per-sport,
# per-shard) can be distinguished by their consumer identity.
CURSOR_CONSUMER = "codex-pull-mlb"


def records(path: str | Path) -> list[IntelligenceEnvelope]:
    return [IntelligenceEnvelope.from_dict(json.loads(line)) for line in Path(path).read_text().splitlines() if line.strip()]


def _run_pull(cursor_file: str, one_batch: bool) -> None:
    """Pull loop with two authoritative-store modes:

    * INSTANCE_CONNECTION_NAME set → the database is authoritative.
      Instantiate the repository ONCE (mirrors service.py's put_* pattern),
      resume from control_replay_cursors, and write each batch's admitted,
      quarantined, and cursor to the database. Failed DB writes SURFACE.

    * INSTANCE_CONNECTION_NAME unset (local dev) → CursorFile behavior is
      preserved unchanged. Records are archived on disk by ControlPlane.
    """
    control = ControlPlane()
    consumer = OwnedApiConsumer(control=control)

    if os.getenv("INSTANCE_CONNECTION_NAME"):
        from .repository import CloudSqlRepository
        repository = CloudSqlRepository()
        # Codex-T3: runtime pull path is DDL-free. Schema must have been
        # created by initialize_schema() at setup time by a privileged role
        # (axiom_user in the m31 DB). m31_user (the runtime role) has only
        # INSERT/SELECT/UPDATE on the tables — no ownership, no DDL.
        # assert_ready() raises immediately if any required table/index is
        # missing; no silent create, no fallback.
        repository.assert_ready()
        cursor = repository.get_cursor(CURSOR_CONSUMER)
        _pull_to_repository(consumer, control, repository, cursor, one_batch)
        return

    # Local dev path — unchanged behavior.
    checkpoint = CursorFile(cursor_file)
    accepted = quarantined = 0
    for admissions, next_cursor in consumer.consume(checkpoint.read(), until_exhausted=not one_batch):
        accepted += sum(item.accepted for item in admissions)
        quarantined += sum(item.status.startswith("quarantined") for item in admissions)
        checkpoint.write(next_cursor)
        print(json.dumps({
            "batch": len(admissions), "accepted": accepted,
            "quarantined": quarantined, "next_cursor": next_cursor,
        }))


def _pull_to_repository(
    consumer: OwnedApiConsumer,
    control: ControlPlane,
    repository,  # CloudSqlRepository, but avoid the import at annotation time
    cursor: str | None,
    one_batch: bool,
) -> None:
    """Drive the pull loop with fetch() directly so we retain the raw payload
    for each record — needed so quarantined-invalid rows (where Admission.record
    is None) can still be persisted to control_quarantine with their original
    payload intact. Uses the public OwnedApiConsumer.fetch() and
    ControlPlane.admit() — no fallback, no reach-into-private state.
    """
    accepted = quarantined = 0
    while True:
        payloads, next_cursor = consumer.fetch(cursor)
        last_accepted_hash: str | None = None
        for payload in payloads:
            admission = control.admit(payload)
            if admission.accepted:
                repository.put_record(admission.record)
                accepted += 1
                last_accepted_hash = admission.record.payload_hash
            elif admission.status.startswith("quarantined"):
                record_id = None
                if admission.record is not None:
                    record_id = admission.record.record_id
                else:
                    # ControlPlane's own archive uses payload.record_id when
                    # available even for parse-failed rows; preserve that
                    # identity in the DB so quarantined records can be traced.
                    record_id = payload.get("record_id") if isinstance(payload, dict) else None
                reason = admission.reasons[0] if admission.reasons else admission.status
                repository.put_quarantine(record_id, reason, payload)
                quarantined += 1
            # `duplicate` records are neither counted-as-accepted nor
            # persisted again — ControlPlane already deduped them.
        repository.put_cursor(CURSOR_CONSUMER, next_cursor, last_accepted_hash)
        print(json.dumps({
            "batch": len(payloads), "accepted": accepted,
            "quarantined": quarantined, "next_cursor": next_cursor,
        }))
        if one_batch or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor


def main() -> None:
    parser = argparse.ArgumentParser(prog="codex-control")
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train"); train.add_argument("data"); train.add_argument("--artifacts", default="artifacts"); train.add_argument("--epochs", type=int, default=20); train.add_argument("--hidden-size", type=int, default=192)
    predict = sub.add_parser("predict"); predict.add_argument("data"); predict.add_argument("--artifacts", default="artifacts")
    export = sub.add_parser("export"); export.add_argument("--artifacts", default="artifacts"); export.add_argument("--output", default="artifacts/codex-control.onnx")
    serve = sub.add_parser("serve"); serve.add_argument("--host", default="0.0.0.0"); serve.add_argument("--port", type=int, default=8787)
    pull = sub.add_parser("pull"); pull.add_argument("--cursor-file", default="data/replay_cursor.json"); pull.add_argument("--one-batch", action="store_true")
    args = parser.parse_args()
    if args.command == "train": print(json.dumps(ControlTrainer().train(records(args.data), args.artifacts, args.epochs, hidden_size=args.hidden_size).__dict__, indent=2))
    elif args.command == "predict": print(json.dumps(ControlInference(args.artifacts).predict(records(args.data)), indent=2))
    elif args.command == "export": print(json.dumps({"artifact": str(export_onnx(args.artifacts, args.output))}))
    elif args.command == "serve":
        import uvicorn; uvicorn.run("codex_control_engine.service:app", host=args.host, port=args.port)
    elif args.command == "pull":
        _run_pull(args.cursor_file, args.one_batch)


if __name__ == "__main__": main()
