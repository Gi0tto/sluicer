"""How a crawl reaches the web: one seam, so the tests never do."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sluicer.fetch import robots_reader_from
from sluicer.fetch.address import _resolve
from sluicer.fetch.http_rung import Response
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Redirects, Rung


@dataclass(frozen=True)
class Web:
    """The three ways a crawl asks a site for something.

    ``rungs`` fetch its pages, through the ladder. ``read`` reads a robots.txt,
    as the ladder would. ``get`` fetches what is not a page -- a sitemap -- as
    the bytes that came back. ``default_web`` builds the real ones; a test hands
    in fakes.
    """

    rungs: Sequence[tuple[str, Rung]]
    read: Callable[[str], str | None]
    get: Callable[[str], Response]


def default_web(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
) -> Web:
    """The real web: the default ladder, with ``redirects`` asked of every hop a
    page's redirect makes, and plain HTTP for robots.txt and sitemaps.

    robots.txt is read without the rule: RFC 9309 says to follow its redirects
    across hosts, and a crawl kept to its site still owes the site's robots.txt
    a reading wherever the site keeps it.

    Raises:
        FetchExtraMissing: the ``fetch`` extra is not installed.
    """
    from sluicer.fetch.http_rung import http_responses, http_rung
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing, default_rungs

    rungs = default_rungs(allow_private, resolve, max_bytes, redirects)
    plain = http_rung(allow_private, resolve, max_bytes, error=FetchExtraMissing)
    get = http_responses(allow_private, resolve, max_bytes, error=FetchExtraMissing)
    return Web(rungs=rungs, read=robots_reader_from(plain), get=get)
