"""Climb only when the page makes us.

The ladder starts at the cheapest rung and stops the moment a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can always see what a page cost and why.

A rung that raises is treated as a rung that failed: if not the last rung,
the climb is recorded and the next rung is tried. The last rung's exception
is the caller's to handle.
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
    for index, (name, rung) in enumerate(rungs):
        try:
            result = rung(url)
        except Exception as e:
            # A rung that raises is a rung that failed
            if index == len(rungs) - 1:
                # Last rung's exception propagates to the caller
                raise
            # Record the climb and try the next rung
            reason = f"the rung raised {type(e).__name__}: {e}"
            climbs.append(Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason))
            continue

        result.climbs = list(climbs)
        found = bool(extract(result.html, url=url).records)
        reason = why_climb(result.status, result.html, found_records=found)
        if reason is None or index == len(rungs) - 1:
            return result
        climbs.append(Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason))
