"""Climb only when the page makes us, and only where we are allowed to.

The ladder starts at the cheapest rung and stops as soon as a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can see what a page cost and why.

A rung that raises is a rung that failed: the climb is recorded and the next
rung tried. If a later rung fails after a cheaper one brought a page back, that
page is returned; if every rung failed, ``FetchFailed`` is raised.

What a site needed is remembered for the process (``RungMemory``): once a
page of a site came back only from a costlier rung, because the cheaper one's
page was a refusal, a challenge or a shell, the site's next pages start at
that rung, and say so in their first climb. A rung that failed teaches
nothing; a remembered rung that fails is forgotten, and the ladder starts
again from the bottom. The stealth rung is never remembered.

The site's robots.txt is asked before any rung runs. A refusal raises
``RobotsRefused`` rather than returning an empty ``Fetched``: "the site said
no" and "the site had nothing" must never look alike. For the same reason a
challenge page is never returned as the page: when it is what the ladder is
left with, ``SiteRefused`` is raised.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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
from sluicer.fetch.gate import GATE, after, site_key
from sluicer.fetch.identity import (
    ROBOTS_CACHE_HOSTS,
    ROBOTS_TTL_SECONDS,
    UNAVAILABLE,
    UNREACHABLE,
    RobotsUnreachable,
    outgoing,
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
from sluicer.fetch.rules import challenge_marker, why_climb

__all__ = [
    "AddressRefused",
    "FetchFailed",
    "PaymentRequired",
    "RedirectRefused",
    "ResponseTooLarge",
    "RobotsRefused",
    "RungMemory",
    "SiteRefused",
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


class SiteRefused(FetchFailed):
    """The site answered with a challenge page, and no rung got past it.

    A waiting room -- "Just a moment...", served in the content's place, often
    with 200 -- is the site declining to be read, so it is raised, never
    returned as the page. ``reason`` is the rule that saw it, naming its
    marker. A ``FetchFailed``, so a caller that catches that catches this; but
    not one worth retrying at once, since the same ladder is shown the same
    page, and not one to work around.
    """

    def __init__(self, url: str, climbs: list[Climb], reason: str) -> None:
        super().__init__(url, climbs, f"the site refused it: {reason}")
        self.reason = reason


class PaymentRequired(FetchFailed):
    """The site answered 402 Payment Required: it asks to be paid to be read.

    Sluicer never pays, and never asks the same question of another rung,
    which would be asking again in the hope of not being charged. Raised, not
    returned: a 402's body is the site's terms, not the page. A
    ``FetchFailed``, so a caller that catches that catches this, but not one
    worth retrying.
    """

    def __init__(self, url: str, climbs: list[Climb]) -> None:
        super().__init__(
            url,
            climbs,
            "the site answered 402 Payment Required; Sluicer does not pay",
        )


@dataclass(frozen=True)
class Needed:
    """The rung a site needed, why, and when that was learnt."""

    rung: str
    reason: str
    learnt: float


class RungMemory:
    """The rung each site needed, for as long as the process runs.

    Keyed by site as the gate paces it (``sluicer.fetch.gate.site_key``: the
    host with or without ``www.``). ``limit`` sites are kept, the least
    recently learnt forgotten first, each for ``ttl`` seconds: a site that
    renders its pages on the server again is asked of plain HTTP again the
    next day. ``clock`` is injected by tests.
    """

    NEVER = frozenset({"stealth"})
    """Rungs never remembered: a disguise is asked for page by page."""

    def __init__(
        self,
        limit: int = ROBOTS_CACHE_HOSTS,
        ttl: float = ROBOTS_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.ttl = ttl
        self.clock = clock
        self._sites: OrderedDict[str, Needed] = OrderedDict()
        self._lock = threading.Lock()

    def recall(self, url: str) -> Needed | None:
        """What ``url``'s site needed, while it is remembered."""
        key = site_key(url)
        with self._lock:
            found = self._sites.get(key)
            if found is not None and self.clock() - found.learnt > self.ttl:
                del self._sites[key]
                return None
            return found

    def learn(self, url: str, rung: str, reason: str) -> None:
        """Remember that ``url``'s site needed ``rung``, for ``reason``."""
        if rung in self.NEVER:
            return
        key = site_key(url)
        with self._lock:
            self._sites[key] = Needed(rung, reason, self.clock())
            self._sites.move_to_end(key)
            while len(self._sites) > self.limit:
                self._sites.popitem(last=False)

    def forget(self, url: str) -> None:
        with self._lock:
            self._sites.pop(site_key(url), None)

    def of(self, url: str) -> str:
        """What ``recall`` remembers ``url`` by, as a climb names it: its site."""
        return site_key(url)

    def clear(self) -> None:
        with self._lock:
            self._sites.clear()


