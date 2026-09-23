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
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any

from sluicer.api import Extraction, extract
from sluicer.crawl.schedule import (
    CONCURRENCY,
    DEFAULT_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    Politeness,
    Queue,
    Schedule,
    Task,
)
from sluicer.crawl.urls import canonical_of, links_on, names_a_file, normalise, site_of
from sluicer.crawl.web import Web, default_web
from sluicer.document import load
from sluicer.fetch import (
    AddressRefused,
    Climb,
    FetchFailed,
    RedirectRefused,
    ResponseTooLarge,
    RobotsRefused,
    fetch,
)
from sluicer.fetch.address import _resolve, why_not_public
from sluicer.fetch.identity import RobotsUnreachable
from sluicer.fetch.result import MAX_RESPONSE_BYTES

MAX_PAGES = 100
"""How many addresses a crawl takes unless told otherwise."""

MAX_DEPTH = 3
"""How many links from the start a crawl goes unless told otherwise."""


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
    ``refused_address``, ``fetch_failed`` (the only ``retryable`` one),
    ``too_large``, ``bad_input`` -- or one of a crawl's own:
    ``redirected_off_site``, with the ``target`` it pointed to, and
    ``crawl_delay_too_long``.
    """

    code: str
    message: str
    retryable: bool = False
    target: str | None = None


@dataclass(frozen=True)
class Page:
    """One address a crawl or a batch took, and what became of it.

    ``url`` is the address taken, normalised; ``landed`` where its redirects
    ended. ``found_on`` is the page whose link led here, None for the start or
    a listed address. ``canonical`` is the page's own ``<link
    rel=canonical>``, and ``links`` every address it lets a crawl follow, in
    document order. ``extraction`` is ``sluicer.extract``'s reading; it and
    the fetch fields are None exactly when ``error`` is not.
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
        if self.error is not None:
            error = asdict(self.error)
            if error["target"] is None:
                del error["target"]
            return {**line, "error": error}
        read = asdict(self.extraction) if self.extraction is not None else {}
        return {
            **line,
            "landed": self.landed,
            "fetch": {
                "rung": self.rung,
                "status": self.status,
                "seconds": round(self.seconds, 3),
                "climbs": [
                    {**asdict(climb), "seconds": round(climb.seconds, 3)}
                    for climb in self.climbs
                ],
            },
            "canonical": self.canonical,
            "summary": read.get("summary", {}),
            "records": read.get("records", []),
            "sources": read.get("sources", []),
            "links": list(self.links),
        }


