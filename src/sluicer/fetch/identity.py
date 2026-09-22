"""Who Sluicer says it is, and whether a site has asked it not to come.

A fetcher that hides behind a browser's user agent cannot be refused, because
nobody can tell it apart from a person. The most requested unaddressed issue on
the largest project in this field asks for exactly the opposite of that, so
Sluicer arrives under its own name and obeys what it is told.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from sluicer import __version__
from sluicer.extras import import_extra

USER_AGENT = f"Sluicer/{__version__} (+https://github.com/Gi0tto/sluicer)"
"""What every request says it is. One line in robots.txt is enough to refuse it."""

ROBOTS_TTL_SECONDS = 24 * 60 * 60
"""How long a robots.txt answer is believed before the site is asked again.

A day is the conventional figure, and the right one here. The promise this
module makes is that one line in a site's robots.txt is enough to turn us
away; an answer cached for the life of the process breaks that promise for
exactly the callers who keep a process alive -- a long-running MCP server
would obey a copy read at boot and never learn that a Disallow was added.
Re-reading is one cheap request a day per host, against a rule the site
owner is entitled to change at any moment.
"""


def robots_url_for(url: str) -> str:
    """Return the address of the robots file governing ``url``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def robots_allows(
    url: str,
    read: Callable[[str], str | None],
    cache: dict[str, tuple[float, str | None]] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Say whether ``url`` may be fetched, according to the site's own rules.

    ``read`` is given the robots address and returns its text, or None when
    there is nothing to read. Injecting it keeps this module out of the
    fetching business and every test off the network.

    A site that publishes no rules has not refused, so nothing to read means
    yes. A site that publishes a refusal is obeyed: a rule we were told about
    is not an obstacle to route around. What counts as "nothing to read" is
    ``read``'s decision, not this function's, and the default reader in
    ``ladder.py`` makes it by RFC 9309: a 5xx robots.txt is unavailable, not
    absent, and comes back as a full disallow rather than as nothing.

    An answer is remembered for ``ROBOTS_TTL_SECONDS`` and then asked for
    again. ``now`` is the clock that decides, injected for the same reason
    ``read`` is: a test proving an entry expires should move time, not spend
    it. ``time.monotonic`` and not the wall clock, because this measures an
    elapsed interval and a machine that resyncs its clock must not change how
    long an answer is believed for.
    """
    store = cache if cache is not None else _CACHE
    key = _cache_key(url)
    entry = store.get(key)
    if entry is None or now() - entry[0] >= ROBOTS_TTL_SECONDS:
        entry = (now(), read(robots_url_for(url)))
        store[key] = entry
    text = entry[1]
    if not text:
        return True
    # Imported here, not at module scope: ``scrapling_rungs`` imports
    # ``USER_AGENT`` from this module, so naming it at the top would close a
    # cycle. ``FetchExtraMissing`` and not the default ``MissingExtra``
    # because protego ships behind the fetch extra and the entry points catch
    # the extra's own class by name -- ``cli.py`` catches
    # ``FetchExtraMissing``, and a bare ``MissingExtra`` sailed past it and
    # reached the user as a traceback, which is the one thing
    # ``sluicer.extras`` promises an absent extra never does.
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    protego = import_extra(
        "protego",
        "fetch",
        doing="Reading a site's robots.txt",
        error=FetchExtraMissing,
    )
    return bool(protego.Protego.parse(text).can_fetch(url, USER_AGENT))


def _cache_key(url: str) -> str:
    """The robots resource ``url`` is governed by, as one string.

    Scheme and host, not host alone: ``http://example.com/robots.txt`` and
    ``https://example.com/robots.txt`` are two resources, and a site is free
    to publish different rules at each. Keyed on the host alone, whichever
    scheme was asked for first answered for both.
    """
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


_CACHE: dict[str, tuple[float, str | None]] = {}
"""Every answer this process has been given, with the moment it was given.

Process-global on purpose -- one site, one answer, however many callers --
and every entry carries its own timestamp so a stale one is re-read rather
than believed forever.
"""
