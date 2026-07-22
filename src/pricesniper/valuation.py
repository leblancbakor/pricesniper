"""Stages 3 & 4: turn grouped listings into scored ``Deal`` objects.

Two independent price signals feed the "reference price" we compare against:

  1. Markdown:      the listing itself shows a higher ``was_price`` (clearance).
  2. Cross-listing: other sellers list the same item (by identity) for more.

We take whichever signal implies the *larger* gap, and record which one it was
so the alert can explain itself. The thresholds here are first-pass guesses;
tuning them is a future milestone (and a good ADR to write when you do).
"""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from .matching import group_by_identity
from .models import Deal, Listing, Priority

DEFAULT_MIN_GAP_PCT = 0.15  # ignore anything smaller than a 15% gap


def find_deals(
    listings: list[Listing],
    min_gap_pct: float = DEFAULT_MIN_GAP_PCT,
) -> list[Deal]:
    """Scan listings and return those that clear the gap threshold, best first."""
    groups = group_by_identity(listings)
    deals: list[Deal] = []

    for group in groups.values():
        for listing in group:
            others = [x for x in group if x is not listing]
            reference, reason, comps = _best_reference(listing, others)
            if reference is None or reference <= listing.price:
                continue

            gap_abs = reference - listing.price
            gap_pct = float(gap_abs / reference)
            if gap_pct < min_gap_pct:
                continue

            deals.append(
                Deal(
                    listing=listing,
                    reference_price=reference,
                    gap_abs=gap_abs,
                    gap_pct=gap_pct,
                    priority=_priority_for(gap_pct, gap_abs),
                    reason=reason,
                    comps=comps,
                )
            )

    # Biggest opportunities first.
    deals.sort(key=lambda d: d.gap_pct, reverse=True)
    return deals


def _best_reference(
    listing: Listing,
    others: list[Listing],
) -> tuple[Decimal | None, str, int]:
    """Pick the reference price that implies the largest, still-credible gap."""
    candidates: list[tuple[Decimal, str, int]] = []

    # Signal 1: the store's own markdown.
    if listing.was_price is not None and listing.was_price > listing.price:
        candidates.append((listing.was_price, "marked down from original price", 0))

    # Signal 2: what other sellers charge for the same item.
    comp_prices = [o.price for o in others if o.in_stock]
    if comp_prices:
        ref = median(comp_prices)
        label = f"cheaper than {len(comp_prices)} other seller(s)"
        candidates.append((ref, label, len(comp_prices)))

    if not candidates:
        return None, "", 0

    # Largest reference => largest gap.
    return max(candidates, key=lambda c: c[0])


def _priority_for(gap_pct: float, gap_abs: Decimal) -> Priority:
    """Placeholder scoring.

    Later this becomes a weighted blend of gap %, absolute margin, match
    confidence, seller trust, and resale liquidity.
    """
    if gap_pct >= 0.40 or gap_abs >= Decimal("200"):
        return Priority.MAJOR
    if gap_pct >= 0.25 or gap_abs >= Decimal("75"):
        return Priority.SOLID
    return Priority.MINOR