class Crawl:
    """Pages as their turn comes: iterate it once.

    ``stopped`` says why it ended, once it has: ``done`` when nothing was left
    to take, ``max_pages`` when the budget left links unfollowed, and
    ``time_budget`` when the time ran out first. ``resumed`` is how many pages
    the state file already held; they are not handed back again.
    """

    def __init__(
        self, pages: Callable[[Crawl], Iterator[Page]], resumed: int = 0
    ) -> None:
        self.stopped: str | None = None
        self.resumed = resumed
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
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    concurrency: int = CONCURRENCY,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
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
        min_delay: the least seconds between two requests to one site.
        max_delay: the longest robots.txt ``Crawl-delay`` waited for.
        concurrency: how many sites may be asked at once.
        time_budget: seconds after which no further page is started.
        allow_private: when false, refuse addresses off the public internet.
        resolve: the name lookup ``allow_private`` decides with.
        max_bytes: the most one page may weigh.
        web: how sites are reached; the real web by default.
        clock, sleep: the time, injected so a test can pace a crawl.

    Returns:
        A ``Crawl`` to iterate for its ``Page``s.

    Raises:
        ValueError: ``start`` is not an http(s) address, or a pattern is not a
            regular expression.
        StateMismatch: ``state`` holds another crawl.
        FetchExtraMissing: the ``fetch`` extra is not installed.
    """
    first = normalise(start)
    if first is None:
        raise ValueError(f"{start!r} is not an http(s) address a crawl can start at")
    frontier = _Frontier(
        first, max_pages, max_depth, same_site, _patterns(include), _patterns(exclude)
    )

    def stays(current: str, target: str) -> str | None:
        if site_of(target) == site_of(current):
            return None
        return f"it leads off {site_of(current)}, to {site_of(target) or target}"

    replayed: list[dict[str, Any]] = []
    if state is not None:
        replayed = _replay(Path(state), frontier)
    web = (
        web
        if web is not None
        else default_web(allow_private, resolve, max_bytes, stays)
    )
    polite = Politeness(web.read, min_delay, clock, sleep)
    visitor = _Visitor(
        web, polite, allow_private, resolve, max_bytes, max_delay, induce, stays
    )
    deadline = None if time_budget is None else clock() + time_budget
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

    return Crawl(pages, resumed=len(replayed))


def extract_many(
    urls: Iterable[str],
    *,
    state: str | Path | None = None,
    induce: bool = False,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    concurrency: int = CONCURRENCY,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Crawl:
    """Read every address in ``urls``, politely, and hand back each page in the
    order the addresses were given.

    The same scheduler as ``crawl``: one request at a time per site, its delay
    between, ``concurrency`` sites at once. No link is followed, and a redirect
    goes wherever it leads, as for one fetch. An address given twice is read
    once; one that is not an http(s) address comes back as a ``bad_input``
    page. With ``state``, an address the file already holds is skipped, and
    every new page is appended. The other arguments are ``crawl``'s.
    """
    done: set[str] = set()
    if state is not None:
        done = {line["url"] for line in _lines(Path(state))}
    queue = Queue()
    queued: set[str] = set(done)
    for given in urls:
        address = normalise(given) or given.strip()
        if address and address not in queued:
            queued.add(address)
            queue.add(address)
    web = web if web is not None else default_web(allow_private, resolve, max_bytes)
    polite = Politeness(web.read, min_delay, clock, sleep)
    visitor = _Visitor(
        web, polite, allow_private, resolve, max_bytes, max_delay, induce, None
    )
    deadline = None if time_budget is None else clock() + time_budget
    schedule: Schedule[Page] = Schedule(visitor.visit, polite, concurrency, deadline)

    def pages(run: Crawl) -> Iterator[Page]:
        with _appending(state) as out:
            for page in schedule.run(queue, lambda task, page: None):
                _write(out, page)
                yield page
        run.stopped = "time_budget" if schedule.out_of_time else "done"

    return Crawl(pages, resumed=len(done))


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
        if max_pages > 0:
            self.queue.add(start)

    def admit(self, url: str | None, depth: int, found_on: str) -> None:
        if url is None or url in self.seen or depth > self.max_depth:
            return
        if self.same_site and site_of(url) != self.site:
            return
        if self.include and not any(p.search(url) for p in self.include):
            return
        if any(p.search(url) for p in self.exclude) or names_a_file(url):
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
        stays: Callable[[str, str], str | None] | None,
    ) -> None:
        self.web = web
        self.polite = polite
        self.allow_private = allow_private
        self.resolve = resolve
        self.max_bytes = max_bytes
        self.max_delay = max_delay
        self.induce = induce
        self.stays = stays

    def visit(self, task: Task) -> Page:
        def failed(
            code: str, message: str, retryable: bool = False, target: str | None = None
        ) -> Page:
            error = PageError(code, message, retryable, target)
            return Page(task.url, task.depth, task.found_on, error=error)

        if normalise(task.url) is None:
            return failed("bad_input", f"{task.url!r} is not an http(s) address")
        # Before its robots.txt is read: that is a request too, and a refused
        # address would come back from it as a robots.txt nobody could read.
        refused = None if self.allow_private else why_not_public(task.url, self.resolve)
        if refused is not None:
            return failed("refused_address", str(AddressRefused(task.url, refused)))
        try:
            delay = self.polite.delay_for(task.url)
        except RobotsUnreachable as unreachable:
            return failed("fetch_failed", str(unreachable), retryable=True)
        if delay > self.max_delay:
            return failed(
                "crawl_delay_too_long",
                f"its robots.txt asks for {delay:g} s between requests, longer "
                f"than the {self.max_delay:g} s this crawl waits",
            )
        self.polite.wait(task.url, delay)
        try:
            fetched = fetch(
                task.url,
                rungs=self.web.rungs,
                robots_reader=self.polite.reader,
                allow_private=self.allow_private,
                resolve=self.resolve,
                max_bytes=self.max_bytes,
            )
        except RobotsRefused as refused:
            return failed("refused_by_robots", str(refused))
        except AddressRefused as refused:
            return failed("refused_address", str(refused))
        except RedirectRefused as refused:
            return failed("redirected_off_site", str(refused), target=refused.target)
        except ResponseTooLarge as heavy:
            return failed("too_large", str(heavy))
        except FetchFailed as failure:
            return failed("fetch_failed", str(failure), retryable=True)
        finally:
            self.polite.ended(task.url)
        landed = normalise(fetched.url) or fetched.url
        # A browser follows a redirect itself when nothing guards it, so the
        # rule is asked again of where the page landed. Too late to spare the
        # other site its request; not too late to keep its page out.
        reason = self.stays(task.url, landed) if self.stays else None
        if reason is not None:
            return failed(
                "redirected_off_site",
                f"{task.url} landed on {landed}, which is not followed: {reason}",
                target=landed,
            )
        doc = load(fetched.html, url=fetched.url)
        return Page(
            task.url,
            task.depth,
            task.found_on,
            landed=landed,
            rung=fetched.rung,
            status=fetched.status,
            seconds=fetched.seconds,
            climbs=tuple(fetched.climbs),
            extraction=extract(fetched.html, url=fetched.url, induce=self.induce),
            canonical=canonical_of(doc),
            links=tuple(links_on(doc)),
        )


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
    """The pages a state file holds, its unfinished last line cut off.

    A line is written whole and then flushed, so only the last can be partial:
    a crawl stopped mid-write. Anything else that is not a page's JSON means
    the file is not a crawl's output.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    complete = data.rfind(b"\n") + 1
    if complete < len(data):
        with path.open("r+b") as handle:
            handle.truncate(complete)
    lines = []
    for number, raw in enumerate(data[:complete].splitlines(), 1):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except ValueError:
            line = None
        if not isinstance(line, dict) or not isinstance(line.get("url"), str):
            raise StateMismatch(str(path), f"line {number} is not a page's JSON")
        lines.append(line)
    return lines


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
