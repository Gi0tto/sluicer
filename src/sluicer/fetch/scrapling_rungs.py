"""The real rungs, each a thin adapter over scrapling.

scrapling is optional: the base install reads HTML you already have, and only
fetching from the web needs a browser stack. Importing this module must stay
free, so the dependency is looked up when a rung is built, not at import time.
"""

from __future__ import annotations

from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.result import Fetched, Rung


class FetchExtraMissing(MissingExtra):
    """The optional ``fetch`` extra (scrapling) is not installed.

    A name of its own, because a caller that wants to say "install the extra"
    needs to catch exactly this and nothing wider. What "missing" means, and
    why a broken install must keep its traceback instead, is stated once in
    ``sluicer.extras`` and applies here unchanged.
    """


def _fetchers():
    """Return the three scrapling fetchers, or say the extra is not installed."""
    fetchers = import_extra(
        "scrapling.fetchers",
        "fetch",
        doing="Fetching a URL",
        error=FetchExtraMissing,
    )
    return fetchers.Fetcher, fetchers.DynamicFetcher, fetchers.StealthyFetcher


def _as_fetched(response, rung: str, requested_url: str) -> Fetched:
    """Wrap a scrapling Response, treating a response with no HTML as a failure.

    A rung that raises is a rung that failed: ``ladder.fetch`` already climbs
    past a failed rung and records why, so a missing body is reported the same
    way rather than let through as a page that was never there.
    """
    if not response.html_content:
        raise ValueError(f"the {rung} rung returned no HTML for {requested_url!r}")
    return Fetched(
        url=getattr(response, "url", None) or requested_url,
        html=response.html_content,
        status=response.status,
        rung=rung,
    )


def default_rungs() -> list[tuple[str, Rung]]:
    """Return the three rungs in the order they cost us."""
    fetcher, dynamic, stealthy = _fetchers()

    def http(url: str) -> Fetched:
        return _as_fetched(fetcher.get(url, timeout=30), "http", url)

    def browser(url: str) -> Fetched:
        return _as_fetched(dynamic.fetch(url, network_idle=True), "browser", url)

    def stealth(url: str) -> Fetched:
        return _as_fetched(stealthy.fetch(url, network_idle=True), "stealth", url)

    return [("http", http), ("browser", browser), ("stealth", stealth)]
