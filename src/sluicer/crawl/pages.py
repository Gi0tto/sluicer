"""Many pages, politely: a crawl that follows links, and a batch that does not.

Both take each address through the ladder, so robots.txt, the address guard and
the byte bound apply to every page as they do to one, and both are paced by
``sluicer.crawl.schedule``. What each page became -- its extraction, or the
reason it has none -- is a ``Page``, and a page that failed is an answer like
any other: it is in the output, with its code.

A crawl is breadth first. Every address is numbered as it is admitted, the
pages come back in that order, and what a page admits is decided when its turn
comes, never when its fetch happens to finish, so the same site crawled twice
gives the same pages in the same order. The output is the state: each page is
one line of JSON, written as its turn comes, and a crawl handed the file again
replays those lines to rebuild what it had seen and continues where they end.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import IO, Any, TypeVar
from urllib.parse import urlsplit

from sluicer.api import Extraction, _extract as extract
from sluicer.crawl.schedule import (
    CONCURRENCY,
    DEFAULT_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
    RETRIES,
    Politeness,
    Queue,
    Schedule,
    Task,
)
from sluicer.crawl.urls import (
    canonical_of,
    links_on,
    names_a_file,
    normalise,
    not_a_start,
    site_of,
)
from sluicer.crawl.web import Parts, Web, default_web
from sluicer.declared.tdmrep import WELL_KNOWN, TdmRule, read_tdmrep, reservation
from sluicer.document import load
from sluicer.fetch import (
    AddressRefused,
    Climb,
    FetchFailed,
    PaymentRequired,
    RedirectRefused,
    ResponseTooLarge,
    RobotsRefused,
    SiteRefused,
    fetch,
)
from sluicer.fetch.address import _resolve, shown, why_not_public
from sluicer.fetch.identity import RobotsUnreachable, outgoing, robots_refusal
from sluicer.fetch.result import MAX_RESPONSE_BYTES

MAX_PAGES = 100
"""How many addresses a crawl takes unless told otherwise."""

MAX_DEPTH = 3
"""How many links from the start a crawl goes unless told otherwise."""

_TOO_DEEP_KEPT = 10_000
"""How many links past ``max_depth`` a crawl keeps, to count them: each page
at the last depth may give 5,000, so a crawl of many pages would otherwise
hold every link of its last layer. Past this many, its notice says "at
least"."""


