"""The pages a site says it has, from its sitemaps.

A sitemap is XML from a place you do not control, so it is read as an attack
would be written. No entity is resolved, nothing is fetched from inside it, and
a document that declares a document type is refused outright: a sitemap never
needs one, and billion laughs and external entities both arrive through one.
Gzip is inflated only up to the bound a page is held to, so a small file that
inflates to gigabytes costs sixteen mebibytes.

Every sitemap is fetched politely, like a page: through robots.txt, after the
site's delay, one at a time. How many are followed, how many addresses are
kept and how long it may take are all bounded, and the answer says when a
bound cut it short.
"""

from __future__ import annotations

import io
import time
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

import lxml.etree

from sluicer.crawl.schedule import DEFAULT_DELAY_SECONDS, MAX_DELAY_SECONDS, Politeness
from sluicer.crawl.urls import links_on, normalise, site_of
from sluicer.crawl.web import Web, default_web
from sluicer.document import load
from sluicer.extras import MissingExtra
from sluicer.fetch import AddressRefused, FetchFailed, fetch
from sluicer.fetch.address import _resolve, why_not_public
from sluicer.fetch.identity import RobotsUnreachable, robots_refusal, robots_sitemaps
from sluicer.fetch.result import MAX_RESPONSE_BYTES

MAX_SITEMAPS = 50
"""The most sitemap files one map reads. A site's index names its files, and
a site with thousands of them is asking for a crawl, not a map."""

MAX_SITEMAP_URLS = 50_000
"""The most addresses a map keeps: the protocol's own limit for one file."""

GUESSES = ("/sitemap.xml", "/sitemap_index.xml")
"""Where a sitemap is looked for when robots.txt names none, in this order."""

_OFF_SITE = "an index lists sitemaps of its own site, and this one is elsewhere"
_GZIP = b"\x1f\x8b"
_BOM = b"\xef\xbb\xbf"


