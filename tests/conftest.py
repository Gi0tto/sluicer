"""Fixtures shared across the test suite.

``protego`` -- the library that actually parses robots.txt -- ships behind
the ``fetch`` extra and stays uninstalled in this virtualenv on purpose, so
any test that needs ``robots_allows`` to do real Allow/Disallow work gets a
fake here rather than each test file inventing its own. The fake is built on
the standard library's own robots parser, which already implements group
selection and longest-match the way a real robots reader does, so it is
honest about Allow and Disallow, not just about returning a fixed answer.
Nothing here touches the network: ``RobotFileParser.parse`` reads text
already sitting in a Python string.

Both fixtures are autouse: a fake ``protego`` module sitting in
``sys.modules`` and an empty per-host robots cache are harmless to every test
that never touches ``robots_allows``, and this keeps every test file that
does from having to remember to ask for them.
"""

import sys
import types
from urllib import robotparser

import pytest


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
