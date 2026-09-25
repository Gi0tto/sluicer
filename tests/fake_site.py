"""A web in a dict, and a clock that only moves when asked, for crawl tests.

``FakeWeb`` answers the three ways a crawl asks -- the ladder's rung, the robots
reader built from it the way production builds it, and the plain GET sitemaps
use -- and records every request with the fake time it started and ended. Each
request costs ``cost`` fake seconds, so "the delay is counted from the end of
the last request" is something a test can see. Nothing here opens a socket.

A page is ``(status, body, headers)``, or a bare string for a 200 page. A
``Location`` header makes a redirect, followed the way the HTTP rung follows
one, hop by hop. An exception is raised as a failed request would be, and a
list is the answers of an address in turn, its last one kept for every later
request: a page that fails once and then answers.
"""

from __future__ import annotations

import time
from itertools import pairwise
from urllib.parse import urljoin

from sluicer.crawl.web import Web
from sluicer.fetch import RedirectRefused, robots_reader_from
from sluicer.fetch.http_rung import Response
from sluicer.fetch.result import Fetched


class Clock:
    """Fake monotonic time: ``sleep`` moves it, and so does every request.

    It starts at the real monotonic time, because the robots cache the ladder
    keeps is on that clock: a fake that started at zero would find every
    answer a day stale when the ladder looked, and read robots.txt again.
    """

    def __init__(self, now: float | None = None) -> None:
        self.now = time.monotonic() if now is None else now
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0, seconds
        self.slept.append(seconds)
        self.now += seconds


class FakeWeb:
    def __init__(self, pages, clock: Clock | None = None, cost: float = 0.25):
        self.pages = dict(pages)
        self.clock = clock or Clock()
        self.cost = cost
        self.requests: list[tuple[str, float, float]] = []
        # The headers each address last answered with, for the page rung.
        self.headers: dict[str, dict[str, str]] = {}

    def _answer(self, url: str):
        started = self.clock.now
        self.clock.now += self.cost
        self.requests.append((url, started, self.clock.now))
        answer = self.pages.get(url, (404, "<html><body>Not found</body></html>", {}))
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, str):
            answer = (200, answer, {})
        status, body, headers = answer
        if isinstance(body, str):
            body = body.encode("utf-8")
        return status, body, {k.lower(): v for k, v in headers.items()}

    def get(self, url: str, redirects=None) -> Response:
        """Follow redirects hop by hop, asking ``redirects`` before each one, as
        the real transport does."""
        current = url
        for _ in range(11):
            status, body, headers = self._answer(current)
            if status in (301, 302, 303, 307, 308) and "location" in headers:
                target = urljoin(current, headers["location"])
                refused = redirects(current, target) if redirects else None
                if refused is not None:
                    raise RedirectRefused(current, target, refused)
                current = target
                continue
            self.headers[current] = headers
            return Response(current, status, headers.get("content-type", ""), body)
        raise RuntimeError(f"{url} redirected too often")

    def rung(self, url: str, redirects=None) -> Fetched:
        response = self.get(url, redirects)
        html = response.body.decode("utf-8", errors="replace")
        if not html:
            raise ValueError(f"no HTML for {url!r}")
        return Fetched(
            url=response.url,
            html=html,
            status=response.status,
            rung="http",
            headers=self.headers.get(response.url, {}),
        )

    def web(self, redirects=None) -> Web:
        """The three ways in; ``redirects`` goes to the page rung only, as
        ``default_web`` sends it."""
        return Web(
            rungs=[("http", lambda url: self.rung(url, redirects))],
            read=robots_reader_from(self.rung),
            get=self.get,
        )

    def as_default(self, monkeypatch) -> None:
        """Stand in for ``default_web``, so a crawl wires its own redirect rule
        into this web exactly as it does into the real one."""

        def default_web(
            allow_private=True,
            resolve=None,
            max_bytes=0,
            redirects=None,
            headers=None,
            cookies=None,
        ):
            return self.web(redirects)

        monkeypatch.setattr("sluicer.crawl.pages.default_web", default_web)

    def asked(self) -> list[str]:
        return [url for url, _, _ in self.requests]

    def gaps(self, site: str) -> list[float]:
        """Seconds between the end of each request to ``site`` and the next."""
        times = [(start, end) for url, start, end in self.requests if site in url]
        return [round(nxt[0] - prev[1], 6) for prev, nxt in pairwise(times)]


def page(title: str, *links: str, extra: str = "") -> str:
    """A page declaring a product named ``title``, linking to ``links``."""
    anchors = "".join(f'<a href="{link}">{link}</a>' for link in links)
    return (
        "<html><head>"
        f"<title>{title}</title>"
        '<script type="application/ld+json">'
        f'{{"@type":"Product","name":"{title}"}}</script>'
        f"{extra}</head><body>{anchors}" + ("Real content. " * 20) + "</body></html>"
    )
