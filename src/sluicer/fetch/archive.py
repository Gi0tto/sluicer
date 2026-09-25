"""Read a page as the Wayback Machine captured it, instead of from its site.

A capture puts no load on the site, and it never changes: the same capture
gives the same answer next year, so a reading is reproducible across time as
well as across runs. ``fetch_archived`` asks the archive for the capture
nearest to a date, in its ``id_`` form -- the page as it was served, without
the archive's toolbar or its rewritten links -- over the plain HTTP rung, with
every guard a live fetch has: robots.txt (the archive's own, which allows
everything by being absent), the size bound, and the refusal of private
addresses. Redirects are followed only within the archive.

The archive answers for any date with its nearest capture, which may be
years away; the capture's own timestamp is read from where the answer landed
and reported as ``Capture.captured``, never passed off as the date asked for.
The headers the site sent with the capture come back as ``x-archive-orig-*``,
and are handed on under their own names, so a canonical in ``Link``,
``X-Robots-Tag`` and the charset are read as for a live page.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from sluicer.fetch.address import _resolve
from sluicer.fetch.gate import GATE, after, ungated
from sluicer.fetch.ladder import FetchFailed, fetch
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Capture, Fetched

ARCHIVE = "web.archive.org"
_ORIGINAL = "x-archive-orig-"
_LANDED = re.compile(r"^https?://web\.archive\.org/web/(\d{4,14})id_/(.+)$")


class NotArchived(FetchFailed):
    """The archive holds no capture of the page."""

    def __init__(self, url: str, at: str) -> None:
        super().__init__(
            url, [], f"{ARCHIVE} holds no capture of {url} (asked for {at})"
        )
        self.at = at


def timestamp(at: str) -> str:
    """``at`` as the archive's timestamp: its digits, year first.

    ``2025``, ``2025-06``, ``2025-06-01``, ``2025-06-01T10:30:00Z`` and
    ``20250601`` are read; anything else, or a month 13, is a ``ValueError``.
    """
    digits = re.sub(r"[-:TZ ]", "", at.strip().upper())
    if not re.fullmatch(r"\d{4}(\d{2}){0,5}", digits):
        raise ValueError(f"{at!r} is not a date: write 2025, 2025-06 or 2025-06-01")
    limits = [
        (4, 1, 9999),
        (6, 1, 12),
        (8, 1, 31),
        (10, 0, 23),
        (12, 0, 59),
        (14, 0, 59),
    ]
    for end, low, high in limits:
        if len(digits) >= end and not low <= int(digits[end - 2 : end]) <= high:
            raise ValueError(f"{at!r} is not a date")
    return digits


def fetch_archived(
    url: str,
    at: str,
    obey_robots: bool = True,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    rung: Callable[[str], Fetched] | None = None,
) -> Fetched:
    """The capture of ``url`` nearest to ``at``, read as a page.

    The ``Fetched`` is the page as the site served it: its ``url`` is the
    captured address, so its links resolve as on the site, its ``headers``
    are the site's, and ``archived`` says which capture it is. ``rung`` is
    injected by tests; by default the plain HTTP rung, told to follow
    redirects only within the archive.

    Raises:
        ValueError: ``at`` is not a date, or ``url`` not an http(s) address.
        NotArchived: the archive has no capture of it.
        FetchFailed: the archive could not be read, or answered off the archive.
        RobotsRefused, AddressRefused, ResponseTooLarge: as ``fetch`` raises
            them, for the archive's address.
    """
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"{url!r} is not an http(s) address")
    asked = timestamp(at)
    address = f"https://{ARCHIVE}/web/{asked}id_/{url}"
    real = rung is None
    if rung is None:
        from sluicer.fetch.http_rung import http_rung
        from sluicer.fetch.scrapling_rungs import FetchExtraMissing

        rung = http_rung(
            allow_private, resolve, max_bytes, FetchExtraMissing, _within_archive
        )
    # The archive is a site like any other, asked in its turn.
    with GATE.turn(address) if real else ungated() as ready:
        fetched = fetch(
            address,
            rungs=[("archive", after(ready, rung))],
            obey_robots=obey_robots,
            allow_private=allow_private,
            resolve=resolve,
            max_bytes=max_bytes,
        )
    if fetched.status == 404:
        raise NotArchived(url, at)
    landed = _LANDED.match(fetched.url)
    if landed is None:
        raise FetchFailed(url, [], f"{ARCHIVE} answered from {fetched.url}")
    if not 200 <= fetched.status < 300:
        raise FetchFailed(
            url, [], f"{ARCHIVE} answered status {fetched.status} for {address}"
        )
    captured, original = landed.group(1), landed.group(2)
    headers = {
        name[len(_ORIGINAL) :]: value
        for name, value in fetched.headers.items()
        if name.startswith(_ORIGINAL)
    }
    if "content-type" in fetched.headers:
        headers.setdefault("content-type", fetched.headers["content-type"])
    return Fetched(
        url=original,
        html=fetched.html,
        status=fetched.status,
        rung="archive",
        climbs=fetched.climbs,
        seconds=fetched.seconds,
        headers=headers,
        archived=Capture(ARCHIVE, asked, captured, original),
    )


def _within_archive(current: str, target: str) -> str | None:
    """Follow a redirect only to the archive itself: its nearest capture."""
    if urlsplit(target).hostname == ARCHIVE and urlsplit(target).scheme == "https":
        return None
    return f"it leads off {ARCHIVE}, to {target}"
