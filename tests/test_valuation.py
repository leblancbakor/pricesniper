"""A couple of sanity checks for the deal engine.

Run with::

    uv run pytest

These are intentionally small; they exist to prove the core loop behaves and to
give you a green baseline to build on. Real tests come as real adapters land.
"""

from __future__ import annotations

import asyncio

from pricesniper.sources.demo import DemoSource
from pricesniper.valuation import find_deals


def _demo_listings():
    return asyncio.run(DemoSource().fetch())


def test_finds_expected_number_of_deals():
    deals = find_deals(_demo_listings())
    # Two priced-gap items are deals; the no-comp keyboard is not.
    assert len(deals) == 2


def test_deals_are_sorted_biggest_gap_first():
    deals = find_deals(_demo_listings())
    pcts = [d.gap_pct for d in deals]
    assert pcts == sorted(pcts, reverse=True)


def test_no_false_positive_without_reference():
    # A lone listing with no comp and no was_price must never be a deal.
    lone = [x for x in _demo_listings() if x.seller == "Wooting.io"]
    assert find_deals(lone) == []


def test_barcode_less_listing_can_still_be_a_markdown_deal():
    # Common in eBay keyword results: no EAN, but a real markdown. It should
    # surface as a deal (via was_price), not be dropped for lacking identity.
    from decimal import Decimal

    from pricesniper.models import Condition, Listing, Region

    lone = Listing(
        title="No-barcode GPU, clearance",
        condition=Condition.NEW,
        price=Decimal("600.00"),
        was_price=Decimal("800.00"),
        currency="EUR",
        url="https://example.eu/x",
        seller="someshop",
        source="test",
        region=Region.EU,
    )
    deals = find_deals([lone])
    assert len(deals) == 1
    assert deals[0].reference_price == Decimal("800.00")
    assert deals[0].comps == 0


def test_different_currencies_are_not_compared():
    # Same barcode, but one price is EUR and one is GBP. They must NOT be
    # treated as a cross-seller gap, since the numbers are not comparable.
    from decimal import Decimal

    from pricesniper.models import Condition, Listing, Region

    def mk(price, currency, region):
        return Listing(
            ean="1234567890123", title="Same item, different market",
            condition=Condition.NEW, price=Decimal(price), currency=currency,
            url=f"https://example/{currency}", seller="s", source="ebay",
            region=region,
        )

    eur = mk("80.00", "EUR", Region.EU)
    gbp = mk("200.00", "GBP", Region.UK)
    # No markdown on either, so the only possible deal would be a bogus
    # cross-currency comparison, which the currency guard must prevent.
    assert find_deals([eur, gbp]) == []


def test_untrusted_single_seller_markdown_is_not_a_deal():
    # The exact false-positive from live eBay: one seller inflates the original
    # price to fake a 47% discount, with no other seller to corroborate it.
    from decimal import Decimal

    from pricesniper.models import Condition, Listing, Region

    faked = Listing(
        ean=None,
        title="Team T-Force Delta 32GB DDR5 6000 (fake markdown)",
        condition=Condition.NEW,
        price=Decimal("711.10"),
        was_price=Decimal("1351.10"),
        currency="EUR",
        url="https://www.ebay.nl/itm/1",
        seller="retail_king",
        source="ebay-nl",
        region=Region.EU,
        trust_markdown=False,
    )
    assert find_deals([faked]) == []


def test_trusted_feed_markdown_is_still_a_deal():
    # A retailer feed markdown stays trustworthy (trust_markdown defaults True).
    from decimal import Decimal

    from pricesniper.models import Condition, Listing, Region

    real = Listing(
        ean="1111111111116",
        title="Genuine clearance from a retailer feed",
        condition=Condition.NEW,
        price=Decimal("129.00"),
        was_price=Decimal("189.00"),
        currency="EUR",
        url="https://shop.example/x",
        seller="Alternate.nl",
        source="feed",
        region=Region.EU,
    )
    deals = find_deals([real])
    assert len(deals) == 1
    assert deals[0].reference_price == Decimal("189.00")
