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


class ProtocolError(ConnectionError):
    """The server's answer was not HTTP that could be read to its end: a body
    cut short, a header line without end, more headers than any page has."""


class BodyCutShort(ProtocolError):
    """The connection ended before the body did: fewer bytes than the length
    announced, a chunked body without its last chunk, or a compressed stream
    without its end in a body only the close delimited.

    Worth asking again, and never a reason to climb: a browser is sent the
    same cut, and shows what came of it as the page.
    """


class BodyUnfinished(ValueError):
    """The body came whole, as its framing counts it, and the compressed
    stream in it stops before its end: the server sent the start of a page
    and said it was all.

    Asked again, it says the same, so it is not worth asking again at once;
    and never a reason to climb, since a browser is sent the same bytes.
    """

    def __init__(self, url: str, encoding: str) -> None:
        super().__init__(
            f"{url} sent a body whose {encoding} stream ends before its end, "
            "though every byte its framing announced came"
        )
        self.url = url
        self.encoding = encoding


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


class RedirectRefused(Exception):
    """A redirect pointed where the caller said it may not lead, and was not asked.

    ``url`` is the address that redirected, ``target`` where it pointed, and
    ``reason`` the caller's rule. Never a reason to climb: a browser asking for
    the same address is sent to the same place.
    """

    def __init__(self, url: str, target: str, reason: str) -> None:
        super().__init__(
            f"{url} redirects to {target}, which is not followed: {reason}"
        )
        self.url = url
        self.target = target
        self.reason = reason


Redirects = Callable[[str, str], str | None]
"""A caller's rule for redirects: given the address that redirected and the one
it names, why that hop may not be followed, or None when it may. The crawler
uses one to keep a crawl on its site; a single fetch has none."""


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


@dataclass(frozen=True)
class CacheHit:
    """How a page came from ``sluicer.fetch.cache`` rather than from its site.

    ``age`` is the seconds since the site last answered for it, and
    ``revalidated`` whether the site was asked this time and said nothing
    changed (304); false means it was not asked at all, the page being
    younger than the cache's ``max_age``.
    """

    age: float
    revalidated: bool


@dataclass(frozen=True)
class Capture:
    """Which archived capture a page was read from (``sluicer.fetch.archive``).

    ``asked`` is the moment asked for and ``captured`` the capture's own, both
    as the archive writes them (``YYYYMMDDhhmmss``, the asked one as long as
    it was given); ``url`` is the address the capture is of.
    """

    archive: str
    asked: str
    captured: str
    url: str


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
    headers: dict[str, str] = field(default_factory=dict)
    """The response's headers, names lowercased, a repeated one's values joined
    with ", ". What the page's server said beside the page: a canonical in
    ``Link``, usage directives in ``X-Robots-Tag``, the charset."""
    archived: Capture | None = None
    """The capture the page was read from, when it came from an archive."""
    cached: CacheHit | None = None
    """How the page came from a cache, when it did."""


Rung = Callable[[str], Fetched]
"""One way of getting a page. It lives here, beside what it returns, so an
adapter does not have to import a type from the orchestrator that drives it."""
