"""Persistence: price history and deal de-duplication.

Two jobs live here, both keyed off the shared models so nothing upstream has to
change:

  * **Price history** records every price we observe, so we can later tell
    whether today's "deal" is a real low or just normal pricing.
  * **De-duplication** remembers which deals we have already alerted on, so a
    deal is announced once, not on every run. If the price drops *further*, the
    key changes and it alerts again, which is exactly what we want.

``Store`` is an interface (like ``SourceAdapter`` on the input side), and
``SQLiteStore`` is the first implementation. Keeping the interface separate means
a Postgres store could drop in later without touching the pipeline. See
docs/adr/0003-sqlite-behind-a-store-interface.md.

Money is stored as TEXT, not a SQLite REAL, because REAL is a float and would
reintroduce exactly the rounding errors we use ``Decimal`` to avoid.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path

from .models import Deal, Listing

# Default on-disk location. `data/` is gitignored, so the database never gets
# committed.
DEFAULT_DB_PATH = Path("data") / "pricesniper.db"


def _deal_key(deal: Deal) -> str:
    """A stable identity for one deal at one price.

    Same product at the same price -> same key -> alerted once. A further price
    drop produces a new key, so it is treated as fresh news.
    """
    listing = deal.listing
    return f"{listing.identity or listing.url}|{listing.price}"


class Store(ABC):
    """Interface every persistence backend implements."""

    @abstractmethod
    def record_price(self, listing: Listing) -> None:
        """Append one price observation to the history."""

    @abstractmethod
    def is_new_deal(self, deal: Deal) -> bool:
        """True if this deal has not been alerted before."""

    @abstractmethod
    def mark_alerted(self, deal: Deal) -> None:
        """Remember that this deal has now been alerted."""

    @abstractmethod
    def price_history(self, identity: str) -> list[tuple[Decimal, str]]:
        """Return ``(price, seen_at)`` rows for a product, oldest first."""


class SQLiteStore(Store):
    """A SQLite-backed store using the standard library's ``sqlite3``."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = path
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False keeps things simple if we go async later; for
        # now everything runs on one thread anyway.
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                identity TEXT,
                seller   TEXT,
                source   TEXT,
                price    TEXT NOT NULL,   -- Decimal as text, for exactness
                currency TEXT NOT NULL,
                seen_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_price_identity ON price_history(identity);

            CREATE TABLE IF NOT EXISTS alerted_deals (
                deal_key   TEXT PRIMARY KEY,
                identity   TEXT,
                price      TEXT NOT NULL,
                priority   TEXT NOT NULL,
                alerted_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def record_price(self, listing: Listing) -> None:
        self._db.execute(
            "INSERT INTO price_history "
            "(identity, seller, source, price, currency, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                listing.identity,
                listing.seller,
                listing.source,
                str(listing.price),
                listing.currency,
                listing.seen_at.isoformat(),
            ),
        )
        self._db.commit()

    def is_new_deal(self, deal: Deal) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM alerted_deals WHERE deal_key = ?", (_deal_key(deal),)
        ).fetchone()
        return row is None

    def mark_alerted(self, deal: Deal) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO alerted_deals "
            "(deal_key, identity, price, priority, alerted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                _deal_key(deal),
                deal.listing.identity,
                str(deal.listing.price),
                deal.priority.value,
                deal.listing.seen_at.isoformat(),
            ),
        )
        self._db.commit()

    def price_history(self, identity: str) -> list[tuple[Decimal, str]]:
        rows = self._db.execute(
            "SELECT price, seen_at FROM price_history "
            "WHERE identity = ? ORDER BY id ASC",
            (identity,),
        ).fetchall()
        return [(Decimal(price), seen_at) for price, seen_at in rows]

    def close(self) -> None:
        self._db.close()
