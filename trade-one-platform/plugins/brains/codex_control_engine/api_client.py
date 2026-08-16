from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

from .control_plane import Admission, ControlPlane


class OwnedApiConsumer:
    """Cursor-based consumer for the owner's sports API with replay checkpoints."""

    def __init__(self, control: ControlPlane | None = None) -> None:
        self.base_url = os.environ["UPSTREAM_BASE_URL"].rstrip("/")
        self.api_key = os.environ["UPSTREAM_API_KEY"]
        self.path = os.getenv("UPSTREAM_BATCH_PATH", "/v1/intelligence/training-events")
        self.timeout = int(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60"))
        self.control = control or ControlPlane()

    def fetch(self, cursor: str | None = None, limit: int = 1000) -> tuple[list[dict], str | None]:
        query = urllib.parse.urlencode({"cursor": cursor or "", "limit": limit})
        request = urllib.request.Request(
            f"{self.base_url}{self.path}?{query}",
            headers={"X-Axiom-Key": self.api_key, "Accept": "application/json"},
        )
        for attempt in range(7):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                return list(payload.get("records", [])), payload.get("next_cursor")
            except urllib.error.HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 6: raise
                retry_after = float(error.headers.get("Retry-After", 0) or 0)
                time.sleep(max(retry_after, min(30, 2 ** attempt + random.random())))
        raise RuntimeError("unreachable")

    def consume(self, cursor: str | None = None, until_exhausted: bool = True) -> Iterator[tuple[list[Admission], str | None]]:
        while True:
            records, next_cursor = self.fetch(cursor)
            admissions = [self.control.admit(payload) for payload in records]
            yield admissions, next_cursor
            if not until_exhausted or not next_cursor or next_cursor == cursor: break
            cursor = next_cursor


class CursorFile:
    def __init__(self, path: str | Path = "data/replay_cursor.json") -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> str | None:
        return json.loads(self.path.read_text()).get("cursor") if self.path.exists() else None

    def write(self, cursor: str | None) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"cursor": cursor, "updated_at": time.time()}))
        temporary.replace(self.path)
