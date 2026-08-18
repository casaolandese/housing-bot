"""Dedup state. Keys are '<source>:<listing_id>' so IDs cannot collide."""
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Dict, Iterable

from src import config
from src.parsers.base import Listing

log = logging.getLogger(__name__)

# Drop entries older than this so the file cannot grow without bound.
RETENTION_DAYS = 120


def load() -> Dict[str, dict]:
    path = config.SEEN_FILE
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        # Never crash the run over a corrupt state file - start fresh, loudly.
        log.error("seen_listings.json unreadable (%s); starting empty", exc)
        return {}


def save(seen: Dict[str, dict]) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    path = config.SEEN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def new_only(listings: Iterable[Listing], seen: Dict[str, dict]):
    return [l for l in listings if l.key not in seen]


def record(seen: Dict[str, dict], listings: Iterable[Listing], notified: bool) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for l in listings:
        seen[l.key] = {
            "first_seen": now,
            "url": l.url,
            "price": l.price,
            "city": l.city,
            "title": l.title,
            "notified": notified,
        }


def prune(seen: Dict[str, dict]) -> Dict[str, dict]:
    cutoff = datetime.now(timezone.utc).timestamp() - RETENTION_DAYS * 86400
    kept = {}
    for key, meta in seen.items():
        try:
            ts = datetime.fromisoformat(meta.get("first_seen", "")).timestamp()
        except ValueError:
            ts = None
        if ts is None or ts >= cutoff:
            kept[key] = meta
    if len(kept) != len(seen):
        log.info("pruned %d expired entries", len(seen) - len(kept))
    return kept
