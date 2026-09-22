import importlib.util
import sys
import types

import pytest

from sluicer.fetch.result import Fetched


def fake_scrapling(
    monkeypatch,
    status=200,
    html="<html><body>hi</body></html>",
    response_url=None,
    include_url=True,
):
    """Stand in for scrapling so no test ever opens a socket.

    ``response_url``, when given, is what the fake Response reports as its own
    URL, standing in for a redirect. ``include_url=False`` drops the ``url``
    attribute from the Response entirely, standing in for a client that never
    set one.
    """
    seen = {}

    class Response:
        def __init__(self, url):
            self.status = status
            self.html_content = html
            self.body = html.encode() if isinstance(html, str) else b""
            self.encoding = "utf-8"
            if include_url:
                self.url = response_url if response_url is not None else url

    def get(url, **kwargs):
        seen["http"] = (url, kwargs)
        return Response(url)

    def dynamic(url, **kwargs):
        seen["browser"] = (url, kwargs)
        return Response(url)

    def stealthy(url, **kwargs):
        seen["stealth"] = (url, kwargs)
        return Response(url)

    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = types.SimpleNamespace(get=get)
    module.DynamicFetcher = types.SimpleNamespace(fetch=dynamic)
    module.StealthyFetcher = types.SimpleNamespace(fetch=stealthy)
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)
    return seen


