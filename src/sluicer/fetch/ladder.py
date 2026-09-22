"""Climb only when the page makes us, and only where we are allowed to.

The ladder starts at the cheapest rung and stops the moment a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can always see what a page cost and why.

A rung that raises is treated as a rung that failed: if not the last rung,
the climb is recorded and the next rung is tried. The last rung's exception
is the caller's to handle.

Before any rung is tried, the site's own robots.txt is asked. A refusal
raises ``RobotsRefused`` rather than returning some empty ``Fetched``: "the
site said no" and "the site had nothing" are different events, and giving
them the same shape is the failure this project spends its history removing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from urllib.parse import urlsplit

from sluicer.api import extract
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import load
from sluicer.fetch.address import AddressRefused, _resolve, why_not_public
from sluicer.fetch.identity import UNREACHABLE, robots_refusal
from sluicer.fetch.result import Climb, Fetched, Rung
from sluicer.fetch.rules import why_climb

__all__ = ["AddressRefused", "FetchFailed", "RobotsRefused", "fetch"]


class RobotsRefused(Exception):
    """The site's own robots.txt refuses this URL to us, or could not be read."""

    def __init__(self, url: str, reason: str = "its robots.txt disallows it") -> None:
        super().__init__(f"{url} is refused: {reason}")
        self.url = url
        self.reason = reason


class FetchFailed(Exception):
    """Every rung of the ladder failed, and nothing came back to return.

    The message names what each rung said, and the last rung's own exception
    is the ``__cause__``. One type for the caller to catch, whatever library
    a rung is built on: a browser's timeout is not an ``OSError``, and a
    command line that only caught those printed a traceback for a slow site.
    """

    def __init__(self, url: str, climbs: list[Climb], last: str) -> None:
        said = "; ".join(f"{c.from_rung}: {c.reason}" for c in climbs)
        before = f" (before that, {said})" if said else ""
        super().__init__(f"Could not fetch {url}: {last}{before}")
        self.url = url
        self.climbs = climbs


def _default_robots_reader(cheapest_rung: Rung) -> Callable[[str], str | None]:
    """Build a robots reader from the ladder's own cheapest rung.

    A caller who wires nothing up still needs a way to read a robots.txt
    file, and the cheapest rung of whatever ladder is already in play --
    the real "http" rung in production, a fake in a test -- already knows
    how to fetch a URL. Reusing it means production needs no extra wiring
    and a test supplying its own rungs needs no extra network stack either.

    What the status means is RFC 9309's answer, not ours, because a site
    owner's expectations are set by the RFC:

    * 2xx -- the body is the rules, and they are read.
    * 4xx -- the site published no rules, so nothing is refused. A 404 is the
      ordinary case, and the RFC treats the whole family the same way.
    * 5xx -- the rules exist but are unavailable, and the RFC says to treat
      that as a full disallow. Returning the text of one -- ``User-agent: *``
      then ``Disallow: /`` -- encodes "unavailable means stay out" in the one
      type this reader already returns, rather than inventing a third return
      value that every caller would then have to learn.
    * the rung raised -- the connection never opened, it timed out. RFC 9309
      section 2.3.1.4 calls that unreachable and says to treat it as a full
      disallow, the same as a 5xx.

    Both refusals carry the reason in a comment line, which robots parsers
    skip and ``robots_refusal`` reads, so the caller is told the file could
    not be read rather than that the site said no.

        A rung returns ``Fetched.html``, not plain text, and a rung that fetches
    a plain-text robots.txt does not mean the body arrives as plain text:
    measured against ``httpbin.org/robots.txt``, scrapling wraps it as
    ``<html><body>User-agent: *\\nDisallow: /deny\\n</body></html>``. Handed
    that directly, protego reads its first line as
    ``<html><body>User-agent: *``, recognises no directive in it, and parses
    no rules at all -- silently allowing everything a site meant to refuse.
    Running the body through ``sluicer.document.load(...).tree.text_content()``
    strips the wrapping back to the bare directives; a robots.txt that was
    already plain text passes through unchanged, since there is no markup in
    it to strip.
    """

    def read(url: str) -> str | None:
        try:
            response = cheapest_rung(url)
        # Deliberately blind: every way a rung can fail to reach robots.txt --
        # refused connection, DNS, a timeout, a rung raising something of its
        # own -- is the same event, "unreachable", and a list of exception
        # types would be a list of the failures we happened to think of.
        except Exception as failure:  # noqa: BLE001
            return _stay_out(f"{type(failure).__name__}: {failure}")
        if response.status >= 500:
            return _stay_out(f"status {response.status}")
        if response.status >= 400:
            return None
        # str(...) because lxml ships no types: this asserts at runtime what
        # the signature claims.
        return str(load(response.html).tree.text_content())

    return read


def _stay_out(reason: str) -> str:
    return f"# {UNREACHABLE}: {reason}\nUser-agent: *\nDisallow: /\n"


def fetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
) -> Fetched:
    """Fetch ``url``, climbing only when a measurement says the rung failed.

    When ``obey_robots`` is true (the default), the site's own robots.txt is
    consulted before the first rung is tried; a refusal raises
    ``RobotsRefused`` and no rung ever runs. ``robots_reader`` is injected
    exactly as ``rungs`` is, and defaults to a reader built from the cheapest
    rung so production needs no wiring.

    When ``stealth`` is true, ``stealth_rung()`` is appended to the ladder:
    climbing to it is something a caller asks for, not something that
    happens on its own.

    A page that redirected to another host is checked against that host's
    robots.txt before it is returned. With ``allow_private`` false, an
    address off the public internet raises ``AddressRefused`` before any
    request, and so does a page whose redirects ended at one; ``resolve`` is
    the name lookup that decides, injected so tests stay off the network.

    When a rung fails after a cheaper one brought a page back, that page is
    returned and the failure is recorded as a climb back down to it. When
    every rung failed, ``FetchFailed`` says what each one said.
    """
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs()
    if stealth:
        from sluicer.fetch.scrapling_rungs import stealth_rung

        rungs = [*rungs, stealth_rung()]
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")

    if not allow_private:
        refused = why_not_public(url, resolve)
        if refused is not None:
            raise AddressRefused(url, refused)

    read = (
        robots_reader
        if robots_reader is not None
        else _default_robots_reader(rungs[0][1])
    )
    if obey_robots:
        refusal = robots_refusal(url, read=read)
        if refusal is not None:
            raise RobotsRefused(url, refusal)

    climbs: list[Climb] = []
    best: Fetched | None = None
    last = len(rungs) - 1
    for index, (name, rung) in enumerate(rungs):
        try:
            result = rung(url)
        except Exception as e:
            failure = f"the rung raised {type(e).__name__}: {e}"
            if index < last:
                climbs.append(
                    Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=failure)
                )
                continue
            if best is None:
                raise FetchFailed(url, climbs, failure) from e
            best.climbs = [
                *climbs,
                Climb(from_rung=name, to_rung=best.rung, reason=failure),
            ]
            return _checked(best, url, allow_private, resolve, obey_robots, read)

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
        climbs.append(Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason))

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
    if not allow_private:
        refused = why_not_public(result.url, resolve)
        if refused is not None:
            raise AddressRefused(result.url, refused)
    if obey_robots and _origin(result.url) != _origin(asked):
        refusal = robots_refusal(result.url, read=read)
        if refusal is not None:
            raise RobotsRefused(result.url, refusal)
    return result


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme, (parts.hostname or "").lower()
