"""Tests for sluicer.fetch.identity: our name, and the robots.txt we read.

protego -- the library that actually parses robots.txt -- ships behind the
``fetch`` extra and stays uninstalled in this virtualenv on purpose, so this
file proves the module works without it. Two of the six tests below hand
``robots_allows`` real Allow/Disallow text, which means something importable
as ``protego`` has to exist for ``import_extra`` to find. The first fixture
below stands one in, built on the standard library's own robots parser, which
already implements group selection and longest-match the way a real robots
reader does -- so the fake is honest about Allow and Disallow, not just about
returning a fixed answer. Nothing here touches the network:
``RobotFileParser.parse`` reads text already sitting in a Python string.

Separately, ``robots_allows`` falls back to a module-level cache when a caller
passes none of its own, so that production code gets per-host caching without
wiring a dict through. Three of the tests below rely on that default and all
target ``example.com``, which would let one test's cached answer leak into the
next only because they share that fallback. The second fixture clears it
before and after every test in this file, so each one still starts as if it
were the first call ever made -- it is a test-isolation seam, not a change to
what ``robots_allows`` does for a real caller.
"""

import sys
import types
from urllib import robotparser

import pytest

from sluicer.fetch.identity import USER_AGENT, robots_allows, robots_url_for

ALLOW_ALL = "User-agent: *\nAllow: /\n"
REFUSE_US = "User-agent: Sluicer\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n"


class _FakeMatcher:
    """Protego's ``can_fetch(url, user_agent)`` shape, over the stdlib parser."""

    def __init__(self, text: str) -> None:
        self._parser = robotparser.RobotFileParser()
        self._parser.parse(text.splitlines())

    def can_fetch(self, url: str, user_agent: str) -> bool:
        return self._parser.can_fetch(user_agent, url)


@pytest.fixture(autouse=True)
def _fake_protego(monkeypatch):
    """Make ``import_extra("protego", ...)`` succeed without installing it."""
    module = types.ModuleType("protego")
    module.Protego = types.SimpleNamespace(parse=_FakeMatcher)
    monkeypatch.setitem(sys.modules, "protego", module)


@pytest.fixture(autouse=True)
def _reset_the_default_cache():
    """Give each test its own answer, not whatever the last test left behind."""
    from sluicer.fetch.identity import _CACHE

    _CACHE.clear()
    yield
    _CACHE.clear()


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
