"""Alerting: turn a ``Deal`` into a notification somewhere.

Like sources and storage, this is an interface with pluggable backends:

  * ``ConsoleAlerter`` prints deals to the terminal (the default, zero setup).
  * ``DiscordAlerter`` posts each deal as a rich embed to a Discord channel.

The Discord backend talks to Discord's REST API directly with a bot token. That
is deliberate: PriceSniper is a batch job (scan, alert, exit), not a long-lived
bot, so it does not need a full gateway connection or the discord.py dependency.
A single authorised POST per deal is all it takes. See
docs/adr/0004-discord-via-rest-not-a-gateway-bot.md.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from .models import Deal, Priority

# --- Embed styling -----------------------------------------------------------
# The left accent bar. One fixed colour for every alert, as designed.
# To colour by priority instead, swap the `EMBED_COLOUR` line in `build_embed`
# for `_PRIORITY_COLOUR[deal.priority]`.
EMBED_COLOUR = 0x7AE715

_PRIORITY_COLOUR = {
    Priority.MAJOR: 0xE74C3C,  # red
    Priority.SOLID: 0x2ECC71,  # green
    Priority.MINOR: 0x95A5A6,  # grey
}

# Small text and icon at the very bottom of the embed. The icon is served from
# this repo rather than a Discord CDN link, because CDN attachment URLs carry
# signed, expiring parameters and would silently stop loading after a while.
FOOTER_TEXT = "delta"
FOOTER_ICON_URL = (
    "https://raw.githubusercontent.com/leblancbakor/pricesniper/main/docs/assets/logo.jpg"
)

# Optional fixed banner across the bottom of every embed. Leave as None to show
# the product photo there instead (the usual case).
BANNER_IMAGE_URL: str | None = None

_PRIORITY_BADGE = {
    Priority.MAJOR: "MAJOR",
    Priority.SOLID: "SOLID",
    Priority.MINOR: "minor",
}

# Currency codes rendered as symbols, so prices read "EUR 129.00" as "129.00"
# with the right sign rather than doubling up the code and the symbol.
_CURRENCY_SYMBOLS = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3"}


def _money(currency: str, amount: object) -> str:
    """Format an amount with its currency symbol, e.g. ``129.00`` -> ``€129.00``."""
    return f"{_CURRENCY_SYMBOLS.get(currency.upper(), currency + ' ')}{amount}"

DISCORD_API = "https://discord.com/api/v10"


class Alerter(ABC):
    """Interface every notification backend implements."""

    @abstractmethod
    async def send(self, deal: Deal) -> None:
        """Deliver one deal notification."""


class ConsoleAlerter(Alerter):
    """Prints deals to stdout. The default when no channel is configured."""

    def __init__(self) -> None:
        self._n = 0

    async def send(self, deal: Deal) -> None:
        self._n += 1
        item = deal.listing
        pct = round(deal.gap_pct * 100)
        badge = f"[{_PRIORITY_BADGE[deal.priority]}]"
        print(
            f"{self._n}. {badge}  {item.title}\n"
            f"    {item.currency} {item.price}  (ref {item.currency} "
            f"{deal.reference_price})  ->  save {item.currency} {deal.gap_abs} / {pct}%\n"
            f"    {deal.reason} - {item.seller} - {item.region.value}\n"
            f"    {item.url}\n"
        )


class DiscordAlerter(Alerter):
    """Posts each deal as an embed to a Discord channel via the REST API."""

    def __init__(self, bot_token: str, channel_id: str) -> None:
        if not bot_token or not channel_id:
            raise ValueError(
                "DiscordAlerter needs both a bot token and a channel id. "
                "Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in your .env."
            )
        self.bot_token = bot_token
        self.channel_id = channel_id

    async def send(self, deal: Deal) -> None:
        import httpx

        url = f"{DISCORD_API}/channels/{self.channel_id}/messages"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        payload = {"embeds": [self.build_embed(deal)]}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            # Discord asks callers to back off on 429 and tells us for how long.
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1.0))
                await asyncio.sleep(retry_after)
                resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()

    @staticmethod
    def build_embed(deal: Deal, now: datetime | None = None) -> dict:
        """Build the Discord embed object for one deal.

        Pure apart from the timestamp default, so it is unit-testable without a
        network. ``now`` is the moment the alert is sent; it defaults to the
        current UTC time and shows in the embed's footer line.
        """
        item = deal.listing
        pct = round(deal.gap_pct * 100)
        cur = item.currency
        sent_at = now or datetime.now(UTC)

        embed: dict = {
            "title": item.title[:256],  # Discord caps embed titles at 256 chars
            "url": item.url,  # makes the title clickable through to the product
            "color": EMBED_COLOUR,
            "description": f"**Save {_money(cur, deal.gap_abs)} ({pct}%)**\n{deal.reason}",
            "fields": [
                {"name": "Price", "value": _money(cur, item.price), "inline": True},
                {
                    "name": "Reference",
                    "value": _money(cur, deal.reference_price),
                    "inline": True,
                },
                {"name": "Priority", "value": _PRIORITY_BADGE[deal.priority], "inline": True},
            ],
            "footer": {"text": FOOTER_TEXT, "icon_url": FOOTER_ICON_URL},
            "timestamp": sent_at.isoformat(),
        }
        if item.image_url:
            # Small in the top-right corner, and large across the bottom.
            embed["thumbnail"] = {"url": item.image_url}
            embed["image"] = {"url": BANNER_IMAGE_URL or item.image_url}
        elif BANNER_IMAGE_URL:
            embed["image"] = {"url": BANNER_IMAGE_URL}
        return embed
