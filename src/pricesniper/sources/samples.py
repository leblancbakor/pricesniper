"""Ready-made configuration for the bundled sample feed.

This is what a real source module looks like: pair a feed location with the
``FeedFieldMap`` that describes its layout. To point PriceSniper at a real feed,
copy this pattern, swap ``SAMPLE_FEED_PATH`` for the feed URL, and adjust the
field map to match that feed's tag names.
"""

from __future__ import annotations

from pathlib import Path

from .feed import FeedFieldMap

# The sample XML that ships next to this module. Using ``__file__`` means it is
# found no matter where the program is launched from.
SAMPLE_FEED_PATH = Path(__file__).with_name("sample_feed.xml")

# The sample feed uses the FeedFieldMap defaults (product/name/price/price_old/
# ean/url/...), so we only need to name it. A real feed would override the tags
# that differ, for example FeedFieldMap(was_price="old_price", ean="gtin", ...).
SAMPLE_FIELD_MAP = FeedFieldMap()
