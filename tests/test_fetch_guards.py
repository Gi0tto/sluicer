"""The fetch layer's limits: the byte bound, the pinned connection, the guard.

Fakes throughout, so the suite opens no socket. What a real curl and a real
Chromium do with the same instructions is checked by ``tests/live/``, which CI
runs with the extra and a browser installed.
"""

import sys
import types

import pytest

from sluicer.fetch.address import AddressRefused, public_addresses
from sluicer.fetch.browser_guard import Guard
from sluicer.fetch.ladder import fetch
from sluicer.fetch.result import Fetched, ResponseTooLarge

PUBLIC = "93.184.215.14"


def public(host):
    return [PUBLIC]


def fake_curl(monkeypatch, replies, chunk=None):
    """A curl_cffi that answers ``replies`` in order: (status, body, headers)."""
    seen = {"sessions": [], "urls": [], "asked": []}

    class Response:
        def __init__(self, reply):
            self.status_code, self.body, self.headers = reply

        def iter_content(self):
            size = chunk or max(len(self.body), 1)
            for start in range(0, len(self.body), size):
                yield self.body[start : start + size]

        def close(self):
            pass

    class Session:
        def __init__(self, **options):
            seen["sessions"].append(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            seen["urls"].append(url)
            seen["asked"].append(kwargs)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return Response(reply)

    curl = types.ModuleType("curl_cffi")
    curl.CurlOpt = types.SimpleNamespace(
        MAXFILESIZE_LARGE="max",
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


PAGE = (200, b"<html><body>ok</body></html>", {})


# -- the HTTP rung ------------------------------------------------------------


def test_the_http_rung_stops_reading_past_the_bound(monkeypatch):
    fake_curl(monkeypatch, [(200, b"x" * 5000, {})], chunk=1000)
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ResponseTooLarge):
        http_rung(max_bytes=2500)("https://example.com/p")


def test_curls_own_refusal_of_a_heavy_body_is_the_same_answer(monkeypatch):
    """Announced lengths and inflated gzip are refused by curl first (code 63)."""
    refusal = RuntimeError(
        "Failed to perform, curl: (63) Would have exceeded max file size"
    )
    fake_curl(monkeypatch, [refusal])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ResponseTooLarge):
        http_rung(max_bytes=2500)("https://example.com/p")


def test_the_http_rung_keeps_the_responses_headers(monkeypatch):
    class Repeated(dict):
        """A curl_cffi header set, where a header can come twice."""

        def multi_items(self):
            return [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Link", "</a>; rel=canonical"),
                ("link", "</b>; rel=next"),
            ]

    fake_curl(
        monkeypatch,
        [(200, b"<html><body>ok</body></html>", Repeated(content_type="text/html"))],
    )
    from sluicer.fetch.http_rung import http_rung

    fetched = http_rung()("https://example.com/p")

    assert fetched.headers == {
        "content-type": "text/html; charset=utf-8",
        "link": "</a>; rel=canonical, </b>; rel=next",
    }


