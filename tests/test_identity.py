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
    assert (
        robots_url_for("https://example.com/deep/page?x=1")
        == "https://example.com/robots.txt"
    )


def test_a_site_with_no_robots_allows_us():
    assert robots_allows("https://example.com/p", read=lambda url: None) is True


def test_a_site_that_refuses_us_is_obeyed():
    assert (
        robots_allows("https://example.com/private/p", read=lambda url: REFUSE_US)
        is False
    )


def test_a_path_that_same_site_allows_is_allowed():
    assert (
        robots_allows("https://example.com/public", read=lambda url: REFUSE_US) is True
    )


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

    assert (
        robots_allows("https://example.com/p", read=read, cache=cache, now=now) is True
    )

    clock[0] = 23 * 60 * 60
    assert (
        robots_allows("https://example.com/p", read=read, cache=cache, now=now) is True
    )
    assert calls == ["https://example.com/robots.txt"], "re-read before the day was out"

    clock[0] = 24 * 60 * 60 + 1
    assert (
        robots_allows("https://example.com/p", read=read, cache=cache, now=now) is False
    )
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
        return (
            "User-agent: *\nDisallow: /\n" if url.startswith("http://") else ALLOW_ALL
        )

    cache: dict = {}

    assert robots_allows("http://example.com/p", read=read, cache=cache) is False
    assert robots_allows("https://example.com/p", read=read, cache=cache) is True
    assert calls == ["http://example.com/robots.txt", "https://example.com/robots.txt"]


def test_a_missing_protego_is_a_broken_install_not_a_missing_extra(absent):
    """Until 0.8 protego came with the fetch extra and a missing one named it;
    the base install fetches now, and brings protego, so a missing protego is
    an install that is broken, raised as the import error it is."""
    from sluicer.extras import MissingExtra

    absent("protego")

    with pytest.raises(ModuleNotFoundError) as raised:
        robots_allows("https://example.com/private/p", read=lambda url: REFUSE_US)

    assert not isinstance(raised.value, MissingExtra)


def test_the_process_cache_forgets_the_least_recently_used_site_past_its_bound(
    monkeypatch,
):
    """Unbounded, a long-running server kept an entry for every site it was sent to."""
    from sluicer.fetch import identity

    bounded = identity._Recent(2)
    monkeypatch.setattr(identity, "_CACHE", bounded)
    asked: list[str] = []

    def read(url: str) -> str:
        asked.append(url)
        return ""

    for site in ("a.test", "b.test", "a.test", "c.test", "a.test", "b.test"):
        robots_allows(f"https://{site}/p", read=read)

    assert list(bounded) == ["https://a.test", "https://b.test"]
    # a stayed because it kept being used; b was forgotten when c came, and
    # asked again at the end.
    assert asked.count("https://a.test/robots.txt") == 1
    assert asked.count("https://b.test/robots.txt") == 2


def test_the_process_cache_is_bounded_by_default():
    from sluicer.fetch import identity

    assert identity._CACHE.limit == identity.ROBOTS_CACHE_HOSTS


# -- what a crawler reads: how often, and where the sitemaps are ---------------


def test_a_crawl_delay_for_us_is_read_from_our_group():
    from sluicer.fetch.identity import robots_delay

    rules = "User-agent: Sluicer\nCrawl-delay: 5\n\nUser-agent: *\nCrawl-delay: 1\n"

    assert robots_delay("https://example.com/p", read=lambda url: rules) == 5.0


def test_a_request_rate_is_read_as_the_interval_it_implies():
    from sluicer.fetch.identity import robots_delay

    rules = "User-agent: *\nCrawl-delay: 2\nRequest-rate: 1/10\n"

    assert robots_delay("https://example.com/p", read=lambda url: rules) == 10.0


def test_a_site_that_asks_nothing_asks_for_no_delay():
    from sluicer.fetch.identity import robots_delay

    assert robots_delay("https://example.com/p", read=lambda url: None) == 0.0
    assert robots_delay("https://other.example/p", read=lambda url: ALLOW_ALL) == 0.0


