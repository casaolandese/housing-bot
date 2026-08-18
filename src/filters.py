"""Rule engine deciding whether a listing is worth an alert.

Design principle: reject only on positive evidence. A listing that simply does
not state a gender or occupation preference is ACCEPTED - in the Dutch market
most listings say nothing, and rejecting silence would discard almost
everything. We only drop a listing when it explicitly excludes us.
"""
import logging
import re
from datetime import date, datetime
from typing import List, Optional, Tuple

from src import config
from src.parsers.base import Listing

log = logging.getLogger(__name__)

_FEMALE_ONLY = [re.compile(p, re.I) for p in config.FEMALE_ONLY_PATTERNS]
_NO_STUDENTS = [re.compile(p, re.I) for p in config.NO_STUDENT_PATTERNS]
_BANNED_TYPE = [re.compile(p, re.I) for p in config.BANNED_TYPE_PATTERNS]


def _haystack(listing: Listing) -> str:
    return " ".join(filter(None, [
        listing.title, listing.description, listing.room_type,
        listing.gender_pref, listing.occupancy,
    ]))


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def check_cheap(listing: Listing) -> Tuple[bool, str]:
    """Filters that need no extra HTTP request. Run before enrichment."""
    if listing.price is None:
        return False, "no price found"
    if listing.price > config.MAX_RENT:
        return False, f"price EUR{listing.price} > EUR{config.MAX_RENT}"
    if listing.city and listing.city.strip().lower() not in config.CITY_ALLOWLIST:
        return False, f"city '{listing.city}' outside target areas"
    if listing.surface_area is not None and listing.surface_area < config.MIN_SURFACE:
        return False, f"surface {listing.surface_area}m2 implausible"

    for pat in _BANNED_TYPE:
        if pat.search(_haystack(listing)):
            return False, f"non-residential type ({pat.pattern})"

    available = _parse_date(listing.available_from)
    if available:
        latest = _parse_date(config.MOVE_IN_LATEST)
        # Anything available now or earlier than the window is fine (we can
        # move in immediately); only listings starting AFTER October are out.
        if latest and available > latest:
            return False, f"available {listing.available_from}, after move-in window"
    return True, "ok"


def check_full(listing: Listing) -> Tuple[bool, str]:
    """Eligibility checks that rely on detail-page text (gender, occupation)."""
    hay = _haystack(listing)

    if listing.gender_pref and listing.gender_pref.strip().lower() == "female":
        return False, "landlord wants a female tenant"
    for pat in _FEMALE_ONLY:
        if pat.search(hay):
            return False, f"female-only listing ({pat.pattern})"

    occ = (listing.occupancy or "").lower()
    # Inclusive phrasings ("everyone welcome", "no preference") are a green
    # light, not a restriction - only treat occupation as a filter when the
    # landlord names specific groups and students are not among them.
    inclusive = any(w in occ for w in
                    ("everyone", "anyone", "all ", "no preference", "not important"))
    if occ and not inclusive and "student" not in occ:
        return False, f"tenant must be: {listing.occupancy}"
    for pat in _NO_STUDENTS:
        if pat.search(hay):
            return False, f"students excluded ({pat.pattern})"
    return True, "ok"


def apply_filters(listings: List[Listing], stage: str = "cheap") -> List[Listing]:
    check = check_cheap if stage == "cheap" else check_full
    kept = []
    for listing in listings:
        ok, reason = check(listing)
        if ok:
            kept.append(listing)
        else:
            log.debug("reject [%s] %s (%s): %s", stage, listing.key, listing.title, reason)
    log.info("filter[%s]: %d/%d kept", stage, len(kept), len(listings))
    return kept
