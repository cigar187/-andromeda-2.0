"""Neutral append-only event log — the training substrate for M31 and its successors.

Purpose: every news event, prediction, signal, outcome, and tribunal decision
gets logged here in a brain-agnostic format. When M32 (or whatever supersedes
M31) arrives, its training data is already sitting here — clean, versioned,
timestamped, complete. Modular component swaps preserve intelligence across
generations because the DATA layer is not tied to any specific brain's shape.

Storage layout:
    {root_dir}/
      _manifest.json                 — schema version + kind catalog
      {kind}/
        {YYYY-MM-DD}.jsonl           — one file per (kind, day), append-only

Event schema (v1):
    event_id            str    — unique, ULID-shaped (timestamp-sortable)
    schema_version      str    — event log schema version ('1.0')
    timestamp           str    — ISO 8601 UTC of the event
    kind                str    — event category (e.g. 'news_ingested')
    source              str    — originating system id (e.g. 'playwright:mlb.com/news')
    component_version   str    — emitting component + version (e.g. 'm31_scout:0.1.0')
    correlation_id      str?   — optional key that links related events across kinds
    payload             dict   — kind-specific data (arbitrary, dict-shaped)

Design rules:
    - Append-only. Never mutate an existing event.
    - JSONL, one event per line, sorted by write order.
    - Every emit gets an event_id derived from timestamp + random suffix so
      writes from parallel processes don't collide.
    - Every emit is fsynced before return (durability > throughput for logs
      this size). Batch writers are welcome to extend this later.
    - Neutral schema — no brain, engine, or formula-specific fields at the top
      level. All that goes in `payload`.

Standard kinds (v1 launch — extend freely):
    news_ingested       — Playwright scout captured a news event
    signal_emitted      — M31 brain (or successor) emitted a normalized signal
    prop_snapshot       — Rundown (or props source) captured a market snapshot
    prediction_made     — Engine produced a projection + directional call
    formula_evaluated   — V5B (or successor) produced a grade
    tribunal_vote       — A stream contributed its vote to the tribunal
    tribunal_verdict    — Fused verdict published
    outcome_settled     — Post-game actual observed
    grade_computed      — Prediction-vs-outcome comparison written
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "1.0"

STANDARD_KINDS_V1 = (
    "news_ingested",
    "signal_emitted",
    "prop_snapshot",
    "slate_snapshot",
    "prediction_made",
    "formula_evaluated",
    "tribunal_vote",
    "tribunal_verdict",
    "outcome_settled",
    "grade_computed",
)


class EventLog:
    """Append-only event log with a neutral schema. Thread- and process-safe
    on POSIX filesystems by opening the daily kind-file in append+binary mode.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest()

    # ── Public API ─────────────────────────────────────────────────────────

    def emit(
        self,
        kind: str,
        source: str,
        payload: dict[str, Any],
        component_version: str,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> str:
        """Append one event to the log. Returns the assigned event_id.

        `timestamp` is auto-generated (UTC now) if not supplied. Provide it
        explicitly for backfills so the log reflects when the event actually
        occurred, not when it was written.
        """
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be dict, got {type(payload).__name__}")
        ts = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event_id = self._make_event_id(ts)
        record = {
            "event_id": event_id,
            "schema_version": SCHEMA_VERSION,
            "timestamp": ts,
            "kind": kind,
            "source": source,
            "component_version": component_version,
            "correlation_id": correlation_id,
            "payload": payload,
        }
        day = ts[:10]
        path = self.root_dir / kind / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str) + "\n"
        # append + fsync — small logs, durability > throughput
        with path.open("ab") as fh:
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        return event_id

    def read(
        self,
        kind: str | None = None,
        date: str | None = None,
        correlation_id: str | None = None,
    ) -> Iterator[dict]:
        """Yield events matching the filters (all optional).

        - kind=None → iterate over every kind directory
        - date=None → iterate over every day file for the matched kinds
        - correlation_id=None → yield all events (else filter to matches)
        """
        kinds = [kind] if kind else self._list_kinds()
        for k in kinds:
            kind_dir = self.root_dir / k
            if not kind_dir.exists():
                continue
            if date is not None:
                paths = [kind_dir / f"{date}.jsonl"] if (kind_dir / f"{date}.jsonl").exists() else []
            else:
                paths = sorted(kind_dir.glob("*.jsonl"))
            for path in paths:
                with path.open("rb") as fh:
                    for raw in fh:
                        try:
                            evt = json.loads(raw.decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        if correlation_id is not None and evt.get("correlation_id") != correlation_id:
                            continue
                        yield evt

    def stats(self) -> dict[str, Any]:
        """Row counts per kind per day + totals."""
        by_kind: dict[str, dict[str, int]] = {}
        totals: dict[str, int] = {}
        for kind_dir in sorted(self.root_dir.iterdir()):
            if not kind_dir.is_dir():
                continue
            k = kind_dir.name
            per_day: dict[str, int] = {}
            for path in sorted(kind_dir.glob("*.jsonl")):
                day = path.stem
                with path.open("rb") as fh:
                    n = sum(1 for _ in fh)
                per_day[day] = n
                totals[k] = totals.get(k, 0) + n
            by_kind[k] = per_day
        return {
            "root_dir": str(self.root_dir),
            "schema_version": SCHEMA_VERSION,
            "totals_by_kind": totals,
            "grand_total": sum(totals.values()),
            "days_by_kind": by_kind,
        }

    # ── Internals ──────────────────────────────────────────────────────────

    def _list_kinds(self) -> list[str]:
        if not self.root_dir.exists():
            return []
        return sorted(p.name for p in self.root_dir.iterdir() if p.is_dir())

    def _ensure_manifest(self) -> None:
        manifest_path = self.root_dir / "_manifest.json"
        if manifest_path.exists():
            return
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "storage_layout": "{root}/{kind}/{YYYY-MM-DD}.jsonl (append-only)",
            "event_schema": {
                "event_id": "str — ULID-shaped, timestamp-sortable, globally unique",
                "schema_version": "str — event log schema version",
                "timestamp": "str — ISO 8601 UTC",
                "kind": "str — event category",
                "source": "str — originating system id",
                "component_version": "str — emitting component + version",
                "correlation_id": "str | null — optional cross-kind linkage key",
                "payload": "dict — kind-specific data",
            },
            "standard_kinds_v1": list(STANDARD_KINDS_V1),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

    @staticmethod
    def _make_event_id(ts: str) -> str:
        # Timestamp-sortable id: strip separators + 12 random hex chars
        compact = ts.replace("-", "").replace(":", "").replace(".", "").rstrip("Z")
        return f"evt_{compact}_{secrets.token_hex(6)}"


# ── Convenience: singleton pattern for droplet standalone scripts ───────────

_default_log: EventLog | None = None


def get_default_log(root_dir: str = "/opt/trade-one/data/events") -> EventLog:
    """Return a shared EventLog instance. Standalone scripts use this so every
    component writes to the same log without threading a handle through code."""
    global _default_log
    if _default_log is None or str(_default_log.root_dir) != str(Path(root_dir)):
        _default_log = EventLog(root_dir)
    return _default_log
