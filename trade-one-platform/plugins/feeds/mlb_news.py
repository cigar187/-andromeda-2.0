"""MLB news feed — multi-source RSS aggregation.

Each nested sub-source (MLB Trade Rumors, CBS Sports, ESPN) is its own swappable
adapter per M1. Publishes `news_ingested` events with TextDocument-shaped bodies.

Dedup: SHA256 of (source_url + title) — same story published twice by the same
outlet across polls is emitted once.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from trade_one.event_log import get_default_log
from trade_one.interfaces import ComponentManifest, FeedAdapter

log = logging.getLogger("feed.mlb_news")
UA = "trade-one-feeds/0.1"


DEFAULT_SOURCES = (
    {"id": "mlbtraderumors", "url": "https://www.mlbtraderumors.com/feed"},
    {"id": "cbssports_mlb", "url": "https://www.cbssports.com/rss/headlines/mlb/"},
    {"id": "espn_mlb", "url": "https://www.espn.com/espn/rss/mlb/news"},
)


def _fetch(url: str, timeout: int = 30) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log.error(f"GET {url} failed: {e!r}")
        return None


class RSSParseError(Exception):
    """RSS body could not be parsed. Distinct from 'RSS was valid but had zero
    items'. Rule-4: don't substitute [] for a parse failure — raise so the
    per-feed caller can decide to skip this cycle vs abort.
    """


def _parse_rss_items(xml_bytes: bytes) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.error(f"RSS parse failed: {e!r}")
        raise RSSParseError(str(e)) from e
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "dc": "http://purl.org/dc/elements/1.1/",
          "content": "http://purl.org/rss/1.0/modules/content/"}
    items = []
    # RSS 2.0
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        desc = (it.findtext("description") or "").strip()
        body = (it.findtext("content:encoded", namespaces=ns) or desc or "").strip()
        author = (it.findtext("dc:creator", namespaces=ns) or it.findtext("author") or "").strip()
        if title or link:
            items.append({"title": title, "link": link, "published_at": pub, "body": body, "author": author})
    # Atom fallback
    if not items:
        for it in root.findall(".//atom:entry", ns):
            title = (it.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = it.find("atom:link", ns)
            link = link_el.get("href", "").strip() if link_el is not None else ""
            pub = (it.findtext("atom:updated", namespaces=ns)
                   or it.findtext("atom:published", namespaces=ns) or "").strip()
            body = (it.findtext("atom:content", namespaces=ns)
                    or it.findtext("atom:summary", namespaces=ns) or "").strip()
            items.append({"title": title, "link": link, "published_at": pub, "body": body, "author": ""})
    return items


def _dedup_key(source_id: str, title: str, link: str) -> str:
    return hashlib.sha256(f"{source_id}|{link}|{title}".encode("utf-8")).hexdigest()


def _rss_pub_to_iso(pub: str) -> str:
    """RFC-2822 style RSS pubDate -> ISO 8601 UTC. Returns "" if unparseable."""
    if not pub:
        return ""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        # ISO already?
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return ""


class MlbNewsFeed(FeedAdapter):
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.sources = list(settings.get("sources", DEFAULT_SOURCES))
        self.event_log = get_default_log(settings.get("event_log_root", "/opt/trade-one/data/events"))
        self.dedup_state_path = Path(settings.get("dedup_state_path",
                                                   "/opt/trade-one/data/feeds/mlb_news_seen.json"))
        self.dedup_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._version = "0.1.0"

    @property
    def manifest(self) -> ComponentManifest:
        return ComponentManifest(
            component_id="feed.mlb.news",
            version=self._version,
            contract_version="1.0",
            kind="feed_adapter",
            capabilities=("mlb", "news", "rss"),
        )

    def _load_seen(self) -> set[str]:
        if not self.dedup_state_path.exists():
            return set()
        try:
            return set(json.loads(self.dedup_state_path.read_text()))
        except Exception:
            return set()

    def _save_seen(self, seen: set[str]) -> None:
        # Cap the set at 10k to keep the file bounded
        MAX = 10_000
        if len(seen) > MAX:
            seen = set(list(seen)[-MAX:])
        self.dedup_state_path.write_text(json.dumps(sorted(seen)))

    def poll(self) -> int:
        seen = self._load_seen()
        n_emitted = 0
        for src in self.sources:
            src_id = src["id"]
            src_url = src["url"]
            raw = _fetch(src_url)
            if not raw:
                continue
            try:
                items = _parse_rss_items(raw)
            except RSSParseError:
                # Already ERROR-logged inside _parse_rss_items; skip THIS source
                # for this poll cycle, other sources retain a fresh attempt.
                continue
            for it in items:
                key = _dedup_key(src_id, it["title"], it["link"])
                if key in seen:
                    continue
                seen.add(key)
                published_iso = _rss_pub_to_iso(it["published_at"])
                self.event_log.emit(
                    kind="news_ingested",
                    source=f"{self.manifest.component_id}:{src_id}",
                    payload={
                        "sport": "mlb",
                        "source_site": src_id,
                        "source_url": src_url,
                        "article_url": it["link"],
                        "title": it["title"],
                        "body": it["body"],
                        "author": it["author"],
                        "published_at": published_iso,
                        "raw_published_at": it["published_at"],
                    },
                    component_version=f"{self.manifest.component_id}:{self._version}",
                    correlation_id=f"news:mlb:{src_id}:{key[:16]}",
                )
                n_emitted += 1
        self._save_seen(seen)
        return n_emitted


def mlb_news(settings: dict) -> MlbNewsFeed:
    return MlbNewsFeed(settings)
