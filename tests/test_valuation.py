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
