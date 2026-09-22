"""Climb only when the page makes us, and only where we are allowed to.

The ladder starts at the cheapest rung and stops the moment a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can always see what a page cost and why.

A rung that raises is treated as a rung that failed: if not the last rung,
the climb is recorded and the next rung is tried. The last rung's exception
is the caller's to handle.

Before any rung is tried, the site's own robots.txt is asked. A refusal
raises ``RobotsRefused`` rather than returning some empty ``Fetched``: "the
site said no" and "the site had nothing" are different events, and giving
them the same shape is the failure this project spends its history removing.
"""

from __future__ import annotations

from typing import Callable, Sequence

from sluicer.api import extract
from sluicer.fetch.identity import robots_allows
from sluicer.fetch.result import Climb, Fetched, Rung
from sluicer.fetch.rules import why_climb


class RobotsRefused(Exception):
    """The site's own robots.txt refuses this URL to us."""

    def __init__(self, url: str) -> None:
        super().__init__(f"{url} is refused by the site's own robots.txt")
        self.url = url


def _default_robots_reader(cheapest_rung: Rung) -> Callable[[str], str | None]:
    """Build a robots reader from the ladder's own cheapest rung.

    A caller who wires nothing up still needs a way to read a robots.txt
    file, and the cheapest rung of whatever ladder is already in play --
    the real "http" rung in production, a fake in a test -- already knows
    how to fetch a URL. Reusing it means production needs no extra wiring
    and a test supplying its own rungs needs no extra network stack either.

    A robots.txt that cannot be reached -- the site is down, the file 404s,
    the connection times out, the rung raises -- is not a refusal, so any
    failure here is swallowed into "nothing to read", exactly as a missing
    robots file is: a site with no reachable robots file has not told us no.
    """

    def read(url: str) -> str | None:
        try:
            return cheapest_rung(url).html
        except Exception:
            return None

    return read


def fetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
) -> Fetched:
    """Fetch ``url``, climbing only when a measurement says the rung failed.

    When ``obey_robots`` is true (the default), the site's own robots.txt is
    consulted before the first rung is tried; a refusal raises
    ``RobotsRefused`` and no rung ever runs. ``robots_reader`` is injected
    exactly as ``rungs`` is, and defaults to a reader built from the cheapest
    rung so production needs no wiring.

    When ``stealth`` is true, ``stealth_rung()`` is appended to the ladder:
    climbing to it is something a caller asks for, not something that
    happens on its own.
    """
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs()
    if stealth:
        from sluicer.fetch.scrapling_rungs import stealth_rung

        rungs = [*rungs, stealth_rung()]
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")

    if obey_robots:
        read = robots_reader if robots_reader is not None else _default_robots_reader(rungs[0][1])
        if not robots_allows(url, read=read):
            raise RobotsRefused(url)

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
