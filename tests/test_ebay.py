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
from pricesniper.sources.ebay import EbaySource, read_watchlist
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
