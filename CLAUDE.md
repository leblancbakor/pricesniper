# CLAUDE.md

Context for AI assistants (and new humans) working in this repo. Keep it short
and current.

## What this is
PriceSniper: a cross-platform tech-deal detector. A pipeline that finds price
gaps/markdowns on barcoded tech, scores them, and (later) alerts on Discord.
Learning + portfolio project, built in the open, decisions recorded as ADRs.

## Architecture in one line
`Sources → Normalize → Match → Value → Score → Alert`, where everything after
Sources is region-agnostic. New data source = new `SourceAdapter` subclass;
never edit the pipeline to add a source. See `docs/architecture.md`.

## Where things live
- `src/pricesniper/models.py`: `Listing`, `Deal`, enums. The shared vocabulary.
- `src/pricesniper/sources/base.py`: the `SourceAdapter` interface.
- `src/pricesniper/sources/`: one file per real source (plus `demo.py`).
- `src/pricesniper/matching.py`: group by identity (EAN/UPC/MPN).
- `src/pricesniper/valuation.py`: reference price, gap, priority.
- `docs/adr/`: one Markdown file per significant decision.

## Conventions
- **Python** managed by **uv**. `uv sync` to set up, `uv run pricesniper` to run,
  `uv run pytest` for tests, `uv run ruff check` to lint.
- **Money is `Decimal`, never `float`.**
- **Paths use `pathlib`, never hand-built strings** (cross-platform).
- **Sources are async** (`async def fetch`) and return `list[Listing]`; return
  an empty list rather than raising on "nothing found".
- **Commits** follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`). Significant decisions get an ADR under `docs/adr/`.
- **Matching stays strict** (identity-only) until a deliberate ADR introduces
  fuzzy matching.

## Hard boundaries (do not cross)
- **Alert-only.** No auto-purchasing.
- **No credential storage.** Ever.
- Real adapters respect each site's ToS / `robots.txt`, prefer official
  feeds/APIs, and rate-limit politely.

## Current status
`v0.1`: pipeline runs on the `demo` source. Next up: first real EU adapter
(`v0.2`). See `ROADMAP.md`.