STICKY = RungMemory()
"""The process's memory: what every fetch of the real web learns and uses."""


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


_PAYMENT_REQUIRED = 402


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
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    memory: RungMemory | None = None,
) -> Fetched:
    """Fetch ``url``, climbing to a costlier rung only when a measurement says so.

    Args:
        url: an http(s) address.
        rungs: ``(name, rung)`` pairs, cheapest first; plain HTTP then a
            browser by default, the browser when the ``browser`` extra is
            installed (without it, a climb to it fails and is recorded, and
            the HTTP page comes back). Injected so tests stay off the network. The
            default rungs are the real web, so a fetch with them holds the
            site in ``sluicer.fetch.gate`` for its whole length -- robots.txt,
            the page, any climb -- a second after anyone's last request to it.
            Injected rungs are the caller's to pace, as a crawl paces its own.
        obey_robots: ask the site's robots.txt first (the default), and again
            for the origin -- scheme, host and port -- a redirect ended on.
        stealth: append the stealth rung, which does not announce itself.
            Never automatic; it needs the ``stealth`` extra.
        robots_reader: how robots.txt is read; built from the cheapest rung
            by default.
        allow_private: when false, refuse addresses off the public internet:
            the one asked for before any request, and every one a redirect or
            the page itself names before it is requested. The MCP server sets
            it.
        resolve: the name lookup ``allow_private`` decides with.
        max_bytes: the most a page may weigh; heavier is ``ResponseTooLarge``,
            and never a reason to climb.
        proxy: the proxy the default rungs and the stealth rung go through;
            ``SLUICER_PROXY`` when None, and none when that is unset. The
            environment's ``HTTPS_PROXY`` is never used. Through a proxy the
            private-network check still judges every address here, but the
            connection is the proxy's: see SECURITY.md.
        headers: sent with every request for the origin asked -- scheme,
            host and port -- and left off any hop a redirect takes elsewhere:
            an ``Authorization``, a header an API wants. Never ``User-Agent``:
            Sluicer always says who it is, so a site can refuse it. Nor with
            a robots.txt, which is read as anyone reads it: its answer is the
            site's, kept for every caller.
        cookies: sent as one ``Cookie`` header the same way, and set in the
            browser's context for the host asked, where a browser's own
            cookie rules apply (a cookie belongs to a host, not a port).
        memory: what each site needed before, and learns what this page
            needs: a site whose page came back only from the browser starts
            its next page there. The process's (``STICKY``) with the default
            rungs; none with injected ones unless handed one.

    Returns:
        The ``Fetched`` page, with every climb, the final URL, and how long
        each rung took.

    Raises:
        RobotsRefused: the site's robots.txt disallows the URL.
        SiteRefused: the page the ladder was left with is a challenge page.
        PaymentRequired: a rung was answered 402; no other rung is asked.
        AddressRefused: the address, or one a redirect led to, is not http
            or https; or ``allow_private`` is false and it is private.
        ResponseTooLarge: the page is heavier than ``max_bytes``.
        RedirectRefused: an injected rung was given a rule for redirects, and a
            hop broke it.
        ValueError: ``headers`` hold a ``User-Agent``, or a header the
            transport writes, or a header or cookie that would break the
            request; or they were given with injected ``rungs``, which send
            what their caller built them to, or with ``stealth``, which sends
            nothing that says who is asking.
        FetchFailed: every rung failed, the URL is invalid, or its robots.txt
            could not be read.
        FetchExtraMissing: ``stealth`` was asked for and the ``stealth`` extra
            is not installed.
    """
    gated = rungs is None
    sending = bool(headers or cookies)
    outgoing(headers, cookies)
    if sending and not gated:
        raise ValueError(
            "headers and cookies are sent by the default rungs; injected rungs "
            "send what their caller built them to send"
        )
    if sending and stealth:
        raise ValueError(
            "the stealth rung sends no headers or cookies of yours: it does not "
            "say who is asking, and a login would"
        )
    plain: Rung | None = None
    if rungs is None:
        from sluicer.fetch.rungs import default_rungs

        rungs = default_rungs(
            allow_private,
            resolve,
            max_bytes,
            proxy=proxy,
            headers=headers,
            cookies=cookies,
            send_to=[url],
        )
        if sending:
            # robots.txt is read as anyone reads it, whatever login the page
            # is asked with: the answer is the site's, kept for a day for
            # every caller, and a redirect's other origin is sent nothing.
            plain = default_rungs(allow_private, resolve, max_bytes, proxy=proxy)[0][1]
    if stealth:
        from sluicer.fetch.stealth import stealth_rung

        rungs = [*rungs, stealth_rung(allow_private, resolve, max_bytes, proxy)]
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
        robots_reader
        if robots_reader is not None
        else robots_reader_from(plain if plain is not None else rungs[0][1])
    )
    if memory is None and gated:
        memory = STICKY
    if not gated:
        return _climb(
            url, rungs, obey_robots, read, allow_private, resolve, max_bytes, memory
        )
    with GATE.turn(url) as ready:
        return _climb(
            url,
            [(name, after(ready, rung)) for name, rung in rungs],
            obey_robots,
            after(ready, read),
            allow_private,
            resolve,
            max_bytes,
            memory,
        )


