"""Tests for the alerting layer.

The Discord POST itself needs a live token and network, so it is not tested here.
What we can test without either is the embed we build and the console backend.

Run with::

    uv run pytest
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pricesniper.alerting import (
    EMBED_COLOUR,
    FOOTER_TEXT,
    ConsoleAlerter,
    DiscordAlerter,
)
from pricesniper.sources.feed import FeedSource
from pricesniper.sources.samples import SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP
from pricesniper.valuation import find_deals


def _a_deal():
    source = FeedSource(SAMPLE_FEED_PATH, SAMPLE_FIELD_MAP, seller="Alternate.nl")
    listings = asyncio.run(source.fetch())
    return find_deals(listings)[0]


def test_embed_has_core_fields_and_link():
    deal = _a_deal()
    embed = DiscordAlerter.build_embed(deal)
    assert embed["title"] == deal.listing.title
    assert embed["url"] == deal.listing.url
    assert len(embed["fields"]) == 3
    # The price field shows the exact listing price.
    price_field = next(f for f in embed["fields"] if f["name"] == "Price")
    assert str(deal.listing.price) in price_field["value"]


def test_embed_uses_the_fixed_brand_colour():
    embed = DiscordAlerter.build_embed(_a_deal())
    assert embed["color"] == EMBED_COLOUR


def test_prices_render_with_a_currency_symbol_not_a_doubled_code():
    embed = DiscordAlerter.build_embed(_a_deal())
    price = next(f for f in embed["fields"] if f["name"] == "Price")["value"]
    assert price.startswith("\u20ac")   # euro sign
    assert "EUR" not in price          # code and symbol must not double up


def test_footer_and_timestamp_are_present():
    fixed = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    embed = DiscordAlerter.build_embed(_a_deal(), now=fixed)
    assert embed["footer"]["text"] == FOOTER_TEXT
    assert embed["footer"]["icon_url"]
    # Timestamp reflects when the alert is sent.
    assert embed["timestamp"] == fixed.isoformat()


def test_title_links_to_the_product_page():
    deal = _a_deal()
    embed = DiscordAlerter.build_embed(deal)
    assert embed["url"] == deal.listing.url
    assert embed["url"].startswith("http")


def test_discord_alerter_requires_config():
    try:
        DiscordAlerter(bot_token="", channel_id="")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when token/channel are missing")


def test_console_alerter_prints(capsys):
    asyncio.run(ConsoleAlerter().send(_a_deal()))
    out = capsys.readouterr().out
    assert "save" in out.lower()


def test_product_photo_shows_both_small_and_large():
    deal = _a_deal()
    embed = DiscordAlerter.build_embed(deal)
    assert embed["thumbnail"]["url"] == deal.listing.image_url
    assert embed["image"]["url"] == deal.listing.image_url


def test_footer_icon_is_repo_hosted_not_an_expiring_cdn_link():
    from pricesniper.alerting import FOOTER_ICON_URL

    assert "cdn.discordapp.com" not in FOOTER_ICON_URL
    assert "?ex=" not in FOOTER_ICON_URL  # signed, expiring parameters
