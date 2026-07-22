"""A source that reads a retailer product feed (XML) and yields ``Listing``s.

Affiliate networks (Daisycon, TradeTracker, Awin) and many retailers publish
product feeds that are built to be consumed by machines. They typically include
price, the original ``was`` price, and the EAN barcode: exactly the fields the
matching stage needs, with no JavaScript rendering and no anti-bot walls to
fight. That is why this is the first real source (see
docs/adr/0002-first-source-feed-over-scrape.md).

Every feed uses different element names, so instead of hard-coding one layout we
drive parsing with a ``FeedFieldMap``: a small description of which feed tag maps
to which ``Listing`` field. One adapter class then handles many feeds by
configuration rather than by copy-pasting a new class each time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

from ..models import Condition, Listing, Region
from .base import SourceAdapter

# A polite, identifying User-Agent. Telling a site who you are is good manners
# and makes you easy to contact or rate-limit rather than silently block.
USER_AGENT = "PriceSniper/0.2 (+https://github.com/leblancbakor/pricesniper)"

# Feed condition strings we recognise, mapped onto our enum. Anything unlisted
# falls back to the map's default (retail feeds are usually new goods).
_CONDITION_WORDS = {
    "new": Condition.NEW,
    "nieuw": Condition.NEW,
    "refurbished": Condition.REFURBISHED,
    "gereviseerd": Condition.REFURBISHED,
    "open_box": Condition.OPEN_BOX,
    "used": Condition.USED,
    "tweedehands": Condition.USED,
}

# Strings that mean "you can buy it right now". Everything else counts as
# out of stock.
_IN_STOCK_WORDS = {
    "in_stock", "instock", "in stock", "op voorraad", "leverbaar",
    "1", "true", "yes", "available", "y",
}


@dataclass(frozen=True)
class FeedFieldMap:
    """Describes how one feed's tags line up with our ``Listing`` fields.

    Only ``title``, ``price`` and ``url`` are required for a usable listing; the
    rest are optional and simply skipped if the feed does not provide them. Set
    the tag name to ``None`` (the default) for anything the feed lacks.
    """

    # The repeating element that wraps one product, e.g. <product> or <item>.
    product_tag: str = "product"

    # Identity (at least one should be present for the item to be matchable).
    ean: str | None = "ean"
    upc: str | None = None
    mpn: str | None = None

    # Description.
    title: str = "name"
    brand: str | None = "brand"
    category: str | None = "category"
    condition: str | None = "condition"

    # Commercial.
    price: str = "price"
    was_price: str | None = "price_old"
    currency: str | None = "currency"
    url: str = "url"
    image_url: str | None = "image"
    stock: str | None = "stock"

    # Behaviour toggles / fallbacks.
    currency_default: str = "EUR"
    condition_default: Condition = Condition.NEW
    decimal_comma: bool = True  # EU feeds usually write prices like "1.299,00"

    # Tags whose text we still want even when the toggles above are off.
    _required: tuple[str, ...] = field(default=("title", "price", "url"), repr=False)


class FeedSource(SourceAdapter):
    """Reads a product feed from a URL or local file and normalises it."""

    def __init__(
        self,
        location: str | Path,
        field_map: FeedFieldMap,
        *,
        name: str = "feed",
        region: Region = Region.EU,
        seller: str = "unknown",
    ) -> None:
        # A feed is one retailer's catalogue, so the seller is constant and set
        # once here rather than read per product.
        self.location = location
        self.field_map = field_map
        self.name = name
        self.region = region
        self.seller = seller

    async def fetch(self) -> list[Listing]:
        raw = await self._read()
        root = ElementTree.fromstring(raw)

        listings: list[Listing] = []
        for node in root.iter(self.field_map.product_tag):
            listing = self._parse_product(node)
            if listing is not None:
                listings.append(listing)
        return listings

    async def _read(self) -> bytes:
        """Return the raw feed bytes from a URL or a local file."""
        loc = str(self.location)
        if loc.startswith(("http://", "https://")):
            # Imported lazily so file-based use does not require httpx at all.
            import httpx

            async with httpx.AsyncClient(
                timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            ) as client:
                resp = await client.get(loc)
                resp.raise_for_status()
                return resp.content
        return Path(self.location).read_bytes()

    def _parse_product(self, node: ElementTree.Element) -> Listing | None:
        """Turn one feed element into a ``Listing``, or ``None`` if unusable.

        A single malformed product should never crash the whole run, so we skip
        it and carry on rather than raising.
        """
        fm = self.field_map
        try:
            title = self._text(node, fm.title)
            url = self._text(node, fm.url)
            price_raw = self._text(node, fm.price)
            if not (title and url and price_raw):
                return None  # missing a required field

            return Listing(
                ean=self._text(node, fm.ean),
                upc=self._text(node, fm.upc),
                mpn=self._text(node, fm.mpn),
                title=title,
                brand=self._text(node, fm.brand),
                category=self._text(node, fm.category),
                condition=self._parse_condition(self._text(node, fm.condition)),
                price=self._parse_price(price_raw),
                currency=(self._text(node, fm.currency) or fm.currency_default).upper(),
                was_price=self._parse_optional_price(self._text(node, fm.was_price)),
                url=url,
                image_url=self._text(node, fm.image_url),
                seller=self.seller,
                in_stock=self._parse_stock(self._text(node, fm.stock)),
                source=self.name,
                region=self.region,
            )
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _text(node: ElementTree.Element, tag: str | None) -> str | None:
        """Read a child tag's stripped text, or ``None`` if absent/empty."""
        if tag is None:
            return None
        child = node.find(tag)
        if child is None or child.text is None:
            return None
        text = child.text.strip()
        return text or None

    def _parse_price(self, raw: str) -> Decimal:
        """Parse a feed price string into an exact ``Decimal``.

        Feeds are messy: "EUR 1.299,00", "129,00", "89.00" all show up. We strip
        anything that is not a digit or separator, then normalise the decimal
        mark based on the feed's convention.
        """
        cleaned = re.sub(r"[^\d.,]", "", raw)
        if self.field_map.decimal_comma:
            # "1.299,00" -> drop thousands dots, turn the comma into the point.
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # "1,299.00" -> drop thousands commas.
            cleaned = cleaned.replace(",", "")
        if not cleaned:
            raise ValueError(f"no numeric price in {raw!r}")
        return Decimal(cleaned)

    def _parse_optional_price(self, raw: str | None) -> Decimal | None:
        if not raw:
            return None
        try:
            return self._parse_price(raw)
        except (InvalidOperation, ValueError):
            return None

    def _parse_condition(self, raw: str | None) -> Condition:
        if not raw:
            return self.field_map.condition_default
        return _CONDITION_WORDS.get(raw.strip().lower(), self.field_map.condition_default)

    @staticmethod
    def _parse_stock(raw: str | None) -> bool:
        if raw is None:
            return True  # assume buyable unless the feed says otherwise
        return raw.strip().lower() in _IN_STOCK_WORDS
