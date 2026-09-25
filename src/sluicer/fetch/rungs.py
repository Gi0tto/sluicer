"""The rungs a caller gets without asking for anything more.

Plain HTTP, on the standard library, in every install; then a browser, when
the ``browser`` extra is installed and the environment has not turned it off.
The browser's library is imported when it first loads a page, never when the
ladder is built, so a ladder without it still climbs: the climb fails, is
recorded with the line that installs it, and the HTTP rung's page comes back.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from sluicer.extras import MissingExtra
from sluicer.fetch.address import _resolve
from sluicer.fetch.http_rung import HTTP_TIMEOUT_SECONDS, http_rung
from sluicer.fetch.identity import outgoing
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Redirects, Rung

__all__ = [
    "HTTP_TIMEOUT_SECONDS",
    "FetchExtraMissing",
    "default_rungs",
]


class FetchExtraMissing(MissingExtra):
    """An optional fetching extra -- ``browser`` or ``stealth`` -- is not
    installed.

    Its message names the install line, and ``extra`` which of the two. What
    counts as missing, as opposed to broken, is ``sluicer.extras``'s rule.
    """


def default_rungs(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> list[tuple[str, Rung]]:
    """Return the ladder a caller gets without asking for anything more.

    Plain HTTP, then a browser, in the order they cost; the browser only while
    ``SLUICER_BROWSER`` is not ``none``. Both announce ``USER_AGENT``, so a
    site that does not want us can refuse us: a browser is a change of cost,
    not of who we are.

    With ``allow_private`` false, both keep off addresses that are not on the
    public web, redirects included: see ``http_rung`` and ``browser_guard``.

    ``redirects`` is a caller's rule for a redirect, asked before the hop is
    requested. The HTTP rung asks it of every hop; the browser rung only when
    it is guarded, since an unguarded browser follows a redirect itself.

    ``proxy`` is ``http_rung``'s, for both rungs: ``SLUICER_PROXY`` when None.
    ``headers`` and ``cookies`` are the caller's, sent to the origin asked
    for and nowhere else; a ``User-Agent`` among them is a ``ValueError``.
    """
    from sluicer.fetch.browser import browser_rung, browser_wanted

    send = outgoing(headers, cookies)
    rungs: list[tuple[str, Rung]] = [
        (
            "http",
            http_rung(
                allow_private,
                resolve,
                max_bytes,
                redirects,
                proxy=proxy,
                send=send,
            ),
        )
    ]
    if browser_wanted():
        rungs.append(
            (
                "browser",
                browser_rung(
                    allow_private,
                    resolve,
                    max_bytes,
                    redirects,
                    proxy,
                    {k: v for k, v in send.items() if k.lower() != "cookie"},
                    _crumbs(send),
                ),
            )
        )
    return rungs


def _crumbs(send: Mapping[str, str]) -> dict[str, str]:
    """The cookies in a ``Cookie`` header, as a browser's context is given
    them: a browser writes that header itself, from its own jar."""
    found: dict[str, str] = {}
    for name, value in send.items():
        if name.lower() != "cookie":
            continue
        for crumb in value.split(";"):
            key, _, said = crumb.strip().partition("=")
            if key:
                found[key] = said
    return found
