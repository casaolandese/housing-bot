"""Shared HTTP plumbing and the Listing shape every parser emits."""
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, List

import requests

from src import config

log = logging.getLogger(__name__)


class BlockedError(Exception):
    """Site actively refused us (403 / bot wall). Not worth retrying this run."""


@dataclass
class Listing:
    """Normalised listing. Optional fields stay None so the email can skip them."""
    source: str
    listing_id: str
    url: str
    title: str = ""
    city: str = ""
    street: str = ""
    postal_code: str = ""
    price: Optional[int] = None
    utilities_included: Optional[bool] = None
    deposit: Optional[int] = None
    registration_cost: Optional[int] = None
    surface_area: Optional[int] = None
    room_type: str = "Room"
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    furnished: str = ""
    gender_pref: str = ""
    housemates: str = ""
    occupancy: str = ""
    age_range: str = ""
    landlord: str = ""
    published: Optional[str] = None
    viewing_date: Optional[str] = None
    description: str = ""
    image_url: str = ""
    enriched: bool = False

    @property
    def key(self) -> str:
        return f"{self.source}:{self.listing_id}"

    @property
    def price_display(self) -> str:
        if self.price is None:
            return "n/a"
        suffix = " incl." if self.utilities_included else ""
        return f"€{self.price}{suffix}"

    def as_dict(self) -> dict:
        return asdict(self)


class BaseParser(ABC):
    """Subclass this to add a site. Implement `collect()`; the rest is provided."""

    source: str = "base"
    #: set False for sites that need a per-listing detail fetch
    detail_fetch: bool = False

    def __init__(self):
        self.session = requests.Session()

    # --- HTTP ---------------------------------------------------------------
    def headers(self) -> dict:
        return {
            "User-Agent": random.choice(config.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

    def get(self, url: str, params: Optional[dict] = None) -> str:
        """GET with exponential backoff. 403 raises immediately: a bot wall is
        not a transient fault, and retrying it only deepens the block."""
        last = None
        for attempt in range(config.MAX_RETRIES):
            try:
                r = self.session.get(
                    url, params=params, headers=self.headers(),
                    timeout=config.REQUEST_TIMEOUT,
                )
                if r.status_code == 403:
                    raise BlockedError(f"{self.source}: 403 for {url}")
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"status {r.status_code}")
                r.raise_for_status()
                return r.text
            except BlockedError:
                raise
            except Exception as exc:  # noqa: BLE001 - retry any transport error
                last = exc
                if attempt < config.MAX_RETRIES - 1:
                    delay = (config.BACKOFF_BASE ** attempt) + random.uniform(0, 0.8)
                    log.warning("%s: %s (retry %d/%d in %.1fs)", self.source, exc,
                                attempt + 1, config.MAX_RETRIES, delay)
                    time.sleep(delay)
        raise RuntimeError(f"{self.source}: giving up on {url}: {last}")

    # --- Contract -----------------------------------------------------------
    @abstractmethod
    def collect(self) -> List[Listing]:
        """Return listings from search pages (cheap fields only)."""

    def enrich(self, listing: Listing) -> Listing:
        """Fetch per-listing detail. Called only for listings that already
        passed the cheap filters, so we never spend requests on rejects."""
        return listing

    def run(self) -> List[Listing]:
        try:
            found = self.collect()
            log.info("%s: %d listings from search", self.source, len(found))
            return found
        except BlockedError as exc:
            log.warning("%s BLOCKED: %s", self.source, exc)
            return []
        except Exception as exc:  # noqa: BLE001 - one dead site must not kill the run
            log.error("%s failed: %s", self.source, exc)
            return []
