"""The real rungs, each a thin adapter over scrapling.

scrapling is optional: the base install reads HTML you already have, and only
fetching from the web needs a browser stack. Importing this module must stay
free, so the dependency is looked up when a rung is built, not at import time.
"""

from __future__ import annotations

from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.identity import USER_AGENT
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
    """Return the rungs a caller gets without asking for anything more.

    Two rungs, in the order they cost us. Both announce ``USER_AGENT``: a
    site that does not want us can refuse us, the way it refuses anyone else
    who says who they are. Climbing from "plain HTTP" to "a browser" is a
    change of cost, not a change of what we are, so both rungs stay here.
    """
    fetcher, dynamic, _ = _fetchers()

    def http(url: str) -> Fetched:
        return _as_fetched(
            fetcher.get(url, timeout=30, headers={"User-Agent": USER_AGENT}),
            "http",
            url,
        )

    def browser(url: str) -> Fetched:
        return _as_fetched(
            dynamic.fetch(url, network_idle=True, extra_headers={"User-Agent": USER_AGENT}),
            "browser",
            url,
        )

    return [("http", http), ("browser", browser)]


def stealth_rung() -> tuple[str, Rung]:
    """Return the third rung, for a caller who has decided they want it.

    Climbing from announcing ourselves to disguising ourselves is a change of
    character, not a change of technique, so it does not happen automatically
    to a caller who never asked for it. It stays available, one argument
    away, for someone who has decided that is what they want.

    No ``User-Agent`` is sent here, and none should be added later: this
    rung's whole purpose is not to be recognised, and announcing an identity
    and then trying to evade detection is incoherent. That is a ruling, not
    an oversight.
    """
    _, _, stealthy = _fetchers()

    def stealth(url: str) -> Fetched:
        return _as_fetched(stealthy.fetch(url, network_idle=True), "stealth", url)

    return ("stealth", stealth)
