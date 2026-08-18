"""Kamernet parser.

Kamernet is a Next.js app that server-renders its search results as JSON inside
the __NEXT_DATA__ script tag, so we read structured data instead of scraping the
DOM. That makes this parser immune to CSS/redesign churn.

Verified against the live site: query params are camelCase and only some are
honoured. `searchCategories=1` (rooms) and `pageNo` work; `maxRent`, `radius`
and `suitableForGenders` are silently ignored, so price / city / gender are all
enforced client-side instead.
"""
import json
import logging
import re
from typing import List, Optional

from src import config
from src.parsers.base import BaseParser, Listing

log = logging.getLogger(__name__)

BASE = "https://kamernet.nl"
SEARCH = BASE + "/en/for-rent/rooms-{city}"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
TAG_RE = re.compile(r"<[^>]+>")

# Verified from live listing URLs: /en/for-rent/room-amsterdam/<street>/room-<id>
LISTING_TYPES = {1: "room", 2: "apartment", 3: "studio", 4: "anti-squat"}
TYPE_LABEL = {1: "Room", 2: "Apartment", 3: "Studio", 4: "Anti-squat"}


def _next_data(html: str) -> Optional[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html))


def _iso_date(value: Optional[str]) -> Optional[str]:
    return value.split("T")[0] if isinstance(value, str) and "T" in value else value


class KamernetParser(BaseParser):
    source = "kamernet"
    detail_fetch = True

    def collect(self) -> List[Listing]:
        out: List[Listing] = []
        seen_ids = set()
        for city in config.CITIES:
            for page in range(1, config.PAGES_PER_CITY + 1):
                html = self.get(
                    SEARCH.format(city=city),
                    params={"searchCategories": 1, "pageNo": page},
                )
                data = _next_data(html)
                if not data:
                    log.warning("kamernet: no __NEXT_DATA__ for %s p%d", city, page)
                    continue
                try:
                    resp = (data["props"]["pageProps"]["targetPageProps"]
                                ["findListingsResponse"])
                except (KeyError, TypeError):
                    log.warning("kamernet: unexpected JSON shape for %s p%d", city, page)
                    continue
                # topAdListings are paid promotions, deliberately excluded
                for raw in resp.get("listings") or []:
                    if raw.get("isTopAdvert"):
                        continue
                    listing = self._to_listing(raw)
                    if listing and listing.listing_id not in seen_ids:
                        seen_ids.add(listing.listing_id)
                        out.append(listing)
        return out

    def _to_listing(self, raw: dict) -> Optional[Listing]:
        lid = raw.get("listingId")
        if not lid:
            return None
        ltype = raw.get("listingType") or 1
        slug = LISTING_TYPES.get(ltype, "room")
        city_slug = raw.get("citySlug") or ""
        street_slug = raw.get("streetSlug") or ""
        url = f"{BASE}/en/for-rent/{slug}-{city_slug}/{street_slug}/{slug}-{lid}"

        street = (raw.get("street") or "").strip()
        city = (raw.get("city") or city_slug).strip()
        area = raw.get("surfaceArea")
        title = ", ".join(p for p in (street, city) if p) or f"{TYPE_LABEL.get(ltype,'Room')} {lid}"

        return Listing(
            source=self.source,
            listing_id=str(lid),
            url=url,
            title=title,
            city=city,
            street=street,
            price=raw.get("totalRentalPrice"),
            utilities_included=raw.get("utilitiesIncluded"),
            surface_area=area,
            room_type=TYPE_LABEL.get(ltype, "Room"),
            available_from=_iso_date(raw.get("availabilityStartDate")),
            available_until=_iso_date(raw.get("availabilityEndDate")),
            image_url=raw.get("resizedFullPreviewImageUrl") or raw.get("thumbnailUrl") or "",
        )

    # --- detail -------------------------------------------------------------
    def enrich(self, listing: Listing) -> Listing:
        """Pull the fields only the detail page carries: real title, English
        description, tenant-gender preference, deposit, housemates, landlord."""
        try:
            html = self.get(listing.url)
        except Exception as exc:  # noqa: BLE001
            log.warning("kamernet: enrich failed for %s: %s", listing.listing_id, exc)
            return listing

        data = _next_data(html)
        d = {}
        if data:
            try:
                d = data["props"]["pageProps"]["targetPageProps"]["listingDetails"] or {}
            except (KeyError, TypeError):
                d = {}

        if d:
            listing.title = (d.get("englishTitle") or d.get("dutchTitle")
                             or listing.title).strip()
            desc = (d.get("englishDescription") or d.get("dutchDescription") or "")
            listing.description = re.sub(r"\s+", " ", desc).strip()
            listing.deposit = d.get("deposit")
            listing.registration_cost = d.get("registrationCost")
            listing.postal_code = d.get("postalCode") or ""
            listing.landlord = d.get("landlordDisplayName") or ""
            listing.published = _iso_date(d.get("publishDate")) or listing.published
            listing.viewing_date = _iso_date(d.get("viewingDate"))
            listing.street = d.get("computedStreetName") or listing.street
            listing.city = d.get("computedCityName") or listing.city
            if d.get("totalRentalPrice"):
                listing.price = d["totalRentalPrice"]
            if d.get("surfaceArea"):
                listing.surface_area = d["surfaceArea"]
            listing.available_from = _iso_date(d.get("availabilityStartDate")) or listing.available_from
            listing.available_until = _iso_date(d.get("availabilityEndDate")) or listing.available_until

        # The gender / occupation preferences are rendered as human-readable
        # text rather than exposed as decoded enums, so read them from there.
        text = _plain_text(html)
        listing.gender_pref = self._match(text, r"Gender\s+(Not important|No preference|Male|Female|Mixed)")
        listing.occupancy = self._match(text, r"Occupation\s+([A-Za-z ,]{3,60}?)\s+Languages")
        listing.age_range = self._match(text, r"Age\s+(\d{1,2}\s*-\s*\d{1,2})\s*years")
        mates = re.search(r"(\d+)\s+roommates?\s+(Mixed gender|Male|Female)\s+roommates", text)
        if mates:
            listing.housemates = f"{mates.group(1)} x {mates.group(2).lower()}"
        listing.furnished = self._match(text, r"\b(Furnished|Unfurnished|Upholstered)\b")
        listing.enriched = True
        return listing

    @staticmethod
    def _match(text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""
