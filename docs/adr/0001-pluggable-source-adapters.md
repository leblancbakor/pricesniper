# 0001 — Pluggable source adapters

- **Status:** accepted
- **Date:** 2026-07-01

## Context
The plan is to start with EU retailers and expand to the US later, and to add
many data sources over time (clearance pages, shopping feeds, official APIs).
Each source returns data in its own messy shape. The risk is that source-specific
details (HTML structure, currency quirks, a particular API's JSON) leak into the
deal-detection logic, so that every new source or region forces edits across the
whole codebase.

We also want this to read as a well-engineered project, not a script — the
architecture is part of the deliverable.

## Decision
We will define a single interface, `SourceAdapter`, with one async method
`fetch() -> list[Listing]`. Every data source is a subclass of it. All sources
normalize their raw data into the shared `Listing` model, and **no stage after
the source is allowed to depend on how a listing was obtained.** `Region` is a
first-class field on `Listing` from day one.

## Consequences
**Easier**
- Adding a source (or a whole new region) is writing one new adapter; matching,
  valuation, scoring, and alerting are untouched.
- Each source is independently testable in isolation.
- The EU → US goal becomes a configuration/adapter change, not a rewrite.

**Harder / accepted trade-offs**
- Every source must fully normalize to `Listing` up front, including currency and
  identity extraction — more work per adapter than a quick one-off scrape.
- A shared model means a schema change ripples to all adapters. This is the point
  (one clear contract), but it is a real cost when the model evolves.

## Alternatives considered
- **Per-source bespoke scripts feeding the deal logic directly.** Faster for the
  very first source, but source details bleed into core logic and the second
  source (and the US move) become painful. Rejected: it trades a small early win
  for compounding later cost.
- **A generic config-driven scraper** (declare selectors in YAML). Powerful but
  heavy, and premature before we understand the real variety of sources.
  Revisit only if adapters start looking near-identical.
