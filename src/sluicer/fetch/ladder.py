"""Climb only when the page makes us, and only where we are allowed to.

The ladder starts at the cheapest rung and stops as soon as a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can see what a page cost and why.

A rung that raises is a rung that failed: the climb is recorded and the next
rung tried. If a later rung fails after a cheaper one brought a page back, that
page is returned; if every rung failed, ``FetchFailed`` is raised.

The site's robots.txt is asked before any rung runs. A refusal raises
``RobotsRefused`` rather than returning an empty ``Fetched``: "the site said
no" and "the site had nothing" must never look alike.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Sequence
from urllib.parse import urlsplit

from sluicer.api import extract
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import load
from sluicer.fetch.address import (
    AddressRefused,
    _resolve,
    why_not_public,
    why_not_web,
)
from sluicer.fetch.identity import (
    UNAVAILABLE,
    UNREACHABLE,
    RobotsUnreachable,
    robots_refusal,
)
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    Climb,
    EmptyBody,
    Fetched,
    RedirectRefused,
    ResponseTooLarge,
    Rung,
)
from sluicer.fetch.rules import why_climb

__all__ = [
    "AddressRefused",
    "FetchFailed",
    "RedirectRefused",
    "ResponseTooLarge",
    "RobotsRefused",
    "fetch",
    "robots_reader_from",
]


class RobotsRefused(Exception):
    """The site's own robots.txt refuses this URL to us.

    ``reason`` says which rule. A robots.txt that could not be read at all is
    a ``FetchFailed`` instead, since it is worth trying again later.
    """

    def __init__(self, url: str, reason: str = "its robots.txt disallows it") -> None:
        super().__init__(f"{url} is refused: {reason}")
        self.url = url
        self.reason = reason


class FetchFailed(Exception):
    """Every rung of the ladder failed, and nothing came back to return.

    Also raised when the address is not a valid URL, or its robots.txt could
    not be read. The message names what each rung said, and the last rung's
    own exception is the ``__cause__``. One type to catch whatever library a
    rung is built on: a browser's timeout, for one, is not an ``OSError``.
    """

    def __init__(self, url: str, climbs: list[Climb], last: str) -> None:
        said = "; ".join(f"{c.from_rung}: {c.reason}" for c in climbs)
        before = f" (before that, {said})" if said else ""
        super().__init__(f"Could not fetch {url}: {last}{before}")
        self.url = url
        self.climbs = climbs


def robots_reader_from(cheapest_rung: Rung) -> Callable[[str], str | None]:
    """Build a robots reader from the ladder's own cheapest rung.

    The cheapest rung -- the real HTTP rung in production, a fake in a test --
    already knows how to fetch a URL, so reading robots.txt needs no wiring.
    Statuses mean what RFC 9309 says they mean:

    * 2xx -- the body is the rules; an empty body is no rules at all.
    * 4xx -- the site published no rules, so nothing is refused.
    * 5xx, or the rung raised -- unreachable (section 2.3.1.4), a full
      disallow. The reader returns a stand-in full disallow whose first line is
      a comment naming the reason; ``robots_refusal`` reads it, raises
      ``RobotsUnreachable`` and does not cache it.

    The body is the rules as they came, text and never markup, only a BOM
    taken off: read through an HTML parser, ``Disallow: /a<b`` opened a tag
    that swallowed every rule after it. The one exception is a body that is a
    whole HTML document, which is how a browser shows a plain-text file; a
    ladder that starts at a browser would hand protego ``<html><body>User-
    agent: ...``, which it reads as no rules and allows everything, so its
    text is taken out.
    """

    def read(url: str) -> str | None:
        try:
            response = cheapest_rung(url)
        except EmptyBody as empty:
            # The rung refuses an empty body because an empty page is no page;
            # an empty robots.txt is a file with no rules, which allows
            # everything, and is judged by its status like any other.
            response = Fetched(url=url, html="", status=empty.status, rung="")
        # Deliberately blind: every way a rung can fail to reach robots.txt is
        # the same event, "unreachable", and a list of exception types would
        # be a list of the failures someone happened to think of.
        except Exception as failure:  # noqa: BLE001
            return _stay_out(UNREACHABLE, f"{type(failure).__name__}: {failure}")
        if response.status >= 500:
            return _stay_out(UNAVAILABLE, f"status {response.status}")
        if response.status >= 400:
            return None
        return _rules_in(response.html)

    return read


_DOCUMENT = re.compile(r"\s*<(?:!doctype\s+html|html)[\s>]", re.IGNORECASE)


def _rules_in(body: str) -> str:
    """The text of a robots.txt body: itself, or a browser's document's text."""
    text = body.removeprefix("\ufeff")
    if not _DOCUMENT.match(text):
        return text
    # str(...) because lxml ships no types: this asserts at runtime what the
    # signature claims.
    return str(load(text).tree.text_content())


def _stay_out(marker: str, reason: str) -> str:
    return f"# {marker}: {reason}\nUser-agent: *\nDisallow: /\n"


def fetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Fetched:
    """Fetch ``url``, climbing to a costlier rung only when a measurement says so.

    Args:
        url: an http(s) address.
        rungs: ``(name, rung)`` pairs, cheapest first; plain HTTP then a
            browser by default. Injected so tests stay off the network.
        obey_robots: ask the site's robots.txt first (the default), and again
            for the host a redirect ended on.
        stealth: append the stealth rung, which does not announce itself.
            Never automatic.
        robots_reader: how robots.txt is read; built from the cheapest rung
            by default.
        allow_private: when false, refuse addresses off the public internet:
            the one asked for before any request, and every one a redirect or
            the page itself names before it is requested. The MCP server sets
            it.
        resolve: the name lookup ``allow_private`` decides with.
        max_bytes: the most a page may weigh; heavier is ``ResponseTooLarge``,
            and never a reason to climb.

    Returns:
        The ``Fetched`` page, with every climb, the final URL, and how long
        each rung took.

    Raises:
        RobotsRefused: the site's robots.txt disallows the URL.
        AddressRefused: the address, or one a redirect led to, is not http
            or https; or ``allow_private`` is false and it is private.
        ResponseTooLarge: the page is heavier than ``max_bytes``.
        RedirectRefused: an injected rung was given a rule for redirects, and a
            hop broke it.
        FetchFailed: every rung failed, the URL is invalid, or its robots.txt
            could not be read.
        FetchExtraMissing: the ``fetch`` extra is not installed.
    """
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs(allow_private, resolve, max_bytes)
    if stealth:
        from sluicer.fetch.scrapling_rungs import stealth_rung

        rungs = [*rungs, stealth_rung(allow_private, resolve, max_bytes)]
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")
    try:
        urlsplit(url).port  # noqa: B018 -- parsing is the check
    except ValueError as invalid:
        raise FetchFailed(
            url, [], f"{url!r} is not a valid address: {invalid}"
        ) from None

    refused = why_not_web(url)
    if refused is None and not allow_private:
        refused = why_not_public(url, resolve)
    if refused is not None:
        raise AddressRefused(url, refused)

    read = (
        robots_reader if robots_reader is not None else robots_reader_from(rungs[0][1])
    )
    if obey_robots:
        refusal = _robots(url, read)
        if refusal is not None:
            raise RobotsRefused(url, refusal)

    climbs: list[Climb] = []
    best: Fetched | None = None
    last = len(rungs) - 1
    for index, (name, rung) in enumerate(rungs):
        started = time.monotonic()
        try:
            result = rung(url)
            if len(result.html) > max_bytes:
                raise ResponseTooLarge(result.url, max_bytes)
        except Exception as e:
            seconds = time.monotonic() - started
            failure = f"the rung raised {type(e).__name__}: {e}"
            # A refusal or a page too heavy is the page's answer, not the
            # rung's: the next rung would be told the same, at a higher cost.
            final = isinstance(e, (AddressRefused, RedirectRefused, ResponseTooLarge))
            if index < last and not final:
                climbs.append(
                    Climb(name, rungs[index + 1][0], failure, seconds=seconds)
                )
                continue
            if best is None:
                if final:
                    raise
                raise FetchFailed(url, climbs, failure) from e
            best.climbs = [*climbs, Climb(name, best.rung, failure, seconds=seconds)]
            return _checked(best, url, allow_private, resolve, obey_robots, read)

        result.seconds = time.monotonic() - started
        result.climbs = list(climbs)
        # What counts as having delivered is a field about a thing, the rule
        # induction uses: a theme-color in the head of an empty React shell is
        # not the page's data.
        records = extract(result.html, url=result.url).records
        found = any(
            field.source in ABOUT_A_THING
            for record in records
            for field in record.fields.values()
        )
        reason = why_climb(result.status, result.html, found_records=found)
        if reason is None or index == last:
            return _checked(result, url, allow_private, resolve, obey_robots, read)
        best = result
        climbs.append(Climb(name, rungs[index + 1][0], reason, seconds=result.seconds))

    raise AssertionError("the ladder ran out of rungs without returning a page")


def _checked(
    result: Fetched,
    asked: str,
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    obey_robots: bool,
    read: Callable[[str], str | None],
) -> Fetched:
    """``result``, once the address its redirects ended at is allowed too."""
    refused = why_not_web(result.url)
    if refused is None and not allow_private:
        refused = why_not_public(result.url, resolve)
    if refused is not None:
        raise AddressRefused(result.url, refused)
    if obey_robots and _origin(result.url) != _origin(asked):
        refusal = _robots(result.url, read)
        if refusal is not None:
            raise RobotsRefused(result.url, refusal)
    return result


def _robots(url: str, read: Callable[[str], str | None]) -> str | None:
    """Why the site's robots.txt refuses ``url``, or None when it allows it.

    Nothing answering for the robots.txt stops the fetch as RFC 9309 says, and
    is reported as the fetch failing: a host that does not resolve has not
    refused us, and saying it had would send the reader to the wrong fix.
    """
    try:
        return robots_refusal(url, read=read)
    except RobotsUnreachable as unreachable:
        raise FetchFailed(url, [], str(unreachable)) from unreachable


def _origin(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
        return parts.scheme.lower(), (parts.hostname or "").lower()
    except ValueError:
        return "", url
