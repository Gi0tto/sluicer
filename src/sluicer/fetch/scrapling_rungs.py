"""The real rungs: plain HTTP on curl_cffi, and the browsers over scrapling.

Both libraries are optional -- the base install reads HTML you already have --
so they are imported when a rung is built, never when this module is.

What each rung sends is checked on the wire, not by the suite: a faked library
accepts whatever keyword it is handed. If you change how a rung is built, ask a
real server what it saw.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.address import AddressRefused, _resolve
from sluicer.fetch.browser_guard import MAX_REDIRECTS, Guard
from sluicer.fetch.http_rung import HTTP_TIMEOUT_SECONDS, chosen_proxy, http_rung
from sluicer.fetch.identity import USER_AGENT
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    Fetched,
    RedirectRefused,
    Redirects,
    ResponseTooLarge,
    Rung,
)

__all__ = [
    "BROWSER_TIMEOUT_MS",
    "HTTP_TIMEOUT_SECONDS",
    "FetchExtraMissing",
    "default_rungs",
    "stealth_rung",
]

BROWSER_TIMEOUT_MS = 30_000
"""How long the browser rung waits for one page, in scrapling's milliseconds.

It bounds each thing the browser waits on -- the page's load, then the network
going quiet -- not the rung as a whole. One try per rung keeps a slow site to
that and to ``HTTP_TIMEOUT_SECONDS`` for plain HTTP, the body included.
scrapling's defaults, three tries of thirty seconds a rung, came to three
minutes, longer than an agent's tool call waits.
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
    declared = getattr(response, "headers", None) or {}
    return Fetched(
        url=getattr(response, "url", None) or requested_url,
        html=response.html_content,
        status=response.status,
        rung=rung,
        headers={str(k).lower(): str(v) for k, v in dict(declared).items()},
    )


def default_rungs(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    proxy: str | None = None,
) -> list[tuple[str, Rung]]:
    """Return the rungs a caller gets without asking for anything more.

    Plain HTTP, then a browser, in the order they cost. Both announce
    ``USER_AGENT``, so a site that does not want us can refuse us: a browser is
    a change of cost, not of who we are.

    With ``allow_private`` false, both keep off addresses that are not on the
    public web, redirects included: see ``http_rung`` and ``browser_guard``.

    ``redirects`` is a caller's rule for a redirect, asked before the hop is
    requested. The HTTP rung asks it of every hop; the browser rung only when
    it is guarded, since an unguarded browser follows a redirect itself.

    The browser rung passes ``useragent``, not ``extra_headers``: measured
    against a live server, the browser context silently overrides a
    ``User-Agent`` in ``extra_headers`` with its own, and the site saw Chrome.

    ``proxy`` is ``http_rung``'s, for both rungs: ``SLUICER_PROXY`` when None.
    Without one the browser is launched with ``--no-proxy-server``, so it
    uses no proxy the system or the environment names either.
    """
    _, dynamic, _ = _fetchers()
    http = http_rung(
        allow_private,
        resolve,
        max_bytes,
        error=FetchExtraMissing,
        redirects=redirects,
        proxy=proxy,
    )
    browser = _browser(
        "browser",
        dynamic.fetch,
        {
            "network_idle": True,
            "useragent": USER_AGENT,
            "timeout": BROWSER_TIMEOUT_MS,
            "retries": 1,
            # scrapling's default adds a Google referer, dressing us up as a
            # visitor who came from a search. Measured on the wire, 2026-09-22.
            "google_search": False,
            **_through(proxy),
        },
        allow_private,
        resolve,
        max_bytes,
        redirects,
    )
    return [("http", http), ("browser", browser)]


def stealth_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    proxy: str | None = None,
) -> tuple[str, Rung]:
    """Return the third rung, for a caller who has decided they want it.

    Going from announcing ourselves to disguising ourselves is a change of
    character, not of cost, so it never happens to a caller who did not ask
    (``fetch(url, stealth=True)``). No ``User-Agent`` is sent, deliberately:
    announcing an identity while evading detection would be incoherent.
    """
    _, _, stealthy = _fetchers()
    return (
        "stealth",
        _browser(
            "stealth",
            stealthy.fetch,
            {"network_idle": True, **_through(proxy)},
            allow_private,
            resolve,
            max_bytes,
        ),
    )


def _through(proxy: str | None) -> dict[str, Any]:
    """A browser's options for ``proxy``: that one, or none at all."""
    chosen = chosen_proxy(proxy)
    if chosen is not None:
        return {"proxy": chosen}
    return {"extra_flags": ["--no-proxy-server"]}


def _browser(
    name: str,
    load: Callable[..., Any],
    options: dict[str, Any],
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
    redirects: Redirects | None = None,
) -> Rung:
    """A rung that loads a page in a browser, guarded when it has to be."""

    def rung(url: str) -> Fetched:
        if allow_private:
            return _bounded(_as_fetched(load(url, **options), name, url), max_bytes)
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            guard = Guard(resolve)
            try:
                response = load(current, **options, page_setup=guard.setup)
            except Exception:
                if guard.redirect is None:
                    raise
                response = None
            if not guard.installed:
                raise RuntimeError(
                    f"the {name} rung could not guard the page's requests, so it "
                    "made none it could vouch for; is scrapling older than 0.4.6?"
                )
            if guard.redirect is not None:
                # The document was sent elsewhere: ask for it as a new fetch.
                target, guard.redirect = guard.redirect, None
                ruled = redirects(current, target) if redirects else None
                if ruled is not None:
                    raise RedirectRefused(current, target, ruled)
                refused = guard.why_refused(target)
                if refused is not None:
                    raise AddressRefused(target, refused)
                current = target
                continue
            return _bounded(_as_fetched(response, name, current), max_bytes)
        raise RuntimeError(f"{url} redirected more than {MAX_REDIRECTS} times")

    return rung


def _bounded(fetched: Fetched, max_bytes: int) -> Fetched:
    """``fetched``, once its HTML is within the bound the HTTP rung keeps."""
    if len(fetched.html) > max_bytes or len(fetched.html.encode()) > max_bytes:
        raise ResponseTooLarge(fetched.url, max_bytes)
    return fetched