class StateMismatch(ValueError):
    """A state file was not written by this crawl: another start, other options,
    or not a crawl's output at all. ``path`` is the file."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path} cannot be resumed here: {reason}")
        self.path = path


@dataclass(frozen=True)
class PageError:
    """Why a page has no extraction.

    ``code`` is one of the MCP server's -- ``refused_by_robots``,
    ``refused_by_site``, ``payment_required``, ``refused_address``,
    ``fetch_failed`` (``retryable``), ``too_large``, ``bad_input`` -- or one
    of a crawl's own: ``redirected_off_site``, with the
    ``target`` it pointed to, ``crawl_delay_too_long``, and ``rate_limited``
    (``retryable``), a site's Retry-After asking for longer than a crawl waits.
    """

    code: str
    message: str
    retryable: bool = False
    target: str | None = None


@dataclass(frozen=True)
class Retry:
    """One time a page was asked again: ``reason`` is what the request before
    it came to -- ``it answered 503``, or why it failed -- and ``after`` the
    seconds from that request's end to this one's start."""

    reason: str
    after: float


@dataclass(frozen=True)
class Page:
    """One address a crawl or a batch took, and what became of it.

    ``url`` is the address taken, normalised; ``landed`` where its redirects
    ended. ``found_on`` is the page whose link led here, None for the start or
    a listed address. ``canonical`` is the page's own ``<link
    rel=canonical>``, and ``links`` every address it lets a crawl follow, in
    document order. A page the site answered with 4xx or 5xx is an
    ``error``, ``fetch_failed``, whose message names the status -- retryable
    for a 429 or a 5xx -- and keeps ``landed``, ``rung``, ``status``,
    ``seconds`` and ``climbs``, as its line keeps ``landed`` and ``fetch``;
    its error page's declarations, links and canonical are not the page's.
    ``extraction`` is ``sluicer.extract``'s reading, as for one fetch; it is
    None exactly when ``error`` is not, and so are the fetch fields but for
    such a page. ``retries`` is every time
    the page was asked again after a request that may succeed later, oldest
    first; what the page is, is what its last request came to.
    """

    url: str
    depth: int = 0
    found_on: str | None = None
    landed: str | None = None
    rung: str | None = None
    status: int | None = None
    seconds: float = 0.0
    climbs: tuple[Climb, ...] = ()
    extraction: Extraction | None = None
    canonical: str | None = None
    links: tuple[str, ...] = ()
    error: PageError | None = None
    retries: tuple[Retry, ...] = ()

    @property
    def ok(self) -> bool:
        """True when the page was fetched and read, whatever it declared."""
        return self.error is None

    @property
    def found(self) -> bool:
        """True when the page gave something: a record or a summary answer."""
        return self.extraction is not None and bool(
            self.extraction.records or self.extraction.summary
        )

    def to_json(self) -> dict[str, Any]:
        """The page as one line of a crawl's output."""
        line: dict[str, Any] = {
            "url": self.url,
            "ok": self.ok,
            "depth": self.depth,
            "found_on": self.found_on,
        }
        if self.retries:
            line["retries"] = [
                {"reason": retry.reason, "after": round(retry.after, 3)}
                for retry in self.retries
            ]
        if self.error is not None:
            error = asdict(self.error)
            if error["target"] is None:
                del error["target"]
            if self.status is not None:
                # The site answered, with its error: where and how is kept, as
                # 0.9.0 printed it, and only its page is left out.
                line |= {"landed": self.landed, "fetch": self._fetch()}
            return {**line, "error": error}
        read = asdict(self.extraction) if self.extraction is not None else {}
        return {
            **line,
            "landed": self.landed,
            "fetch": self._fetch(),
            "canonical": self.canonical,
            "summary": read.get("summary", {}),
            "records": read.get("records", []),
            "sources": read.get("sources", []),
            "links": list(self.links),
            # Guesses read off the visible page, never in the summary; empty
            # when the crawl was asked not to read them.
            "visible": read.get("visible", {}),
        }

    def _fetch(self) -> dict[str, Any]:
        return {
            "rung": self.rung,
            "status": self.status,
            "seconds": round(self.seconds, 3),
            "climbs": [
                {**asdict(climb), "seconds": round(climb.seconds, 3)}
                for climb in self.climbs
            ],
        }


class Crawl:
    """Pages as their turn comes: iterate it once.

    ``stopped`` says why it ended, once it has: ``done`` when nothing was left
    to take, ``max_pages`` when the budget left links unfollowed, and
    ``time_budget`` when the time ran out first. ``resumed`` is how many pages
    the state file already held; they are not handed back again. ``notice``
    is a sentence to pass on, or None: when the pages come from somewhere
    other than asked -- a sitemap crawl of a site whose sitemaps listed nothing
    reads the start page's links -- or, once a crawl has ended, when links
    deeper than its ``max_depth`` were left unfollowed.
    """

    def __init__(
        self, pages: Callable[[Crawl], Iterator[Page]], resumed: int = 0
    ) -> None:
        self.stopped: str | None = None
        self.resumed = resumed
        self.notice: str | None = None
        self._pages = pages(self)

    def __iter__(self) -> Iterator[Page]:
        return self._pages

    def __next__(self) -> Page:
        return next(self._pages)


