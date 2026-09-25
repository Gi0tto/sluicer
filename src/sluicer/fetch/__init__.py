"""Getting the page, at the lowest cost that works.

``fetch`` climbs the ladder, ``Fetched`` is what it brings back, and ``Climb``
is one step up with the measurement that forced it. ``robots_reader_from``
builds the reader the ladder asks robots.txt with, for a caller that asks it
too: a crawler pacing itself by ``Crawl-delay`` reads the same file the same
way. Import them from here, not from ``sluicer.fetch.ladder``, which is free to
move. Fetching needs the ``fetch`` extra.
"""

from sluicer.fetch.ladder import (
    AddressRefused,
    FetchFailed,
    PaymentRequired,
    RobotsRefused,
    SiteRefused,
    fetch,
    robots_reader_from,
)
from sluicer.fetch.result import Climb, Fetched, RedirectRefused, ResponseTooLarge

__all__ = [
    "AddressRefused",
    "Climb",
    "FetchFailed",
    "Fetched",
    "PaymentRequired",
    "RedirectRefused",
    "ResponseTooLarge",
    "RobotsRefused",
    "SiteRefused",
    "fetch",
    "robots_reader_from",
]
