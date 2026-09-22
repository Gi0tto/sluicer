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

from collections.abc import Callable, Sequence

from sluicer.api import extract
from sluicer.document import load
from sluicer.fetch.identity import robots_allows
from sluicer.fetch.result import Climb, Fetched, Rung
from sluicer.fetch.rules import why_climb


class RobotsRefused(Exception):
    """The site's own robots.txt refuses this URL to us."""

    def __init__(self, url: str) -> None:
        super().__init__(f"{url} is refused by the site's own robots.txt")
        self.url = url


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
    * the rung raised -- the connection never opened, the name did not
      resolve, it timed out. Nothing answered, so nothing told us to stay
      out, and there is nothing to read.

    The status used to be ignored entirely: every one of those cases returned
    "nothing to read", which this module treats as permission, and the cache
    then pinned it. A site answering 503 under load was a site with no rules.

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

    UNAVAILABLE_MEANS_STAY_OUT = "User-agent: *\nDisallow: /"

    def read(url: str) -> str | None:
        try:
            response = cheapest_rung(url)
        # Deliberately blind, and the docstring above says why: every way a
        # rung can fail to reach robots.txt -- refused connection, DNS, a
        # timeout, a rung raising something of its own -- is the same event,
        # "nothing answered", and nothing that never answered can have
        # refused us. Narrowing this to a list of exception types would be a
        # list of the failures we happened to think of, and the first one
        # missing from it would escape as a traceback out of a robots check.
        except Exception:  # noqa: BLE001
            return None
        if response.status >= 500:
            return UNAVAILABLE_MEANS_STAY_OUT
        if response.status >= 400:
            return None
        return load(response.html).tree.text_content()

    return read


def fetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
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
    """
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs()
    if stealth:
        from sluicer.fetch.scrapling_rungs import stealth_rung

        rungs = [*rungs, stealth_rung()]
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")

    if obey_robots:
        read = (
            robots_reader
            if robots_reader is not None
            else _default_robots_reader(rungs[0][1])
        )
        if not robots_allows(url, read=read):
            raise RobotsRefused(url)

    climbs: list[Climb] = []
    last = len(rungs) - 1
    for index, (name, rung) in enumerate(rungs):
        try:
            result = rung(url)
        except Exception as e:
            # A rung that raises is a rung that failed
            if index == last:
                # Last rung's exception propagates to the caller
                raise
            # Record the climb and try the next rung
            reason = f"the rung raised {type(e).__name__}: {e}"
            climbs.append(
                Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason)
            )
            continue

        result.climbs = list(climbs)
        found = bool(extract(result.html, url=url).records)
        reason = why_climb(result.status, result.html, found_records=found)
        if reason is None or index == last:
            return result
        climbs.append(
            Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason)
        )

    # Unreachable, and written out rather than left implicit. The ladder is
    # known non-empty by the guard above, and the last rung either returns a
    # page or re-raises, so the loop cannot run out. Falling off the end used
    # to return None from a function declared to return ``Fetched`` -- the
    # exact shape of "a failure wearing the shape of a success" this module
    # exists to refuse. If a Sequence ever disagrees with its own ``len``,
    # this says so instead of handing the caller a None it cannot use.
    raise AssertionError("the ladder ran out of rungs without returning a page")
