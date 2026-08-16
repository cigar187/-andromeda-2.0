"""Feed runner — config-driven. Loads registered FeedAdapter factories from a JSON
config, calls .poll() on each, emits a run-summary event.

Config shape (extends trade-one.json OR standalone feeds config file):
{
  "feeds": {
    "<slot_id>": {"factory": "module.path:factory_name", "settings": {...}},
    ...
  }
}

No hard-wiring: adding/replacing a feed = one config line. Zero code change here.
"""
from __future__ import annotations

import importlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from .event_log import get_default_log
from .interfaces import FeedAdapter

log = logging.getLogger("feeds_runner")


def load_feeds(config_path: str | Path) -> dict[str, FeedAdapter]:
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    feeds_section = payload.get("feeds", {})
    adapters: dict[str, FeedAdapter] = {}
    for slot_id, spec in feeds_section.items():
        factory_str = spec["factory"]
        module_name, attribute = factory_str.split(":", 1)
        factory = getattr(importlib.import_module(module_name), attribute)
        instance = factory(dict(spec.get("settings", {})))
        if not isinstance(instance, FeedAdapter):
            raise TypeError(f"{factory_str} did not return a FeedAdapter")
        adapters[slot_id] = instance
    return adapters


def run_all(config_path: str | Path, event_log_root: str = "/opt/trade-one/data/events"
            ) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info(f"loading feeds from {config_path}")
    adapters = load_feeds(config_path)
    log.info(f"loaded {len(adapters)} feeds: {list(adapters.keys())}")

    per_feed: dict[str, dict[str, Any]] = {}
    event_log = get_default_log(event_log_root)
    for slot_id, adapter in adapters.items():
        t0 = time.monotonic()
        try:
            n = adapter.poll()
            per_feed[slot_id] = {"ok": True, "events_emitted": n, "elapsed_s": round(time.monotonic() - t0, 2)}
            log.info(f"[{slot_id}] emitted {n} events in {per_feed[slot_id]['elapsed_s']}s")
        except Exception as e:
            per_feed[slot_id] = {"ok": False, "error": repr(e), "elapsed_s": round(time.monotonic() - t0, 2)}
            log.error(f"[{slot_id}] FAILED: {e!r}")

    summary = {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config_path": str(config_path),
        "n_feeds": len(adapters),
        "per_feed": per_feed,
    }
    event_log.emit(
        kind="signal_emitted",
        source="feeds_runner",
        payload={"kind": "feed_run_summary", **summary},
        component_version="feeds_runner:0.1.0",
    )
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default="config/feeds.json")
    ap.add_argument("--event-log-root", type=str, default="/opt/trade-one/data/events")
    args = ap.parse_args()
    result = run_all(args.config, args.event_log_root)
    print(json.dumps(result, indent=2))
