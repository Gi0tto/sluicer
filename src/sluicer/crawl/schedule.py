"""Which address next, when, and in what order the answers are handed back.

Politeness is what this module is for. A site is never asked twice at once, and
never again sooner than its delay after its last request ended: at least
``DEFAULT_DELAY_SECONDS``, longer when its robots.txt asks, and at least as
long as it has lately taken to answer. Every request counts -- its robots.txt,
its sitemaps, its pages. Different sites are asked side by side, up to a
bound. "Never twice at once" holds for the process, not only for one crawl:
each request is made holding its site in ``sluicer.fetch.gate``, which every
other fetch holds too.

Order is the other promise. Tasks are numbered as they are added, and the pages
come back in that order whatever order they finished in, so the same crawl of
the same site always writes the same file.
"""

from __future__ import annotations

import email.utils
import math
import time
from collections.abc import Callable, Iterator, MutableMapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property, partial
from typing import Generic, TypeVar

from sluicer.crawl.urls import site_of
from sluicer.fetch.gate import (
    DEFAULT_DELAY_SECONDS as DEFAULT_DELAY_SECONDS,
    ENDED,
    GATE,
    LOCK,
    Gate,
)
from sluicer.fetch.identity import robots_delay
from sluicer.fetch.result import Fetched, Rung

MAX_DELAY_SECONDS = 60.0
"""The longest wait between two requests to one site a crawl accepts. A site
asking for more is not crawled at all rather than crawled for a week: its pages
say ``crawl_delay_too_long``, with the delay it asked for."""

SLOWING_STATUSES = frozenset({429, 503})
"""Statuses by which a site says it is asked too often or cannot answer now:
429 Too Many Requests and 503 Service Unavailable (RFC 6585, RFC 9110)."""

CONCURRENCY = 4
"""How many sites are asked at the same moment, never more than once each."""

RETRIES = 2
"""How many times a crawl asks again for a page whose request may succeed
later: one that did not answer -- a connection reset, a timeout, a name that
did not resolve, a robots.txt that could not be read -- or answered 429 or a
5xx. Never a 4xx but 429: a 404 or a 403 is the site's answer about the page,
and asking again gets it again."""

LOOKAHEAD = 256
"""How far past the first unfinished task a free site may be served from.

Pages come back in order, so one waiting behind a slow site is held in memory;
this bounds how many are.
"""

_Result = TypeVar("_Result")


_ENDED = ENDED
"""When each site's last request ended, for the whole process: the gate's."""


@dataclass(frozen=True)
class Task:
    """One address to take, numbered in the order it was added.

    ``depth`` is how many links it is from where the crawl started, and
    ``found_on`` the page whose link it was; both are None-ish for an address
    that was handed in.
    """

    seq: int
    url: str
    depth: int = 0
    found_on: str | None = None

    @cached_property
    def site(self) -> str:
        return site_of(self.url)


