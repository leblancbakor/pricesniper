# 0002: Start with a product feed, not a scraper

- **Status:** accepted
- **Date:** 2026-07-23

## Context
v0.2 needed the first real source to replace the demo. The obvious candidate was
a Dutch retailer's outlet page (Alternate). Before writing code, we checked
`robots.txt` and inspected the page, and found three problems:

1. The outlet listing pages render their product grid with JavaScript, so a
   plain HTTP fetch (our httpx/selectolax stack) sees no products.
2. The underlying data lives behind `/rest/` and `.json` endpoints, which the
   site's `robots.txt` disallows, so we should not call them.
3. Scraped listing pages frequently omit the EAN barcode, and the matching stage
   depends on that identifier.

Working around all three means a headless browser (Playwright) plus fragile
selectors, and still leaves the missing-EAN problem.

By contrast, affiliate networks (Daisycon, TradeTracker, Awin) and many
retailers publish product feeds designed to be consumed programmatically. These
carry price, original price, and the EAN, in a stable structure, with no
JavaScript and no anti-bot measures.

## Decision
We will make the first real source a product feed, parsed by a generic
`FeedSource` adapter driven by a `FeedFieldMap`. The map describes which feed tag
maps to which `Listing` field, so one adapter handles many feed layouts by
configuration. A bundled sample feed lets the pipeline run with no external
setup; pointing it at a real feed URL is a one-line change.

## Consequences
**Easier**
- Clean, structured data including the EAN the matcher needs.
- No JavaScript rendering, no anti-bot friction, no `robots.txt` grey area.
- New feeds are usually a new `FeedFieldMap`, not a new class.

**Harder / accepted trade-offs**
- Using a live retailer feed needs a (free) affiliate-network account and a bit
  of setup, which is friction the demo hides.
- Feeds refresh on the retailer's schedule, so they lag fast-moving prices more
  than a direct scrape would.
- Feed coverage is limited to whichever retailers a network carries.

## Alternatives considered
- **Scrape the outlet pages with Playwright now.** Keeps us in scraping
  territory but is a heavier dependency, more fragile, and does not solve the
  missing-EAN problem. Deferred to a later adapter so scraping is learned
  deliberately rather than forced on the first source.
- **Scrape a simpler, server-rendered shop with httpx.** Possible, but hit or
  miss per site and still EAN-dependent. Not a reliable foundation to start on.
