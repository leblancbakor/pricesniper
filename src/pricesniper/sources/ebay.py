"""A source that pulls live listings from eBay via the Browse API.

This is the adapter your matching stage was built for. eBay's Browse API can
search by GTIN (the barcode), so for each EAN on a watchlist we get back every
live listing for that exact product, from many sellers, with prices. That is
real cross-seller arbitrage: the same item, priced differently across sellers,
which `valuation.py` turns into deals. eBay.nl / eBay.de keep it EU-domestic.

Auth uses the OAuth2 client-credentials flow: the app swaps its key and secret
for a short-lived application token, with no user login involved. See
docs/adr/0005-ebay-browse-api-for-arbitrage.md.
"""

from __future__ import annotations

import asyncio
import base64
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from ..models import Condition, Listing, Region
from .base import SourceAdapter


class BarcodeCache(Protocol):
    """The slice of storage the eBay source needs: remember and recall the
    identity recovered for an item, so repeat runs skip the network lookup.
    ``SQLiteStore`` satisfies this structurally."""

    def get_cached_identity(
        self, item_id: str
    ) -> tuple[str | None, str | None] | None: ...

    def cache_identity(
        self, item_id: str, gtin: str | None, mpn: str | None
    ) -> None: ...

USER_AGENT = "PriceSniper/0.4 (+https://github.com/leblancbakor/pricesniper)"

# Base URLs per environment. Sandbox is for testing with fake data; production
# hits the real marketplace.
_BASE_URLS = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}
_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Which region and currency each eBay marketplace belongs to. Used to tag
# listings and to keep price comparisons within one currency.
_MARKETPLACE_INFO = {
    "EBAY_NL": (Region.EU, "EUR"),
    "EBAY_DE": (Region.EU, "EUR"),
    "EBAY_FR": (Region.EU, "EUR"),
    "EBAY_IT": (Region.EU, "EUR"),
    "EBAY_ES": (Region.EU, "EUR"),
    "EBAY_GB": (Region.UK, "GBP"),
    "EBAY_US": (Region.US, "USD"),
}

# eBay condition text mapped onto our enum. Unknown values fall back to UNKNOWN.
_CONDITION_WORDS = {
    "new": Condition.NEW,
    "new other (see details)": Condition.OPEN_BOX,
    "open box": Condition.OPEN_BOX,
    "certified - refurbished": Condition.REFURBISHED,
    "certified refurbished": Condition.REFURBISHED,
    "excellent - refurbished": Condition.REFURBISHED,
    "seller refurbished": Condition.REFURBISHED,
    "used": Condition.USED,
    "pre-owned": Condition.USED,
}


def read_watchlist(path: str | Path) -> list[str]:
    """Read a watchlist file: one entry per line, ``#`` comments ignored.

    An entry is either a barcode (all digits) or a free-text keyword phrase.
    ``EbaySource`` searches each one the right way.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        code = line.split("#", 1)[0].strip()
        if code:
            out.append(code)
    return out


def is_gtin(entry: str) -> bool:
    """True if the entry looks like a barcode (8 to 14 digits), else it is a
    keyword phrase. Covers EAN-8, UPC-12, EAN-13 and GTIN-14."""
    return entry.isdigit() and 8 <= len(entry) <= 14


class EbaySource(SourceAdapter):
    """Fetches live listings for a watchlist of GTINs from eBay."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        watchlist: list[str],
        *,
        marketplaces: list[str] | None = None,
        environment: str = "production",
        name: str = "ebay",
        per_gtin_limit: int = 20,
        recover_barcodes: bool = True,
        max_lookups: int = 60,
        cache: BarcodeCache | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError(
                "EbaySource needs an app key and secret. Set EBAY_CLIENT_ID and "
                "EBAY_CLIENT_SECRET in your .env."
            )
        if environment not in _BASE_URLS:
            raise ValueError(f"environment must be one of {sorted(_BASE_URLS)}")
        self.client_id = client_id
        self.client_secret = client_secret
        self.watchlist = watchlist
        # One or more marketplaces, searched in turn. Listings from different
        # marketplaces that share a barcode become cross-market arbitrage.
        self.marketplaces = marketplaces or ["EBAY_NL"]
        self.base_url = _BASE_URLS[environment]
        self.name = name
        self.per_gtin_limit = per_gtin_limit
        # Keyword search summaries often omit the barcode even when the full
        # listing has one. Recovery fetches item detail to fill it in, so
        # cross-seller matching can work. Capped to protect the API quota.
        self.recover_barcodes = recover_barcodes
        self.max_lookups = max_lookups
        self.cache = cache
        self._lookups_done = 0
        self._token: str | None = None
        self._token_expiry: float = 0.0

    @staticmethod
    def _region_for(marketplace: str) -> Region:
        return _MARKETPLACE_INFO.get(marketplace, (Region.EU, "EUR"))[0]

    async def fetch(self) -> list[Listing]:
        import httpx

        self._lookups_done = 0
        listings: list[Listing] = []
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            token = await self._get_token(client)
            for marketplace in self.marketplaces:
                region = self._region_for(marketplace)
                # Tag the source with the marketplace, e.g. "ebay-de", so it is
                # clear where each listing (and each deal) came from.
                source = f"{self.name}-{marketplace.split('_')[-1].lower()}"
                for entry in self.watchlist:
                    query = {"gtin": entry} if is_gtin(entry) else {"q": entry}
                    fallback_ean = entry if is_gtin(entry) else None
                    data = await self._search(client, token, marketplace, query)
                    summaries = data.get("itemSummaries", [])
                    if self.recover_barcodes:
                        await self._recover_barcodes(
                            client, token, marketplace, summaries
                        )
                    listings.extend(
                        self._parse_search_response(
                            {"itemSummaries": summaries},
                            fallback_ean,
                            source,
                            region,
                        )
                    )
        return listings

    async def _recover_barcodes(self, client, token, marketplace, summaries) -> None:
        """Fill in missing barcodes for summaries that lack one. Cached items are
        applied for free; only genuinely new items cost a network lookup and count
        against the per-run cap. Newly resolved items are written to the cache, so
        coverage accumulates across runs. Enriches summary dicts in place."""
        candidates = [
            s
            for s in summaries
            if not s.get("gtin") and not s.get("mpn") and s.get("itemId")
        ]

        # Apply anything we already know; queue the rest for a lookup.
        to_fetch: list[dict] = []
        for s in candidates:
            cached = (
                self.cache.get_cached_identity(s["itemId"]) if self.cache else None
            )
            if cached is not None:
                self._apply_identity(s, cached[0], cached[1])
            else:
                to_fetch.append(s)

        remaining = self.max_lookups - self._lookups_done
        to_fetch = to_fetch[:remaining]
        if not to_fetch:
            return

        # Bound concurrency so we stay polite to the API.
        sem = asyncio.Semaphore(5)

        async def one(summary: dict) -> None:
            async with sem:
                detail = await self._get_item(
                    client, token, marketplace, summary["itemId"]
                )
            gtin, mpn = self._identity_from_item(detail)
            self._apply_identity(summary, gtin, mpn)
            if self.cache:
                self.cache.cache_identity(summary["itemId"], gtin, mpn)

        await asyncio.gather(*(one(s) for s in to_fetch))
        self._lookups_done += len(to_fetch)

    @staticmethod
    def _apply_identity(summary: dict, gtin: str | None, mpn: str | None) -> None:
        if gtin:
            summary["gtin"] = gtin
        if mpn and not summary.get("mpn"):
            summary["mpn"] = mpn

    async def _get_item(self, client, token: str, marketplace: str, item_id: str) -> dict:
        """Fetch full item detail for one listing. Returns {} on failure."""
        resp = await client.get(
            f"{self.base_url}/buy/browse/v1/item/{item_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
            },
        )
        if resp.status_code != 200:
            return {}
        return resp.json()

    @staticmethod
    def _identity_from_item(detail: dict) -> tuple[str | None, str | None]:
        """Pull a barcode and MPN out of an item-detail response (pure).

        Checks the top-level ``gtin``/``mpn`` fields first, then the item's
        localized aspects, where sellers often put EAN/MPN as free-form specs.
        """
        gtin = detail.get("gtin")
        mpn = detail.get("mpn")
        for aspect in detail.get("localizedAspects", []):
            name = (aspect.get("name") or "").strip().lower()
            value = (aspect.get("value") or "").strip()
            if not value:
                continue
            if gtin is None and name in {"ean", "gtin", "upc", "barcode"}:
                gtin = value
            elif mpn is None and name in {"mpn", "herstellernummer", "part number"}:
                mpn = value
        return gtin, mpn

    async def _get_token(self, client) -> str:
        """Fetch (and cache) an application access token."""
        # Reuse the token until a minute before it expires.
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token

        creds = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        resp = await client.post(
            f"{self.base_url}/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": _OAUTH_SCOPE},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.monotonic() + int(payload.get("expires_in", 7200))
        return self._token

    async def _search(self, client, token: str, marketplace: str, query: dict) -> dict:
        """Call Browse item_summary/search on one marketplace with a query
        (``gtin`` or ``q``). Returns {} on any non-200 so one bad query never
        stops the run."""
        resp = await client.get(
            f"{self.base_url}/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
            },
            params={**query, "limit": self.per_gtin_limit},
        )
        if resp.status_code != 200:
            return {}
        return resp.json()

    @staticmethod
    def _parse_search_response(
        data: dict, searched_gtin: str | None, source: str, region: Region
    ) -> list[Listing]:
        """Map an eBay search response into ``Listing``s (pure, so testable)."""
        listings: list[Listing] = []
        for item in data.get("itemSummaries", []):
            try:
                price = item.get("price") or {}
                value = price.get("value")
                url = item.get("itemWebUrl")
                title = item.get("title")
                if not (value and url and title):
                    continue

                marketing = item.get("marketingPrice") or {}
                original = (marketing.get("originalPrice") or {}).get("value")

                listings.append(
                    Listing(
                        ean=item.get("gtin") or searched_gtin,
                        mpn=item.get("mpn"),
                        title=title,
                        brand=item.get("brand"),
                        category=None,
                        condition=EbaySource._condition(item.get("condition")),
                        price=Decimal(str(value)),
                        currency=price.get("currency", "EUR"),
                        was_price=Decimal(str(original)) if original else None,
                        url=url,
                        image_url=(item.get("image") or {}).get("imageUrl"),
                        seller=(item.get("seller") or {}).get("username", "ebay"),
                        in_stock=True,
                        # Marketplace "original price" is seller-supplied and
                        # easily faked, so we never treat it as a deal on its own.
                        trust_markdown=False,
                        source=source,
                        region=region,
                    )
                )
            except (InvalidOperation, ValueError, TypeError):
                continue  # skip a malformed item, keep the rest
        return listings

    @staticmethod
    def _condition(raw: str | None) -> Condition:
        if not raw:
            return Condition.UNKNOWN
        return _CONDITION_WORDS.get(raw.strip().lower(), Condition.UNKNOWN)
