# 0005: eBay Browse API for cross-seller arbitrage

- **Status:** accepted
- **Date:** 2026-07-27

## Context
The feed source (v0.2) gives clean data but mostly surfaces one retailer's
markdowns. The valuation stage was also built to spot *cross-seller* gaps: the
same product priced differently by different sellers. To do that we need a
source that returns many sellers' listings for the same product, keyed by
barcode. Scraping several retailers to assemble that is fragile and slow.

eBay's Browse API can search by GTIN and return every live listing for that
barcode across sellers, using a simple application token (client-credentials
OAuth, no user login). Joining the Developers Program is free.

## Decision
Add an `EbaySource` adapter that, for each GTIN on a `watchlist.txt`, queries the
Browse API and normalises the results into `Listing`s. It reads credentials from
`.env` and is selected with `--source ebay`. The feed source stays the default.

## Consequences
**Easier**
- Real cross-seller arbitrage data, which is exactly what `valuation.py` was
  designed for but never had.
- One free API instead of many fragile scrapers; EU marketplaces (eBay.nl,
  eBay.de) keep it domestic.
- A second real adapter validates the `SourceAdapter` seam from ADR-0001: it
  slotted in with no change to matching, valuation, storage, or alerting.

**Harder / accepted trade-offs**
- Production access can need an extra approval step beyond the sandbox.
- Coverage is eBay's marketplace only; it complements rather than replaces
  retailer feeds.
- Results are only as good as the watchlist; we search known barcodes rather
  than discovering products.

## Alternatives considered
- **Scrape multiple retailers for cross-seller prices.** Fragile, slower, and
  runs into the JavaScript and anti-bot problems from ADR-0002.
- **Wait for affiliate feeds only.** Those lag on approval and lean toward
  single-retailer markdowns, not cross-seller gaps.
