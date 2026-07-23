# 0003: SQLite via the standard library, behind a Store interface

- **Status:** accepted
- **Date:** 2026-07-23

## Context
v0.3 needs to persist two things: a history of observed prices, and a record of
which deals have already been alerted (so we do not re-announce them every run).
The roadmap originally noted "SQLite via SQLAlchemy". Before committing to that,
it is worth weighing whether an ORM earns its keep this early.

The data model is tiny and flat: two tables, a handful of columns, simple inserts
and lookups by key. There are no relationships to navigate, no migrations yet,
and the person building this is learning Python and would benefit from seeing the
SQL directly rather than through an ORM's abstraction.

## Decision
Use the standard library's `sqlite3` directly, hidden behind a `Store` interface
(an abstract base class), with `SQLiteStore` as the first implementation. Prices
are stored as TEXT and rebuilt into `Decimal` on read, so exactness is preserved
(a SQLite REAL is a float and would defeat the point of using `Decimal`).

This mirrors the input side of the pipeline: just as `SourceAdapter` hides where
listings come from, `Store` hides where they are persisted. Nothing in the
pipeline depends on the backend.

## Consequences
**Easier**
- Zero new dependencies; `sqlite3` ships with Python.
- The SQL is visible and teachable, which suits the learning goal.
- The `Store` interface keeps the door open: a `PostgresStore` (with or without
  SQLAlchemy) can drop in later without touching callers, which is the outcome
  the ORM was meant to provide anyway.

**Harder / accepted trade-offs**
- Hand-written SQL means no automatic migrations; schema changes are manual for
  now.
- `sqlite3` is synchronous, so heavy use would eventually want an async story.
  Fine at this scale.

## Alternatives considered
- **SQLAlchemy now (the original roadmap note).** Powerful and migration-friendly,
  but premature for two flat tables, and it adds a dependency and a learning
  layer before either is needed. Deferred: the `Store` interface means we can
  adopt it later exactly when Postgres or migrations make it worthwhile.
- **A flat file (JSON/CSV).** Simplest of all, but poor at concurrent-safe
  dedupe lookups and price-history queries, which SQLite handles for free.
