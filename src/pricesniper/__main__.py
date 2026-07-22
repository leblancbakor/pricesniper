"""Runnable entry point for the v0.1 demo pipeline.

    uv run pricesniper
    # or, equivalently:
    uv run python -m pricesniper

It wires the whole loop together against fake data so you can see the pipeline
work end to end before any real scraping exists::

    source.fetch()  ->  find_deals()  ->  print

Swap ``DemoSource`` for a real adapter and nothing else here has to change.
"""

from __future__ import annotations

import asyncio

from . import __version__
from .models import Deal
from .sources.feed import FeedSource
from .sources.samples import SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP
from .valuation import find_deals

_BADGES = {"major": "[MAJOR]", "solid": "[SOLID]", "minor": "[minor]"}


def _format_deal(index: int, deal: Deal) -> str:
    item = deal.listing
    pct = round(deal.gap_pct * 100)
    badge = _BADGES[deal.priority.value]
    return "\n".join(
        [
            f"{index}. {badge}  {item.title}",
            f"    {item.currency} {item.price}  (ref {item.currency} "
            f"{deal.reference_price})  ->  save {item.currency} {deal.gap_abs} / {pct}%",
            f"    {deal.reason} - {item.seller} - {item.region.value}",
            f"    {item.url}",
        ]
    )


async def _run() -> None:
    # Point this at a real feed URL (and the matching field map) to go live.
    # For now it reads the bundled sample feed so it runs with zero setup.
    source = FeedSource(
        SAMPLE_FEED_PATH,
        SAMPLE_FIELD_MAP,
        name="alternate-sample",
        seller="Alternate.nl",
    )
    listings = await source.fetch()
    deals = find_deals(listings)

    print(
        f"\nPriceSniper v{__version__} - scanned {len(listings)} listings "
        f"from '{source.name}' ({source.region.value})"
    )
    print(f"Found {len(deals)} deal(s):\n")
    for i, deal in enumerate(deals, start=1):
        print(_format_deal(i, deal))
        print()


def main() -> None:
    """Sync wrapper so it works as a console-script entry point."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
