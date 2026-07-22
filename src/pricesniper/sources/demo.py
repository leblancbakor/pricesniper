"""A fake source so the pipeline runs with zero setup and shows results today.

Delete or ignore this once real adapters exist — it's here purely so
``uv run pricesniper`` produces meaningful output on a fresh clone. The data is
invented but shaped exactly like what a real EU tech adapter would return.

The three items below deliberately exercise the three cases the engine must
handle:
  * two sellers list the SAME GPU (same EAN) at very different prices
    -> cross-listing arbitrage deal
  * one RAM kit is marked down from its ``was_price``
    -> markdown deal
  * a keyboard has no comps and no markdown
    -> correctly ignored (proof we don't cry wolf)
"""

from __future__ import annotations

from decimal import Decimal

from ..models import Condition, Listing, Region
from .base import SourceAdapter


class DemoSource(SourceAdapter):
    name = "demo"
    region = Region.EU

    async def fetch(self) -> list[Listing]:
        return [
            Listing(
                ean="0812674024900",
                title="NVIDIA RTX 5080 Founders Edition",
                brand="NVIDIA",
                category="GPU",
                condition=Condition.NEW,
                price=Decimal("879.00"),
                currency="EUR",
                url="https://example.eu/rtx5080-a",
                seller="Alternate.nl",
                source=self.name,
                region=self.region,
            ),
            Listing(
                ean="0812674024900",
                title="NVIDIA GeForce RTX 5080 (FE)",
                brand="NVIDIA",
                category="GPU",
                condition=Condition.NEW,
                price=Decimal("1149.00"),
                currency="EUR",
                url="https://example.eu/rtx5080-b",
                seller="Coolblue.nl",
                source=self.name,
                region=self.region,
            ),
            Listing(
                ean="0730143314085",
                title="Corsair Vengeance 32GB DDR5-6000",
                brand="Corsair",
                category="RAM",
                condition=Condition.NEW,
                price=Decimal("184.00"),
                was_price=Decimal("259.00"),
                currency="EUR",
                url="https://example.eu/corsair-ddr5",
                seller="Azerty.nl",
                source=self.name,
                region=self.region,
            ),
            Listing(
                ean="4711295940103",
                title="Wooting 80HE Keyboard",
                brand="Wooting",
                category="Peripheral",
                condition=Condition.NEW,
                price=Decimal("199.00"),
                currency="EUR",
                url="https://example.eu/wooting-80he",
                seller="Wooting.io",
                source=self.name,
                region=self.region,
            ),
        ]
