from __future__ import annotations

import json
import os
import hmac
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .contracts import IntelligenceEnvelope


@dataclass(slots=True)
class Admission:
    accepted: bool
    status: str
    record: IntelligenceEnvelope | None
    reasons: list[str]


class ControlPlane:
    """Deterministic front door. Learned systems never bypass this layer."""

    def __init__(self, raw_dir: str | Path | None = None, quarantine_dir: str | Path | None = None) -> None:
        self.raw_dir = Path(raw_dir or os.getenv("RAW_ARCHIVE_DIR", "data/raw"))
        self.quarantine_dir = Path(quarantine_dir or os.getenv("QUARANTINE_DIR", "data/quarantine"))
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.seen: dict[str, str] = {}

    def admit(self, payload: dict) -> Admission:
        if os.getenv("REQUIRE_SIGNED_RECORDS", "false").lower() == "true":
            secret = os.getenv("CONTROL_HMAC_SECRET")
            signature = payload.get("signature")
            unsigned = dict(payload); unsigned.pop("signature", None)
            expected = hmac.new((secret or "").encode(), json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
            if not secret or not signature or not hmac.compare_digest(str(signature), expected):
                self._archive(self.quarantine_dir, payload, "invalid_signature")
                return Admission(False, "quarantined_signature", None, ["missing or invalid HMAC signature"])
        try:
            record = IntelligenceEnvelope.from_dict(payload)
        except (ValueError, TypeError, KeyError) as error:
            self._archive(self.quarantine_dir, payload, "invalid")
            return Admission(False, "quarantined_invalid", None, [str(error)])
        previous_hash = self.seen.get(record.record_id)
        if previous_hash == record.payload_hash:
            return Admission(False, "duplicate", record, ["identical record_id and payload hash"])
        if previous_hash and previous_hash != record.payload_hash:
            self._archive(self.quarantine_dir, payload, "record_id_collision")
            return Admission(False, "quarantined_collision", record, ["record_id reused with different payload"])
        self.seen[record.record_id] = record.payload_hash
        self._archive(self.raw_dir, record.to_dict(), "accepted")
        return Admission(True, "accepted", record, [])

    @staticmethod
    def _archive(directory: Path, payload: dict, prefix: str) -> None:
        identity = str(payload.get("record_id") or payload.get("source", {}).get("provider_record_id") or "unknown")
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in identity)[:120]
        path = directory / f"{prefix}-{safe}.json"
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
