"""Which address next, when, and in what order the answers are handed back.

Politeness is what this module is for. A site is never asked twice at once, and
never again sooner than its delay after its last request ended: at least
``DEFAULT_DELAY_SECONDS``, longer when its robots.txt asks. Every request
counts -- its robots.txt, its sitemaps, its pages. Different sites are asked
side by side, up to a bound.

Order is the other promise. Tasks are numbered as they are added, and the pages
come back in that order whatever order they finished in, so the same crawl of
the same site always writes the same file.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from functools import cached_property, partial
from typing import Generic, TypeVar

from sluicer.crawl.urls import site_of
from sluicer.fetch.identity import robots_delay

DEFAULT_DELAY_SECONDS = 1.0
"""The least time between two requests to one site, counted from the end of the
first, so a slow answer is never a reason to ask again sooner. A second is the
figure polite crawlers have long kept to; a site whose robots.txt asks for more
gets more."""

MAX_DELAY_SECONDS = 60.0
"""The longest wait between two requests to one site a crawl accepts. A site
asking for more is not crawled at all rather than crawled for a week: its pages
say ``crawl_delay_too_long``, with the delay it asked for."""

CONCURRENCY = 4
"""How many sites are asked at the same moment, never more than once each."""

LOOKAHEAD = 256
"""How far past the first unfinished task a free site may be served from.

Pages come back in order, so one waiting behind a slow site is held in memory;
this bounds how many are.
"""

_Result = TypeVar("_Result")


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
    """

    def __init__(
        self,
        read: Callable[[str], str | None],
        min_delay: float = DEFAULT_DELAY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_delay = min_delay
        self.clock = clock
        self.sleep = sleep
        self._read = read
        self._ended: dict[str, float] = {}
        self._delays: dict[str, float] = {}
        self._lock = threading.Lock()

    def reader(self, url: str) -> str | None:
        """Read the robots.txt at ``url``, as a request to its site."""
        try:
            return self._read(url)
        finally:
            self.ended(url)

    def delay_for(self, url: str) -> float:
        """The seconds ``url``'s site wants between requests: ours, or its
        robots.txt's if longer. Reading that robots.txt may be a request.

        Raises:
            RobotsUnreachable: the robots.txt could not be read.
        """
        delay = max(self.min_delay, robots_delay(url, self.reader, now=self.clock))
        with self._lock:
            self._delays[site_of(url)] = delay
        return delay

    def ready_at(self, site: str) -> float:
        """When ``site`` may next be asked, as far as is known without asking."""
        with self._lock:
            ended = self._ended.get(site)
            delay = self._delays.get(site, self.min_delay)
        return -math.inf if ended is None else ended + delay

    def wait(self, url: str, delay: float) -> None:
        """Sleep until ``url``'s site has rested ``delay`` seconds."""
        with self._lock:
            ended = self._ended.get(site_of(url))
        if ended is not None:
            rest = ended + delay - self.clock()
            if rest > 0:
                self.sleep(rest)

    def ended(self, url: str) -> None:
        """Note that a request to ``url``'s site has just ended."""
        with self._lock:
            self._ended[site_of(url)] = self.clock()


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
                soonest = (
                    None
                    if self.out_of_time
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
