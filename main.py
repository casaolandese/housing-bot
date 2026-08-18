"""Housing bot entry point.

Flow: collect -> cheap filter -> enrich survivors -> strict filter -> dedup ->
notify -> persist. Enrichment sits after the cheap filter on purpose: detail
pages cost one request each, and we only want to spend them on listings that
already match price, city and move-in window.
"""
import argparse
import logging
import sys
from typing import List

from src import config, filters, notifier, storage
from src.parsers.base import Listing
from src.parsers.directwonen import DirectWonenParser
from src.parsers.kamernet import KamernetParser
from src.parsers.pararius import ParariusParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

PARSERS = [KamernetParser, DirectWonenParser, ParariusParser]


def collect_all() -> List[Listing]:
    found: List[Listing] = []
    for cls in PARSERS:
        if not getattr(cls, "enabled", True):
            log.info("%s: disabled, skipping", cls.source)
            continue
        found.extend(cls().run())
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Amsterdam/Utrecht room alert bot")
    ap.add_argument("--dry-run", action="store_true", help="never send email")
    ap.add_argument("--no-store", action="store_true", help="do not persist state")
    ap.add_argument("--limit", type=int, default=0, help="cap enrichment (testing)")
    args = ap.parse_args()
    if args.dry_run:
        config.DRY_RUN = True

    seen = storage.load()
    first_run = not seen
    log.info("state: %d listings seen previously%s",
             len(seen), " (FIRST RUN)" if first_run else "")

    listings = collect_all()
    if not listings:
        log.warning("no listings collected from any source - check for blocks")
        return 1

    # Dedup before enrichment so we never re-fetch detail pages we've seen.
    fresh = storage.new_only(listings, seen)
    log.info("%d of %d are new since last run", len(fresh), len(listings))
    if not fresh:
        return 0

    candidates = filters.apply_filters(fresh, stage="cheap")
    if args.limit:
        candidates = candidates[:args.limit]

    enriched: List[Listing] = []
    by_source = {cls.source: cls for cls in PARSERS}
    parser_cache = {}
    for listing in candidates:
        cls = by_source.get(listing.source)
        if cls and getattr(cls, "detail_fetch", False):
            parser = parser_cache.setdefault(listing.source, cls())
            listing = parser.enrich(listing)
        enriched.append(listing)

    matches = filters.apply_filters(enriched, stage="full")
    # Re-check price after enrichment: the detail page is authoritative.
    matches = [m for m in matches
               if m.price is not None and m.price <= config.MAX_RENT]

    log.info("=> %d listings to notify about", len(matches))
    for m in matches:
        log.info("   EUR %-5s %-9s %-32s %s", m.price, m.city, m.title[:32], m.url)

    sent = notifier.notify(matches, first_run=first_run) if matches else 0
    log.info("emails sent: %d", sent)

    if not args.no_store:
        # Record every listing we evaluated, not just matches, so rejects are
        # never re-examined on the next run.
        storage.record(seen, fresh, notified=False)
        storage.record(seen, matches, notified=bool(sent))
        storage.save(storage.prune(seen))
        log.info("state saved: %d entries", len(seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
