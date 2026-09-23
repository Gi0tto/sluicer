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

import os
import sys
import types
from urllib import robotparser

import pytest
from hypothesis import HealthCheck, settings

# The properties in tests/properties run under one of three profiles, chosen by
# HYPOTHESIS_PROFILE. ``default`` is what every run of the suite gets: few
# examples, drawn from a fixed seed, so the suite stays a few seconds long and a
# red build on an unrelated change can be reproduced by running it again.
# ``search`` is what CI adds on every push: hundreds of examples from a fresh
# seed, a few minutes. ``fuzz`` is the weekly search: thousands, about half an
# hour on a CI runner, which is too long to wait for on every push.
#
# No deadline in either: a property that parses a page is timed by the machine
# it runs on, and a slow CI runner is not a bug. What each property must cost is
# asserted where it matters, as a bound on output, not on the clock.
#
# Hypothesis keeps what it finds in .hypothesis/ in the working directory, a
# directory of files; nothing here reaches the network.
_UNHURRIED = [HealthCheck.too_slow, HealthCheck.data_too_large]
settings.register_profile(
    "default",
    max_examples=15,
    deadline=None,
    derandomize=True,
    suppress_health_check=_UNHURRIED,
)
settings.register_profile(
    "search",
    max_examples=300,
    deadline=None,
    print_blob=True,
    suppress_health_check=_UNHURRIED,
)
settings.register_profile(
    "fuzz",
    max_examples=2500,
    deadline=None,
    print_blob=True,
    suppress_health_check=_UNHURRIED,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


class _FakeMatcher:
    """Protego's shape, over the stdlib parser: ``can_fetch(url, user_agent)``,
    ``crawl_delay`` and ``request_rate`` for a user agent, and ``sitemaps``.

    The stdlib reads ``Crawl-delay`` and ``Request-rate`` by the same group
    rules, so a fake delay is chosen the way a real one is. Where protego
    differs -- it reads a fractional delay, the stdlib only whole seconds -- the
    ``with-extras`` CI job asks the real one.
    """

    def __init__(self, text: str) -> None:
        self._parser = robotparser.RobotFileParser()
        self._parser.parse(text.splitlines())

    def can_fetch(self, url: str, user_agent: str) -> bool:
        return self._parser.can_fetch(user_agent, url)

    def crawl_delay(self, user_agent: str):
        found = self._parser.crawl_delay(user_agent)
        return None if found is None else float(found)

    def request_rate(self, user_agent: str):
        return self._parser.request_rate(user_agent)

    @property
    def sitemaps(self):
        return iter(self._parser.site_maps() or [])


@pytest.fixture(autouse=True)
def _fake_protego(monkeypatch):
    """Make ``import_extra("protego", ...)`` succeed without installing it."""
    module = types.ModuleType("protego")
    module.Protego = types.SimpleNamespace(parse=_FakeMatcher)
    monkeypatch.setitem(sys.modules, "protego", module)


@pytest.fixture(autouse=True)
def _reset_the_default_cache():
    """Give each test its own answer, not whatever the last test left behind.

    The crawler's record of when each site was last asked is process-wide for
    the same reason the robots answers are, and is cleared with them: a fake
    clock's hours would otherwise have the next test wait them out.
    """
    from sluicer.crawl.schedule import _ENDED
    from sluicer.fetch.identity import _CACHE

    _CACHE.clear()
    _ENDED.clear()
    yield
    _CACHE.clear()
    _ENDED.clear()


@pytest.fixture
def absent(monkeypatch):
    """Make named packages genuinely unimportable, submodules and all.

    Measured, an absent package raises ``ModuleNotFoundError`` whose ``name``
    is the top-level package, and that is the only failure ``import_extra``
    treats as "the extra is missing". Leaving ``None`` in ``sys.modules`` does
    not say that, so a finder that refuses the name is what stands in for
    absence. Removing the modules matters too: the autouse fake ``protego``
    above is already sitting in ``sys.modules``, and a test about protego
    being missing has to take it back out.
    """

    def make_absent(*names: str) -> None:
        class Finder:
            def find_spec(self, name, path=None, target=None):
                for gone in names:
                    if name == gone or name.startswith(gone + "."):
                        raise ModuleNotFoundError(
                            f"No module named {name!r}", name=name
                        )

        for name in list(sys.modules):
            if any(name == gone or name.startswith(gone + ".") for gone in names):
                monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])

    return make_absent
