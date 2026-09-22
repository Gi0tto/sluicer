"""Getting the page, at the lowest cost that works.

This is the fetch surface: ``fetch`` climbs the ladder, ``Fetched`` is what it
brings back, and ``Climb`` is one step up with the measurement that forced it.
Importing them from here rather than from ``sluicer.fetch.ladder`` names the
job instead of the implementation, and leaves that module free to move.
"""

from sluicer.fetch.ladder import fetch
from sluicer.fetch.result import Climb, Fetched

__all__ = ["Climb", "Fetched", "fetch"]
