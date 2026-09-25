"""One site, one request at a time, for the whole process, on the real clock.

The crawl tests pace one crawl with a fake clock. What was broken was between
callers: two crawls of one site, or six single fetches at once -- what parallel
MCP ``extract_declared`` calls are -- each paced only itself, and the site was
asked 0-3 ms apart. So these run callers on real threads, with delays of a few
hundredths of a second, and read every request's start and end.
"""

from __future__ import annotations

import threading
import time
from itertools import pairwise

import pytest

from sluicer.crawl import crawl
from sluicer.crawl.web import Web
from sluicer.fetch import fetch
from sluicer.fetch.gate import GATE, Gate
from sluicer.fetch.http_rung import Response
from sluicer.fetch.result import Fetched

ROOT = "https://example.com"
DELAY = 0.05
# A thread's wake-up is late by a hair, never early; a request's own end is
# noted a hair after the rung returned.
TOLERANCE = 0.005


class Site:
    """Pages that take ``cost`` real seconds each, every request written down."""

    def __init__(self, cost: float = 0.01) -> None:
        self.cost = cost
        self.lock = threading.Lock()
        self.requests: list[tuple[str, float, float]] = []

    def _asked(self, url: str) -> None:
        started = time.monotonic()
        time.sleep(self.cost)
        with self.lock:
            self.requests.append((url, started, time.monotonic()))

    def rung(self, url: str) -> Fetched:
        self._asked(url)
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="", status=404, rung="http")
        n = int(url.rsplit("/", 1)[1] or 0)
        links = "".join(f'<a href="/{n * 2 + i}">x</a>' for i in (1, 2))
        html = (
            '<html><head><script type="application/ld+json">'
            f'{{"@type":"Thing","name":"p{n}"}}</script></head>'
            f"<body>{links}{'text ' * 60}</body></html>"
        )
        return Fetched(url=url, html=html, status=200, rung="http")

    def read(self, url: str) -> str | None:
        self._asked(url)
        return None

    def get(self, url: str) -> Response:
        self._asked(url)
        return Response(url, 404, "text/plain", b"")

    def web(self) -> Web:
        return Web(rungs=[("http", self.rung)], read=self.read, get=self.get)

    def gaps(self) -> list[float]:
        """Seconds from each request's end to the next one's start."""
        ordered = sorted(self.requests, key=lambda request: request[1])
        return [nxt[1] - prev[2] for prev, nxt in pairwise(ordered)]


def _together(*calls) -> None:
    """Run ``calls`` on threads of their own, all at once; re-raise a failure."""
    failures: list[BaseException] = []

    def run(call) -> None:
        try:
            call()
        except BaseException as failure:  # noqa: BLE001 -- raised again below
            failures.append(failure)

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        raise failures[0]


def test_two_crawls_of_one_site_at_once_ask_it_one_request_at_a_time():
    site = Site()

    def one() -> None:
        list(crawl(f"{ROOT}/0", max_pages=4, min_delay=DELAY, web=site.web()))

    _together(one, one)

    assert len(site.requests) >= 8
    assert min(site.gaps()) >= DELAY - TOLERANCE, site.gaps()


@pytest.fixture
def default_ladder(monkeypatch):
    """``fetch`` with its default rungs, which are these, paced by the gate a
    few hundredths of a second apart."""
    site = Site()
    monkeypatch.setattr(
        "sluicer.fetch.rungs.default_rungs",
        lambda *args, **kwargs: [("http", site.rung)],
    )
    monkeypatch.setattr(GATE, "min_delay", DELAY)
    return site


def test_single_fetches_at_once_are_asked_one_after_another(default_ladder):
    """What six parallel extract_declared calls do; measured before, their
    requests arrived within 3 ms of each other."""
    _together(*(lambda n=n: fetch(f"{ROOT}/{n}") for n in range(6)))

    asked = [url for url, _, _ in default_ladder.requests]
    assert sorted(asked).count(f"{ROOT}/robots.txt") == 1, "read once, then known"
    assert len(asked) == 7
    gaps = default_ladder.gaps()
    assert all(gap >= -TOLERANCE for gap in gaps), "two were never in flight at once"
    assert sorted(gaps)[1] >= DELAY - TOLERANCE, gaps


def test_a_single_fetch_asks_its_robots_txt_and_its_page_as_one_turn(
    default_ladder,
):
    fetch(f"{ROOT}/1")

    (robots, page) = default_ladder.requests
    assert robots[0] == f"{ROOT}/robots.txt"
    assert page[1] - robots[2] < DELAY, "one fetch is one visit"


def test_a_crawl_and_single_fetches_share_the_site(default_ladder):
    site = default_ladder

    def crawling() -> None:
        list(crawl(f"{ROOT}/0", max_pages=3, min_delay=DELAY, web=site.web()))

    _together(crawling, *(lambda n=n: fetch(f"{ROOT}/{10 + n}") for n in range(3)))

    gaps = site.gaps()
    assert all(gap >= -TOLERANCE for gap in gaps), gaps
    assert len([gap for gap in gaps if gap < DELAY - TOLERANCE]) <= 1, (
        "only a fetch's own robots.txt and page follow each other"
    )


def test_a_fetch_refused_by_a_known_robots_txt_waits_for_nothing(default_ladder):
    from sluicer.fetch import RobotsRefused
    from sluicer.fetch.identity import _CACHE

    _CACHE[f"{ROOT}"] = (time.monotonic(), "User-agent: *\nDisallow: /\n")
    GATE.mark_ended(f"{ROOT}/", time.monotonic())
    started = time.monotonic()

    with pytest.raises(RobotsRefused):
        fetch(f"{ROOT}/1")

    assert time.monotonic() - started < DELAY
    assert default_ladder.requests == []


def test_a_site_is_held_by_one_thread_and_again_by_the_same_one():
    gate = Gate(min_delay=0.0)
    inside = []

    def holder() -> None:
        with gate.hold(f"{ROOT}/a"), gate.hold(f"{ROOT}/b"):
            inside.append(("in", time.monotonic()))
            time.sleep(0.05)
            inside.append(("out", time.monotonic()))

    _together(holder, holder)

    assert [what for what, _ in inside] == ["in", "out", "in", "out"]


def test_www_and_the_bare_host_are_one_site_to_the_gate():
    gate = Gate(min_delay=10.0)
    gate.mark_ended("https://www.example.com/", time.monotonic())
    slept = []
    gate.sleep = slept.append

    with gate.turn("http://example.com/p") as ready:
        ready()

    assert slept and 9 < slept[0] <= 10