def test_a_delay_that_is_not_a_number_is_no_delay(monkeypatch):
    """protego reads ``Crawl-delay: nan`` as a float; waiting NaN seconds raises."""
    import sys
    import types

    from sluicer.fetch.identity import robots_delay

    for said in (float("nan"), -3.0):
        rules = types.SimpleNamespace(
            crawl_delay=lambda agent, said=said: said,
            request_rate=lambda agent: None,
        )
        protego = types.ModuleType("protego")
        protego.Protego = types.SimpleNamespace(parse=lambda text, rules=rules: rules)
        monkeypatch.setitem(sys.modules, "protego", protego)

        assert (
            robots_delay("https://example.com/p", read=lambda url: "x", cache={}) == 0
        )


def test_the_sitemaps_a_robots_file_names_are_read_in_its_order():
    from sluicer.fetch.identity import robots_sitemaps

    rules = (
        "Sitemap: https://example.com/b.xml\nUser-agent: *\nDisallow: /x\n"
        "Sitemap: https://example.com/a.xml.gz\n"
    )

    assert robots_sitemaps("https://example.com/", read=lambda url: rules) == [
        "https://example.com/b.xml",
        "https://example.com/a.xml.gz",
    ]
    assert robots_sitemaps("https://none.example/", read=lambda url: None) == []


def test_one_read_answers_the_refusal_the_delay_and_the_sitemaps():
    from sluicer.fetch.identity import (
        robots_cached,
        robots_delay,
        robots_refusal,
        robots_sitemaps,
    )

    calls = []

    def read(url):
        calls.append(url)
        return "User-agent: *\nCrawl-delay: 3\nSitemap: https://example.com/s.xml\n"

    assert robots_cached("https://example.com/a") is False
    robots_refusal("https://example.com/a", read=read)
    assert robots_cached("https://example.com/b") is True
    robots_delay("https://example.com/b", read=read)
    robots_sitemaps("https://example.com/c", read=read)

    assert calls == ["https://example.com/robots.txt"]


def test_an_unreadable_robots_file_leaves_the_delay_unknown_not_zero():
    """A delay read as zero from a robots.txt nobody read would pace nothing."""
    from sluicer.fetch.identity import UNREACHABLE, RobotsUnreachable, robots_delay

    stand_in = f"# {UNREACHABLE}: TimeoutError\nUser-agent: *\nDisallow: /\n"

    with pytest.raises(RobotsUnreachable):
        robots_delay("https://example.com/p", read=lambda url: stand_in)


@pytest.fixture
def real_protego(monkeypatch):
    """The real protego, where the fake's stdlib parser would agree with anything.

    The stdlib splits a user agent at its first slash, so it never met the
    words after our name; protego looks for a group's name anywhere in it.
    """
    import importlib
    import sys

    monkeypatch.delitem(sys.modules, "protego")
    try:
        return importlib.import_module("protego")
    except ModuleNotFoundError:
        pytest.skip("the real protego arrives with the fetch extra")


@pytest.mark.parametrize("word", ["https", "github", "gi0tto", "com"])
def test_a_group_named_for_a_word_of_our_user_agent_is_not_ours(real_protego, word):
    """RFC 9309 matches a group against the product token, and protego found
    ``https`` in ``Sluicer/0.7.0 (+https://github.com/Gi0tto/sluicer)``: a
    group written for another crawler refused us, and its delay paced us."""
    from sluicer.fetch.identity import robots_delay

    theirs = f"User-agent: {word}\nDisallow: /\nCrawl-delay: 30\n"
    text = theirs + "\nUser-agent: *\nAllow: /\n"

    assert robots_allows("https://example.com/p", read=lambda u: text, cache={})
    assert robots_delay("https://example.com/p", read=lambda u: text, cache={}) == 0


def test_our_own_group_is_ours_whatever_case_it_is_written_in(real_protego):
    text = "User-agent: sluicer\nDisallow: /\n\nUser-agent: *\nAllow: /\n"

    assert not robots_allows("https://example.com/p", read=lambda u: text, cache={})


def test_the_audits_site_files_are_judged_by_the_product_token_too(real_protego):
    from sluicer.audit.report import SiteFile
    from sluicer.fetch.site import _refusal

    robots = SiteFile(
        "https://example.com/robots.txt",
        200,
        "User-agent: github\nDisallow: /\n\nUser-agent: *\nAllow: /\n",
    )

    assert _refusal("https://example.com/llms.txt", robots) is None
