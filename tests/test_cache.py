"""A cache that asks the site whether a page changed, and never guesses."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from sluicer.cli import main
from sluicer.fetch import RobotsRefused
from sluicer.fetch.cache import Cache, fetch_cached
from sluicer.fetch.http_rung import Response
from sluicer.fetch.result import CacheHit, Fetched

URL = "https://shop.example/p"
PAGE = '<html><head><title>Pads</title></head><body><p class="x">text</p></body></html>'
VALIDATED = {
    "content-type": "text/html; charset=utf-8",
    "etag": '"v1"',
    "last-modified": "Wed, 08 Feb 2023 21:02:32 GMT",
    "set-cookie": "session=secret",
}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class Site:
    """The ladder's one rung, and the transport a revalidation sends through."""

    def __init__(
        self, html=PAGE, headers=VALIDATED, status=200, answer=304, rung="http"
    ):
        self.html, self.headers, self.status = html, headers, status
        self.answer, self.rung_name = answer, rung
        self.pages: list[str] = []
        self.asked: list[tuple[str, dict[str, str]]] = []

    def rung(self, url: str) -> Fetched:
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="", status=404, rung="http")
        self.pages.append(url)
        return Fetched(
            url=url,
            html=self.html,
            status=self.status,
            rung=self.rung_name,
            headers=dict(self.headers),
        )

    def transport(self, url: str, send):
        self.asked.append((url, dict(send)))
        if self.answer == 304:
            return Response(url, 304, "", b"")
        return Response(
            url, self.answer, "text/html", self.html.encode(), {"etag": '"v2"'}
        )

    def fetch(self, cache: Cache, **options):
        return fetch_cached(
            URL,
            cache,
            rungs=[(self.rung_name, self.rung)],
            transport=self.transport,
            **options,
        )


def test_a_page_is_kept_and_its_site_asked_whether_it_changed(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)

    first = site.fetch(cache)
    clock.now += 600
    second = site.fetch(cache)

    assert first.cached is None and site.pages == [URL]
    assert site.asked == [
        (
            URL,
            {
                "If-None-Match": '"v1"',
                "If-Modified-Since": "Wed, 08 Feb 2023 21:02:32 GMT",
            },
        )
    ]
    assert second.cached == CacheHit(0.0, revalidated=True)
    assert second.html == PAGE and second.status == 200
    assert second.headers["etag"] == '"v1"'
    assert "set-cookie" not in second.headers, "a page's cookies are never kept"
    clock.now += 5
    third = fetch_cached(URL, Cache(tmp_path, max_age=10, clock=clock), rungs=[])
    assert third.cached == CacheHit(5.0, revalidated=False), "vouched for at the 304"


def test_a_page_younger_than_max_age_is_given_back_without_asking(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, max_age=60, clock=clock)
    site.fetch(cache)
    clock.now += 59.5
    kept = site.fetch(cache)
    assert kept.cached == CacheHit(59.5, revalidated=False)
    assert site.asked == [] and site.pages == [URL]
    clock.now += 1
    site.fetch(cache)
    assert len(site.asked) == 1, "older than max_age, the site is asked"


def test_a_page_that_changed_is_the_answer_and_is_kept(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)
    site.fetch(cache)
    site.answer, site.html = 200, PAGE.replace("Pads", "Discs")
    changed = site.fetch(cache)
    assert changed.cached is None and "Discs" in changed.html
    assert site.pages == [URL], "the answer to the conditional request is the page"
    site.answer = 304
    again = site.fetch(cache)
    assert "Discs" in again.html
    assert site.asked[-1][1]["If-None-Match"] == '"v2"'


def test_a_page_that_changed_into_a_challenge_goes_up_the_ladder(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)
    site.fetch(cache)
    site.answer = 403
    site.fetch(cache)
    assert site.pages == [URL, URL], "the whole ladder was asked again"


