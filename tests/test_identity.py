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
