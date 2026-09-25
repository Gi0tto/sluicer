"""One site, one request at a time, for the whole process.

Politeness is kept per site, not per caller: two crawls of one site, a crawl
and a map, or an agent calling ``extract_declared`` four times at once all ask
the same machines. Measured before this gate, two concurrent crawls of one
site sent pairs of requests 0.000 s apart, and six parallel single-page
fetches arrived within 3 ms; each caller paced only itself.

A site is held by one thread at a time (``hold``), and the moment its last
request ended is kept for the process (``ENDED``). Whoever holds it sleeps,
holding it, until the site's delay has passed, makes its request, and notes
when it ended; only then may anyone else ask. A crawl takes the site for each
request it makes, and waits its own delay, a robots.txt's ``Crawl-delay``
included. A single fetch -- the command line, the MCP server, the HTTP API --
takes it once for the whole fetch (``turn``): its robots.txt, the page and any
climb follow each other, as a fetch of one page always has, and the next
caller waits ``DEFAULT_DELAY_SECONDS`` after it ends.

The locks are threading locks, re-entrant, because every caller that fetches
runs on a thread: the crawl's pool, the MCP SDK's worker for a sync tool, the
HTTP API's own pool. Nothing here runs on an event loop. A turn never takes a
second site's lock inside the first's, so two threads cannot each hold what
the other waits for.
"""

from __future__ import annotations

import math
import threading
import time
import weakref
from collections import OrderedDict
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from typing import TypeVar

from sluicer.fetch.identity import ROBOTS_CACHE_HOSTS

DEFAULT_DELAY_SECONDS = 1.0
"""The least time between two requests to one site, counted from the end of the
first, so a slow answer is never a reason to ask again sooner. A second is the
figure polite crawlers have long kept to; a site whose robots.txt asks for more
gets more from a crawl."""


class _Recent(OrderedDict[str, float]):
    """A mapping that forgets its least recently written site past ``limit``."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def __setitem__(self, key: str, value: float) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


ENDED = _Recent(ROBOTS_CACHE_HOSTS)
"""When each site's last request ended, for the whole process, on the
monotonic clock; bounded like the robots.txt answers, and for the same reason."""

LOCK = threading.Lock()
"""Guards ``ENDED``, the site locks' registry, and a crawl's own records of its
sites. Held only for a read or a write, never while sleeping or fetching."""


class _Site:
    """A site's lock, alive while anyone holds or waits for it."""

    __slots__ = ("__weakref__", "lock")

    def __init__(self) -> None:
        self.lock = threading.RLock()


def site_key(url: str) -> str:
    """The site ``url`` is paced as: ``sluicer.crawl.urls.site_of``.

    Imported when asked, not with this module: the crawl package imports the
    fetch package, and the ladder imports this one.
    """
    from sluicer.crawl.urls import site_of

    return site_of(url) or url


class Gate:
    """Who may ask a site now, and when it was last asked.

    ``min_delay`` is the rest a ``turn`` waits by default; ``clock`` and
    ``sleep`` are the time, injected by tests; ``ended`` is the process's
    record by default.
    """

    def __init__(
        self,
        min_delay: float = DEFAULT_DELAY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        ended: MutableMapping[str, float] | None = None,
    ) -> None:
        self.min_delay = min_delay
        self.clock = clock
        self.sleep = sleep
        self.ended = ENDED if ended is None else ended
        self._sites: weakref.WeakValueDictionary[str, _Site] = (
            weakref.WeakValueDictionary()
        )

    @contextmanager
    def hold(self, url: str) -> Iterator[None]:
        """Have ``url``'s site to this thread alone until the block ends.

        Re-entrant: a thread that holds a site may take it again, as a cache
        that revalidates and then climbs the whole ladder does.
        """
        key = site_key(url)
        with LOCK:
            site = self._sites.get(key)
            if site is None:
                site = self._sites[key] = _Site()
        with site.lock:
            yield

    def last_ended(self, url: str) -> float | None:
        """When the last request to ``url``'s site ended, if one is known."""
        with LOCK:
            return self.ended.get(site_key(url))

    def mark_ended(self, url: str, now: float) -> None:
        """Note that a request to ``url``'s site ended at ``now``."""
        with LOCK:
            self.ended[site_key(url)] = now

    @contextmanager
    def turn(
        self, url: str, delay: float | None = None
    ) -> Iterator[Callable[[], None]]:
        """Hold ``url``'s site for the block, and hand it ``ready``, to call
        before each request it makes.

        The first ``ready`` sleeps until ``delay`` (``min_delay`` by default)
        has passed since the site's last request ended; the others return at
        once. When the block ends, however it ends, the site's last request is
        noted as ended then, if one was made: a fetch whose robots.txt answer
        was known, and which that answer refused, asked nothing and waits for
        nothing.
        """
        rest = self.min_delay if delay is None else delay
        asked = False

        def ready() -> None:
            nonlocal asked
            if asked:
                return
            asked = True
            ended = self.last_ended(url)
            wait = (-math.inf if ended is None else ended + rest) - self.clock()
            if wait > 0:
                self.sleep(wait)

        with self.hold(url):
            try:
                yield ready
            finally:
                if asked:
                    self.mark_ended(url, self.clock())


GATE = Gate()
"""The process's gate: every fetch Sluicer makes of the real web goes through it."""

_Answer = TypeVar("_Answer")


def after(
    ready: Callable[[], None], ask: Callable[[str], _Answer]
) -> Callable[[str], _Answer]:
    """``ask``, each call made once ``ready`` says the site's turn has come."""

    def asked(url: str) -> _Answer:
        ready()
        return ask(url)

    return asked


@contextmanager
def ungated() -> Iterator[Callable[[], None]]:
    """A turn that waits for nothing, for a caller whose web is injected."""
    yield lambda: None