def test_only_a_page_the_http_rung_brought_with_a_validator_is_revalidated(tmp_path):
    for site in (
        Site(rung="browser"),
        Site(headers={"content-type": "text/html"}),
    ):
        cache = Cache(tmp_path / site.rung_name / str(len(site.headers)), clock=Clock())
        site.fetch(cache)
        site.fetch(cache)
        assert site.asked == [] and len(site.pages) == 2


def test_an_error_page_is_never_kept(tmp_path):
    site = Site(status=404)
    cache = Cache(tmp_path, clock=Clock())
    site.fetch(cache)
    site.fetch(cache)
    assert site.asked == [] and len(site.pages) == 2
    assert list(tmp_path.iterdir()) == []


CHALLENGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>Checking your browser</body></html>"
)


def test_a_challenge_served_with_200_is_never_kept(tmp_path):
    """Measured before: every rung got "Just a moment..." with a 200, the first
    call kept it, and the second gave it back as the page, a CacheHit that
    asked nobody."""
    import contextlib

    from sluicer.fetch import FetchFailed

    http = Site(html=CHALLENGE)
    browser = Site(html=CHALLENGE, rung="browser")
    cache = Cache(tmp_path, max_age=3600, clock=Clock())

    for _ in range(2):
        with contextlib.suppress(FetchFailed):
            fetch_cached(
                URL,
                cache,
                rungs=[("http", http.rung), ("browser", browser.rung)],
                transport=http.transport,
            )

    assert cache.read(URL) is None
    assert list(tmp_path.iterdir()) == []
    assert len(browser.pages) == 2, "the site was asked again, not the cache"


def test_a_revalidation_answered_402_is_the_answer_not_a_reason_to_ask_again(
    tmp_path,
):
    from sluicer.fetch import PaymentRequired

    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)
    site.fetch(cache)
    site.answer = 402

    with pytest.raises(PaymentRequired):
        site.fetch(cache)

    assert site.pages == [URL], "the whole ladder was not asked again"


def test_a_page_as_bytes_is_kept_as_text(tmp_path):
    cache = Cache(tmp_path, clock=Clock())
    cache.write(URL, Fetched(url=URL, html=PAGE.encode(), status=200, rung="http"))
    assert cache.read(URL)["html"] == PAGE


def test_an_entry_that_is_broken_or_not_this_pages_is_no_entry(tmp_path):
    cache = Cache(tmp_path, clock=Clock())
    Site().fetch(cache)
    [path] = list(tmp_path.glob("*.json"))
    entry = json.loads(path.read_text(encoding="utf-8"))
    for broken in (
        "not json",
        json.dumps([1]),
        json.dumps({**entry, "format": 0}),
        json.dumps({**entry, "url": "https://other.example/"}),
        json.dumps({**entry, "html": None}),
    ):
        path.write_text(broken, encoding="utf-8")
        assert cache.read(URL) is None


def test_a_revalidation_asks_robots_txt_first(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)
    site.fetch(cache)

    def refusing(url):
        if url.endswith("/robots.txt"):
            return Fetched(
                url=url, html="User-agent: *\nDisallow: /", status=200, rung="http"
            )
        return site.rung(url)

    from sluicer.fetch.identity import _CACHE

    _CACHE.clear()
    with pytest.raises(RobotsRefused):
        fetch_cached(URL, cache, rungs=[("http", refusing)], transport=site.transport)
    assert site.asked == []
    _CACHE.clear()


def test_max_age_is_seconds_and_never_negative(tmp_path):
    with pytest.raises(ValueError, match="not negative"):
        Cache(tmp_path, max_age=-1)


# -- the command line --------------------------------------------------------------


