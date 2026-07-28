# 0007: Recover missing barcodes from item detail

- **Status:** accepted
- **Date:** 2026-07-28

## Context
eBay keyword search is the only way to get broad coverage (barcode search alone
returned almost nothing), but the search *summary* objects usually omit the GTIN
even when the full listing has one. A live run returned 304 listings with zero
shared barcodes, so cross-seller matching could not fire and, after ADR-0006,
that correctly meant zero deals. Cross-seller arbitrage is the whole point, so we
need identities back.

The full item-detail endpoint (`/buy/browse/v1/item/{id}`) often carries the
`gtin` and `mpn`, and sellers frequently put the EAN in the listing's item
specifics (localized aspects) too. But detail is one extra API call per listing,
which at 304 listings a run would burn quota fast.

## Decision
After search, fetch item detail for summaries that lack an identity and fill in
the recovered `gtin`/`mpn`, up to a per-run cap (`EBAY_MAX_LOOKUPS`, default 60).
Lookups run with bounded concurrency. Recovery is on by default and can be turned
off. The extractor also reads EAN/MPN out of localized aspects, not just the
top-level fields.

## Consequences
**Easier**
- Keyword listings that carried a barcode all along become matchable, so genuine
  cross-seller deals appear.
- The cap keeps API usage predictable regardless of how many listings a run
  pulls.

**Harder / accepted trade-offs**
- Extra API calls (bounded by the cap), and a slower run when recovery is active.
- Recovery only helps listings whose seller actually entered an identity
  somewhere; truly identifier-less listings stay unmatched. That is expected.
- A per-run cap means some listings go un-recovered on large runs. A persistent
  itemId to barcode cache would remove most repeat lookups and is the natural
  next step.

## Alternatives considered
- **Fetch detail for every listing, uncapped.** Simplest, but wasteful and quota-
  hungry. The cap is a small amount of code for a lot of safety.
- **Trust keyword titles for matching instead of barcodes.** Fuzzy and error
  prone, exactly the false-match problem the identity-only rule (ADR-0001 era)
  was set up to avoid.
