"""The stealth rung: scrapling's stealthy browser, only for a caller who asked.

scrapling is faked, so these check what the rung hands it; what a server saw
was measured on the wire when the Google referer was found (2026-09-24).
"""

import importlib.util
import sys
import types

import pytest

PUBLIC = "93.184.215.14"


def fake_scrapling(monkeypatch, html="<html><body>hi</body></html>", pages=None):
    """A scrapling whose stealthy browser answers ``html``, or ``pages``: an
    address to its HTML, or ``"->"`` and the document's redirect."""
    seen = {"loads": []}

    def stealthy(url, **kwargs):
        seen["stealth"] = (url, kwargs)
        seen["loads"].append(url)
        guard = kwargs["page_setup"].__self__ if "page_setup" in kwargs else None
        if guard is not None:
            guard.installed = True
        answer = html if pages is None else pages[url]
        if answer is not None and answer.startswith("->"):
            guard.redirect = answer[2:]
            raise RuntimeError("Page.goto: net::ERR_BLOCKED_BY_CLIENT")
        return types.SimpleNamespace(
            html_content=answer, status=200, url=url, headers={"X-Robots-Tag": "none"}
        )

    module = types.ModuleType("scrapling.fetchers")
    module.StealthyFetcher = types.SimpleNamespace(fetch=stealthy)
    package = types.ModuleType("scrapling")
    package.__spec__ = importlib.util.spec_from_loader("scrapling", loader=None)
    monkeypatch.setitem(sys.modules, "scrapling", package)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)
    return seen


def test_the_stealth_rung_is_bounded_like_the_browser_and_borrows_nothing(
    monkeypatch,
):
    monkeypatch.delenv("SLUICER_PROXY", raising=False)
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.stealth import stealth_rung

    name, rung = stealth_rung()
    page = rung("https://example.com/p")

    assert name == "stealth" and page.rung == "stealth"
    assert seen["stealth"][1] == {
        "network_idle": True,
        "google_search": False,
        "timeout": 30_000,
        "retries": 1,
        "extra_flags": ["--no-proxy-server"],
    }
    assert page.headers == {"x-robots-tag": "none"}


def test_the_stealth_rung_never_claims_to_come_from_a_search(monkeypatch):
    """scrapling's google_search defaults to true, a Referer of
    https://www.google.com/ on every page: measured on the wire, the stealth
    rung sent it. Not announcing ourselves is one thing; saying we came from
    somewhere we did not is another."""
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.stealth import stealth_rung

    stealth_rung()[1]("https://example.com/p")

    assert seen["stealth"][1]["google_search"] is False


def test_the_stealth_rung_sends_no_user_agent_and_none_of_the_callers_headers(
    monkeypatch,
):
    """Its purpose is not to be recognised: announcing an identity, ours or
    the caller's login, while evading detection would be incoherent."""
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.stealth import stealth_rung

    stealth_rung()[1]("https://example.com/p")

    kwargs = seen["stealth"][1]
    for said in ("headers", "extra_headers", "useragent", "cookies"):
        assert said not in kwargs


def test_the_stealth_rung_goes_through_the_proxy_asked_for(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.stealth import stealth_rung

    stealth_rung(proxy="http://proxy.example:3128")[1]("https://example.com/p")

    assert seen["stealth"][1]["proxy"] == "http://proxy.example:3128"
    assert "extra_flags" not in seen["stealth"][1]


def test_a_missing_scrapling_says_the_stealth_extra_installs_it(absent):
    absent("scrapling")
    from sluicer.fetch.rungs import FetchExtraMissing
    from sluicer.fetch.stealth import stealth_rung

    with pytest.raises(FetchExtraMissing) as raised:
        stealth_rung()

    assert raised.value.extra == "stealth"
    assert 'Install it with: pip install "sluicer[stealth]"' in str(raised.value)


class _BrokenFetchers:
    """An installed scrapling whose ``fetchers`` module raises on import:
    a version skew inside it, which is a bug, not a missing extra."""

    def find_spec(self, name, path=None, target=None):
        if name == "scrapling.fetchers":
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError("cannot import name 'Foo' from 'scrapling.engines'")


def test_a_broken_scrapling_install_is_not_a_missing_extra(monkeypatch):
    package = types.ModuleType("scrapling")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "scrapling", package)
    monkeypatch.delitem(sys.modules, "scrapling.fetchers", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BrokenFetchers(), *sys.meta_path])

    from sluicer.fetch.rungs import FetchExtraMissing
    from sluicer.fetch.stealth import _stealthy

    with pytest.raises(ImportError) as raised:
        _stealthy()

    assert not isinstance(raised.value, FetchExtraMissing)
    assert "sluicer[stealth]" not in str(raised.value)


