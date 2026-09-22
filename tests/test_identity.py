"""Tests for sluicer.fetch.identity: our name, and the robots.txt we read.

The fake ``protego`` module and the per-test robots-cache reset both live in
``tests/conftest.py`` now, autouse, since ``tests/test_fetch_ladder.py`` needs
the same real Allow/Disallow behaviour to test how the ladder consults
robots.txt. See that file's docstring for what the fake stands in for and why
the cache needs resetting.

Three of the tests below rely on the default per-host cache and all target
``example.com``, which would let one test's cached answer leak into the next
if the cache were not reset between tests -- the autouse fixture in
``conftest.py`` is what keeps each one starting fresh.
"""

import pytest

from sluicer.fetch.identity import USER_AGENT, robots_allows, robots_url_for

ALLOW_ALL = "User-agent: *\nAllow: /\n"
REFUSE_US = "User-agent: Sluicer\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n"


def test_the_user_agent_says_who_we_are_and_where_to_find_us():
    assert "Sluicer" in USER_AGENT
    assert "https://github.com/" in USER_AGENT


def test_robots_lives_at_the_root_of_the_host():
    assert robots_url_for("https://example.com/deep/page?x=1") == "https://example.com/robots.txt"


def test_a_site_with_no_robots_allows_us():
    assert robots_allows("https://example.com/p", read=lambda url: None) is True


def test_a_site_that_refuses_us_is_obeyed():
    assert robots_allows("https://example.com/private/p", read=lambda url: REFUSE_US) is False


def test_a_path_that_same_site_allows_is_allowed():
    assert robots_allows("https://example.com/public", read=lambda url: REFUSE_US) is True


def test_the_answer_is_cached_per_host():
    calls = []

    def read(url):
        calls.append(url)
        return ALLOW_ALL

    cache: dict = {}
    robots_allows("https://example.com/a", read=read, cache=cache)
    robots_allows("https://example.com/b", read=read, cache=cache)
    robots_allows("https://other.com/a", read=read, cache=cache)

    assert calls == ["https://example.com/robots.txt", "https://other.com/robots.txt"]


def test_an_answer_older_than_a_day_is_asked_again():
    """A site that adds a Disallow must be noticed, not pinned for the process.

    The cache had no TTL, no bound and no invalidation, so a long-running MCP
    server that read a site's robots.txt once obeyed that copy for its whole
    lifetime. That defeats the stated purpose: a site owner should be able to
    turn us away with one line, and one line they add tomorrow counts.

    The clock is injected rather than slept through: the point is a day
    passing, and the test has a day to spare only if it never waits one.
    """
    answers = ["User-agent: *\nAllow: /\n", "User-agent: *\nDisallow: /\n"]
    calls: list[str] = []

    def read(url):
        calls.append(url)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    clock = [0.0]
    cache: dict = {}

    def now():
        return clock[0]

    assert robots_allows("https://example.com/p", read=read, cache=cache, now=now) is True

    clock[0] = 23 * 60 * 60
    assert robots_allows("https://example.com/p", read=read, cache=cache, now=now) is True
    assert calls == ["https://example.com/robots.txt"], "re-read before the day was out"

    clock[0] = 24 * 60 * 60 + 1
    assert robots_allows("https://example.com/p", read=read, cache=cache, now=now) is False
    assert len(calls) == 2, "the expired entry was not read again"


def test_http_and_https_on_one_host_are_two_different_robots_files():
    """They are two resources, and a site is free to publish different rules.

    The key was the netloc alone, so whichever scheme was asked for first
    answered for both -- an http:// page could be refused on the strength of
    an https://robots.txt that was never fetched, or allowed against one that
    would have refused it. ``robots_url_for`` has always kept the scheme; only
    the cache threw it away.
    """
    calls: list[str] = []

    def read(url):
        calls.append(url)
        return "User-agent: *\nDisallow: /\n" if url.startswith("http://") else ALLOW_ALL

    cache: dict = {}

    assert robots_allows("http://example.com/p", read=read, cache=cache) is False
    assert robots_allows("https://example.com/p", read=read, cache=cache) is True
    assert calls == ["http://example.com/robots.txt", "https://example.com/robots.txt"]


def test_a_missing_protego_says_the_fetch_extra_is_what_installs_it(absent):
    """The label has to be the one the entry points catch, not the base class.

    ``sluicer.extras`` states the rule this breaks: an absent extra is a
    sentence, never a traceback. The call site used the default
    ``MissingExtra``, and ``cli.py`` catches ``FetchExtraMissing`` by name, so
    a bare ``MissingExtra`` sailed straight past that handler. protego ships
    behind the fetch extra, so the fetch extra's own exception is what a
    missing protego has to raise.
    """
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    absent("protego")

    with pytest.raises(FetchExtraMissing) as raised:
        robots_allows("https://example.com/private/p", read=lambda url: REFUSE_US)

    assert raised.value.extra == "fetch"
    assert "uv pip install 'sluicer[fetch]'" in str(raised.value)
