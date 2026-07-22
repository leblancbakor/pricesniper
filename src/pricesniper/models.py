"""Core domain models for PriceSniper.

These Pydantic models are the shared "language" every part of the pipeline
speaks. A source adapter's only job is to turn a messy retailer page into a list
of ``Listing`` objects; everything downstream (matching, valuation, alerting)
operates purely on these models and never touches raw HTML again.

If you know TypeScript: think of these as Zod schemas / interfaces, except they
validate at *runtime*, so bad data fails loudly and early instead of silently
flowing through the system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Region(StrEnum):
    """Market a listing belongs to.

    Kept as an enum so adding the US later is a one-line change here, not a
    hunt-and-replace across the codebase.
    """

    EU = "EU"
    US = "US"
    UK = "UK"


class Condition(StrEnum):
    NEW = "new"
    OPEN_BOX = "open_box"
    REFURBISHED = "refurbished"
    USED = "used"
    UNKNOWN = "unknown"


class Priority(StrEnum):
    """How loud an alert should be. The real thresholds live in valuation.py."""

    MINOR = "minor"
    SOLID = "solid"
    MAJOR = "major"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Listing(BaseModel):
    """A single offer for a single product, on a single site, at a moment in time.

    This is what a ``SourceAdapter`` produces. Note the three identity fields
    (ean/upc/mpn): matching is only trustworthy when at least one is present,
    which is exactly why we start with barcoded tech.

    Money is stored as ``Decimal``, never ``float`` — floats can't represent
    values like 0.10 exactly, and rounding errors on prices are unacceptable.
    """

    # --- identity (used to decide "is this the same product?") ---
    ean: str | None = None  # European Article Number (barcode)
    upc: str | None = None  # Universal Product Code (US barcode)
    mpn: str | None = None  # Manufacturer Part Number

    # --- description ---
    title: str
    brand: str | None = None
    category: str | None = None
    condition: Condition = Condition.UNKNOWN

    # --- commercial ---
    price: Decimal
    currency: str = Field(min_length=3, max_length=3)  # ISO 4217, e.g. "EUR"
    was_price: Decimal | None = None  # original / MSRP if the page shows one
    url: str
    image_url: str | None = None
    seller: str
    in_stock: bool = True

    # --- provenance ---
    source: str  # which adapter produced this
    region: Region
    seen_at: datetime = Field(default_factory=_utcnow)

    @property
    def identity(self) -> str | None:
        """The best available product identifier, or ``None`` if unmatchable.

        Preference order: EAN -> UPC -> MPN. Two listings that share this value
        are treated as the same product by the matcher.
        """
        return self.ean or self.upc or self.mpn


class Deal(BaseModel):
    """A detected opportunity: a listing priced meaningfully below a reference."""

    listing: Listing
    reference_price: Decimal  # what we think it's "really" worth
    gap_abs: Decimal  # reference_price - listing.price (money saved)
    gap_pct: float  # gap_abs / reference_price, in the range 0..1
    priority: Priority
    reason: str  # human-readable "why this is a deal"
    comps: int = 0  # how many other listings backed the reference price
