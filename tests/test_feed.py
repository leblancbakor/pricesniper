"""Tests for the feed adapter: parsing correctness and the deals it yields.

Run with::

    uv run pytest
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from pricesniper.models import Priority
from pricesniper.sources.feed import FeedFieldMap, FeedSource
from pricesniper.sources.samples import SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP
from pricesniper.valuation import find_deals


def _sample_listings():
    source = FeedSource(SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP, seller="Alternate.nl")
    return asyncio.run(source.fetch())


def test_reads_every_product():
    listings = _sample_listings()
    assert len(listings) == 5


def test_eu_comma_prices_parse_to_exact_decimals():
    by_ean = {x.ean: x for x in _sample_listings()}
    macbook = by_ean["0195949999123"]
    # "1.049,00" must become exactly 1049.00, not 1.049 or a float.
    assert macbook.price == Decimal("1049.00")
    assert macbook.was_price == Decimal("1299.00")


def test_constant_seller_is_applied():
    assert all(x.seller == "Alternate.nl" for x in _sample_listings())


def test_markdowns_become_deals_but_full_price_items_do_not():
    deals = find_deals(_sample_listings())
    # Four items carry a price_old; the mouse (full price) must be ignored.
    assert len(deals) == 4
    assert all(d.listing.seller == "Alternate.nl" for d in deals)
    assert "mouse" not in " ".join(d.listing.title.lower() for d in deals)


def test_absolute_margin_can_outrank_percentage():
    deals = {d.listing.brand: d for d in find_deals(_sample_listings())}
    # The MacBook is only ~19% off but saves 250 euros, so it lands as MAJOR.
    assert deals["Apple"].priority is Priority.MAJOR


def test_price_parser_handles_both_conventions():
    comma = FeedSource("x.xml", FeedFieldMap(decimal_comma=True))
    dot = FeedSource("x.xml", FeedFieldMap(decimal_comma=False))
    assert comma._parse_price("1.299,00") == Decimal("1299.00")
    assert comma._parse_price("EUR 129,00") == Decimal("129.00")
    assert dot._parse_price("1,299.00") == Decimal("1299.00")