class Politeness:
    """When each site may next be asked, by its own rules and by ours.

    ``reader`` is ``read`` with every call counted as a request to the site it
    asked, so a robots.txt fetched in passing -- by the ladder, after a
    redirect -- paces the next request like any other.

    When a site's last request ended is remembered for the whole process, as
    the robots.txt answers are: a map and then a crawl of one site, or an agent
    calling the crawl tool twice, keep the delay between them too. Measured on
    scrapeme.live before, the first request of a batch followed the map's last
    by 0.00 s. Each request is made in a ``turn``, holding its site in
    ``gate``, so a crawl running beside it, or a single fetch, waits for it to
    end: measured before, two crawls of one site at once asked it 0.000 s
    apart.
    """

    def __init__(
        self,
        read: Callable[[str], str | None],
        min_delay: float = DEFAULT_DELAY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        ended: MutableMapping[str, float] | None = None,
        gate: Gate = GATE,
        ceiling: float = MAX_DELAY_SECONDS,
    ) -> None:
        self.min_delay = min_delay
        self.ceiling = ceiling
        self.clock = clock
        self.sleep = sleep
        self.gate = gate
        self._read = read
        self._ended = gate.ended if ended is None else ended
        self._delays: dict[str, float] = {}
        # What robots.txt and ours ask, before anything the site's answers
        # added: what a retry's backoff doubles.
        self._rules: dict[str, float] = {}
        # How long each site has lately taken to answer, and when the request
        # it is answering now began.
        self._latency: dict[str, float] = {}
        self._began: dict[str, float] = {}
        # Sites whose last page failed through all its retries: asked once a
        # page until one of their requests is answered.
        self._failing: set[str] = set()
        # What a site's own answers asked for: a delay it doubled by a 429 or
        # a 503 with no Retry-After, a moment a Retry-After named, and one it
        # named past what the crawl waits for, until which it is not asked.
        self._slowed: dict[str, float] = {}
        self._not_before: dict[str, float] = {}
        self._refused_until: dict[str, float] = {}
        self._lock = LOCK

    @contextmanager
    def turn(self, url: str, delay: float | None = None) -> Iterator[None]:
        """Make one request to ``url``'s site: holding it, after ``delay`` (the
        delay known for it by default), and counted, and timed, when the block
        ends."""
        with self.gate.hold(url):
            if delay is None:
                self.rest(url)
            else:
                self.wait(url, delay)
            self.began(url)
            try:
                yield
            finally:
                self.ended(url)

    def reader(self, url: str) -> str | None:
        """Read the robots.txt at ``url`` as a request to its site: after the
        site's delay, and counted when it ends."""
        with self.turn(url):
            return self._read(url)

    def hop(self, current: str, target: str) -> str | None:
        """The rule each hop of a page's redirect is asked before it is requested.

        A hop to another site is refused, with the reason: that site is asked
        in its own turn, never inside another's. A hop that stays is a request
        like any other, and waits the site's delay after the one before it.
        """
        if site_of(target) != site_of(current):
            return f"it leads off {site_of(current)}, to {site_of(target) or target}"
        self.ended(current)
        self.rest(target)
        self.began(target)
        return None

    def paced(self, rungs: Sequence[tuple[str, Rung]]) -> list[tuple[str, Rung]]:
        """``rungs``, each call a request that waits its turn and is counted.

        The ladder calls the next rung the moment the last one came back, and
        reads a redirect's robots.txt the moment the page landed; each is a
        request to the site the moment before just asked.
        """

        def pace(rung: Rung) -> Rung:
            def paced(url: str) -> Fetched:
                with self.turn(url):
                    return rung(url)

            return paced

        return [(name, pace(rung)) for name, rung in rungs]

    def rest(self, url: str) -> None:
        """Sleep until ``url``'s site may be asked again, by the delay known."""
        with self._lock:
            delay = self._delays.get(site_of(url), self.min_delay)
        self.wait(url, delay)

    def delay_for(self, url: str) -> float:
        """The seconds ``url``'s site wants between requests: ours, or its
        robots.txt's if longer. Reading that robots.txt may be a request.

        Raises:
            RobotsUnreachable: the robots.txt could not be read.
        """
        delay = max(self.min_delay, robots_delay(url, self.reader, now=self.clock))
        with self._lock:
            self._rules[site_of(url)] = delay
            delay = max(delay, self._slowed.get(site_of(url), 0.0))
            self._delays[site_of(url)] = delay
        return delay

    def slow_down(self, url: str, fetched: Fetched, ceiling: float) -> None:
        """Take a 429's or a 503's word for how often ``url``'s site may be asked.

        A ``Retry-After`` up to ``ceiling`` is waited before the next request;
        a longer one is not waited for, and until it has passed the site is
        not asked at all (``refused_for``). Without one, the site's delay
        doubles for the rest of the crawl, up to ``ceiling``. Any other status
        changes nothing.
        """
        if fetched.status not in SLOWING_STATUSES:
            return
        site = site_of(url)
        wait = retry_after(fetched.headers)
        with self._lock:
            if wait is not None:
                named = self._refused_until if wait > ceiling else self._not_before
                named[site] = max(named.get(site, -math.inf), self.clock() + wait)
                return
            current = self._delays.get(site, self.min_delay)
            self._slowed[site] = min(ceiling, max(current * 2, self.min_delay))
            self._delays[site] = max(current, self._slowed[site])

    def refused_for(self, url: str) -> float:
        """The seconds left before ``url``'s site said, by a Retry-After longer
        than a crawl waits, it may be asked again; 0 when it said no such
        thing, or the moment has passed."""
        with self._lock:
            until = self._refused_until.get(site_of(url))
        return 0.0 if until is None else max(0.0, until - self.clock())

    def ready_at(self, site: str) -> float:
        """When ``site`` may next be asked, as far as is known without asking."""
        with self._lock:
            ended = self._ended.get(site)
            delay = max(self._delays.get(site, self.min_delay), self._pace(site))
            until = self._not_before.get(site, -math.inf)
        return max(until, -math.inf if ended is None else ended + delay)

    def wait(self, url: str, delay: float) -> None:
        """Sleep until ``url``'s site has rested ``delay`` seconds, or as long
        as it has lately taken to answer, when that is longer."""
        site = site_of(url)
        with self._lock:
            ended = self._ended.get(site)
            until = self._not_before.get(site, -math.inf)
            delay = max(delay, self._pace(site))
        ready = max(until, -math.inf if ended is None else ended + delay)
        rest = ready - self.clock()
        if rest > 0:
            self.sleep(rest)

    def began(self, url: str) -> None:
        """Note that a request to ``url``'s site starts now, to time it."""
        with self._lock:
            self._began[site_of(url)] = self.clock()

    def ended(self, url: str) -> None:
        """Note that a request to ``url``'s site has just ended, and how long
        it took when its start was noted.

        The pace follows the answers as Scrapy's AutoThrottle does, for one
        request at a time: each one's seconds are averaged with the pace
        before, so one slow answer moves it halfway and a site that stays slow
        is soon asked as slowly as it answers.
        """
        site = site_of(url)
        with self._lock:
            now = self.clock()
            self._ended[site] = now
            began = self._began.pop(site, None)
            if began is not None:
                took = now - began
                known = self._latency.get(site)
                self._latency[site] = took if known is None else (known + took) / 2

    def pace(self, url: str) -> float:
        """The rest ``url``'s site has earned by how long it takes to answer:
        its recent answers' seconds, never more than the crawl's ceiling."""
        with self._lock:
            return self._pace(site_of(url))

    def _pace(self, site: str) -> float:
        return min(self.ceiling, self._latency.get(site, 0.0))

    def backoff(self, url: str, retry: int) -> float | None:
        """How many seconds after its last request ended ``url``'s site is
        asked again for a page's ``retry``-th time, counting from 1; None when
        it is not asked again.

        Twice the site's delay for the first retry, four times for the second,
        and so on: the delay its robots.txt and ours ask, doubled each time, or
        longer when the site asked for longer -- a Retry-After, a delay a 429
        doubled, a pace its slow answers set -- and never more than the
        crawl's ceiling but for a Retry-After within it. None for a site whose
        last page failed through all its retries, until it answers again.
        """
        site = site_of(url)
        with self._lock:
            if site in self._failing:
                return None
            rule = self._rules.get(site, self.min_delay)
            current = max(self._delays.get(site, self.min_delay), self._pace(site))
            ended = self._ended.get(site)
            until = self._not_before.get(site, -math.inf)
        wait = min(self.ceiling, max(rule * 2.0**retry, current))
        return wait if ended is None else max(wait, until - ended)

    def last_ended(self, url: str) -> float | None:
        """When the last request to ``url``'s site ended, if one is known."""
        with self._lock:
            return self._ended.get(site_of(url))

    def failing(self, url: str, failed: bool) -> None:
        """Note whether ``url``'s site failed a page through all its retries
        (``failed``), or answered one."""
        with self._lock:
            if failed:
                self._failing.add(site_of(url))
            else:
                self._failing.discard(site_of(url))