def _climb(
    url: str,
    rungs: Sequence[tuple[str, Rung]],
    obey_robots: bool,
    read: Callable[[str], str | None],
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
    memory: RungMemory | None = None,
) -> Fetched:
    """``fetch``'s requests: robots.txt, then the rungs, cheapest first, or
    from the one ``memory`` says the site needed."""
    if obey_robots:
        refusal = _robots(url, read)
        if refusal is not None:
            raise RobotsRefused(url, refusal)

    climbs: list[Climb] = []
    start = 0
    names = [name for name, _ in rungs]
    known = memory.recall(url) if memory is not None else None
    if memory is not None and known is not None and known.rung in names[1:]:
        start = names.index(known.rung)
        climbs.append(
            Climb(
                names[0],
                known.rung,
                f"an earlier page of {memory.of(url)} needed it: {known.reason}",
            )
        )
    best: Fetched | None = None
    # Why ``best`` is a challenge, when it is one: never a page to fall back to.
    best_refused: str | None = None
    # Why the cheapest rung's page was not enough, for ``memory`` to learn.
    needed: str | None = None
    last = len(rungs) - 1
    index = start
    while index <= last:
        name, rung = rungs[index]
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
            if index == start > 0 and not final and memory is not None:
                # What the site needed failed this time: forgotten, and the
                # ladder starts again from its cheapest rung.
                memory.forget(url)
                climbs.append(
                    Climb(
                        name,
                        names[0],
                        f"{failure}; starting again from {names[0]}",
                        seconds=seconds,
                    )
                )
                start = index = 0
                continue
            if index < last and not final:
                climbs.append(
                    Climb(name, rungs[index + 1][0], failure, seconds=seconds)
                )
                index += 1
                continue
            if best is None:
                if final:
                    raise
                raise FetchFailed(url, climbs, failure) from e
            best.climbs = [*climbs, Climb(name, best.rung, failure, seconds=seconds)]
            if best_refused is not None:
                raise SiteRefused(url, best.climbs, best_refused) from e
            return _checked(best, url, allow_private, resolve, obey_robots, read)

        result.seconds = time.monotonic() - started
        result.climbs = list(climbs)
        if result.status == _PAYMENT_REQUIRED:
            raise PaymentRequired(url, result.climbs)
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
        if reason is None:
            checked = _checked(result, url, allow_private, resolve, obey_robots, read)
            if memory is not None and index > 0:
                if needed is not None:
                    memory.learn(url, name, needed)
                elif index == start and known is not None:
                    memory.learn(url, name, known.reason)
            return checked
        challenge = challenge_marker(result.html, found_records=found) is not None
        if index == last:
            checked = _checked(result, url, allow_private, resolve, obey_robots, read)
            if challenge:
                raise SiteRefused(url, climbs, reason)
            return checked
        if index == 0:
            needed = reason
        best, best_refused = result, reason if challenge else None
        climbs.append(Climb(name, rungs[index + 1][0], reason, seconds=result.seconds))
        index += 1

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


def _origin(url: str) -> tuple[str, str, int | None]:
    """A URL's scheme, host and port: whose robots.txt governs it."""
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        port = parts.port or (443 if scheme == "https" else 80)
        return scheme, (parts.hostname or "").lower(), port
    except ValueError:
        return "", url, None
