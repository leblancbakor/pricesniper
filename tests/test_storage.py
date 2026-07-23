"""Tests for the persistence layer: price history and de-duplication.

Run with::

    uv run pytest
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from pricesniper.sources.feed import FeedSource
from pricesniper.sources.samples import SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP
from pricesniper.storage import SQLiteStore
from pricesniper.valuation import find_deals


def _sample_listings():
    source = FeedSource(SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP, seller="Alternate.nl")
    return asyncio.run(source.fetch())


def _store() -> SQLiteStore:
    # In-memory database keeps each test isolated and fast.
    return SQLiteStore(":memory:")


def test_price_history_round_trips_exact_decimals():
    store = _store()
    listings = _sample_listings()
    for listing in listings:
        store.record_price(listing)

    # MacBook, "1.049,00" in the feed, must come back as an exact Decimal.
    history = store.price_history("0195949999123")
    assert len(history) == 1
    price, _seen_at = history[0]
    assert price == Decimal("1049.00")
    assert isinstance(price, Decimal)


def test_a_deal_is_new_once_then_remembered():
    store = _store()
    deal = find_deals(_sample_listings())[0]

    assert store.is_new_deal(deal) is True
    store.mark_alerted(deal)
    assert store.is_new_deal(deal) is False


def test_second_pass_finds_no_new_deals():
    store = _store()
    deals = find_deals(_sample_listings())

    first_pass = [d for d in deals if store.is_new_deal(d)]
    for d in first_pass:
        store.mark_alerted(d)
    second_pass = [d for d in deals if store.is_new_deal(d)]

    assert len(first_pass) == 4
    assert len(second_pass) == 0


def test_history_keeps_growing_across_runs():
    store = _store()
    listings = _sample_listings()
    for _ in range(3):  # three scans
        for listing in listings:
            store.record_price(listing)

    # One product observed three times => three history rows.
    assert len(store.price_history("0195949999123")) == 3