def retry_after(headers: dict[str, str]) -> float | None:
    """The seconds a response's ``Retry-After`` asks for, or None.

    RFC 9110 allows a number of seconds or a date. A date is counted from the
    response's own ``Date``, so the wait is the one the server meant whatever
    this machine's clock says; with no ``Date`` it cannot be counted, and is
    None, as is anything that is neither. A moment already past is 0.
    """
    written = (headers.get("retry-after") or "").strip()
    if written.isdigit():
        return float(written)
    try:
        then = email.utils.parsedate_to_datetime(written)
        sent = email.utils.parsedate_to_datetime(headers.get("date") or "")
    except (TypeError, ValueError, IndexError):
        return None
    if then.tzinfo is None or sent.tzinfo is None:
        return None
    return max(0.0, (then - sent).total_seconds())


class Queue:
    """The tasks not yet taken, in the order they were added."""

    def __init__(self, first: int = 0) -> None:
        self.added = 0
        self._next = first
        self._waiting: list[Task] = []

    def add(self, url: str, depth: int = 0, found_on: str | None = None) -> Task:
        task = Task(self._next, url, depth, found_on)
        self._next += 1
        self.added += 1
        self._waiting.append(task)
        return task

    def __bool__(self) -> bool:
        return bool(self._waiting)

    def head(self) -> int:
        """The number of the first task not yet taken, or of the next one added."""
        return self._waiting[0].seq if self._waiting else self._next

    def first(self) -> Task | None:
        """Take the first task whatever its site's state: for replaying a file."""
        return self._waiting.pop(0) if self._waiting else None

    def take(self, may_start: Callable[[str], bool], below: int) -> Task | None:
        """Take the first task numbered below ``below`` whose site may start.

        The first one found is the earliest of its site, since a site that may
        not start stops every task of it alike.
        """
        for index, task in enumerate(self._waiting):
            if task.seq >= below:
                return None
            if may_start(task.site):
                return self._waiting.pop(index)
        return None

    def soonest(
        self, ready_at: Callable[[str], float], busy: set[str], below: int
    ) -> float | None:
        """When the first of the waiting sites that is not busy may start."""
        times = [
            ready_at(task.site)
            for task in self._waiting
            if task.seq < below and task.site not in busy
        ]
        return min(times, default=None)


