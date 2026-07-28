# Architecture Decision Records (ADRs)

An ADR is a short note capturing **one significant decision**: the context, the
choice, and the consequences. They're how this project records *why* it's built
the way it is, the reasoning that code alone can't show.

Each decision gets its own numbered file. ADRs are immutable once accepted: if a
later decision changes things, write a new ADR that supersedes the old one rather
than editing history. That way the repo tells the honest story of how the design
evolved.

Use [`template.md`](template.md) to start a new one.

## Index
- [0001: Pluggable source adapters](0001-pluggable-source-adapters.md)
- [0002: Start with a product feed, not a scraper](0002-first-source-feed-over-scrape.md)
- [0003: SQLite via the standard library, behind a Store interface](0003-sqlite-behind-a-store-interface.md)
- [0004: Alert via Discord's REST API, not a gateway bot](0004-discord-via-rest-not-a-gateway-bot.md)
- [0005: eBay Browse API for cross-seller arbitrage](0005-ebay-browse-api-for-arbitrage.md)
- [0006: Do not trust single-seller markdowns](0006-do-not-trust-single-seller-markdowns.md)
- [0007: Recover missing barcodes from item detail](0007-recover-missing-barcodes-from-item-detail.md)
