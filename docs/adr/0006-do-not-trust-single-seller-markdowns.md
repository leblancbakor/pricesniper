# 0006: Do not trust single-seller markdowns

- **Status:** accepted
- **Date:** 2026-07-28

## Context
The first live eBay run returned 304 listings and six "MAJOR" deals. Inspection
(via `--verbose`) showed all six were false positives: a single seller
(`retail_king`) had set an inflated "original price" (for example a 32GB DDR5 kit
marked down from 1351 to 711 euros) to fake a 47% discount. None of the 304
listings shared a barcode, so nothing corroborated those markdowns.

An open marketplace lets any seller type any strikethrough price. A retailer
product feed, by contrast, reports the shop's own genuine original price. Treating
both the same way makes the tool cry wolf, and an alert people cannot trust is
worse than no alert.

## Decision
Add a `trust_markdown` flag to `Listing` (default `True`). Sources whose markdown
is genuine (retailer feeds) leave it true; `EbaySource` sets it `False`. The
valuation stage only uses the markdown signal when `trust_markdown` is true.
Untrusted listings can still become deals, but only through cross-seller
comparison (multiple sellers of the same barcode), which cannot be faked by one
seller.

## Consequences
**Easier**
- No more fake-markdown alerts. eBay deals must now be corroborated across
  sellers to fire.
- Trust is encoded as data on each listing, so mixed-source runs judge each
  listing correctly.

**Harder / accepted trade-offs**
- eBay produces fewer deals now, and with no shared barcodes it currently
  produces none. That is the honest result: zero real deals beats six fake ones.
- It raises the priority of barcode recovery, so eBay listings can be matched
  across sellers and yield genuine cross-seller deals.

## Alternatives considered
- **Corroborate the markdown against other sellers.** The right idea, but it
  needs cross-seller data we do not yet have for eBay (no shared barcodes), so it
  cannot help until barcode recovery lands.
- **Drop `was_price` from eBay entirely.** Simpler, but throws away data that
  becomes useful once it can be corroborated. Keeping it but not trusting it is
  the better middle ground.
