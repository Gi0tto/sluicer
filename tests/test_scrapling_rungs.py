import sys
import types

import pytest

from sluicer.fetch.result import Fetched


def fake_scrapling(monkeypatch, status=200, html="<html><body>hi</body></html>"):
    """Stand in for scrapling so no test ever opens a socket."""
    seen = {}

    class Response:
        def __init__(self, url):
            self.status = status
            self.html_content = html
            self.body = html.encode()
            self.encoding = "utf-8"
            self.url = url

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
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http", "browser", "stealth"]


def test_a_rung_returns_a_fetched_carrying_the_status(monkeypatch):
    seen = fake_scrapling(monkeypatch, status=403)
    from sluicer.fetch.scrapling_rungs import default_rungs

    name, rung = default_rungs()[0]
    result = rung("https://example.com/p")

    assert isinstance(result, Fetched)
    assert result.status == 403
    assert result.rung == "http"
    assert seen["http"][0] == "https://example.com/p"


def test_a_missing_scrapling_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", None)
    import importlib

    import sluicer.fetch.scrapling_rungs as rungs_module

    importlib.reload(rungs_module)
    with pytest.raises(ImportError) as raised:
        rungs_module.default_rungs()

    assert "sluicer[fetch]" in str(raised.value)