def test_the_command_line_reads_through_the_cache_and_says_so(monkeypatch, tmp_path):
    seen = {}

    def cached(url, cache, **options):
        seen.update(directory=cache.directory, max_age=cache.max_age, **options)
        return Fetched(
            url=url,
            html=PAGE,
            status=200,
            rung="http",
            cached=CacheHit(12.0, revalidated=False),
        )

    monkeypatch.setattr("sluicer.fetch.cache.fetch_cached", cached)
    result = CliRunner().invoke(
        main, ["extract", URL, "--cache", str(tmp_path), "--max-age", "60"]
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["fetch"]["cached"] == {
        "age": 12.0,
        "revalidated": False,
    }
    assert seen["directory"] == tmp_path and seen["max_age"] == 60.0
    inspected = CliRunner().invoke(main, ["inspect", URL, "--cache", str(tmp_path)])
    assert (
        "cached    kept 12 s ago, within --max-age: the site was not asked"
        in inspected.stdout
    )


def test_max_age_needs_a_cache_and_a_cache_is_not_for_captures(tmp_path):
    alone = CliRunner().invoke(main, ["extract", URL, "--max-age", "5"])
    assert alone.exit_code == 2 and "it needs --cache" in alone.stderr
    both = CliRunner().invoke(
        main, ["extract", URL, "--cache", str(tmp_path), "--at", "2020"]
    )
    assert both.exit_code == 2 and "never changes" in both.stderr


def test_a_question_that_cannot_be_put_falls_back_to_the_whole_ladder(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)
    site.fetch(cache)

    def empty(url, send):
        return Response(url, 200, "text/html", b"")

    again = fetch_cached(URL, cache, rungs=[("http", site.rung)], transport=empty)
    assert again.cached is None and site.pages == [URL, URL]


def test_the_http_transport_sends_the_validators_by_default(tmp_path, monkeypatch):
    clock = Clock()
    cache = Cache(tmp_path, clock=clock)
    cache.write(
        URL,
        Fetched(url=URL, html=PAGE, status=200, rung="http", headers=dict(VALIDATED)),
    )
    sent = {}

    def http_responses(allow_private, resolve, max_bytes, send=None):
        sent.update(allow_private=allow_private, send=dict(send or {}))
        return lambda url: Response(url, 304, "", b"")

    def http_rung(allow_private, resolve, max_bytes):
        return lambda url: Fetched(url=url, html="", status=404, rung="http")

    monkeypatch.setattr("sluicer.fetch.http_rung.http_responses", http_responses)
    monkeypatch.setattr("sluicer.fetch.http_rung.http_rung", http_rung)
    clock.now += 60
    kept = fetch_cached(
        URL, cache, allow_private=False, resolve=lambda h: ["93.184.216.34"]
    )
    assert kept.cached == CacheHit(0.0, revalidated=True)
    assert sent == {
        "allow_private": False,
        "send": {
            "If-None-Match": '"v1"',
            "If-Modified-Since": "Wed, 08 Feb 2023 21:02:32 GMT",
        },
    }


def test_a_page_fetched_with_a_login_is_kept_for_that_login_alone(tmp_path):
    """A page read behind a cookie is that cookie's page: given back to a
    request without it, it would hand one account's page to anyone."""
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock, max_age=3600)

    site.fetch(cache, cookies={"session": "abc"})
    site.fetch(cache)
    kept = site.fetch(cache, cookies={"session": "abc"})

    assert site.pages == [URL, URL]
    assert kept.cached is not None


def test_a_revalidation_sends_the_callers_headers_beside_the_validators(tmp_path):
    clock, site = Clock(), Site()
    cache = Cache(tmp_path, clock=clock)

    site.fetch(cache, headers={"Authorization": "Bearer t"})
    clock.now += 60
    site.fetch(cache, headers={"Authorization": "Bearer t"})

    assert site.asked == [
        (
            URL,
            {
                "Authorization": "Bearer t",
                "If-None-Match": '"v1"',
                "If-Modified-Since": "Wed, 08 Feb 2023 21:02:32 GMT",
            },
        )
    ]


def test_the_cache_refuses_a_user_agent_like_the_fetch_does(tmp_path):
    with pytest.raises(ValueError, match="User-Agent"):
        Site().fetch(Cache(tmp_path), headers={"User-Agent": "Mozilla/5.0"})