class SitemapUnreadable(Exception):
    """What was fetched cannot be read as a sitemap; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Sitemap:
    """What one sitemap file lists, as written.

    ``kind`` is ``urlset`` (pages), ``sitemapindex`` (more sitemaps) or
    ``text`` (one address a line). ``entries`` are each ``loc`` with its
    ``lastmod``. ``broken`` says why reading stopped early, when it did: the
    entries before that point are kept, and the reason goes with them.
    """

    kind: str
    entries: tuple[tuple[str, str | None], ...]
    broken: str | None = None


@dataclass(frozen=True)
class SiteUrl:
    """One address a site has: ``lastmod`` as its sitemap wrote it, and the
    ``sitemap`` that listed it, None when it was a link on the start page."""

    url: str
    lastmod: str | None = None
    sitemap: str | None = None


@dataclass(frozen=True)
class SitemapRead:
    """One sitemap a map tried: what it was, how many entries it held, and why
    it could not be read, when it could not."""

    url: str
    kind: str | None = None
    entries: int = 0
    error: str | None = None


@dataclass(frozen=True)
class SiteMap:
    """The addresses of a site, and where they came from.

    ``source`` is ``sitemaps`` when its sitemaps gave any address on the site,
    and ``links`` when they gave none and the start page's links stand in.
    ``truncated`` is true when a bound -- the limit, the number of sitemaps,
    the time -- stopped the map before the site's sitemaps were read out.
    """

    url: str
    source: str
    urls: tuple[SiteUrl, ...]
    sitemaps: tuple[SitemapRead, ...]
    truncated: bool = False


def parse_sitemap(
    body: bytes,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_entries: int = MAX_SITEMAP_URLS,
) -> Sitemap:
    """Read a sitemap's bytes: gzip or not, XML or a list of addresses.

    No more than ``max_entries`` are read; a file listing more says so in
    ``broken``, since the protocol caps one file at fifty thousand and what
    lies past the cap was never read.

    Raises:
        SitemapUnreadable: it is not a sitemap, it declares a document type,
            its gzip is broken, or it inflates past ``max_bytes``.
    """
    data = _inflated(body, max_bytes)
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return _xml(data, max_entries)
    # Whitespace before the XML declaration is an error libxml2 will not read
    # past and every search engine does; measured, web-scraping.dev's sitemap
    # opens with a newline. Nothing a document says is in it.
    bom = _BOM if data.startswith(_BOM) else b""
    data = bom + data[len(bom) :].lstrip(b" \t\r\n")
    if data[len(bom) :].startswith(b"<"):
        return _xml(data, max_entries)
    return _text(data, max_entries)


def _inflated(body: bytes, max_bytes: int) -> bytes:
    """``body``, inflated when it is gzip, never past ``max_bytes``.

    Told by its first two bytes, not by the address or a header: a server that
    announced the gzip as an encoding has already had it undone, and one that
    names a file ``.xml.gz`` may serve it plain.
    """
    if not body.startswith(_GZIP):
        return body
    inflate = zlib.decompressobj(zlib.MAX_WBITS | 16)
    try:
        data = inflate.decompress(body, max_bytes + 1)
    except zlib.error as broken:
        raise SitemapUnreadable(f"its gzip is broken: {broken}") from None
    if len(data) > max_bytes:
        raise SitemapUnreadable(
            f"it inflates to more than {max_bytes} bytes, the bound a page is held to"
        )
    if not inflate.eof:
        raise SitemapUnreadable("its gzip ends before the file does")
    return data


def _xml(data: bytes, max_entries: int) -> Sitemap:
    events = lxml.etree.iterparse(
        io.BytesIO(data),
        events=("start", "end"),
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    root = None
    kind = item = ""
    entries: list[tuple[str, str | None]] = []
    try:
        for event, element in events:
            if root is None:
                root, kind = element, _local(element)
                if kind not in ("urlset", "sitemapindex"):
                    raise SitemapUnreadable(
                        f"it is not a sitemap: its root is <{kind}>"
                    )
                info = element.getroottree().docinfo
                if info.internalDTD is not None or info.externalDTD is not None:
                    raise SitemapUnreadable(
                        "it declares a document type, which a sitemap never needs "
                        "and an entity attack does, so it was not read"
                    )
                item = "url" if kind == "urlset" else "sitemap"
                continue
            if event != "end" or element.getparent() is not root:
                continue
            if _local(element) == item:
                entry = _entry(element)
                if entry is not None:
                    entries.append(entry)
            # What has been read is let go, so a large file costs one entry.
            element.clear()
            while element.getprevious() is not None:
                del root[0]
            if len(entries) > max_entries:
                return Sitemap(kind, tuple(entries[:max_entries]), _past(max_entries))
    except lxml.etree.XMLSyntaxError as broken:
        if root is None:
            raise SitemapUnreadable(f"it is not XML: {broken}") from None
        return Sitemap(kind, tuple(entries), broken=f"it stops being XML: {broken}")
    return Sitemap(kind, tuple(entries))


def _entry(element: lxml.etree._Element) -> tuple[str, str | None] | None:
    loc = lastmod = None
    for child in element:
        name = _local(child)
        if name == "loc":
            loc = (child.text or "").strip()
        elif name == "lastmod":
            lastmod = (child.text or "").strip() or None
    return (loc, lastmod) if loc else None


def _local(element: lxml.etree._Element) -> str:
    """The element's name without its namespace: sitemaps are written under
    three, and under none."""
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(data: bytes, max_entries: int) -> Sitemap:
    lines = data.decode("utf-8", errors="replace").splitlines()
    entries = [
        (line.strip(), None)
        for line in lines
        if line.strip().lower().startswith(("http://", "https://"))
    ]
    if not entries:
        raise SitemapUnreadable("it is neither XML nor a list of addresses")
    if len(entries) > max_entries:
        return Sitemap("text", tuple(entries[:max_entries]), _past(max_entries))
    return Sitemap("text", tuple(entries))


def _past(max_entries: int) -> str:
    return f"it lists more than {max_entries} entries, and the rest were not read"


def map_site(
    url: str,
    limit: int = MAX_SITEMAP_URLS,
    max_sitemaps: int = MAX_SITEMAPS,
    *,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SiteMap:
    """The addresses of ``url``'s site, from its sitemaps or, failing those, the
    links on the page at ``url``.

    The sitemaps are the ones its robots.txt names, in its order; when it names
    none, ``/sitemap.xml`` and then ``/sitemap_index.xml``. An index is followed
    to the sitemaps it lists on the same site; one robots.txt names may live
    anywhere, since the site vouched for it. Only addresses on the site are
    kept -- the same host, with or without ``www.``, http or https -- each once,
    in the order the sitemaps list them.

    Args:
        url: where the site starts; its links are the fallback.
        limit: the most addresses kept.
        max_sitemaps: the most sitemap files read.
        min_delay: the least seconds between two requests to one site.
        max_delay: the longest ``Crawl-delay`` waited for; a sitemap behind a
            longer one is reported unread.
        time_budget: seconds after which no further sitemap is asked for.
        allow_private: when false, refuse addresses off the public internet.
        resolve: the name lookup ``allow_private`` decides with.
        max_bytes: the most a sitemap, inflated, or a page may weigh.
        web: how the site is reached; the real web by default.
        clock, sleep: the time, injected so a test can pace a map.

    Returns:
        A ``SiteMap``, with every sitemap tried and what became of it.

    Raises:
        FetchFailed: ``url`` is not an http(s) address, its robots.txt could
            not be read, or its sitemaps gave nothing and the page failed too.
        AddressRefused: ``allow_private`` is false and ``url`` is private.
        RobotsRefused, ResponseTooLarge: the sitemaps gave nothing, and this is
            what happened to the page.
        FetchExtraMissing: the ``fetch`` extra is not installed.
    """
    start = normalise(url)
    if start is None:
        raise FetchFailed(url, [], f"{url!r} is not an http(s) address")
    if not allow_private:
        refused = why_not_public(start, resolve)
        if refused is not None:
            raise AddressRefused(start, refused)
    web = web if web is not None else default_web(allow_private, resolve, max_bytes)
    polite = Politeness(web.read, min_delay, clock, sleep)
    deadline = None if time_budget is None else clock() + time_budget
    site = site_of(start)
    try:
        waiting = robots_sitemaps(start, polite.reader, now=clock)
    except RobotsUnreachable as unreachable:
        raise FetchFailed(start, [], str(unreachable)) from unreachable
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(start))
    guesses = [] if waiting else [origin + path for path in GUESSES]
    reads: list[SitemapRead] = []
    asked: set[str] = set()
    kept: dict[str, SiteUrl] = {}
    truncated = False

    def read(address: str) -> bool:
        """Read one sitemap into ``kept`` and ``waiting``; whether it read."""
        nonlocal truncated
        found = _fetch_sitemap(
            address, polite, web, max_delay, max_bytes, allow_private, resolve
        )
        if isinstance(found, str):
            reads.append(SitemapRead(address, error=found))
            return False
        reads.append(SitemapRead(address, found.kind, len(found.entries), found.broken))
        if found.broken is not None and found.broken.startswith("it lists more"):
            truncated = True
        for loc, lastmod in found.entries:
            listed = normalise(loc)
            if listed is None:
                continue
            if found.kind == "sitemapindex":
                if site_of(listed) == site:
                    waiting.append(listed)
                else:
                    reads.append(SitemapRead(listed, error=_OFF_SITE))
            elif site_of(listed) == site and listed not in kept:
                if len(kept) >= limit:
                    truncated = True
                    break
                kept[listed] = SiteUrl(listed, lastmod, address)
        return True

    while waiting or guesses:
        if (
            len(asked) >= max_sitemaps
            or len(kept) >= limit
            or (deadline is not None and clock() >= deadline)
        ):
            truncated = True
            break
        address = normalise(waiting.pop(0)) if waiting else guesses.pop(0)
        if address is None or address in asked:
            continue
        asked.add(address)
        if read(address):
            # The first guess that reads is the site's sitemap; the second
            # would be asked for nothing.
            guesses.clear()

    if kept:
        return SiteMap(start, "sitemaps", tuple(kept.values()), tuple(reads), truncated)
    links = _links_of_start(
        start, site, polite, web, limit, allow_private, resolve, max_bytes
    )
    return SiteMap(start, "links", links, tuple(reads), truncated)


def _fetch_sitemap(
    address: str,
    polite: Politeness,
    web: Web,
    max_delay: float,
    max_bytes: int,
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
) -> Sitemap | str:
    """One sitemap, read politely, or the sentence that says why it was not."""
    refused = None if allow_private else why_not_public(address, resolve)
    if refused is not None:
        return f"it is not fetched: {refused}"
    try:
        if robots_refusal(address, polite.reader, now=polite.clock) is not None:
            return "its robots.txt disallows it"
        delay = polite.delay_for(address)
    except RobotsUnreachable as unreachable:
        return str(unreachable)
    if delay > max_delay:
        return (
            f"its site asks for {delay:g} s between requests, "
            f"longer than the {max_delay:g} s this map waits"
        )
    polite.wait(address, delay)
    try:
        response = web.get(address)
    except MissingExtra:
        raise
    # Deliberately blind, as the ladder is about its rungs: every way a
    # transport can fail to bring a sitemap back is the same event here, this
    # sitemap was not read, and the sentence says why.
    except Exception as failure:  # noqa: BLE001
        return f"{type(failure).__name__}: {failure}"
    finally:
        polite.ended(address)
    if response.status != 200:
        return f"it answered {response.status}"
    try:
        return parse_sitemap(response.body, max_bytes, MAX_SITEMAP_URLS)
    except SitemapUnreadable as unreadable:
        return unreadable.reason


def _links_of_start(
    start: str,
    site: str,
    polite: Politeness,
    web: Web,
    limit: int,
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
) -> tuple[SiteUrl, ...]:
    """The links on the start page that stay on the site, in document order."""
    try:
        delay = polite.delay_for(start)
    except RobotsUnreachable as unreachable:
        raise FetchFailed(start, [], str(unreachable)) from unreachable
    polite.wait(start, delay)
    try:
        fetched = fetch(
            start,
            rungs=polite.paced(web.rungs),
            robots_reader=polite.reader,
            allow_private=allow_private,
            resolve=resolve,
            max_bytes=max_bytes,
        )
    finally:
        polite.ended(start)
    links = links_on(load(fetched.html, url=fetched.url))
    return tuple(SiteUrl(link) for link in links if site_of(link) == site)[:limit]
