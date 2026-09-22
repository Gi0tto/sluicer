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


def test_the_three_rungs_come_back_in_cost_order(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = default_rungs()
    assert [name for name, _ in rungs] == ["http", "browser", "stealth"]

    for _, rung in rungs:
        rung("https://example.com/p")

    assert seen["http"][1] == {"timeout": 30}
    assert seen["browser"][1] == {"network_idle": True}
    assert seen["stealth"][1] == {"network_idle": True}


def test_a_rung_returns_a_fetched_carrying_the_status(monkeypatch):
    seen = fake_scrapling(monkeypatch, status=403)
    from sluicer.fetch.scrapling_rungs import default_rungs

    name, rung = default_rungs()[0]
    result = rung("https://example.com/p")

    assert isinstance(result, Fetched)
    assert result.status == 403
    assert result.rung == "http"
    assert seen["http"][0] == "https://example.com/p"
    assert seen["http"][1] == {"timeout": 30}


def test_a_missing_scrapling_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", None)
    import importlib

    import sluicer.fetch.scrapling_rungs as rungs_module

    importlib.reload(rungs_module)
    with pytest.raises(ImportError) as raised:
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
    from sluicer.fetch.scrapling_rungs import default_rungs

    for _, rung in default_rungs():
        result = rung("https://example.com/start")
        assert result.url == "https://example.com/final"


def test_a_response_without_a_url_falls_back_to_the_one_we_asked_for(monkeypatch):
    """A response with no URL of its own never yields an empty string."""
    fake_scrapling(monkeypatch, include_url=False)
    from sluicer.fetch.scrapling_rungs import default_rungs

    for _, rung in default_rungs():
        result = rung("https://example.com/p")
        assert result.url == "https://example.com/p"
