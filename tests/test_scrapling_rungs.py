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
    http_redirect=None,
):
    """Stand in for scrapling and curl_cffi so no test ever opens a socket.

    ``response_url``, when given, is what a fake browser Response reports as
    its own URL, standing in for a redirect the browser followed.
    ``include_url=False`` drops the ``url`` attribute from it entirely,
    standing in for a client that never set one. ``http_redirect``, when given,
    is where the HTTP rung's first answer sends it, with a 302.
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

    def dynamic(url, **kwargs):
        seen["browser"] = (url, kwargs)
        return Response(url)

    def stealthy(url, **kwargs):
        seen["stealth"] = (url, kwargs)
        return Response(url)

    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = types.SimpleNamespace()
    module.DynamicFetcher = types.SimpleNamespace(fetch=dynamic)
    module.StealthyFetcher = types.SimpleNamespace(fetch=stealthy)
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)

    replies = []
    if http_redirect is not None:
        replies.append((302, b"", {"location": http_redirect}))

    class CurlResponse:
        def __init__(self, reply):
            self.status_code, self._body, self.headers = reply

        def iter_content(self):
            yield self._body

        def close(self):
            seen["closed"] = seen.get("closed", 0) + 1

    class Session:
        def __init__(self, **options):
            seen.setdefault("http_sessions", []).append(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            seen["http"] = (url, kwargs)
            seen.setdefault("http_urls", []).append(url)
            body = html.encode() if isinstance(html, str) else b""
            reply = replies.pop(0) if replies else (status, body, {})
            return CurlResponse(reply)

    curl = types.ModuleType("curl_cffi")
    curl.CurlOpt = types.SimpleNamespace(
        MAXFILESIZE_LARGE="maxfilesize",
        RESOLVE="resolve",
        PROTOCOLS_STR="protocols",
        REDIR_PROTOCOLS_STR="redir_protocols",
        TIMEOUT_MS="timeout_ms",
        PROXY="proxy",
    )
    requests = types.ModuleType("curl_cffi.requests")
    requests.Session = Session
    monkeypatch.setitem(sys.modules, "curl_cffi", curl)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", requests)
    return seen


def test_the_default_rungs_come_back_in_cost_order(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = default_rungs()
    assert [name for name, _ in rungs] == ["http", "browser"]

    for _, rung in rungs:
        rung("https://example.com/p")

    assert seen["http"][1]["headers"] == {"User-Agent": USER_AGENT}
    assert seen["browser"][1]["useragent"] == USER_AGENT
    assert seen["browser"][1]["network_idle"] is True


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

    assert seen["stealth"][1] == {
        "network_idle": True,
        "extra_flags": ["--no-proxy-server"],
    }


def test_a_rung_returns_a_fetched_carrying_the_status(monkeypatch):
    seen = fake_scrapling(monkeypatch, status=403)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    _name, rung = default_rungs()[0]
    result = rung("https://example.com/p")

    assert isinstance(result, Fetched)
    assert result.status == 403
    assert result.rung == "http"
    assert seen["http"][0] == "https://example.com/p"
    assert seen["http"][1]["headers"] == {"User-Agent": USER_AGENT}


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

    _name, rung = default_rungs()[0]
    with pytest.raises(ValueError) as raised:
        rung("https://example.com/p")

    message = str(raised.value)
    assert "http" in message
    assert "HTML" in message


def test_the_response_url_is_preferred_over_the_requested_one(monkeypatch):
    """A browser response can report a different URL: a redirect it followed."""
    fake_scrapling(monkeypatch, response_url="https://example.com/final")
    from sluicer.fetch.scrapling_rungs import default_rungs, stealth_rung

    for _, rung in [default_rungs()[1], stealth_rung()]:
        result = rung("https://example.com/start")
        assert result.url == "https://example.com/final"


def test_the_http_rung_follows_a_redirect_itself_and_reports_where_it_landed(
    monkeypatch,
):
    seen = fake_scrapling(monkeypatch, http_redirect="/final")
    from sluicer.fetch.scrapling_rungs import default_rungs

    result = dict(default_rungs())["http"]("https://example.com/start")

    assert result.url == "https://example.com/final"
    assert seen["http_urls"] == [
        "https://example.com/start",
        "https://example.com/final",
    ]
    assert seen["http"][1]["allow_redirects"] is False


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


def test_the_http_rung_does_not_dress_up_as_a_browser(monkeypatch):
    """Measured on 2026-09-22 against a local server: scrapling's defaults sent
    ``Referer: https://www.google.com/`` and a Chrome TLS fingerprint under our
    own user agent. A fake Google referral is not arriving under our own name.
    The rung is now curl_cffi with no impersonation, and on the wire it sends
    what the scrapling rung sent once those were off: ``Host``,
    ``Accept-Encoding`` and our ``User-Agent``.
    """
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["http"]("https://example.com/p")

    assert seen["http_sessions"][0].get("impersonate") is None
    headers = seen["http"][1].get("headers") or {}
    assert "referer" not in {key.lower() for key in headers}
    assert "referer" not in seen["http"][1]


def test_the_browser_rung_does_not_claim_to_come_from_google(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["browser"]("https://example.com/p")

    assert seen["browser"][1].get("google_search") is False


def test_a_rung_tries_once_and_gives_up_in_bounded_time(monkeypatch):
    """Three retries of thirty seconds on each rung was three minutes for one slow
    page, longer than an agent's tool call waits."""
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = dict(default_rungs())
    rungs["http"]("https://example.com/p")
    rungs["browser"]("https://example.com/p")

    assert "retry" not in seen["http_sessions"][0]  # curl_cffi: one try
    assert seen["http"][1].get("timeout") <= 20
    assert seen["browser"][1].get("retries") == 1
    assert seen["browser"][1].get("timeout") <= 30_000


def test_a_browser_answer_keeps_its_headers_names_lowercased():
    import types

    from sluicer.fetch.scrapling_rungs import _as_fetched

    response = types.SimpleNamespace(
        html_content="<html><body>hi</body></html>",
        status=200,
        url="https://example.com/p",
        headers={"X-Robots-Tag": "noindex", "Link": "</c>; rel=canonical"},
    )
    fetched = _as_fetched(response, "browser", "https://example.com/p")
    assert fetched.headers == {"x-robots-tag": "noindex", "link": "</c>; rel=canonical"}
    del response.headers
    assert _as_fetched(response, "browser", "https://example.com/p").headers == {}


def test_the_browser_uses_no_proxy_unless_one_is_asked_for(monkeypatch):
    """Without one, Chromium is told --no-proxy-server, so neither the system's
    proxy nor the environment's is used behind our back."""
    monkeypatch.delenv("SLUICER_PROXY", raising=False)
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs, stealth_rung

    dict(default_rungs())["browser"]("https://example.com/p")
    stealth_rung()[1]("https://example.com/p")

    for rung in ("browser", "stealth"):
        options = seen[rung][1]
        assert options["extra_flags"] == ["--no-proxy-server"], rung
        assert "proxy" not in options, rung


def test_the_browser_goes_through_the_proxy_asked_for(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = dict(default_rungs(proxy="http://proxy.example:3128"))
    rungs["browser"]("https://example.com/p")
    rungs["http"]("https://example.com/p")

    assert seen["browser"][1]["proxy"] == "http://proxy.example:3128"
    assert "extra_flags" not in seen["browser"][1]
    assert seen["http"][1]["proxy"] == "http://proxy.example:3128"
