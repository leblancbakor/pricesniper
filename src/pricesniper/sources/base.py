"""The extensibility seam of the whole project.

Every data source (a scrapeable clearance page, a Google Shopping feed, an
official API) is a subclass of ``SourceAdapter`` that implements exactly one
method: ``fetch()``, returning a list of normalized ``Listing`` objects.

Because everything downstream depends only on ``Listing`` (never on *how* it was
obtained), going from EU to US later means writing new adapters, not touching
matching, valuation, or alerting. See docs/adr/0001-pluggable-source-adapters.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Listing, Region


class SourceAdapter(ABC):
    """Base class every data source implements.

    Subclasses set ``name`` and ``region`` and implement ``fetch()``. Keeping
    ``fetch`` async matters because most sources are network-bound (HTTP
    requests); async lets many run concurrently later without threads. If you
    know JS, this is the same ``async``/``await`` you already use.
    """

    name: str = "unnamed"
    region: Region = Region.EU

    @abstractmethod
    async def fetch(self) -> list[Listing]:
        """Return the current listings from this source.

        Implementations should return normalized ``Listing`` objects and must
        not raise on an empty result; return an empty list instead.
        """
        raise NotImplementedError