def test_a_response_without_html_is_a_failed_rung(monkeypatch):
    fake_scrapling(monkeypatch, html=None)
    from sluicer.fetch.stealth import stealth_rung

    with pytest.raises(ValueError, match="no HTML"):
        stealth_rung()[1]("https://example.com/p")


def test_the_guarded_stealth_rung_asks_a_documents_redirect_again(monkeypatch):
    seen = fake_scrapling(
        monkeypatch,
        pages={
            "https://example.com/old": "->https://example.com/new",
            "https://example.com/new": "<p>new</p>",
        },
    )
    from sluicer.fetch.stealth import stealth_rung

    rung = stealth_rung(allow_private=False, resolve=lambda host: [PUBLIC])[1]

    assert rung("https://example.com/old").url == "https://example.com/new"
    assert seen["loads"] == ["https://example.com/old", "https://example.com/new"]


def test_the_guarded_stealth_rung_refuses_a_redirect_somewhere_private(monkeypatch):
    from sluicer.fetch.address import AddressRefused

    fake_scrapling(monkeypatch, pages={"https://example.com/old": "->http://10.0.0.1/"})
    from sluicer.fetch.stealth import stealth_rung

    rung = stealth_rung(allow_private=False, resolve=lambda host: [PUBLIC])[1]
    with pytest.raises(AddressRefused):
        rung("https://example.com/old")


def test_the_stealth_page_is_held_to_the_bound(monkeypatch):
    from sluicer.fetch.result import ResponseTooLarge

    fake_scrapling(monkeypatch, html="<p>" + "x" * 5000 + "</p>")
    from sluicer.fetch.stealth import stealth_rung

    with pytest.raises(ResponseTooLarge):
        stealth_rung(max_bytes=1000)[1]("https://example.com/p")


class _RepeatingHeaders:
    """A response's headers that name some twice, as a multi-dict does."""

    def __init__(self, pairs):
        self.pairs = pairs

    def items(self):
        return list(self.pairs)

    def __bool__(self):
        return bool(self.pairs)


@pytest.mark.parametrize(
    "headers",
    [
        _RepeatingHeaders(
            [
                ("Link", "<https://a.example/c>; rel=canonical"),
                ("X-Robots-Tag", "noindex"),
                ("Link", "<https://a.example/n>; rel=next"),
                ("X-Robots-Tag", "nofollow"),
            ]
        ),
        {
            "Link": "<https://a.example/c>; rel=canonical",
            "link": "<https://a.example/n>; rel=next",
            "X-Robots-Tag": "noindex",
            "x-robots-tag": "nofollow",
        },
    ],
    ids=["repeated", "two-cases"],
)
def test_a_header_the_stealth_rung_is_given_twice_keeps_both_values(
    monkeypatch, headers
):
    """The architecture audit of 0.9.0 (D8): the rung kept only the last value
    of a name given twice, against Fetched.headers' "a repeated one's values
    joined". scrapling 0.4.15 joins them itself, measured on a local server;
    the rung no longer relies on it."""
    fake_scrapling(monkeypatch)
    from sluicer.fetch.stealth import _as_fetched

    response = types.SimpleNamespace(
        html_content="<p>hi</p>", status=200, url="https://a.example/", headers=headers
    )

    page = _as_fetched(response, "https://a.example/")

    assert page.headers == {
        "link": "<https://a.example/c>; rel=canonical, <https://a.example/n>; rel=next",
        "x-robots-tag": "noindex, nofollow",
    }
