"""Pararius parser - currently inert.

Pararius (and its sibling huurwoningen.nl) return HTTP 403 to any non-browser
client, verified before implementation. There is no parsing bug to fix here:
the response never contains listings. The parser is kept so the plug-in
architecture stays complete and so it can be revived if the block is lifted,
but it reports the block and returns nothing rather than failing the run.
"""
import logging
from typing import List

from src.parsers.base import BaseParser, Listing

log = logging.getLogger(__name__)

SEARCH = "https://www.pararius.com/apartments/{city}/0-{max_rent}"


class ParariusParser(BaseParser):
    source = "pararius"
    enabled = False  # flip to True if Pararius ever stops blocking

    def collect(self) -> List[Listing]:
        log.info("pararius: skipped - site blocks automated clients (HTTP 403)")
        return []
