"""Getting the page, at the lowest cost that works.

``fetch`` climbs the ladder, ``Fetched`` is what it brings back, and ``Climb``
is one step up with the measurement that forced it. ``robots_reader_from``
builds the reader the ladder asks robots.txt with, for a caller that asks it
too: a crawler pacing itself by ``Crawl-delay`` reads the same file the same
way. ``RungMemory`` is the rung each site needed, and ``STICKY`` the process's.
Import them from here, not from ``sluicer.fetch.ladder``, which is free to
move. Plain HTTP needs no extra; the browser rung needs the ``browser`` one.
"""

from sluicer.fetch.ladder import (
    STICKY,
    AddressRefused,
    FetchFailed,
    Needed,
    PaymentRequired,
    RobotsRefused,
    RungMemory,
    SiteRefused,
    fetch,
    robots_reader_from,
)
from sluicer.fetch.result import Climb, Fetched, RedirectRefused, ResponseTooLarge

__all__ = [
    "STICKY",
    "AddressRefused",
    "Climb",
    "FetchFailed",
    "Fetched",
    "Needed",
    "PaymentRequired",
    "RedirectRefused",
    "ResponseTooLarge",
    "RobotsRefused",
    "RungMemory",
    "SiteRefused",
    "fetch",
    "robots_reader_from",
]
