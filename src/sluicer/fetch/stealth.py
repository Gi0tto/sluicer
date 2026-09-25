"""The stealth rung: scrapling's stealthy browser, for a caller who asked.

The one place Sluicer uses scrapling, behind the ``stealth`` extra. It does
not announce itself -- that is what it is for -- so it never runs unless a
caller asks for it by name (``fetch(url, stealth=True)``, ``--stealth``), for
one page at a time: a crawl, a map, a batch and the servers never climb to it,
and no site is remembered as needing it. It borrows no identity either: no
Google referer, which scrapling sends unless told not to, and none of the
caller's headers or cookies, which would say who is asking.

What it sends is checked on the wire, not by the suite: a faked library
accepts whatever keyword it is handed. If you change how the rung is built,
ask a real server what it saw.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Iterable
from typing import Any

from sluicer.extras import import_extra
from sluicer.fetch.address import AddressRefused, _resolve
from sluicer.fetch.browser import BROWSER_TIMEOUT_MS
from sluicer.fetch.browser_guard import MAX_REDIRECTS, Guard
from sluicer.fetch.http_rung import chosen_proxy
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    Fetched,
    ResponseTooLarge,
    Rung,
)
from sluicer.fetch.rungs import FetchExtraMissing


def _stealthy() -> Any:
    """scrapling's ``StealthyFetcher``, or say the ``stealth`` extra is missing.

    ``Any``, because scrapling is imported by name at call time.
    """
    fetchers = import_extra(
        "scrapling.fetchers",
        "stealth",
        doing="The stealth rung",
        error=FetchExtraMissing,
    )
    return fetchers.StealthyFetcher


def stealth_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    proxy: str | None = None,
) -> tuple[str, Rung]:
    """Return the stealth rung, for a caller who has decided they want it.

    Going from announcing ourselves to disguising ourselves is a change of
    character, not of cost, so it never happens to a caller who did not ask.
    No ``User-Agent`` is sent, deliberately: announcing an identity while
    evading detection would be incoherent. Nor is a borrowed one claimed:
    scrapling's ``google_search`` sent ``Referer: https://www.google.com/``
    from this rung, measured, and it is off. Not saying who we are is not
    saying we came from a search. One try and the browser rung's timeout
    bound it the same way.

    Raises ``FetchExtraMissing`` at once when scrapling is not installed: a
    caller who asked for this rung by name is told now, not by a climb that
    fails later. scrapling itself is imported when the rung first loads a
    page, which most fetches never reach.
    """
    try:
        present = importlib.util.find_spec("scrapling") is not None
    except (ImportError, ValueError):
        present = False
    if not present:
        # Raises the sentence with the install line, or imports what a
        # finder could not see.
        _stealthy()

    def load(url: str, **options: Any) -> Any:
        return _stealthy().fetch(url, **options)

    return (
        "stealth",
        _browser(
            load,
            {
                "network_idle": True,
                "google_search": False,
                "timeout": BROWSER_TIMEOUT_MS,
                "retries": 1,
                **_through(proxy),
            },
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


def _as_fetched(response: Any, requested_url: str) -> Fetched:
    """Wrap a scrapling Response, treating a response with no HTML as a failure.

    A missing body raises, so the ladder records it as a failed rung rather
    than returning a page that was never there.
    """
    if not response.html_content:
        raise ValueError(f"the stealth rung returned no HTML for {requested_url!r}")
    declared = getattr(response, "headers", None) or {}
    return Fetched(
        url=getattr(response, "url", None) or requested_url,
        html=response.html_content,
        status=response.status,
        rung="stealth",
        headers={str(k).lower(): str(v) for k, v in dict(declared).items()},
    )


def _browser(
    load: Callable[..., Any],
    options: dict[str, Any],
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
) -> Rung:
    """A rung that loads a page in scrapling's browser, guarded when it has to be."""

    def rung(url: str) -> Fetched:
        if allow_private:
            return _bounded(_as_fetched(load(url, **options), url), max_bytes)
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
                    "the stealth rung could not guard the page's requests, so it "
                    "made none it could vouch for; is scrapling older than 0.4.6?"
                )
            if guard.redirect is not None:
                # The document was sent elsewhere: ask for it as a new fetch.
                target, guard.redirect = guard.redirect, None
                refused = guard.why_refused(target)
                if refused is not None:
                    raise AddressRefused(target, refused)
                current = target
                continue
            return _bounded(_as_fetched(response, current), max_bytes)
        raise RuntimeError(f"{url} redirected more than {MAX_REDIRECTS} times")

    return rung


def _bounded(fetched: Fetched, max_bytes: int) -> Fetched:
    """``fetched``, once its HTML is within the bound the HTTP rung keeps."""
    if len(fetched.html) > max_bytes or len(fetched.html.encode()) > max_bytes:
        raise ResponseTooLarge(fetched.url, max_bytes)
    return fetched
