# Roadmap

Milestones are sized so each is a satisfying, self-contained commit you can write
up. "Done" means it runs, is tested where it makes sense, and has an ADR if it
involved a real decision.

### `v0.1`: the loop, on fake data  ✅ (this commit)
- Shared model (`Listing`, `Deal`), `SourceAdapter` interface, a `demo` source.
- Matching + valuation + scoring.
- Runnable end to end: `uv run pricesniper` prints deals. Tests green.

### `v0.2`: first real EU source  ✅
- `FeedSource`: a generic product-feed adapter driven by a `FeedFieldMap`, so one
  class parses many feed layouts by configuration. Handles EU comma decimals,
  optional was-prices, stock, and the EAN the matcher needs.
- Runs on a bundled sample feed today; a real feed URL is a one-line swap.
- [ADR-0002](docs/adr/0002-first-source-feed-over-scrape.md): why a feed beat
  scraping the outlet pages (JavaScript rendering, `robots.txt`, missing EANs).
- Next: sign up with an affiliate network (Daisycon / TradeTracker / Awin) and
  point `FeedSource` at a live feed.

### `v0.3`: persistence and Discord alerts
- SQLite store (via SQLAlchemy) for seen-listing dedupe **and** price history.
- Discord bot posts deal embeds: title (linked), image, price math, priority.

### `v0.4`: a second EU source
- Add a second adapter. This is where the pluggable design pays off, proof the
  seam works. Great ADR material.

### `v0.5`: thesis and context field
- Optional short "why this matters" blurb per deal (e.g. the RAM/AI supply
  narrative), from category + catalyst context.

### `v1.0`: go US
- First US adapter + region config. Demonstrates the EU → US design goal end to
  end without rewriting the pipeline.

### Later / ideas
- Telegram alerts alongside Discord.
- Priority score v2: weighted blend of gap %, absolute margin, match confidence,
  seller trust, resale liquidity.
- Restock / drop monitor for limited-stock hype items (a distinct engine).
- A small web dashboard over the price-history data.
