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
from .valuation import DEFAULT_MIN_GAP_PCT, find_deals

WATCHLIST_PATH = "watchlist.txt"


def _make_source(kind: str) -> SourceAdapter:
    """Build the chosen data source. eBay reads credentials from .env."""
    if kind == "ebay":
        load_dotenv()
        raw_markets = os.getenv("EBAY_MARKETPLACE", "EBAY_NL")
        marketplaces = [m.strip() for m in raw_markets.split(",") if m.strip()]
        return EbaySource(
            client_id=os.getenv("EBAY_CLIENT_ID", ""),
            client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
            watchlist=read_watchlist(WATCHLIST_PATH),
            marketplaces=marketplaces,
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


def _print_scan(listings: list) -> None:
    """Verbose diagnostics: show what was scanned and why deals did or did not
    appear. Invaluable when a run returns listings but zero deals."""
    from .matching import group_by_identity

    print("Scanned listings:")
    for x in listings:
        ident = x.ean or x.upc or x.mpn or "no-barcode"
        print(
            f"  {x.currency} {x.price:>8}  {x.source:<10} "
            f"{(x.seller or '?')[:16]:<16} {ident:<15} {x.title[:48]}"
        )

    groups = group_by_identity(listings)
    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    no_barcode = sum(1 for x in listings if (x.ean or x.upc or x.mpn) is None)
    print(
        f"\n  {len(listings)} listings | {len(listings) - no_barcode} with a "
        f"barcode | {no_barcode} without"
    )
    print(
        f"  {len(multi)} barcode group(s) with 2+ sellers "
        f"(these can become cross-seller deals)"
    )

    # Near-misses: every positive gap, so you can see how close you were even
    # when nothing cleared the real threshold.
    near = find_deals(listings, min_gap_pct=0.0)[:5]
    if near:
        pct = round(DEFAULT_MIN_GAP_PCT * 100)
        print(f"\n  Closest gaps found (deal threshold is {pct}%):")
        for d in near:
            print(
                f"    {round(d.gap_pct * 100):>3}%  save {d.listing.currency} "
                f"{d.gap_abs}  {d.listing.title[:44]}"
            )
    else:
        print("\n  No positive gaps at all: no markdowns and no matched sellers.")
    print()


async def _run(alert_kind: str, source_kind: str, verbose: bool) -> None:
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
        f"from '{source.name}'"
    )
    if verbose:
        _print_scan(listings)
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show every scanned listing and how close the near-misses were",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.alert, args.source, args.verbose))
    except ValueError as exc:
        # e.g. --alert discord or --source ebay without the config in .env.
        raise SystemExit(f"Configuration error: {exc}") from None


if __name__ == "__main__":
    main()
