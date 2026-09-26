"""Who Sluicer says it is, and whether a site has asked it not to come.

A fetcher behind a browser's user agent cannot be refused, since nobody can tell
it from a person. Sluicer arrives under its own name and obeys robots.txt.
"""

from __future__ import annotations

import importlib
import math
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sluicer import __version__
from sluicer.fetch.address import shown

PRODUCT_TOKEN = "Sluicer"
"""The name a robots.txt group is matched against, and nothing else.

RFC 9309 matches a group's ``User-agent`` against the crawler's product token,
case-insensitively. Handed the whole user agent, protego looks for a group's
name anywhere in it at a word's start, so ``User-agent: https`` -- or
``github``, or ``com`` -- was taken for ours: another crawler's rules refused
us and its delay paced us.
"""

USER_AGENT = f"{PRODUCT_TOKEN}/{__version__} (+https://github.com/Gi0tto/sluicer)"
"""What every request says it is. One line in robots.txt is enough to refuse it:
``User-agent: Sluicer``."""

_WRITTEN_BY_THE_TRANSPORT = frozenset(
    {
        "host",
        "accept-encoding",
        "connection",
        "keep-alive",
        "content-length",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "proxy-authorization",
        "proxy-connection",
    }
)
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


def refused_header(name: str) -> str | None:
    """Why a caller may not send a header called ``name``, or None when it may.

    ``User-Agent`` is ours: a site that does not want Sluicer must be able to
    say so, and a caller who could rename us would take that from it. The
    others are the transport's own -- where the request goes, how its body
    and its connection are framed, which encodings it can decode -- and a
    caller's would contradict it.
    """
    lowered = name.strip().lower()
    if not _TOKEN.fullmatch(name.strip()):
        return f"{name!r} is not a header name"
    if lowered == "user-agent":
        return (
            "the User-Agent is not replaced: Sluicer always says it is "
            f"{PRODUCT_TOKEN}, so that a site can refuse it"
        )
    if lowered in _WRITTEN_BY_THE_TRANSPORT:
        return f"the {name.strip()} header is written by the transport, not by a caller"
    return None


