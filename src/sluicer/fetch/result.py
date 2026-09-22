"""What a fetch returns, including how much it had to spend."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Climb:
    """One step between rungs, and the measurement that forced it.

    A step back down -- ``to_rung`` cheaper than ``from_rung`` -- records a rung
    that failed after a cheaper one had brought a page back, which is then the
    page returned.
    """

    from_rung: str
    to_rung: str
    reason: str


@dataclass
class Fetched:
    """A page, the rung that got it, and every climb along the way.

    ``url`` is where the fetch landed, after redirects, and is what the page's
    relative links resolve against; ``status`` is the HTTP status.
    """

    url: str
    html: str
    status: int
    rung: str
    climbs: list[Climb] = field(default_factory=list)


Rung = Callable[[str], Fetched]
"""One way of getting a page. It lives here, beside what it returns, so an
adapter does not have to import a type from the orchestrator that drives it."""
