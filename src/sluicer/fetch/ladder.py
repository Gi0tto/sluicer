"""Climb only when the page makes us.

The ladder starts at the cheapest rung and stops the moment a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can always see what a page cost and why.
"""

from __future__ import annotations

from typing import Callable, Sequence

from sluicer.api import extract
from sluicer.fetch.result import Climb, Fetched
from sluicer.fetch.rules import why_climb

Rung = Callable[[str], Fetched]


def fetch(url: str, rungs: Sequence[tuple[str, Rung]] | None = None) -> Fetched:
    """Fetch ``url``, climbing only when a measurement says the rung failed."""
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs()
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")

    climbs: list[Climb] = []
    result = None
    for index, (name, rung) in enumerate(rungs):
        result = rung(url)
        result.climbs = list(climbs)
        found = bool(extract(result.html, url=url).records)
        reason = why_climb(result.status, result.html, found_records=found)
        if reason is None or index == len(rungs) - 1:
            return result
        climbs.append(Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason))
    return result
