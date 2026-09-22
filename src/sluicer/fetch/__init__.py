"""Getting the page, at the lowest cost that works.

``fetch`` climbs the ladder, ``Fetched`` is what it brings back, and ``Climb``
is one step up with the measurement that forced it. Import them from here, not
from ``sluicer.fetch.ladder``, which is free to move. Fetching needs the
``fetch`` extra.
"""

from sluicer.fetch.ladder import AddressRefused, FetchFailed, RobotsRefused, fetch
from sluicer.fetch.result import Climb, Fetched

__all__ = [
    "AddressRefused",
    "Climb",
    "FetchFailed",
    "Fetched",
    "RobotsRefused",
    "fetch",
]
