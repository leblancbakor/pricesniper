"""Stage 2: decide which listings refer to the same physical product.

v0.1 rule: exact match on a shared identity (EAN / UPC / MPN). This is
deliberately strict. Fuzzy title/image matching is powerful but error-prone, and
one wrong "same product" match produces a bogus "50% profit!" alert that
destroys trust. We earn fuzzy matching later; for now, no identity means no
match.
"""

from __future__ import annotations

from collections import defaultdict

from .models import Listing


def group_by_identity(listings: list[Listing]) -> dict[str, list[Listing]]:
    """Group listings that share an identity key.

    Listings with no identity (no barcode / MPN) are skipped rather than guessed
    at. Returns a dict of ``identity -> [listings]``.
    """
    groups: dict[str, list[Listing]] = defaultdict(list)
    for listing in listings:
        key = listing.identity
        if key is None:
            continue  # unmatchable for now; see module docstring
        groups[key].append(listing)
    return dict(groups)