def test_curl_is_told_the_bound_too(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(max_bytes=2500)("https://example.com/p")

    assert seen["sessions"][0]["curl_options"]["max"] == 2500


def test_a_guarded_connection_is_pinned_to_the_addresses_that_were_checked(
    monkeypatch,
):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(allow_private=False, resolve=public)("https://example.com:8443/p")

    assert seen["sessions"][0]["curl_options"]["resolve"] == [
        f"example.com:8443:{PUBLIC}"
    ]


def test_an_ipv6_address_is_pinned_in_brackets(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung(allow_private=False, resolve=lambda host: ["2606:2800:21f::1"])
    rung("https://example.com/p")

    assert seen["sessions"][0]["curl_options"]["resolve"] == [
        "example.com:443:[2606:2800:21f::1]"
    ]


def test_an_unguarded_connection_is_not_pinned(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://example.com/p")

    assert "resolve" not in seen["sessions"][0]["curl_options"]


def test_a_redirect_into_a_private_address_is_refused_before_it_is_asked(
    monkeypatch,
):
    seen = fake_curl(monkeypatch, [(302, b"", {"location": "http://10.0.0.1/admin"})])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused) as refused:
        http_rung(allow_private=False, resolve=public)("https://example.com/p")

    assert refused.value.url == "http://10.0.0.1/admin"
    assert seen["urls"] == ["https://example.com/p"]


@pytest.mark.parametrize(
    "target",
    [
        "gopher://127.0.0.1:6379/_SET%20pwned%201%0D%0A",
        "dict://127.0.0.1:11211/stats",
        "file:///etc/hosts",
        "ftp://example.com/file",
    ],
)
def test_a_redirect_off_the_web_is_refused_before_it_is_asked(monkeypatch, target):
    """curl speaks gopher, dict and file too. Measured before this was refused:
    a 302 to gopher:// sent ``SET pwned 1`` to whatever listened on that port,
    and a 302 to file:///etc/hosts returned the file as the page, with the
    defaults every command line fetch has."""
    seen = fake_curl(monkeypatch, [(302, b"", {"location": target}), PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused, match="only http and https") as refused:
        http_rung()("https://example.com/p")

    assert refused.value.url == target
    assert seen["urls"] == ["https://example.com/p"]


def test_curl_is_told_to_speak_only_http_and_https(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://example.com/p")

    options = seen["sessions"][0]["curl_options"]
    assert options["protocols"] == "http,https"
    assert options["redir_protocols"] == "http,https"


def test_an_address_off_the_web_is_never_asked_by_the_rung(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused, match="not file"):
        http_rung()("file:///etc/hosts")

    assert seen["urls"] == []


def test_the_ladder_refuses_an_address_off_the_web_whatever_it_allows():
    browser = _rung("browser")

    with pytest.raises(AddressRefused, match="not file"):
        fetch("file:///etc/hosts", rungs=[("browser", browser)], allow_private=True)

    assert browser.calls == []


def test_a_page_that_landed_off_the_web_is_refused():
    """A rung that follows redirects itself is judged where it landed."""

    def landed_elsewhere(url):
        return Fetched(url="file:///etc/hosts", html="<p>ok</p>", status=200, rung="x")

    with pytest.raises(AddressRefused, match="not file"):
        fetch(
            "https://example.com/p",
            rungs=[("x", landed_elsewhere)],
            robots_reader=lambda url: None,
        )


def test_curl_is_given_the_whole_deadline_not_a_floor_on_speed(monkeypatch):
    """curl_cffi's timeout on a stream is "under a byte a second for that
    long": a body dripped eight bytes a second held a request for as long as
    it dripped. curl's own TIMEOUT_MS is the whole transfer, body included."""
    seen = fake_curl(monkeypatch, [(302, b"", {"location": "/q"}), PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(timeout=7)("https://example.com/p")

    first, second = (s["curl_options"]["timeout_ms"] for s in seen["sessions"])
    assert 0 < second <= first <= 7000, "each hop gets what is left of one deadline"


def test_a_fetch_past_its_deadline_asks_nothing_more(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(TimeoutError, match="longer than 0 seconds"):
        http_rung(timeout=0)("https://example.com/p")

    assert seen["urls"] == []


def test_curls_timeout_is_a_timeout(monkeypatch):
    """Whatever class curl_cffi raises it as, code 28 is the deadline."""
    timed_out = RuntimeError(
        "Failed to perform, curl: (28) Operation timed out after 1501 milliseconds"
    )
    fake_curl(monkeypatch, [timed_out])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(TimeoutError, match="longer than 20 seconds") as raised:
        http_rung()("https://example.com/p")

    assert isinstance(raised.value, OSError), "callers catch OSError"


def test_no_proxy_is_used_unless_one_is_asked_for(monkeypatch):
    """libcurl reads HTTPS_PROXY itself: measured, a CONNECT reached a local
    proxy nobody had named to Sluicer. An empty PROXY is curl's "none"."""
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
    monkeypatch.delenv("SLUICER_PROXY", raising=False)
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://example.com/p")

    assert seen["sessions"][0]["curl_options"]["proxy"] == ""
    assert "proxy" not in seen["asked"][0]


@pytest.mark.parametrize("by", ["argument", "environment"])
def test_a_proxy_asked_for_is_the_one_used(monkeypatch, by):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    kwargs = {}
    if by == "argument":
        kwargs["proxy"] = "socks5h://proxy.example:1080"
    else:
        monkeypatch.setenv("SLUICER_PROXY", "socks5h://proxy.example:1080")
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(**kwargs)("https://example.com/p")

    assert seen["asked"][0]["proxy"] == "socks5h://proxy.example:1080"
    assert "proxy" not in seen["sessions"][0]["curl_options"]


def test_an_empty_proxy_is_none(monkeypatch):
    monkeypatch.setenv("SLUICER_PROXY", "socks5h://proxy.example:1080")
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(proxy="")("https://example.com/p")

    assert seen["sessions"][0]["curl_options"]["proxy"] == ""


def test_a_redirect_loop_ends(monkeypatch):
    loop = [(302, b"", {"location": "/p"}) for _ in range(20)]
    fake_curl(monkeypatch, loop)
    from sluicer.fetch.http_rung import TooManyRedirects, http_rung

    with pytest.raises(TooManyRedirects):
        http_rung()("https://example.com/p")


def test_the_charset_the_response_was_sent_with_decodes_it(monkeypatch):
    body = "<html><body>Café</body></html>".encode("windows-1252")
    fake_curl(
        monkeypatch, [(200, body, {"content-type": "text/html; charset=windows-1252"})]
    )
    from sluicer.fetch.http_rung import http_rung

    assert "Café" in http_rung()("https://example.com/p").html


def test_a_name_that_resolves_to_nothing_is_not_left_for_curl_to_look_up():
    """Left to curl, the second lookup is the one DNS rebinding answers."""
    with pytest.raises(OSError):
        public_addresses("https://example.com/p", resolve=lambda host: [])


def test_a_host_written_as_an_address_needs_no_pin(monkeypatch):
    seen = fake_curl(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(allow_private=False)(f"https://{PUBLIC}/p")

    assert "resolve" not in seen["sessions"][0]["curl_options"]


# -- the browser guard --------------------------------------------------------


class FakeRequest:
    def __init__(self, url, document=False):
        self.url = url
        self._document = document
        self.frame = types.SimpleNamespace(parent_frame=None if document else object())

    def is_navigation_request(self):
        return self._document


class FakeRoute:
    """A route whose ``fetch`` answers from ``answers``, keyed by URL."""

    def __init__(self, url, answers, document=False):
        self.request = FakeRequest(url, document)
        self.answers = answers
        self.fetched = []
        self.outcome = None

    def fetch(self, url, max_redirects):
        assert max_redirects == 0
        self.fetched.append(url)
        status, location = self.answers[url]
        headers = {"location": location} if location else {}
        return types.SimpleNamespace(status=status, headers=headers)

    def fulfill(self, response):
        self.outcome = ("fulfilled", response.status)

    def abort(self, reason):
        self.outcome = ("aborted", reason)

    def continue_(self):
        self.outcome = ("continued", None)


def resolve_by_name(host):
    return ["10.0.0.5"] if host.startswith("internal") else [PUBLIC]


def test_the_guard_turns_away_a_request_for_a_private_address():
    guard = Guard(resolve_by_name)
    route = FakeRoute("http://internal.example/img", {})

    guard._route(route)

    assert route.outcome == ("aborted", "blockedbyclient")
    assert route.fetched == []
    assert guard.refused[0][0] == "http://internal.example/img"


def test_the_guard_walks_a_subresource_redirect_chain_itself():
    """Chromium follows a fulfilled redirect without asking the route: measured.

    So the chain is walked here, and the private hop at its end never asked.
    """
    guard = Guard(resolve_by_name)
    answers = {
        "https://cdn.example/a": (302, "/b"),
        "https://cdn.example/b": (302, "http://internal.example/secret"),
    }
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.fetched == ["https://cdn.example/a", "https://cdn.example/b"]
    assert route.outcome == ("aborted", "blockedbyclient")
    assert guard.refused == [
        (
            "http://internal.example/secret",
            guard.why_refused("http://internal.example/x"),
        )
    ]


def test_the_guard_hands_over_the_last_answer_of_a_public_chain():
    guard = Guard(resolve_by_name)
    answers = {
        "https://cdn.example/a": (301, "/b"),
        "https://cdn.example/b": (200, None),
    }
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.outcome == ("fulfilled", 200)


def test_the_documents_own_redirect_is_left_for_the_rung_to_ask_again():
    guard = Guard(resolve_by_name)
    answers = {"https://example.com/old": (301, "https://example.com/new")}
    route = FakeRoute("https://example.com/old", answers, document=True)

    guard._route(route)

    assert guard.redirect == "https://example.com/new"
    assert route.outcome == ("aborted", "blockedbyclient")


def test_the_guard_lets_non_web_schemes_through_untouched():
    guard = Guard(resolve_by_name)
    route = FakeRoute("data:image/png;base64,AAAA", {})

    guard._route(route)

    assert route.outcome == ("continued", None)


def test_the_guard_looks_each_host_up_once():
    asked = []

    def resolve(host):
        asked.append(host)
        return [PUBLIC]

    guard = Guard(resolve)
    for path in ("a", "b", "c"):
        guard.why_refused(f"https://cdn.example/{path}")

    assert asked == ["cdn.example"]


def test_a_websocket_to_a_private_address_is_never_connected():
    guard = Guard(resolve_by_name)
    connected = []
    socket = types.SimpleNamespace(
        url="ws://internal.example/live", connect_to_server=lambda: connected.append(1)
    )

    guard._socket(socket)

    assert connected == []
    assert guard.refused[0][0] == "ws://internal.example/live"


def test_a_websocket_to_a_public_address_is_connected():
    guard = Guard(resolve_by_name)
    connected = []
    socket = types.SimpleNamespace(
        url="wss://live.example/feed", connect_to_server=lambda: connected.append(1)
    )

    guard._socket(socket)

    assert connected == [1]


def test_a_route_that_nothing_answers_is_aborted_not_left_hanging():
    guard = Guard(resolve_by_name)
    route = FakeRoute("https://down.example/a", {})  # fetch raises KeyError

    guard._route(route)

    assert route.outcome == ("aborted", "failed")


# -- the browser rung, guarded --------------------------------------------------


def fake_browser(monkeypatch, pages, install=True):
    """A scrapling whose browser loads ``pages`` (url -> html or a redirect)."""
    loads = []

    def load(url, **options):
        loads.append(url)
        guard = options["page_setup"].__self__ if "page_setup" in options else None
        if guard is not None and install:
            guard.installed = True
        answer = pages[url]
        if answer.startswith("->"):
            guard.redirect = answer[2:]
            raise RuntimeError("Page.goto: net::ERR_BLOCKED_BY_CLIENT")
        return types.SimpleNamespace(html_content=answer, status=200, url=url)

    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = types.SimpleNamespace()
    module.DynamicFetcher = types.SimpleNamespace(fetch=load)
    module.StealthyFetcher = types.SimpleNamespace(fetch=load)
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)
    fake_curl(monkeypatch, [])
    return loads


def test_the_guarded_browser_asks_for_the_documents_redirect_as_a_new_fetch(
    monkeypatch,
):
    loads = fake_browser(
        monkeypatch,
        {
            "https://example.com/old": "->https://example.com/new",
            "https://example.com/new": "<p>new</p>",
        },
    )
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(allow_private=False, resolve=public))["browser"]
    result = browser("https://example.com/old")

    assert result.url == "https://example.com/new"
    assert loads == ["https://example.com/old", "https://example.com/new"]


def test_the_guarded_browser_refuses_a_document_redirected_somewhere_private(
    monkeypatch,
):
    loads = fake_browser(monkeypatch, {"https://example.com/old": "->http://10.0.0.1/"})
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(allow_private=False, resolve=public))["browser"]
    with pytest.raises(AddressRefused):
        browser("https://example.com/old")

    assert loads == ["https://example.com/old"]


def test_a_guard_that_never_ran_fails_the_rung_instead_of_trusting_it(monkeypatch):
    """scrapling logs and swallows an exception raised in ``page_setup``."""
    fake_browser(monkeypatch, {"https://example.com/p": "<p>hi</p>"}, install=False)
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(allow_private=False, resolve=public))["browser"]
    with pytest.raises(RuntimeError, match="could not guard"):
        browser("https://example.com/p")


def test_the_browsers_page_is_held_to_the_same_bound(monkeypatch):
    fake_browser(monkeypatch, {"https://example.com/p": "<p>" + "x" * 5000 + "</p>"})
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(max_bytes=1000))["browser"]
    with pytest.raises(ResponseTooLarge):
        browser("https://example.com/p")


# -- the ladder ----------------------------------------------------------------


def _rung(name, html="<html><body>ok</body></html>", raises=None, status=200):
    calls = []

    def rung(url):
        calls.append(url)
        if raises is not None:
            raise raises
        return Fetched(url=url, html=html, status=status, rung=name)

    rung.calls = calls
    return rung


def test_a_page_too_heavy_is_never_a_reason_to_climb():
    heavy = _rung("http", raises=ResponseTooLarge("https://example.com/p", 10))
    browser = _rung("browser")

    with pytest.raises(ResponseTooLarge):
        fetch(
            "https://example.com/p",
            rungs=[("http", heavy), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []


def test_the_ladder_holds_an_injected_rung_to_the_bound():
    big = _rung("http", html="<p>" + "x" * 5000 + "</p>")

    with pytest.raises(ResponseTooLarge):
        fetch(
            "https://example.com/p",
            rungs=[("http", big)],
            robots_reader=lambda url: None,
            max_bytes=1000,
        )


def test_a_redirect_refused_inside_a_rung_is_a_refusal_not_a_climb():
    refusing = _rung("http", raises=AddressRefused("http://10.0.0.1/", "private"))
    browser = _rung("browser")

    with pytest.raises(AddressRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", refusing), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []


def test_the_ladder_says_how_long_each_rung_took():
    refused = _rung("http", status=403, html="<html><body>Forbidden</body></html>")
    browser = _rung(
        "browser", html="<html><body>" + "Real text. " * 40 + "</body></html>"
    )

    result = fetch(
        "https://example.com/p",
        rungs=[("http", refused), ("browser", browser)],
        robots_reader=lambda url: None,
    )

    assert result.rung == "browser"
    assert result.seconds >= 0
    assert [climb.seconds >= 0 for climb in result.climbs] == [True]


def test_the_guard_installs_its_route_its_socket_route_and_no_service_workers():
    calls = []
    page = types.SimpleNamespace(
        add_init_script=lambda script: calls.append(
            ("script", "serviceWorker" in script)
        ),
        route=lambda pattern, handler: calls.append(("route", pattern)),
        route_web_socket=lambda pattern, handler: calls.append(("socket", pattern)),
    )
    guard = Guard(resolve_by_name)

    guard.setup(page)

    assert guard.installed
    assert calls == [("script", True), ("route", "**/*"), ("socket", "**/*")]


def test_the_guard_ends_a_subresource_redirect_loop():
    guard = Guard(resolve_by_name)
    answers = {"https://cdn.example/a": (302, "/a")}
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.outcome == ("aborted", "blockedbyclient")
    assert "redirects" in guard.refused[-1][1]


def test_an_address_the_guard_cannot_parse_is_refused():
    assert Guard(resolve_by_name).why_refused("http://[::1") is not None


def test_the_guarded_browser_ends_a_document_redirect_loop(monkeypatch):
    fake_browser(monkeypatch, {"https://example.com/a": "->https://example.com/a"})
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(allow_private=False, resolve=public))["browser"]
    with pytest.raises(RuntimeError, match="redirected more than"):
        browser("https://example.com/a")


def test_a_browser_failure_that_is_not_a_redirect_is_the_rungs_failure(monkeypatch):
    fake_browser(monkeypatch, {})  # every load raises KeyError
    from sluicer.fetch.scrapling_rungs import default_rungs

    browser = dict(default_rungs(allow_private=False, resolve=public))["browser"]
    with pytest.raises(KeyError):
        browser("https://example.com/p")


@pytest.mark.parametrize(
    ("status", "fetched"), [(200, True), (404, True), (503, False)]
)
def test_an_empty_robots_txt_is_judged_by_its_status(monkeypatch, status, fetched):
    """An empty robots.txt has no rules and allows everything (RFC 9309).

    The HTTP rung refuses an empty body, since an empty page is no page, and
    the robots reader built from it took that refusal for an unreachable
    robots.txt: a site whose robots.txt was an empty file could not be fetched
    at all. A 5xx with an empty body is still unreachable.
    """
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.ladder import FetchFailed

    fake_curl(monkeypatch, [(status, b"", {}), PAGE])
    ladder = [("http", http_rung())]

    if fetched:
        assert fetch("https://example.com/p", rungs=ladder).html.startswith("<html>")
    else:
        with pytest.raises(FetchFailed, match="status 503"):
            fetch("https://example.com/p", rungs=ladder)


def test_an_empty_page_is_still_a_rung_that_failed(monkeypatch):
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.result import EmptyBody

    fake_curl(monkeypatch, [(200, b"", {})])

    with pytest.raises(EmptyBody, match="returned no HTML") as raised:
        http_rung()("https://example.com/p")

    assert raised.value.status == 200
    assert isinstance(raised.value, ValueError), "callers catch ValueError"


# -- a caller's rule for redirects ----------------------------------------------


def _same_host(current, target):
    from urllib.parse import urlsplit

    if urlsplit(target).hostname != urlsplit(current).hostname:
        return "it leaves the site"
    return None


def test_a_redirect_the_callers_rule_refuses_is_never_asked(monkeypatch):
    from sluicer.fetch.result import RedirectRefused

    seen = fake_curl(
        monkeypatch, [(301, b"", {"location": "https://elsewhere.example/p"}), PAGE]
    )
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(RedirectRefused) as refused:
        http_rung(redirects=_same_host)("https://example.com/p")

    assert refused.value.url == "https://example.com/p"
    assert refused.value.target == "https://elsewhere.example/p"
    assert refused.value.reason == "it leaves the site"
    assert seen["urls"] == ["https://example.com/p"]


def test_a_redirect_the_callers_rule_allows_is_followed(monkeypatch):
    seen = fake_curl(monkeypatch, [(302, b"", {"location": "/q"}), PAGE])
    from sluicer.fetch.http_rung import http_rung

    result = http_rung(redirects=_same_host)("https://example.com/p")

    assert result.url == "https://example.com/q"
    assert seen["urls"] == ["https://example.com/p", "https://example.com/q"]


def test_the_transport_hands_back_the_bytes_as_they_came(monkeypatch):
    """A sitemap may be gzip nobody announced; decoding it as a page destroys it."""
    import gzip

    body = gzip.compress(b"<urlset/>")
    fake_curl(monkeypatch, [(200, body, {"content-type": "application/x-gzip"})])
    from sluicer.fetch.http_rung import http_responses

    response = http_responses()("https://example.com/sitemap.xml.gz")

    assert response.body == body
    assert response.status == 200
    assert response.content_type == "application/x-gzip"
    assert response.url == "https://example.com/sitemap.xml.gz"


def test_the_guarded_browser_asks_the_callers_rule_about_its_document(monkeypatch):
    from sluicer.fetch.result import RedirectRefused

    loads = fake_browser(
        monkeypatch, {"https://example.com/old": "->https://elsewhere.example/new"}
    )
    from sluicer.fetch.scrapling_rungs import default_rungs

    rungs = default_rungs(allow_private=False, resolve=public, redirects=_same_host)
    with pytest.raises(RedirectRefused):
        dict(rungs)["browser"]("https://example.com/old")

    assert loads == ["https://example.com/old"]


def test_a_redirect_the_callers_rule_refused_is_not_a_reason_to_climb():
    from sluicer.fetch.result import RedirectRefused

    refusing = _rung(
        "http",
        raises=RedirectRefused("https://example.com/p", "https://b.example/", "no"),
    )
    browser = _rung("browser")

    with pytest.raises(RedirectRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", refusing), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []
