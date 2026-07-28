"""Tests for the eBay adapter.

The live API needs credentials and a network, so those are not exercised here.
What we can test without either is the response parser (the mapping from eBay's
JSON into our ``Listing`` model) and the watchlist loader.

Run with::

    uv run pytest
"""

from __future__ import annotations

from decimal import Decimal

from pricesniper.models import Condition, Region
from pricesniper.sources.ebay import EbaySource, is_gtin, read_watchlist
from pricesniper.valuation import find_deals

# A trimmed but realistic Browse item_summary/search response: two sellers list
# the same GTIN at different prices, one of them on sale.
SAMPLE_RESPONSE = {
    "total": 2,
    "itemSummaries": [
        {
            "itemId": "v1|111|0",
            "title": "Corsair Vengeance 32GB DDR5-6000 CL30",
            "gtin": "0840006687894",
            "brand": "Corsair",
            "condition": "New",
            "price": {"value": "134.99", "currency": "EUR"},
            "itemWebUrl": "https://www.ebay.nl/itm/111",
            "image": {"imageUrl": "https://i.ebayimg.com/images/g/aaa/s-l225.jpg"},
            "seller": {"username": "techdeals_nl", "feedbackPercentage": "99.4"},
        },
        {
            "itemId": "v1|222|0",
            "title": "Corsair Vengeance 32GB DDR5 6000 CL30 (sale)",
            "gtin": "0840006687894",
            "brand": "Corsair",
            "condition": "New",
            "price": {"value": "159.00", "currency": "EUR"},
            "marketingPrice": {
                "originalPrice": {"value": "189.00", "currency": "EUR"},
                "discountPercentage": "16",
            },
            "itemWebUrl": "https://www.ebay.nl/itm/222",
            "seller": {"username": "bigshop_de"},
        },
        {
            # Malformed (no price): must be skipped, not crash the run.
            "itemId": "v1|333|0",
            "title": "Broken listing",
            "itemWebUrl": "https://www.ebay.nl/itm/333",
        },
    ],
}


def _parsed():
    return EbaySource._parse_search_response(
        SAMPLE_RESPONSE, "0840006687894", "ebay", Region.EU
    )


def test_parses_valid_items_and_skips_broken_ones():
    listings = _parsed()
    assert len(listings) == 2  # the price-less third item is dropped


def test_maps_fields_including_seller_and_was_price():
    listings = _parsed()
    cheap = min(listings, key=lambda x: x.price)
    assert cheap.price == Decimal("134.99")
    assert cheap.seller == "techdeals_nl"
    assert cheap.ean == "0840006687894"
    assert cheap.condition is Condition.NEW
    on_sale = next(x for x in listings if x.was_price is not None)
    assert on_sale.was_price == Decimal("189.00")


def test_two_sellers_same_gtin_produce_a_cross_seller_deal():
    # The whole point of eBay: same barcode, different sellers => arbitrage.
    deals = find_deals(_parsed())
    # The cheaper listing should surface as a deal backed by the other seller.
    cross = next(d for d in deals if d.listing.price == Decimal("134.99"))
    assert cross.comps >= 1  # its reference came from another seller's price
    assert cross.reference_price == Decimal("159.00")


def test_missing_credentials_raise():
    try:
        EbaySource(client_id="", client_secret="", watchlist=[])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError without credentials")


def test_watchlist_loader_ignores_comments_and_blanks(tmp_path):
    f = tmp_path / "watchlist.txt"
    f.write_text(
        "# header comment\n\n0840006687894  # corsair\n4711387451236\n",
        encoding="utf-8",
    )
    assert read_watchlist(f) == ["0840006687894", "4711387451236"]


def test_is_gtin_distinguishes_barcodes_from_keywords():
    assert is_gtin("4895194969662") is True     # 13-digit EAN
    assert is_gtin("012345678") is True          # 9 digits, still a barcode
    assert is_gtin("5070") is False              # too short: a model number
    assert is_gtin("RTX 5070 Ti") is False       # has letters and spaces


def test_keyword_search_has_no_fallback_gtin():
    # For a keyword search there is no searched barcode, so items keep only the
    # gtin they carry themselves (here, none), and are matched by other means.
    resp = {
        "itemSummaries": [
            {
                "title": "KLEVV FIT V 32GB DDR5 6000 (used, no barcode listed)",
                "condition": "New",
                "price": {"value": "349.00", "currency": "EUR"},
                "marketingPrice": {"originalPrice": {"value": "459.00", "currency": "EUR"}},
                "itemWebUrl": "https://www.ebay.de/itm/999",
                "seller": {"username": "private_seller"},
            }
        ]
    }
    listings = EbaySource._parse_search_response(resp, None, "ebay", Region.EU)
    assert len(listings) == 1
    assert listings[0].ean is None                # no barcode carried or injected
    assert listings[0].was_price == Decimal("459.00")


def test_marketplace_region_mapping():
    assert EbaySource._region_for("EBAY_DE") is Region.EU
    assert EbaySource._region_for("EBAY_NL") is Region.EU
    assert EbaySource._region_for("EBAY_GB") is Region.UK
    assert EbaySource._region_for("EBAY_US") is Region.US


def test_multiple_marketplaces_are_stored():
    src = EbaySource(
        client_id="x", client_secret="y", watchlist=[],
        marketplaces=["EBAY_DE", "EBAY_NL"],
    )
    assert src.marketplaces == ["EBAY_DE", "EBAY_NL"]


def test_identity_recovered_from_top_level_fields():
    detail = {"gtin": "4895194969662", "mpn": "KD5AGUA80-60A380C"}
    gtin, mpn = EbaySource._identity_from_item(detail)
    assert gtin == "4895194969662"
    assert mpn == "KD5AGUA80-60A380C"


def test_identity_recovered_from_localized_aspects():
    # Sellers often put the barcode in the free-form item specifics instead.
    detail = {
        "localizedAspects": [
            {"name": "Brand", "value": "KLEVV"},
            {"name": "EAN", "value": "4895194969662"},
            {"name": "MPN", "value": "KD5AGUA80-60A380C"},
        ]
    }
    gtin, mpn = EbaySource._identity_from_item(detail)
    assert gtin == "4895194969662"
    assert mpn == "KD5AGUA80-60A380C"


def test_identity_absent_returns_none():
    gtin, mpn = EbaySource._identity_from_item({"localizedAspects": []})
    assert gtin is None and mpn is None


def test_recovery_enriches_summaries_and_respects_the_cap():
    import asyncio

    src = EbaySource(
        client_id="x", client_secret="y", watchlist=[], max_lookups=2
    )

    # Stub the network call: pretend eBay detail always has this barcode.
    async def fake_get_item(client, token, marketplace, item_id):
        return {"gtin": f"111111111111{item_id[-1]}"}

    src._get_item = fake_get_item  # type: ignore[assignment]

    summaries = [
        {"itemId": f"v1|{i}|0", "title": f"item {i}"} for i in range(5)
    ]
    asyncio.run(src._recover_barcodes(None, "tok", "EBAY_NL", summaries))

    recovered = [s for s in summaries if s.get("gtin")]
    assert len(recovered) == 2  # cap of 2 respected, not all 5
    assert src._lookups_done == 2


def test_cached_items_cost_no_lookup_and_new_ones_are_cached():
    import asyncio

    class FakeCache:
        def __init__(self):
            self.data = {"v1|known|0": ("4895194969662", None)}

        def get_cached_identity(self, item_id):
            return self.data.get(item_id)

        def cache_identity(self, item_id, gtin, mpn):
            self.data[item_id] = (gtin, mpn)

    cache = FakeCache()
    src = EbaySource(
        client_id="x", client_secret="y", watchlist=[], max_lookups=60, cache=cache
    )

    calls = []

    async def fake_get_item(client, token, marketplace, item_id):
        calls.append(item_id)
        return {"gtin": "9999999999999"}

    src._get_item = fake_get_item  # type: ignore[assignment]

    summaries = [
        {"itemId": "v1|known|0", "title": "already cached"},
        {"itemId": "v1|new|0", "title": "needs a lookup"},
    ]
    asyncio.run(src._recover_barcodes(None, "tok", "EBAY_NL", summaries))

    # The cached item was applied without any network call.
    assert calls == ["v1|new|0"]
    assert summaries[0]["gtin"] == "4895194969662"
    # The new item got looked up and written back to the cache.
    assert summaries[1]["gtin"] == "9999999999999"
    assert cache.data["v1|new|0"] == ("9999999999999", None)
    assert src._lookups_done == 1  # only the uncached one counted