def test_the_default_rungs_come_back_in_cost_order(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = default_rungs()
    assert [name for name, _ in rungs] == ["http", "browser"]

    for _, rung in rungs:
        rung("https://example.com/p")

    assert seen["http"][1] == {"timeout": 30, "headers": {"User-Agent": USER_AGENT}}
    assert seen["browser"][1] == {"network_idle": True, "useragent": USER_AGENT}


def test_the_stealth_rung_comes_after_the_default_ladder_in_cost(monkeypatch):
    """This assertion used to be part of the three-rung default ladder.

    Stealth is no longer automatic, but it is still the most expensive rung,
    and it still sends none of our identity: moved here, not deleted.
    """
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import stealth_rung

    name, rung = stealth_rung()
    assert name == "stealth"

    rung("https://example.com/p")

    assert seen["stealth"][1] == {"network_idle": True}


def test_a_rung_returns_a_fetched_carrying_the_status(monkeypatch):
    seen = fake_scrapling(monkeypatch, status=403)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    name, rung = default_rungs()[0]
    result = rung("https://example.com/p")

    assert isinstance(result, Fetched)
    assert result.status == 403
    assert result.rung == "http"
    assert seen["http"][0] == "https://example.com/p"
    assert seen["http"][1] == {"timeout": 30, "headers": {"User-Agent": USER_AGENT}}


def test_the_default_ladder_does_not_include_stealth(monkeypatch):
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http", "browser"]


def test_stealth_is_available_to_a_caller_who_asks(monkeypatch):
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import stealth_rung

    name, rung = stealth_rung()

    assert name == "stealth"
    result = rung("https://example.com/p")
    assert result.rung == "stealth"


def test_the_http_rung_says_who_it_is(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["http"]("https://example.com/p")

    headers = seen["http"][1].get("headers") or {}
    assert headers.get("User-Agent") == USER_AGENT


def test_the_browser_rung_says_who_it_is(monkeypatch):
    """Measured against a live request: ``extra_headers`` is overridden by the

    browser context's own generated user agent, and never reaches the wire.
    ``useragent`` is the keyword the browser context itself actually applies.
    Both are asserted so the wrong one cannot silently come back: a fake
    accepts whatever it is handed, so the test that only checked
    ``extra_headers`` passed while the real request still said Chrome.
    """
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["browser"]("https://example.com/p")

    kwargs = seen["browser"][1]
    assert kwargs.get("useragent") == USER_AGENT
    assert (kwargs.get("extra_headers") or {}).get("User-Agent") is None


def test_the_stealth_rung_sends_no_user_agent(monkeypatch):
    """Its whole purpose is not to be recognised; announcing an identity and

    then trying to evade detection would be incoherent. See the comment next
    to ``stealth_rung`` in ``scrapling_rungs.py`` for the ruling.
    """
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import stealth_rung

    _, rung = stealth_rung()
    rung("https://example.com/p")

    kwargs = seen["stealth"][1]
    assert "headers" not in kwargs
    assert "extra_headers" not in kwargs
    assert "useragent" not in kwargs


class _NoScrapling:
    """A ``scrapling`` that is not installed at all.

    Measured, an absent package raises ``ModuleNotFoundError`` whose ``name``
    is the top-level package. Leaving ``None`` in ``sys.modules`` does not say
    that: it names ``scrapling.fetchers``, which is what a *broken* install
    looks like, so a finder that refuses the name is what stands in for
    absence here.
    """

    def find_spec(self, name, path=None, target=None):
        if name == "scrapling" or name.startswith("scrapling."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


def test_a_missing_scrapling_says_how_to_install_it(monkeypatch):
    monkeypatch.delitem(sys.modules, "scrapling", raising=False)
    monkeypatch.delitem(sys.modules, "scrapling.fetchers", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoScrapling(), *sys.meta_path])

    import sluicer.fetch.scrapling_rungs as rungs_module

    with pytest.raises(rungs_module.FetchExtraMissing) as raised:
        rungs_module.default_rungs()

    assert "sluicer[fetch]" in str(raised.value)


def test_a_response_without_html_is_a_failed_rung(monkeypatch):
    """No HTML is a failed rung, not a page: the ladder climbs past it."""
    fake_scrapling(monkeypatch, html=None)
    from sluicer.fetch.scrapling_rungs import default_rungs

    name, rung = default_rungs()[0]
    with pytest.raises(ValueError) as raised:
        rung("https://example.com/p")

    message = str(raised.value)
    assert "http" in message
    assert "HTML" in message


def test_the_response_url_is_preferred_over_the_requested_one(monkeypatch):
    """A response can report a different URL than the one requested: a redirect."""
    fake_scrapling(monkeypatch, response_url="https://example.com/final")
    from sluicer.fetch.scrapling_rungs import default_rungs, stealth_rung

    for _, rung in [*default_rungs(), stealth_rung()]:
        result = rung("https://example.com/start")
        assert result.url == "https://example.com/final"


def test_a_response_without_a_url_falls_back_to_the_one_we_asked_for(monkeypatch):
    """A response with no URL of its own never yields an empty string."""
    fake_scrapling(monkeypatch, include_url=False)
    from sluicer.fetch.scrapling_rungs import default_rungs, stealth_rung

    for _, rung in [*default_rungs(), stealth_rung()]:
        result = rung("https://example.com/p")
        assert result.url == "https://example.com/p"


class _BrokenFetchers:
    """An installed scrapling whose ``fetchers`` module raises on import.

    Nothing is missing here: ``scrapling`` imports fine, and the failure comes
    from inside it, the way a version skew between scrapling and one of its own
    modules looks. The import machinery reports that as a plain ``ImportError``
    with no ``name``, which is exactly what a genuinely absent package does not
    look like.
    """

    def find_spec(self, name, path=None, target=None):
        if name == "scrapling.fetchers":
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError("cannot import name 'Foo' from 'scrapling.engines'")


def test_a_broken_scrapling_install_is_not_a_missing_extra(monkeypatch):
    """A failure from inside a working install must surface as the bug it is."""
    package = types.ModuleType("scrapling")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "scrapling", package)
    monkeypatch.delitem(sys.modules, "scrapling.fetchers", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BrokenFetchers(), *sys.meta_path])

    from sluicer.fetch.scrapling_rungs import FetchExtraMissing, _fetchers

    with pytest.raises(ImportError) as raised:
        _fetchers()

    assert not isinstance(raised.value, FetchExtraMissing)
    assert str(raised.value) == "cannot import name 'Foo' from 'scrapling.engines'"
    assert "sluicer[fetch]" not in str(raised.value)
