"""The files a site serves beside a page: robots.txt, llms.txt, llms-full.txt.

Read for ``sluicer.audit``, over plain HTTP only -- a text file wants no
browser -- and under the same rules as every other request: our own name, and
the site's robots.txt obeyed for the two llms files. robots.txt itself is
always read, as RFC 9309 has every crawler do. A file that could not be read
is a ``SiteFile`` saying why, never an exception: one missing file is part of
what an audit reports, not a reason to stop it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from sluicer.audit.report import Site, SiteFile
from sluicer.extras import import_extra
from sluicer.fetch.address import AddressRefused, _resolve
from sluicer.fetch.http_rung import http_rung
from sluicer.fetch.identity import USER_AGENT, robots_url_for
from sluicer.fetch.result import MAX_RESPONSE_BYTES, ResponseTooLarge, Rung
from sluicer.fetch.scrapling_rungs import FetchExtraMissing

LLMS_FILES = ("/llms.txt", "/llms-full.txt")
"""Where llmstxt.org puts the file, at the root, and the longer companion
many sites publish beside it."""


def read_site(
    url: str,
    rung: Rung | None = None,
    obey_robots: bool = True,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
) -> Site:
    """Read what the site of ``url`` serves beside it.

    Args:
        url: the page; its scheme and host name the site.
        rung: how a file is fetched; the HTTP rung by default, returning an
            empty body as an answer. Injected so tests stay off the network.
        obey_robots: leave out an llms file the site's robots.txt refuses to
            Sluicer, or any file when robots.txt could not be read.
        allow_private: as for ``fetch``: when false, refuse addresses off the
            public internet, redirects included.
        resolve: the name lookup ``allow_private`` decides with.

    Raises:
        AddressRefused: ``allow_private`` is false and the site is private.
        FetchExtraMissing: the ``fetch`` extra is not installed.
    """
    if rung is None:
        rung = http_rung(
            allow_private,
            resolve,
            MAX_RESPONSE_BYTES,
            error=FetchExtraMissing,
            allow_empty=True,
        )
    robots = _read(rung, robots_url_for(url))
    parts = urlsplit(url)
    files = []
    for path in LLMS_FILES:
        address = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        refusal = _refusal(address, robots) if obey_robots else None
        files.append(
            SiteFile(address, error=refusal) if refusal else _read(rung, address)
        )
    return Site(robots, files[0], files[1])


def _read(rung: Rung, address: str) -> SiteFile:
    """What ``address`` answered, or why nothing did."""
    try:
        fetched = rung(address)
    except AddressRefused:
        raise
    except ResponseTooLarge as heavy:
        return SiteFile(address, error=str(heavy))
    # Deliberately blind, as the ladder's robots reader is: every way a
    # request fails is the same event here, a file that could not be read.
    except Exception as failure:  # noqa: BLE001
        return SiteFile(address, error=f"{type(failure).__name__}: {failure}")
    text = fetched.html if 200 <= fetched.status < 300 else None
    return SiteFile(fetched.url, status=fetched.status, text=text)


def _refusal(address: str, robots: SiteFile) -> str | None:
    """Why ``address`` is not to be fetched, per the robots.txt read, or None."""
    if robots.status is not None and 400 <= robots.status < 500:
        return None
    if not robots.found:
        return (
            "not fetched: the site's robots.txt could not be read, which RFC 9309 "
            "treats as a refusal"
        )
    protego = import_extra(
        "protego",
        "fetch",
        doing="Reading a site's robots.txt",
        error=FetchExtraMissing,
    )
    if protego.Protego.parse(robots.text or "").can_fetch(address, USER_AGENT):
        return None
    return "not fetched: the site's robots.txt disallows it"
