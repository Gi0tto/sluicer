"""What a fetch returns, including how much it had to spend."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
"""The most a page may weigh, in bytes of HTML, before the fetch gives up on it.

Sixteen mebibytes is several times the heaviest ordinary page; past it, a
response is a file, a mistake or an attack, and parsing it is what costs the
memory. The HTTP rung stops reading at the bound, compressed or not, so a
small gzip that inflates to gigabytes costs sixteen mebibytes.
"""


class ResponseTooLarge(Exception):
    """The page is heavier than the fetch was allowed to read.

    Never a reason to climb: a browser asking for the same page gets the same
    bytes, and more of them.
    """

    def __init__(self, url: str, limit: int) -> None:
        super().__init__(f"{url} is larger than {limit} bytes; it was not read")
        self.url = url
        self.limit = limit


class EmptyBody(ValueError):
    """A rung was answered with nothing at all.

    For a page it is a rung that failed, and the ladder climbs past it. For a
    robots.txt it is an answer -- an empty file has no rules -- so the status
    the site answered with is kept, for the reader to decide by.
    """

    def __init__(self, url: str, rung: str, status: int) -> None:
        super().__init__(f"the {rung} rung returned no HTML for {url!r}")
        self.url = url
        self.status = status


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
    seconds: float = 0.0
    """How long ``from_rung`` took before the ladder climbed past it."""


@dataclass
class Fetched:
    """A page, the rung that got it, and every climb along the way.

    ``url`` is where the fetch landed, after redirects, and is what the page's
    relative links resolve against; ``status`` is the HTTP status; ``seconds``
    is how long the rung that got it took.
    """

    url: str
    html: str
    status: int
    rung: str
    climbs: list[Climb] = field(default_factory=list)
    seconds: float = 0.0


Rung = Callable[[str], Fetched]
"""One way of getting a page. It lives here, beside what it returns, so an
adapter does not have to import a type from the orchestrator that drives it."""
