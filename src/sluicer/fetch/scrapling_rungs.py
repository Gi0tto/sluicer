"""The real rungs, each a thin adapter over scrapling.

scrapling is optional -- the base install reads HTML you already have -- so it
is imported when a rung is built, never when this module is.

What each rung sends is checked on the wire, not by the suite: a faked library
accepts whatever keyword it is handed. If you change how a rung is built, ask a
real server what it saw.
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

One try per rung and these two bounds keep a slow site under a minute for the
whole ladder. scrapling's defaults, three tries of thirty seconds a rung, came to
three minutes, longer than an agent's tool call waits.
"""


class FetchExtraMissing(MissingExtra):
    """The optional ``fetch`` extra (scrapling) is not installed.

    Its message names the install line. What counts as missing, as opposed to
    broken, is ``sluicer.extras``'s rule.
    """


def _fetchers() -> tuple[Any, Any, Any]:
    """Return the three scrapling fetchers, or say the extra is not installed.

    ``Any``, because scrapling is imported by name at call time and there is no
    ``Fetcher`` here for an annotation to name.
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

    A missing body raises, so the ladder records it as a failed rung rather
    than returning a page that was never there.
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

    Plain HTTP, then a browser, in the order they cost. Both announce
    ``USER_AGENT``, so a site that does not want us can refuse us: a browser is
    a change of cost, not of who we are.

    The browser rung passes ``useragent``, not ``extra_headers``: measured
    against a live server, the browser context silently overrides a
    ``User-Agent`` in ``extra_headers`` with its own, and the site saw Chrome.
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
                # and a Chrome TLS fingerprint, dressing up as a browser that
                # came from a search. Measured on the wire on 2026-09-22.
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

    Going from announcing ourselves to disguising ourselves is a change of
    character, not of cost, so it never happens to a caller who did not ask
    (``fetch(url, stealth=True)``). No ``User-Agent`` is sent, deliberately:
    announcing an identity while evading detection would be incoherent.
    """
    _, _, stealthy = _fetchers()

    def stealth(url: str) -> Fetched:
        return _as_fetched(stealthy.fetch(url, network_idle=True), "stealth", url)

    return ("stealth", stealth)
