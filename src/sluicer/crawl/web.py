"""How a crawl reaches the web: one seam, so the tests never do.

A crawl also remembers, for as long as it runs, which rung each part of a site
needed (``Parts``): a shop's listing pages are plain HTML and its product
pages a script's, and a site that needed the browser for a product need not
be asked of it for its next listing page.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from sluicer.fetch import STICKY, RungMemory, robots_reader_from
from sluicer.fetch.address import _resolve
from sluicer.fetch.gate import site_key
from sluicer.fetch.http_rung import Response
from sluicer.fetch.ladder import Needed
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Redirects, Rung


@dataclass(frozen=True)
class Web:
    """The three ways a crawl asks a site for something.

    ``rungs`` fetch its pages, through the ladder. ``read`` reads a robots.txt,
    as the ladder would. ``get`` fetches what is not a page -- a sitemap -- as
    the bytes that came back. ``default_web`` builds the real ones; a test hands
    in fakes. ``memory`` is the rung each site needed, which its next page
    starts at: the process's for the real web, none for a fake unless given.
    """

    rungs: Sequence[tuple[str, Rung]]
    read: Callable[[str], str | None]
    get: Callable[[str], Response]
    memory: RungMemory | None = None


def default_web(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Web:
    """The real web: the default ladder, with ``redirects`` asked of every hop a
    page's redirect makes, and plain HTTP for robots.txt and sitemaps.

    robots.txt is read without the rule: RFC 9309 says to follow its redirects
    across hosts, and a crawl kept to its site still owes the site's robots.txt
    a reading wherever the site keeps it.

    ``headers`` and ``cookies`` go with every request -- pages, robots.txt,
    sitemaps -- to the origin asked, as ``fetch`` sends them.
    """
    from sluicer.fetch.http_rung import http_responses, http_rung
    from sluicer.fetch.identity import outgoing
    from sluicer.fetch.rungs import default_rungs

    send = outgoing(headers, cookies)
    rungs = default_rungs(
        allow_private, resolve, max_bytes, redirects, headers=headers, cookies=cookies
    )
    plain = http_rung(allow_private, resolve, max_bytes, send=send)
    get = http_responses(allow_private, resolve, max_bytes, send=send)
    return Web(rungs=rungs, read=robots_reader_from(plain), get=get, memory=STICKY)


class Parts(RungMemory):
    """The rung each part of a site needed during one crawl, over what the
    process remembers of the whole site.

    A part is an address's directory, its path without the last segment:
    ``/p/`` for ``/p/1``, ``/c/`` for ``/c/1?page=2``, ``/`` for a page at the
    root. What a part needed decides where its next page starts: the browser
    once one of its pages needed it, plain HTTP once one came back from plain
    HTTP (``served``). A part not seen yet starts where the site does, by the
    process's memory, which learns and forgets as it always has.

    Measured before, on a local shop whose listings are server-rendered and
    whose products a script draws: once its first product needed the browser,
    three of its seven listing pages were asked of the browser too, 0.7 s each
    where plain HTTP took 2 ms. A site whose every page is a script's is asked
    as before: its first page per part is the one that learns.
    """

    def __init__(self, site: RungMemory) -> None:
        super().__init__(site.limit, site.ttl, site.clock)
        self.site = site
        self._parts: dict[str, Needed | None] = {}
        self._part_lock = threading.Lock()

    def recall(self, url: str) -> Needed | None:
        key = _part(url)
        with self._part_lock:
            if key in self._parts:
                return self._parts[key]
        return self.site.recall(url)

    def learn(self, url: str, rung: str, reason: str) -> None:
        if rung not in self.NEVER:
            with self._part_lock:
                self._parts[_part(url)] = Needed(rung, reason, self.clock())
        self.site.learn(url, rung, reason)

    def forget(self, url: str) -> None:
        with self._part_lock:
            self._parts.pop(_part(url), None)
        self.site.forget(url)

    def served(self, url: str) -> None:
        """Note that ``url``'s page came back from the cheapest rung, with no
        climb: the next page of its part starts there, unless the part was
        seen to need more."""
        with self._part_lock:
            self._parts.setdefault(_part(url), None)

    def clear(self) -> None:
        with self._part_lock:
            self._parts.clear()

    def of(self, url: str) -> str:
        with self._part_lock:
            known = self._parts.get(_part(url)) is not None
        if not known:
            return self.site.of(url)
        return f"{_directory(url)} on {site_key(url)}"


def _directory(url: str) -> str:
    path = urlsplit(url).path or "/"
    return path[: path.rindex("/") + 1]


def _part(url: str) -> str:
    return f"{site_key(url)} {_directory(url)}"
