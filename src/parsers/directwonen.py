"""DirectWonen parser.

Plain server-rendered HTML, so this one genuinely needs BeautifulSoup. Detail
URLs follow /huurwoningen-huren/<city>/<street>/<type>-<id>, verified live.
Parsing is anchor-driven rather than class-driven: we locate listing links by
their URL shape (stable) and then read facts out of the surrounding card, so a
CSS class rename cannot break us.
"""
import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from src import config
from src.parsers.base import BaseParser, Listing

log = logging.getLogger(__name__)

BASE = "https://directwonen.nl"
SEARCH = BASE + "/huurwoningen-huren/{city}"
DETAIL_RE = re.compile(
    r"/huurwoningen-huren/([a-z0-9\-\.]+)/([a-z0-9\-\.]+)/(kamer|studio|appartement|woning)-(\d+)",
    re.I,
)
WANTED_TYPES = {"kamer", "studio"}  # rooms and studios only, never whole homes
TYPE_LABEL = {"kamer": "Room", "studio": "Studio"}
PRICE_RE = re.compile(r"€\s*([\d.]{3,7})")
AREA_RE = re.compile(r"(\d{1,3})\s*m[²2]")


class DirectWonenParser(BaseParser):
    source = "directwonen"

    def collect(self) -> List[Listing]:
        out: List[Listing] = []
        seen = set()
        for city in config.CITIES:
            html = self.get(SEARCH.format(city=city))
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.find_all("a", href=True):
                m = DETAIL_RE.search(anchor["href"])
                if not m:
                    continue
                city_slug, street_slug, ltype, lid = m.groups()
                ltype = ltype.lower()
                if ltype not in WANTED_TYPES or lid in seen:
                    continue
                seen.add(lid)
                listing = self._from_anchor(anchor, city_slug, street_slug, ltype, lid)
                if listing:
                    out.append(listing)
        return out

    def _from_anchor(self, anchor, city_slug, street_slug, ltype, lid) -> Optional[Listing]:
        card = self._card(anchor)
        text = re.sub(r"\s+", " ", card.get_text(" ", strip=True)) if card else ""

        price = None
        prices = [int(p.replace(".", "")) for p in PRICE_RE.findall(text)]
        # cards show rent plus sometimes deposit/fees; rent is the largest plausible one
        plausible = [p for p in prices if 100 <= p <= 5000]
        if plausible:
            price = max(plausible)

        area = None
        am = AREA_RE.search(text)
        if am:
            area = int(am.group(1))

        street = street_slug.replace("-", " ").title()
        city = city_slug.replace("-", " ").title()
        return Listing(
            source=self.source,
            listing_id=lid,
            url=f"{BASE}/huurwoningen-huren/{city_slug}/{street_slug}/{ltype}-{lid}",
            title=f"{street}, {city}",
            city=city,
            street=street,
            price=price,
            surface_area=area,
            room_type=TYPE_LABEL.get(ltype, "Room"),
            description=text[:400],
        )

    @staticmethod
    def _card(anchor):
        """Walk up a few levels to the card element that holds price/size text."""
        node = anchor
        for _ in range(4):
            if node.parent is None:
                break
            node = node.parent
            if len(node.get_text(strip=True)) > 60:
                return node
        return anchor