class Schedule(Generic[_Result]):
    """Runs tasks through ``visit`` politely, and hands the results back in order.

    ``commit`` sees each result in order before it is handed back, and may add
    tasks: a crawl admits the page's links there. ``deadline`` is a clock time
    after which no task is started; results after the first task it left
    untaken are dropped, so what comes back is always a prefix of the order.
    ``out_of_time`` says whether that happened.
    """

    def __init__(
        self,
        visit: Callable[[Task], _Result],
        politeness: Politeness,
        concurrency: int = CONCURRENCY,
        deadline: float | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("A schedule needs room for at least one request.")
        self.visit = visit
        self.politeness = politeness
        self.concurrency = concurrency
        self.deadline = deadline
        self.out_of_time = False

    def run(
        self, queue: Queue, commit: Callable[[Task, _Result], None]
    ) -> Iterator[_Result]:
        clock = self.politeness.clock
        pool = (
            ThreadPoolExecutor(self.concurrency, thread_name_prefix="sluicer-crawl")
            if self.concurrency > 1
            else None
        )
        running: dict[Future[_Result], Task] = {}
        busy: set[str] = set()
        finished: dict[int, tuple[Task, _Result]] = {}
        head = queue.head()
        try:
            while True:
                if self.deadline is not None and clock() >= self.deadline:
                    self.out_of_time = True
                below = head + LOOKAHEAD
                while not self.out_of_time and len(running) < self.concurrency:
                    task = queue.take(partial(self._may_start, busy, clock()), below)
                    if task is None:
                        break
                    busy.add(task.site)
                    running[self._start(pool, task)] = task
                if not running:
                    if self.out_of_time or not queue:
                        return
                    self._rest(queue, busy, below)
                    continue
                # Full, or out of time, nothing can start until something ends;
                # a timeout then would only spin.
                full = self.out_of_time or len(running) >= self.concurrency
                soonest = (
                    None
                    if full
                    else queue.soonest(self.politeness.ready_at, busy, below)
                )
                timeout = None if soonest is None else max(0.0, soonest - clock())
                done, _ = wait(running, timeout=timeout, return_when=FIRST_COMPLETED)
                for future in done:
                    task = running.pop(future)
                    busy.discard(task.site)
                    finished[task.seq] = (task, future.result())
                while head in finished:
                    task, result = finished.pop(head)
                    head += 1
                    commit(task, result)
                    yield result
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)

    def _may_start(self, busy: set[str], now: float, site: str) -> bool:
        return site not in busy and self.politeness.ready_at(site) <= now

    def _start(self, pool: ThreadPoolExecutor | None, task: Task) -> Future[_Result]:
        if pool is not None:
            return pool.submit(self.visit, task)
        # One at a time, in this thread: the order is then the clock's too,
        # which is what lets a test pace a crawl with a fake one.
        future: Future[_Result] = Future()
        try:
            future.set_result(self.visit(task))
        except Exception as failure:  # noqa: BLE001 -- re-raised by result()
            future.set_exception(failure)
        return future

    def _rest(self, queue: Queue, busy: set[str], below: int) -> None:
        """Nothing is running and nothing may start: sleep until something may."""
        clock = self.politeness.clock
        soonest = queue.soonest(self.politeness.ready_at, busy, below)
        if soonest is None:
            return
        if self.deadline is not None:
            soonest = min(soonest, self.deadline)
        rest = soonest - clock()
        if rest > 0:
            self.politeness.sleep(rest)
