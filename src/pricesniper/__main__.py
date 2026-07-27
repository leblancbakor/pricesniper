"""Runnable entry point for the pipeline.

    uv run pricesniper                 # scan + print deals to the console
    uv run pricesniper --alert discord # scan + post new deals to Discord

The loop::

    source.fetch() -> find_deals() -> record history + skip seen -> alert

Every scanned price is written to the local SQLite store, and only deals we have
not alerted on before are sent, so running it twice does not repeat itself.
Discord settings are read from a local ``.env`` (see ``.env.example``).
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from . import __version__
from .alerting import Alerter, ConsoleAlerter, DiscordAlerter
from .sources.base import SourceAdapter
from .sources.ebay import EbaySource, read_watchlist
from .sources.feed import FeedSource
from .sources.samples import SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP
from .storage import SQLiteStore
from .valuation import find_deals

WATCHLIST_PATH = "watchlist.txt"


def _make_source(kind: str) -> SourceAdapter:
    """Build the chosen data source. eBay reads credentials from .env."""
    if kind == "ebay":
        load_dotenv()
        return EbaySource(
            client_id=os.getenv("EBAY_CLIENT_ID", ""),
            client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
            watchlist=read_watchlist(WATCHLIST_PATH),
            marketplace=os.getenv("EBAY_MARKETPLACE", "EBAY_NL"),
            environment=os.getenv("EBAY_ENV", "production"),
        )
    # Default: the bundled sample feed (swap the path for a real feed URL).
    return FeedSource(
        SAMPLE_FEED_PATH,
        SAMPLE_FIELD_MAP,
        name="alternate-sample",
        seller="Alternate.nl",
    )


def _make_alerter(kind: str) -> Alerter:
    """Pick an alerter. Discord config is read from .env."""
    if kind == "discord":
        load_dotenv()  # read .env into the environment
        return DiscordAlerter(
            bot_token=os.getenv("DISCORD_BOT_TOKEN", ""),
            channel_id=os.getenv("DISCORD_CHANNEL_ID", ""),
        )
    return ConsoleAlerter()


async def _run(alert_kind: str, source_kind: str) -> None:
    source = _make_source(source_kind)
    store = SQLiteStore()
    alerter = _make_alerter(alert_kind)

    listings = await source.fetch()
    deals = find_deals(listings)

    # Record every observed price so history builds up over time.
    for listing in listings:
        store.record_price(listing)

    # Only surface deals we have not already alerted on.
    new_deals = [deal for deal in deals if store.is_new_deal(deal)]

    print(
        f"\nPriceSniper v{__version__} - scanned {len(listings)} listings "
        f"from '{source.name}' ({source.region.value})"
    )
    print(
        f"Found {len(deals)} deal(s), {len(new_deals)} new "
        f"({len(deals) - len(new_deals)} already alerted). "
        f"Alerting via {alert_kind}.\n"
    )
    for deal in new_deals:
        await alerter.send(deal)
        store.mark_alerted(deal)

    store.close()


def main() -> None:
    """Sync wrapper so it works as a console-script entry point."""
    parser = argparse.ArgumentParser(
        prog="pricesniper", description="Find and alert tech deals."
    )
    parser.add_argument(
        "--source",
        choices=["feed", "ebay"],
        default="feed",
        help="where to pull listings from (default: feed, the bundled sample)",
    )
    parser.add_argument(
        "--alert",
        choices=["console", "discord"],
        default="console",
        help="where to send new deals (default: console)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.alert, args.source))
    except ValueError as exc:
        # e.g. --alert discord or --source ebay without the config in .env.
        raise SystemExit(f"Configuration error: {exc}") from None


if __name__ == "__main__":
    main()
