"""The real rungs, each a thin adapter over scrapling.

scrapling is optional: the base install reads HTML you already have, and only
fetching from the web needs a browser stack. Importing this module must stay
free, so the dependency is looked up when a rung is built, not at import time.
"""

from __future__ import annotations

from typing import Any

from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.identity import USER_AGENT
from sluicer.fetch.result import Fetched, Rung

HTTP_TIMEOUT_SECONDS = 20
"""How long the plain HTTP rung waits for one response."""

BROWSER_TIMEOUT_MS = 30_000
"""How long the browser rung waits for one page, in scrapling's milliseconds.

One try each, and these two bounds, keep a slow site to under a minute for the
whole ladder; scrapling's defaults of three tries of thirty seconds a rung made
it three minutes, longer than an agent's tool call waits for an answer.
"""


class FetchExtraMissing(MissingExtra):
    """The optional ``fetch`` extra (scrapling) is not installed.

    A name of its own, because a caller that wants to say "install the extra"
    needs to catch exactly this and nothing wider. What "missing" means, and
    why a broken install must keep its traceback instead, is stated once in
    ``sluicer.extras`` and applies here unchanged.
    """


def _fetchers() -> tuple[Any, Any, Any]:
    """Return the three scrapling fetchers, or say the extra is not installed.

    ``Any``, three times, for the reason ``mcp_server.build_server`` gives for
    its own: scrapling is an optional extra imported by name at call time, so
    there is no ``Fetcher`` in this module for an annotation to resolve to.
    """
    fetchers = import_extra(
        "scrapling.fetchers",
        "fetch",
        doing="Fetching a URL",
        error=FetchExtraMissing,
    )
    return fetchers.Fetcher, fetchers.DynamicFetcher, fetchers.StealthyFetcher


def _as_fetched(response: Any, rung: str, requested_url: str) -> Fetched:
    """Wrap a scrapling Response, treating a response with no HTML as a failure.

    ``response`` is a scrapling ``Response``, a type this module cannot name
    without importing the extra it exists to not import at module level.

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

    The browser rung uses ``useragent``, not ``extra_headers``, and this was
    measured, not assumed: against a live request to
    ``https://httpbin.org/user-agent``, ``extra_headers={"User-Agent": ...}``
    was silently overridden by the browser context's own generated user
    agent (the server still saw Chrome), while ``useragent=...`` reached the
    wire correctly. A unit test cannot catch this on its own, because a fake
    accepts whatever keyword it is handed; it took a real server to find it.
    """
    fetcher, dynamic, _ = _fetchers()

    def http(url: str) -> Fetched:
        return _as_fetched(
            fetcher.get(
                url,
                timeout=HTTP_TIMEOUT_SECONDS,
                retries=1,
                headers={"User-Agent": USER_AGENT},
                # scrapling's defaults add ``Referer: https://www.google.com/``
                # and a Chrome TLS fingerprint, which is dressing up as a
                # browser that came from a search. Measured on the wire.
                stealthy_headers=False,
                impersonate=None,
            ),
            "http",
            url,
        )

    def browser(url: str) -> Fetched:
        return _as_fetched(
            dynamic.fetch(
                url,
                network_idle=True,
                useragent=USER_AGENT,
                timeout=BROWSER_TIMEOUT_MS,
                retries=1,
                # The browser's own Google referer, off for the same reason.
                google_search=False,
            ),
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
