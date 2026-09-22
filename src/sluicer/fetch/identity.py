"""Who Sluicer says it is, and whether a site has asked it not to come.

A fetcher that hides behind a browser's user agent cannot be refused, because
nobody can tell it apart from a person. The most requested unaddressed issue on
the largest project in this field asks for exactly the opposite of that, so
Sluicer arrives under its own name and obeys what it is told.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from sluicer import __version__
from sluicer.extras import import_extra

USER_AGENT = f"Sluicer/{__version__} (+https://github.com/Gi0tto/sluicer)"
"""What every request says it is. One line in robots.txt is enough to refuse it."""


def robots_url_for(url: str) -> str:
    """Return the address of the robots file governing ``url``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def robots_allows(
    url: str,
    read: Callable[[str], str | None],
    cache: dict | None = None,
) -> bool:
    """Say whether ``url`` may be fetched, according to the site's own rules.

    ``read`` is given the robots address and returns its text, or None when
    there is nothing to read. Injecting it keeps this module out of the
    fetching business and every test off the network.

    A site that publishes no rules has not refused, so a missing or unreadable
    robots file means yes. A site that publishes a refusal is obeyed: a rule we
    were told about is not an obstacle to route around.
    """
    host = urlsplit(url).netloc
    store = cache if cache is not None else _CACHE
    if host not in store:
        store[host] = read(robots_url_for(url))
    text = store[host]
    if not text:
        return True
    protego = import_extra("protego", "fetch", doing="Reading a site's robots.txt")
    return bool(protego.Protego.parse(text).can_fetch(url, USER_AGENT))


_CACHE: dict[str, str | None] = {}
