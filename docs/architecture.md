# Architecture

This document explains how PriceSniper fits together and *why* it is shaped this
way. For the point-in-time decisions behind specific choices, see
[`adr/`](adr/).

## The core idea: a pipeline of single-purpose stages

Finding deals is really one data pipeline:

> **get prices → figure out what a thing is worth → decide if the gap is real →
> tell someone fast enough to act.**

Each stage does exactly one job and hands a clean, validated object to the next.
No stage reaches back into a previous stage's concerns. This is what keeps the
system understandable as it grows and is the reason a new data source never
forces a change to the deal logic.

```
Sources → Normalize → Match → Value → Score → Alert
                                 └─────────────→ Store (price history, dedupe)
```

## The shared model (`models.py`)

Every stage speaks in terms of three objects:

- **`Listing`** — one offer, on one site, at one moment. This is the *only* thing
  a source produces. It carries three identity fields (`ean` / `upc` / `mpn`);
  at least one must be present for the item to be matchable.
- **`Deal`** — a `Listing` that we've judged to be priced meaningfully below a
  reference, with the gap, a priority, and a human-readable reason attached.
- Enums (`Region`, `Condition`, `Priority`) that keep categorical values honest.

Money is `Decimal`, never `float`. Prices must be exact.

## Stage by stage

### 1. Sources (`sources/`)
Each data source is a `SourceAdapter` subclass implementing one async method,
`fetch() -> list[Listing]`. A source might scrape a clearance page, read a Google
Shopping feed, or call an official API — downstream code neither knows nor cares.
**This is the extensibility seam.** EU → US expansion happens entirely here.

### 2. Match (`matching.py`)
Groups listings that refer to the same physical product. v0.1 uses exact identity
matching only (shared EAN/UPC/MPN). Strictness is intentional: a single wrong
match yields a false "deal" and erodes trust. Fuzzy matching is a deliberate,
later step.

### 3. Value + 4. Score (`valuation.py`)
For each listing we derive a **reference price** from the strongest available
signal — the store's own `was_price` markdown, or the median of what other
sellers charge for the same item — then compute the gap. Gaps above a threshold
become `Deal`s, tagged with a priority tier. Current thresholds are first-pass
placeholders; tuning them into a proper weighted score is a roadmapped milestone.

### 5. Alert *(not built yet — v0.3)*
Formats `Deal`s into Discord embeds, with de-duplication so the same listing is
not announced twice.

### Store *(not built yet — v0.3)*
Persists seen-listing IDs (for dedupe) and price history (a feature in its own
right). Starts as SQLite, can grow into Postgres without touching callers.

## Why region is a first-class field, not an afterthought

`Region` lives on every `Listing` from the start. This is what makes the EU-first,
US-later plan a configuration change rather than a rewrite: the pipeline already
carries the concept end to end, so a US adapter simply stamps `Region.US` and
everything downstream keeps working. See
[ADR-0001](adr/0001-pluggable-source-adapters.md).

## What is deliberately *not* here

- **No auto-purchasing and no stored credentials.** The project is alert-only by
  design — a security and ethics boundary, not a missing feature.
- **No fuzzy matching yet.** Trust first; cleverness later.
- **No real scrapers yet.** The `demo` source stands in so the pipeline is
  runnable and testable from commit one.