def outgoing(
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The headers a caller asked to send, cookies folded into one ``Cookie``.

    A header ``refused_header`` refuses, a value that runs onto another line,
    or a cookie whose name or value would break the header is a
    ``ValueError`` naming it, before anything is asked of any site.
    """
    sent: dict[str, str] = {}
    for name, value in (headers or {}).items():
        refusal = refused_header(name)
        if refusal is not None:
            raise ValueError(refusal)
        if "\r" in value or "\n" in value:
            raise ValueError(f"the {name} header's value runs onto another line")
        sent[name.strip()] = value.strip()
    crumbs = []
    for name, value in (cookies or {}).items():
        if not _TOKEN.fullmatch(name):
            raise ValueError(f"{name!r} is not a cookie name")
        if any(c in value for c in ';,\r\n"') or value != value.strip():
            raise ValueError(f"the value of the cookie {name} would break the header")
        crumbs.append(f"{name}={value}")
    if crumbs:
        given = next((key for key in sent if key.lower() == "cookie"), None)
        joined = "; ".join(crumbs)
        if given is None:
            sent["Cookie"] = joined
        else:
            sent[given] = f"{sent[given]}; {joined}"
    return sent


ROBOTS_TTL_SECONDS = 24 * 60 * 60
"""How long a robots.txt answer is believed before the site is asked again.

A day, the conventional figure. Cached for the life of the process, a
long-running MCP server would never learn that a Disallow was added.
"""


ROBOTS_CACHE_HOSTS = 4096
"""How many sites' robots.txt answers the process keeps, least recent out first.

Without a bound, a long-running server that is sent to many sites keeps one
entry for each of them for a day. Four thousand answers are a few megabytes at
most, and a site pushed out is only asked again.
"""


UNREACHABLE = "sluicer: robots.txt unreachable"
"""The comment a reader's stand-in carries when nothing answered at all."""

UNREACHABLE_AGAIN = "sluicer: robots.txt unreachable, and would be again"
"""The same, when what failed would fail again if asked later: a name that
does not exist, an encoding this install cannot read. Not worth a retry."""

UNAVAILABLE = "sluicer: robots.txt unavailable"
"""The comment a reader's stand-in refusal carries when the site answered 5xx."""


# Said after a robots.txt's 5xx, which is not the page's own answer: a site
# that answers 500 to anyone not logged in has its logged-in pages refused.
_UNAVAILABLE_MEANS = (
    ", which RFC 9309 reads as nothing allowed until it answers otherwise; a "
    "robots.txt is asked without the caller's headers and cookies"
)


class RobotsUnreachable(Exception):
    """The robots.txt could not be read -- no answer, or a 5xx -- so nothing is.

    RFC 9309 treats both as a full disallow, and nothing is fetched. It is not
    reported as the site refusing us, though: a host that does not resolve has
    refused nothing, and a 503 is a reason to try later, not a rule.

    ``transient`` says whether asking again later may meet something else:
    false when what failed would fail again, a name that does not exist
    among them, which until 0.9.1 was asked again as if it might.
    """

    def __init__(self, url: str, detail: str, transient: bool = True) -> None:
        super().__init__(shown(f"could not read the robots.txt for {url}: {detail}"))
        self.url = shown(url)
        self.detail = shown(detail)
        self.transient = transient


def robots_url_for(url: str) -> str:
    """Return the address of the robots file governing ``url``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def robots_allows(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Say whether ``url`` may be fetched, according to the site's own rules.

    Args:
        url: the page to be fetched.
        read: given the robots.txt address, returns its text, or None when the
            site publishes none (which means yes). Injected so this module
            does no fetching and tests stay off the network. The ladder's
            default reader follows RFC 9309 for statuses.
        cache: where answers are kept; the process-wide cache by default.
        now: the clock, monotonic so a clock resync does not change how long
            an answer is believed; injected so a test can move time.

    An answer is remembered for ``ROBOTS_TTL_SECONDS``. A robots.txt that
    could not be read counts as a refusal here; ``robots_refusal`` tells the
    two apart.
    """
    try:
        return robots_refusal(url, read, cache, now) is None
    except RobotsUnreachable:
        return False


def robots_refusal(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> str | None:
    """Why ``url`` may not be fetched, or None when it may.

    ``robots_allows``, with the reason kept. When the robots.txt could not be
    read at all -- nothing answered, or it answered 5xx -- it raises
    ``RobotsUnreachable`` instead, and that answer is not remembered.
    """
    rules = _rules(url, read, cache, now)
    if rules is None or rules.can_fetch(url, PRODUCT_TOKEN):
        return None
    return "its robots.txt disallows it"


def robots_delay(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> float:
    """How many seconds the site asks us to leave between requests; 0 if none.

    ``Crawl-delay``, or the interval a ``Request-rate`` of ``n/s`` implies,
    whichever asks for more, from the group that applies to ``PRODUCT_TOKEN``.
    Neither is in RFC 9309, and both are what a site that wants to be asked
    less often actually writes. A value that is not a number is no request;
    an infinite one is kept, so a caller bounding its waits can refuse it.
    Read through the same cache as ``robots_refusal``, with the same
    ``RobotsUnreachable``.
    """
    rules = _rules(url, read, cache, now)
    if rules is None:
        return 0.0
    delay = float(rules.crawl_delay(PRODUCT_TOKEN) or 0.0)
    rate = rules.request_rate(PRODUCT_TOKEN)
    if rate is not None and rate.requests > 0:
        delay = max(delay, rate.seconds / rate.requests)
    return 0.0 if math.isnan(delay) or delay < 0 else delay


def robots_sitemaps(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The sitemaps the site's robots.txt names, in the order it names them.

    ``Sitemap:`` lines belong to no group, so they are the site's whatever user
    agent asks. Read through the same cache as ``robots_refusal``.
    """
    rules = _rules(url, read, cache, now)
    return [] if rules is None else [str(found) for found in rules.sitemaps]


def _rules(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None,
    now: Callable[[], float],
) -> Any:
    """The parsed robots.txt governing ``url``, or None when it publishes none.

    ``Any``: protego is imported by name, so there is no class here to name.
    """
    text = _robots_text(url, read, cache, now)
    if not text:
        return None
    parser = protego()
    parsed = _PARSED.get(text)
    if parsed is None:
        parsed = _PARSED[text] = parser.Protego.parse(text)
    return parsed


def protego() -> Any:
    """protego, the robots.txt parser: a dependency of the base install.

    Imported by name when first asked, so that reading HTML, which never
    reads a robots.txt, does not pay for it; ``Any``, because protego ships
    no types.
    """
    return importlib.import_module("protego")


def _robots_text(
    url: str,
    read: Callable[[str], str | None],
    cache: MutableMapping[str, tuple[float, str | None]] | None,
    now: Callable[[], float],
) -> str | None:
    """The text of the robots.txt governing ``url``, remembered for a day."""
    store = cache if cache is not None else _CACHE
    key = _cache_key(url)
    entry = store.get(key)
    if entry is None or now() - entry[0] >= ROBOTS_TTL_SECONDS:
        entry = (now(), read(robots_url_for(url)))
        first = entry[1].splitlines()[0] if entry[1] else ""
        for marker, said, why, again in (
            (UNREACHABLE, "", "", True),
            (UNREACHABLE_AGAIN, "", "", False),
            (UNAVAILABLE, "it answered ", _UNAVAILABLE_MEANS, True),
        ):
            if first.startswith(f"# {marker}: "):
                # RFC 9309 puts a 5xx and a network error in one class, and
                # neither is remembered: one bad minute must not keep a
                # long-running server away from a site for a day.
                store.pop(key, None)
                raise RobotsUnreachable(
                    url, said + first[len(marker) + 4 :] + why, transient=again
                )
    # Written back even when it was only read: that is what keeps a site in
    # use from being the one a bounded cache forgets.
    store[key] = entry
    return entry[1]


def robots_cached(
    url: str,
    cache: MutableMapping[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Whether the answer for ``url``'s robots.txt is at hand, so asking costs
    no request. A crawler counts a request it makes as one the site receives."""
    entry = (cache if cache is not None else _CACHE).get(_cache_key(url))
    return entry is not None and now() - entry[0] < ROBOTS_TTL_SECONDS


def _cache_key(url: str) -> str:
    """The robots resource ``url`` is governed by, as one string.

    Scheme, host and port: ``http://`` and ``https://`` robots.txt are two
    resources, and a site may publish different rules at each. Written as
    the origin is, whatever the address's spelling: the scheme and host
    lowercased, a default port left out, a user and password dropped. Until
    0.9.1 the key was the raw ``scheme://netloc``, so ``http://A.com:80/``
    and ``http://a.com/`` were two entries, and the robots.txt asked twice.
    """
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return url
    written = f"[{host}]" if ":" in host else host
    if port is not None and port != {"http": 80, "https": 443}.get(scheme):
        written += f":{port}"
    return f"{scheme}://{written}"


class _Recent(OrderedDict[str, tuple[float, str | None]]):
    """A mapping that forgets its least recently written entry past ``limit``.

    ``robots_refusal`` writes back every answer it uses, so written is used.
    """

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def __setitem__(self, key: str, value: tuple[float, str | None]) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


class _RecentParsed(OrderedDict[str, Any]):
    """The last ``limit`` robots.txt texts parsed, by their text."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


_PARSED = _RecentParsed(64)
"""The rules each recent robots.txt parses to, by its text: a crawl asks for
every address it reads, and each asking parsed the text again, 2.5 s for one
of 16 MiB. By the text, not the site, so a site's new robots.txt is parsed
afresh; a string keeps its hash, so finding a long one again costs little."""

_CACHE = _Recent(ROBOTS_CACHE_HOSTS)
"""Every answer this process has been given, with the moment it was given.

Process-global on purpose: one site, one answer, however many callers. Bounded
by ``ROBOTS_CACHE_HOSTS``.
"""
