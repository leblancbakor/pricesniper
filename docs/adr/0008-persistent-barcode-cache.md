# 0008: Persistent barcode cache

- **Status:** accepted
- **Date:** 2026-07-28

## Context
ADR-0007 added barcode recovery via item-detail lookups, capped per run to
protect the API quota. But the cap (default 60) meant a run could only ever
resolve a slice of a large result set, and every run started from nothing and
re-looked-up the same items. Coverage never grew, and quota was wasted on
repeats.

ADR-0007 already flagged the fix: remember resolved barcodes across runs.

## Decision
Cache each looked-up item's identity in the SQLite store, keyed by eBay itemId,
including negative results (looked up, none found) so those are not retried
either. During recovery, cached items are applied for free and only genuinely new
items cost a lookup and count against the cap. The eBay source depends on a
narrow `BarcodeCache` protocol (two methods), which `SQLiteStore` satisfies
structurally, so the source stays decoupled from the full storage layer.

## Consequences
**Easier**
- Coverage accumulates: each run spends its lookup budget on new items, so the
  set of matchable listings grows over time and more real cross-seller deals
  surface.
- Far fewer API calls on repeat runs (demonstrated: 3 lookups on first run, 0 on
  the second for the same items).

**Harder / accepted trade-offs**
- Cached barcodes can go stale if a listing is relisted under a new itemId, but
  itemIds are stable enough and a wrong cache only affects matching, not price.
- The source now takes an optional collaborator (the cache). Kept clean by
  depending on a small protocol rather than the concrete store.

## Alternatives considered
- **A separate cache file/store.** Avoids touching the main store, but duplicates
  SQLite plumbing and splits state across two databases. Reusing the existing
  store via a narrow protocol is cleaner.
- **No negative caching.** Simpler, but items with genuinely no identity would be
  re-looked-up every run, wasting most of the quota. Caching the negative result
  is what makes the budget go to new work.
