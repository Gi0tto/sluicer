"""The real rungs, each a thin adapter over scrapling.

scrapling is optional: the base install reads HTML you already have, and only
fetching from the web needs a browser stack. Importing this module must stay
free, so the dependency is looked up when a rung is built, not at import time.
"""

from __future__ import annotations

from sluicer.fetch.ladder import Rung
from sluicer.fetch.result import Fetched

_MISSING = (
    "Fetching a URL needs scrapling, which is not installed. "
    "Install it with: uv pip install 'sluicer[fetch]'"
)


def _fetchers():
    try:
        from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher
    except ImportError as missing:  # pragma: no cover - exercised via sys.modules
        raise ImportError(_MISSING) from missing
    if Fetcher is None:
        raise ImportError(_MISSING)
    return Fetcher, DynamicFetcher, StealthyFetcher


def _as_fetched(response, rung: str) -> Fetched:
    return Fetched(
        url=getattr(response, "url", ""),
        html=response.html_content,
        status=response.status,
        rung=rung,
    )


def default_rungs() -> list[tuple[str, Rung]]:
    """Return the three rungs in the order they cost us."""
    fetcher, dynamic, stealthy = _fetchers()

    def http(url: str) -> Fetched:
        return _as_fetched(fetcher.get(url, timeout=30), "http")

    def browser(url: str) -> Fetched:
        return _as_fetched(dynamic.fetch(url, network_idle=True), "browser")

    def stealth(url: str) -> Fetched:
        return _as_fetched(stealthy.fetch(url, network_idle=True), "stealth")

    return [("http", http), ("browser", browser), ("stealth", stealth)]