def crawl(
    start: str,
    max_pages: int = MAX_PAGES,
    max_depth: int = MAX_DEPTH,
    same_site: bool = True,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    *,
    state: str | Path | None = None,
    induce: bool = False,
    visible: bool = True,
    respect_tdm: bool = False,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    concurrency: int = CONCURRENCY,
    retries: int = RETRIES,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl:
    """Crawl from ``start``, following links breadth first, one page at a time
    per site, and hand back each page as its turn comes.

    Args:
        start: where the crawl begins; always taken.
        max_pages: the most addresses taken, whatever becomes of them.
        max_depth: the most links from ``start``; 0 takes ``start`` alone.
        same_site: follow only links on ``start``'s site -- its host, with or
            without ``www.``, over http or https. A redirect off the site is
            then refused before the other site is asked.
        include: regular expressions; when given, a link is followed only if
            one of them is found in its address.
        exclude: regular expressions; a link in whose address one is found is
            not followed. Neither applies to ``start``.
        state: a JSON Lines file: pages it already holds are not fetched
            again, and every new page is appended as its turn comes.
        induce: also read repeated rows from a page that declares nothing.
        visible: also guess the title, author and dates each page shows, as
            ``extract`` does, into its line's ``visible``; on by default.
        respect_tdm: give a page whose site reserves its text and data mining
            rights (TDMRep: its tdmrep.json, headers or meta tags) as a
            ``tdm_reserved`` error, never its data.
        min_delay: the least seconds between two requests to one site; a site
            that takes longer to answer waits as long as it lately took.
        max_delay: the longest robots.txt ``Crawl-delay`` waited for, and the
            longest wait a slow site or a retry is given.
        concurrency: how many sites may be asked at once.
        retries: how many times a page is asked again when its request did
            not answer, or answered 429 or a 5xx, each after twice the wait
            before; 0 asks once.
        time_budget: seconds after which no further page, or retry, is started.
        allow_private: when false, refuse addresses off the public internet.
        resolve: the name lookup ``allow_private`` decides with.
        max_bytes: the most one page may weigh.
        web: how sites are reached; the real web by default.
        clock, sleep: the time, injected so a test can pace a crawl.
        headers, cookies: ``fetch``'s, sent with the crawl's requests for the
            origin of ``start`` -- scheme, host and port -- pages and
            sitemaps, and with no other: not the site's ``www.`` twin, not
            its pages over plain http, not a robots.txt, which is read as
            anyone reads it. Never a ``User-Agent``.

    Returns:
        A ``Crawl`` to iterate for its ``Page``s.

    Raises:
        ValueError: ``start`` is not an http(s) address, or a pattern is not a
            regular expression; or ``headers`` and ``cookies`` are refused as
            ``fetch`` refuses them, or given with a ``web`` of the caller's.
        StateMismatch: ``state`` holds another crawl.
    """
    first = normalise(start)
    if first is None:
        raise ValueError(shown(not_a_start(start)))
    frontier = _Frontier(
        first, max_pages, max_depth, same_site, _patterns(include), _patterns(exclude)
    )

    def kept(landed: str) -> str | None:
        if not same_site or site_of(landed) == frontier.site:
            return None
        return f"it is off {frontier.site}"

    _sendable(web, headers, cookies)
    replayed: list[dict[str, Any]] = []
    if state is not None:
        replayed = _replay(Path(state), frontier)
        _cut_unfinished(Path(state))
    polite, web = _reach(
        web,
        min_delay,
        clock,
        sleep,
        allow_private,
        resolve,
        max_bytes,
        headers,
        cookies,
        max_delay,
        [first],
    )
    deadline = None if time_budget is None else clock() + time_budget
    visitor = _Visitor(
        web,
        polite,
        allow_private,
        resolve,
        max_bytes,
        max_delay,
        induce,
        kept,
        respect_tdm,
        retries,
        deadline,
        visible,
    )
    schedule: Schedule[Page] = Schedule(visitor.visit, polite, concurrency, deadline)

    def pages(run: Crawl) -> Iterator[Page]:
        with _appending(state) as out:
            for page in schedule.run(frontier.queue, frontier.commit):
                _write(out, page)
                yield page
        run.stopped = (
            "time_budget"
            if schedule.out_of_time
            else "max_pages"
            if frontier.cut
            else "done"
        )
        # Links reached and then taken after all are no longer left out.
        deeper = len(frontier.too_deep - frontier.seen)
        if deeper:
            # Past the cap more were left out than were kept, so the count
            # kept is a floor, and says so.
            floor = "at least " if frontier.too_deep_more else ""
            run.notice = (
                f"{floor}{deeper} link{'s' if deeper != 1 else ''} deeper than "
                f"max_depth {max_depth} {'were' if deeper != 1 else 'was'} "
                "not followed"
            )

    return Crawl(pages, resumed=len(replayed))


def extract_many(
    urls: Iterable[str],
    *,
    state: str | Path | None = None,
    induce: bool = False,
    visible: bool = True,
    respect_tdm: bool = False,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    concurrency: int = CONCURRENCY,
    retries: int = RETRIES,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl:
    """Read every address in ``urls``, politely, and hand back each page in the
    order the addresses were given.

    The same scheduler as ``crawl``: one request at a time per site, its delay
    between, ``concurrency`` sites at once. No link is followed. A redirect to
    another site is not followed inside the fetch: that page says
    ``redirected_off_site``, and its target is read in its own turn, at the
    end of the list, so every site is asked one request at a time however the
    list's addresses redirect. An address given twice is read once; one that
    is not an http(s) address comes back as a ``bad_input`` page. With
    ``state``, an address the file already holds is skipped, and every new
    page is appended. The other arguments are ``crawl``'s; ``headers`` and
    ``cookies`` go to every address's own origin, as a list of addresses
    handed to ``curl -H`` has them sent to each -- to the origins of the
    addresses given, and not to one a redirect's target, read in its own
    turn, is on.
    """
    # One a crawl cannot take is answered as given, a password in it hidden.
    given = [normalise(address) or shown(address.strip()) for address in urls]
    return _extract_listed(
        given,
        given,
        state=state,
        induce=induce,
        visible=visible,
        respect_tdm=respect_tdm,
        min_delay=min_delay,
        max_delay=max_delay,
        concurrency=concurrency,
        retries=retries,
        time_budget=time_budget,
        allow_private=allow_private,
        resolve=resolve,
        max_bytes=max_bytes,
        web=web,
        clock=clock,
        sleep=sleep,
        headers=headers,
        cookies=cookies,
    )


def _extract_listed(
    given: list[str],
    send_to: Sequence[str],
    *,
    state: str | Path | None,
    induce: bool,
    visible: bool,
    respect_tdm: bool,
    min_delay: float,
    max_delay: float,
    concurrency: int,
    retries: int,
    time_budget: float | None,
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
    web: Web | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    headers: Mapping[str, str] | None,
    cookies: Mapping[str, str] | None,
) -> Crawl:
    """``extract_many`` of ``given``, normalised, sending ``headers`` and
    ``cookies`` to the origins of ``send_to`` alone."""
    _sendable(web, headers, cookies)
    queue = Queue()
    queued: set[str] = set()
    targets: list[str] = []
    if state is not None:
        for line in _lines(Path(state)):
            queued.add(line["url"])
            error = line.get("error")
            if isinstance(error, dict) and isinstance(error.get("target"), str):
                targets.append(error["target"])
        _cut_unfinished(Path(state))

    def add(address: str, found_on: str | None = None) -> None:
        if address and address not in queued:
            queued.add(address)
            queue.add(address, found_on=found_on)

    for address in given:
        add(address)
    for target in targets:
        add(normalise(target) or target)

    def commit(task: Task, page: Page) -> None:
        if page.error is not None and page.error.target is not None:
            add(normalise(page.error.target) or page.error.target, page.url)

    polite, web = _reach(
        web,
        min_delay,
        clock,
        sleep,
        allow_private,
        resolve,
        max_bytes,
        headers,
        cookies,
        max_delay,
        send_to,
    )
    deadline = None if time_budget is None else clock() + time_budget
    visitor = _Visitor(
        web,
        polite,
        allow_private,
        resolve,
        max_bytes,
        max_delay,
        induce,
        None,
        respect_tdm,
        retries,
        deadline,
        visible,
    )
    schedule: Schedule[Page] = Schedule(visitor.visit, polite, concurrency, deadline)

    def pages(run: Crawl) -> Iterator[Page]:
        with _appending(state) as out:
            for page in schedule.run(queue, commit):
                _write(out, page)
                yield page
        run.stopped = "time_budget" if schedule.out_of_time else "done"

    return Crawl(pages, resumed=len(queued) - queue.added)


def _reach(
    web: Web | None,
    min_delay: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    max_delay: float = MAX_DELAY_SECONDS,
    send_to: Iterable[str] = (),
) -> tuple[Politeness, Web]:
    """The pacing and the web it paces, each built with the other.

    The real web asks the pacing about every redirect hop, and the pacing
    reads robots.txt through the web; the reader is looked up when first
    called, by which time both exist. ``send_to`` is the addresses the caller
    named, whose origins alone are sent ``headers`` and ``cookies``.
    """
    reached: list[Web] = []
    polite = Politeness(
        lambda url: reached[0].read(url),
        min_delay,
        clock,
        sleep,
        ceiling=max_delay,
    )
    reached.append(
        web
        if web is not None
        else default_web(
            allow_private,
            resolve,
            max_bytes,
            polite.hop,
            headers=headers,
            cookies=cookies,
            send_to=send_to,
        )
    )
    return polite, reached[0]


def _check_retries(retries: int) -> None:
    """Refuse, before anything is asked, retries a crawl does not make."""
    if not 0 <= retries <= MAX_RETRIES:
        raise ValueError(
            f"retries must be 0 or more and at most {MAX_RETRIES}, not {retries}"
        )


def _sendable(
    web: Web | None,
    headers: Mapping[str, str] | None,
    cookies: Mapping[str, str] | None,
) -> None:
    """Refuse, before anything is asked, headers the crawl could not send."""
    outgoing(headers, cookies)
    if web is not None and (headers or cookies):
        raise ValueError(
            "headers and cookies go into the web a crawl builds; one handed "
            "a web of its own sends what that web was built to send"
        )


class _Frontier:
    """What a crawl has seen, and what it takes next, decided in one order.

    An address is admitted once: when a page's turn comes, each of its links
    that passes the rules is numbered and queued. Where a page landed and the
    canonical it declares on the site are marked seen then too, so neither is
    fetched again under the other name.
    """

    def __init__(
        self,
        start: str,
        max_pages: int,
        max_depth: int,
        same_site: bool,
        include: list[re.Pattern[str]],
        exclude: list[re.Pattern[str]],
    ) -> None:
        self.site = site_of(start)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.same_site = same_site
        self.include = include
        self.exclude = exclude
        self.queue = Queue()
        self.seen: set[str] = {start}
        self.cut = False
        # Links a crawl would have taken but for max_depth, each once, at
        # most _TOO_DEEP_KEPT of them; too_deep_more says one more was seen.
        self.too_deep: set[str] = set()
        self.too_deep_more = False
        if max_pages > 0:
            self.queue.add(start)

    def admit(self, url: str | None, depth: int, found_on: str) -> None:
        if url is None or url in self.seen:
            return
        if self.same_site and site_of(url) != self.site:
            return
        if self.include and not any(p.search(url) for p in self.include):
            return
        if any(p.search(url) for p in self.exclude) or names_a_file(url):
            return
        if depth > self.max_depth:
            # Counted, not dropped without a word: a paginated listing ten
            # pages deep stopped at the fourth, and the crawl said it was done.
            if url in self.too_deep:
                return
            if len(self.too_deep) < _TOO_DEEP_KEPT:
                self.too_deep.add(url)
            else:
                self.too_deep_more = True
            return
        # Last, so that "cut" means a link that would otherwise have been taken.
        if self.queue.added >= self.max_pages:
            self.cut = True
            return
        self.seen.add(url)
        self.queue.add(url, depth, found_on)

    def commit(self, task: Task, page: Page) -> None:
        if page.landed is not None:
            self.seen.add(page.landed)
        if page.canonical is not None and site_of(page.canonical) == site_of(page.url):
            self.seen.add(page.canonical)
        if page.error is not None and page.error.code == "redirected_off_site":
            self.admit(normalise(page.error.target or ""), page.depth, page.url)
        for link in page.links:
            self.admit(link, page.depth + 1, page.url)


class _Visitor:
    """Takes one address: waits its site's turn, fetches it, reads it."""

    def __init__(
        self,
        web: Web,
        polite: Politeness,
        allow_private: bool,
        resolve: Callable[[str], Iterable[str]],
        max_bytes: int,
        max_delay: float,
        induce: bool,
        kept: Callable[[str], str | None] | None,
        respect_tdm: bool = False,
        retries: int = RETRIES,
        deadline: float | None = None,
        visible: bool = True,
    ) -> None:
        _check_retries(retries)
        self.web = web
        self.polite = polite
        self.rungs = polite.paced(web.rungs)
        # Which rung each part of a site needed, for this crawl, over what
        # the web remembers of the whole site.
        self.memory = Parts(web.memory) if web.memory is not None else None
        self.allow_private = allow_private
        self.resolve = resolve
        self.max_bytes = max_bytes
        self.max_delay = max_delay
        self.induce = induce
        self.visible = visible
        self.kept = kept
        self.respect_tdm = respect_tdm
        self.retries = retries
        self.deadline = deadline
        # Each site's tdmrep.json, read once, as its robots.txt is.
        self.tdm_rules: dict[str, list[TdmRule]] = {}

    def rules_of(self, url: str) -> list[TdmRule]:
        """The site's tdmrep.json rules, read once per site, politely.

        Read as a sitemap is: refused where robots.txt refuses it, after the
        site's delay; a file that could not be read holds no rules.
        """
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self.tdm_rules:
            return self.tdm_rules[origin]
        address = origin + WELL_KNOWN
        rules: list[TdmRule] = []
        try:
            if (
                robots_refusal(address, self.polite.reader, now=self.polite.clock)
                is None
            ):
                with self.polite.turn(address, self.polite.delay_for(address)):
                    response = self.web.get(address)
                if 200 <= response.status < 300:
                    rules = read_tdmrep(response.body.decode("utf-8", "replace"))
        # Deliberately blind: a file that could not be read, however, is a
        # site that declared nothing there, and the page's own tags still count.
        except Exception:  # noqa: BLE001
            rules = []
        self.tdm_rules[origin] = rules
        return rules

    def visit(self, task: Task) -> Page:
        """Take ``task``, asking again, a bounded number of times and each time
        later, while what came back may be different later."""
        page, retries = asking_again(
            self.polite,
            task.url,
            self.retries,
            self.deadline,
            lambda: self._take(task),
            _worth_asking_again,
        )
        return replace(page, retries=retries) if retries else page

    def _take(self, task: Task) -> Page:
        """One try at ``task``: its robots.txt, its fetch, its reading."""

        def failed(
            code: str, message: str, retryable: bool = False, target: str | None = None
        ) -> Page:
            error = PageError(code, message, retryable, target)
            return Page(task.url, task.depth, task.found_on, error=error)

        if normalise(task.url) is None:
            return failed("bad_input", not_a_start(task.url))
        # Before its robots.txt is read: that is a request too, and a refused
        # address would come back from it as a robots.txt nobody could read.
        refused = None if self.allow_private else why_not_public(task.url, self.resolve)
        if refused is not None:
            return failed("refused_address", str(AddressRefused(task.url, refused)))
        try:
            delay = self.polite.delay_for(task.url)
        except RobotsUnreachable as unreachable:
            return failed(
                "fetch_failed", str(unreachable), retryable=unreachable.transient
            )
        if delay > self.max_delay:
            return failed(
                "crawl_delay_too_long",
                f"its robots.txt asks for {delay:g} s between requests, longer "
                f"than the {self.max_delay:g} s this crawl waits",
            )
        refused_for = self.polite.refused_for(task.url)
        if refused_for > 0:
            return failed(
                "rate_limited",
                f"it asked, by Retry-After, not to be asked for {refused_for:g} s "
                f"more, longer than the {self.max_delay:g} s this crawl waits",
                retryable=True,
            )
        self.polite.wait(task.url, delay)
        try:
            fetched = fetch(
                task.url,
                rungs=self.rungs,
                robots_reader=self.polite.reader,
                allow_private=self.allow_private,
                resolve=self.resolve,
                max_bytes=self.max_bytes,
                memory=self.memory,
            )
        except RobotsRefused as refused:
            return failed("refused_by_robots", str(refused))
        except AddressRefused as refused:
            return failed("refused_address", str(refused))
        except RedirectRefused as refused:
            return failed("redirected_off_site", str(refused), target=refused.target)
        except ResponseTooLarge as heavy:
            return failed("too_large", str(heavy))
        except SiteRefused as refused:
            return failed("refused_by_site", str(refused))
        except PaymentRequired as unpaid:
            return failed("payment_required", str(unpaid))
        except FetchFailed as failure:
            return failed("fetch_failed", str(failure), retryable=failure.transient)
        finally:
            self.polite.ended(task.url)
        if self.memory is not None and not fetched.climbs:
            self.memory.served(task.url)
        landed = normalise(fetched.url) or fetched.url
        # A browser follows a redirect itself when nothing guards it, so where
        # the page landed is judged again. Too late to spare the other site its
        # request; not too late to keep its page out of a crawl of this one.
        reason = self.kept(landed) if self.kept else None
        if reason is not None:
            return failed(
                "redirected_off_site",
                f"{task.url} landed on {landed}, which is not followed: {reason}",
                target=landed,
            )
        doc = load(fetched.html, url=fetched.url)
        extraction = extract(
            fetched.html,
            url=fetched.url,
            induce=self.induce,
            headers=fetched.headers,
            visible=self.visible,
        )
        if self.respect_tdm:
            found = reservation(
                self.rules_of(fetched.url), fetched.url, extraction.rights
            )
            if found is not None and found.reserved:
                policy = f", policy {found.policy}" if found.policy else ""
                return failed(
                    "tdm_reserved",
                    f"{fetched.url} reserves its text and data mining rights "
                    f"(TDMRep, by its {found.source}{policy})",
                )
        # A 429 or a 503 is the site asking to be asked less often: the next
        # request to it waits its Retry-After, or twice the delay.
        self.polite.slow_down(task.url, fetched, self.max_delay)
        if fetched.status >= 400:
            # The site's error, not the page: its title is "404 Not Found",
            # and until 0.9.1 its line said ok true with that as its summary.
            # Its links and canonical are the error page's too: a 404 that
            # names a product as its canonical would have the product marked
            # seen. A 429 or a 5xx may pass, and is asked again.
            again = fetched.status == 429 or fetched.status >= 500
            error = PageError(
                "fetch_failed",
                f"{fetched.url} answered status {fetched.status}: the site's "
                "error, not the page",
                retryable=again,
            )
            return Page(
                task.url,
                task.depth,
                task.found_on,
                landed=landed,
                rung=fetched.rung,
                status=fetched.status,
                seconds=fetched.seconds,
                climbs=tuple(fetched.climbs),
                error=error,
            )
        answered = fetched.status < 400
        return Page(
            task.url,
            task.depth,
            task.found_on,
            landed=landed,
            rung=fetched.rung,
            status=fetched.status,
            seconds=fetched.seconds,
            climbs=tuple(fetched.climbs),
            extraction=extraction,
            canonical=canonical_of(doc, fetched.headers) if answered else None,
            links=tuple(links_on(doc, fetched.headers)) if answered else (),
        )


_Try = TypeVar("_Try")


def asking_again(
    polite: Politeness,
    url: str,
    retries: int,
    deadline: float | None,
    take: Callable[[], _Try],
    why: Callable[[_Try], str | None],
) -> tuple[_Try, tuple[Retry, ...]]:
    """``take()``, and again while ``why`` says what it came to may be
    different later: at most ``retries`` more times, each after
    ``polite.backoff``, never one that would start past ``deadline``. The
    last try, and each retry made.

    A site whose try failed through all its retries is noted as failing, so
    its next pages are asked once until one of them is answered.
    """
    made: list[Retry] = []
    while True:
        answer = take()
        reason = why(answer)
        if reason is None:
            polite.failing(url, failed=False)
            break
        if len(made) >= retries:
            polite.failing(url, failed=bool(retries))
            break
        after = polite.backoff(url, len(made) + 1)
        if after is None or polite.refused_for(url) > 0:
            break
        ended = polite.last_ended(url)
        if deadline is not None and ended is not None and ended + after > deadline:
            break
        made.append(Retry(reason, after))
        polite.wait(url, after)
    return answer, tuple(made)


def _worth_asking_again(page: Page) -> str | None:
    """What ``page`` came to, when asking again later may bring back more:
    a fetch that failed in a way that may pass -- the page or its robots.txt
    did not answer, or its answer was cut short (``FetchFailed.transient``)
    -- or a 429 or a 5xx. None for any other answer: a redirect loop, an
    encoding the fetch cannot read, a 404 are asked again for the same."""
    if page.status is not None and (page.status == 429 or page.status >= 500):
        return f"it answered {page.status}"
    if page.error is not None:
        retry = page.error.code == "fetch_failed" and page.error.retryable
        return page.error.message if retry else None
    return None


def _patterns(given: Sequence[str]) -> list[re.Pattern[str]]:
    try:
        return [re.compile(pattern) for pattern in given]
    except re.error as bad:
        raise ValueError(f"{bad.pattern!r} is not a regular expression: {bad}") from bad


def _replay(path: Path, frontier: _Frontier) -> list[dict[str, Any]]:
    """Admit again what the pages in ``path`` admitted, in their order.

    Each line must be the page this crawl would take next; one that is not
    means the file was written by another crawl, and resuming it would mix two.
    """
    lines = _lines(path)
    for number, line in enumerate(lines, 1):
        task = frontier.queue.first()
        if task is None or line.get("url") != task.url:
            expected = "nothing more" if task is None else task.url
            raise StateMismatch(
                str(path),
                f"line {number} is {line.get('url')!r}, where this crawl takes "
                f"{expected}; it was written by a crawl of another site or with "
                "other options",
            )
        frontier.commit(task, _page_of(line, task))
    return lines


def _page_of(line: dict[str, Any], task: Task) -> Page:
    """As much of a page as its admissions need, from its line."""
    error = line.get("error")
    return Page(
        task.url,
        task.depth,
        task.found_on,
        landed=line.get("landed"),
        canonical=line.get("canonical"),
        links=tuple(line.get("links") or ()),
        error=None
        if not isinstance(error, dict)
        else PageError(
            str(error.get("code")),
            str(error.get("message")),
            target=error.get("target"),
        ),
    )


def _lines(path: Path) -> list[dict[str, Any]]:
    """The pages a state file holds, its unfinished last line left out.

    A line is written whole and then flushed, so only the last can be partial:
    a crawl stopped mid-write, which is the start of a page's line. Anything
    else that is not a page's JSON means the file is not a crawl's output. The
    file is only read here; ``_cut_unfinished`` drops the partial line once
    the caller has accepted the file, so a file that is refused is left as it
    was -- measured before, pointed at someone's notes, ``--resume`` cut their
    last line off and then refused them.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    complete = data.rfind(b"\n") + 1
    written = data[:complete].splitlines()
    lines = []
    for number, raw in enumerate(written, 1):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except ValueError:
            line = None
        if not isinstance(line, dict) or not isinstance(line.get("url"), str):
            raise StateMismatch(str(path), f"line {number} is not a page's JSON")
        lines.append(line)
    unfinished = data[complete:]
    if unfinished and not (
        unfinished.startswith(_PAGE_LINE) or _PAGE_LINE.startswith(unfinished)
    ):
        raise StateMismatch(str(path), f"line {len(written) + 1} is not a page's JSON")
    return lines


_PAGE_LINE = b'{"url": '
"""How every line ``_write`` writes begins, so how a line cut short begins."""


def _cut_unfinished(path: Path) -> None:
    """Drop the line a stopped crawl left half written, once the file is
    accepted as this crawl's: the next page is appended after whole lines."""
    try:
        with path.open("r+b") as handle:
            data = handle.read()
            complete = data.rfind(b"\n") + 1
            if complete < len(data):
                handle.truncate(complete)
    except FileNotFoundError:
        return


@contextmanager
def _appending(state: str | Path | None) -> Iterator[IO[str] | None]:
    """The state file, opened to append, or nothing when there is none."""
    if state is None:
        yield None
        return
    with Path(state).open("a", encoding="utf-8") as handle:
        yield handle


def _write(out: IO[str] | None, page: Page) -> None:
    if out is not None:
        out.write(json.dumps(page.to_json(), ensure_ascii=False) + "\n")
        out.flush()
