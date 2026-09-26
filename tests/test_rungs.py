"""The default ladder and the browser rung, without a browser.

The HTTP rung talks to ``tests/fake_wire.py``'s sockets and the browser rung
drives ``tests/fake_browser.py``'s host, so what each is told can be read
back. What a real Chromium does with it is ``tests/live/guard_check.py``'s
question.
"""

import sys
import threading
import types

import pytest

from fake_browser import FakeHost
from fake_wire import fake_http
from sluicer.fetch.identity import USER_AGENT

PAGE = (200, b"<html><body>ok</body></html>", {})
SHELL = (
    '<html><head><script src="/app.js"></script></head>'
    '<body><div id="root"></div></body></html>'
)
RENDERED = "<html><body>" + "Real text, rendered. " * 30 + "</body></html>"


def _browser(pages, **options):
    from sluicer.fetch.browser import browser_rung

    host = FakeHost(pages)
    return browser_rung(host=host, **options), host


def test_the_default_rungs_come_back_in_cost_order(monkeypatch):
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    from sluicer.fetch.rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http", "browser"]


def test_a_machine_without_a_browser_can_say_so(monkeypatch):
    monkeypatch.setenv("SLUICER_BROWSER", "none")
    from sluicer.fetch.rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http"]


def test_plain_http_needs_neither_scrapling_nor_a_browser(monkeypatch, absent):
    """Measured on 0.7.0: with scrapling absent, fetch() raised
    FetchExtraMissing before the HTTP rung was even built, so no URL could be
    read at all in an install without the browsers."""
    absent("scrapling", "playwright", "curl_cffi")
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.rungs import default_rungs

    page = dict(default_rungs())["http"]("https://example.com/p")

    assert page.html == "<html><body>ok</body></html>"
    assert seen.requests[0].headers["user-agent"] == USER_AGENT


def test_a_missing_browser_is_a_climb_that_failed_and_says_how_to_install_it(
    monkeypatch, absent
):
    absent("playwright")
    fake_http(
        monkeypatch,
        [(404, b"", {}), (200, SHELL.encode(), {"Content-Type": "text/html"})],
    )
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    from sluicer.fetch import fetch

    page = fetch("https://example.com/app")

    assert page.rung == "http"
    assert [(c.from_rung, c.to_rung) for c in page.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
    ]
    assert 'Install it with: pip install "sluicer[browser]"' in page.climbs[1].reason


def test_the_browser_says_who_it_is_and_nothing_more(monkeypatch):
    """scrapling's defaults dropped --enable-automation, chose a dark scheme
    and a doubled pixel ratio -- its own comments call them anti-detection --
    and would have sent a Google referer. A page's context here is told our
    name, no service workers, and no proxy."""
    monkeypatch.delenv("SLUICER_PROXY", raising=False)
    browser, host = _browser({"https://example.com/p": "<p>hi</p>"})

    page = browser("https://example.com/p")

    assert page.rung == "browser"
    assert host.contexts[0].options == {
        "user_agent": USER_AGENT,
        "service_workers": "block",
    }
    assert host.contexts[0].closed


def test_the_browser_is_launched_sandboxed_with_no_proxy_of_its_own(monkeypatch):
    """Playwright launches Chromium with --no-sandbox unless told otherwise:
    measured on 0.8.0, the browser that renders any page it is sent ran its
    renderers with no sandbox."""
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.delenv("SLUICER_BROWSER_SANDBOX", raising=False)
    launched = {}

    def launch(**options):
        launched.update(options)
        return "browser"

    from sluicer.fetch.browser import _open

    playwright = types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch))
    assert _open(playwright) == "browser"
    assert launched == {
        "args": [
            "--no-proxy-server",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ],
        "chromium_sandbox": True,
    }


@pytest.mark.parametrize("off", ["0", "off", "no", "false"])
def test_the_sandbox_is_turned_off_only_when_asked(monkeypatch, off):
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.setenv("SLUICER_BROWSER_SANDBOX", off)
    launched = {}

    def launch(**options):
        launched.update(options)
        return "browser"

    from sluicer.fetch.browser import _open

    _open(types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch)))
    assert launched["chromium_sandbox"] is False


def test_a_sandbox_that_cannot_start_says_how_to_run_without_it(monkeypatch):
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.delenv("SLUICER_BROWSER_SANDBOX", raising=False)

    class Error(Exception):
        pass

    def launch(**options):
        raise Error(
            "BrowserType.launch: Target page, context or browser has been closed\n"
            "[pid=1][err] No usable sandbox! Update your kernel"
        )

    from sluicer.fetch.browser import _open

    with pytest.raises(RuntimeError, match="SLUICER_BROWSER_SANDBOX=0"):
        _open(types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch)))


def test_a_browser_elsewhere_is_driven_over_cdp(monkeypatch):
    monkeypatch.setenv("SLUICER_CDP_URL", "ws://127.0.0.1:9222/devtools/browser/x")
    from sluicer.fetch.browser import _open

    playwright = types.SimpleNamespace(
        chromium=types.SimpleNamespace(
            connect_over_cdp=lambda url: ("remote", url),
            launch=lambda **kw: pytest.fail("launched a browser beside the remote one"),
        )
    )
    assert _open(playwright) == ("remote", "ws://127.0.0.1:9222/devtools/browser/x")


@pytest.mark.parametrize(
    ("asked", "server"),
    [
        ("http://proxy.example:3128", {"server": "http://proxy.example:3128"}),
        ("socks5h://proxy.example:1080", {"server": "socks5://proxy.example:1080"}),
        (
            "http://me:pw@proxy.example:3128",
            {
                "server": "http://proxy.example:3128",
                "username": "me",
                "password": "pw",
            },
        ),
    ],
)
def test_the_browser_goes_through_the_proxy_asked_for(asked, server):
    browser, host = _browser({"https://example.com/p": "<p>hi</p>"}, proxy=asked)

    browser("https://example.com/p")

    assert host.contexts[0].options["proxy"] == server


def test_a_browser_answer_keeps_its_headers_names_lowercased_repeats_joined():
    browser, _ = _browser({"https://example.com/p": "<p>hi</p>"})

    page = browser("https://example.com/p")

    assert page.headers == {
        "x-robots-tag": "noindex",
        "link": "</a>; rel=canonical, </b>; rel=next",
    }


def test_the_page_a_browser_landed_on_is_the_one_reported():
    """An unguarded browser follows a redirect itself; the page says where."""
    browser, _ = _browser(
        {
            "https://example.com/start": "->https://example.com/final",
            "https://example.com/final": "<p>there</p>",
        }
    )

    assert browser("https://example.com/start").url == "https://example.com/final"


def test_one_browser_serves_every_page_of_the_process_from_one_thread():
    """A browser launched per page was 1.18 s and 1.1 GB a page, measured;
    kept, a page costs a context. Playwright's objects belong to the thread
    that made them, so the pages asked from other threads run on its one."""
    from sluicer.fetch.browser import BrowserHost

    threads = []
    opened = []

    class Browser:
        def is_connected(self):
            return True

        def close(self):
            pass

    def job(browser):
        threads.append(threading.current_thread().name)
        return browser

    host = BrowserHost(open=lambda playwright: opened.append(1) or Browser())
    sync_api = types.ModuleType("playwright.sync_api")

    class Driver:
        def __enter__(self):
            return object()

        def __exit__(self, *exc):
            return False

    sync_api.sync_playwright = Driver
    modules = {
        "playwright": types.ModuleType("playwright"),
        "playwright.sync_api": sync_api,
    }
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        answers = []
        callers = [
            threading.Thread(target=lambda: answers.append(host.run(job, wait=10)))
            for _ in range(4)
        ]
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join()
        host.close()
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert len(answers) == 4 and len({id(a) for a in answers}) == 1
    assert opened == [1]
    assert set(threads) == {"sluicer-browser"}


def test_a_browser_that_will_not_start_fails_the_page_and_the_next_page_tries_again():
    from sluicer.fetch.browser import BrowserHost

    attempts = []

    def refuse(playwright):
        attempts.append(1)
        raise RuntimeError("Executable doesn't exist; run playwright install")

    host = BrowserHost(open=refuse)
    sync_api = types.ModuleType("playwright.sync_api")

    class Driver:
        def __enter__(self):
            return object()

        def __exit__(self, *exc):
            return False

    sync_api.sync_playwright = Driver
    saved = {n: sys.modules.get(n) for n in ("playwright", "playwright.sync_api")}
    sys.modules["playwright"] = types.ModuleType("playwright")
    sys.modules["playwright.sync_api"] = sync_api
    try:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="playwright install"):
                host.run(lambda browser: browser, wait=10)
        host.close()
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert attempts == [1, 1]


def test_a_rung_tries_once_and_gives_up_in_bounded_time():
    """Three retries of thirty seconds on each rung was three minutes for one
    slow page, longer than an agent's tool call waits."""
    from sluicer.fetch.browser import BROWSER_TIMEOUT_MS
    from sluicer.fetch.http_rung import HTTP_TIMEOUT_SECONDS

    assert HTTP_TIMEOUT_SECONDS <= 20
    assert BROWSER_TIMEOUT_MS <= 30_000


# -- the caller's headers and cookies, in the browser ---------------------------


def test_the_callers_cookies_are_set_for_the_origin_asked():
    browser, host = _browser(
        {"https://example.com/p": "<p>hi</p>"}, cookies={"session": "abc"}
    )

    browser("https://example.com/p")

    assert host.contexts[0].cookies == [
        {"name": "session", "value": "abc", "url": "https://example.com"}
    ]


def test_the_callers_headers_go_only_to_the_origin_asked_unguarded():
    browser, host = _browser(
        {"https://example.com/p": "<p>hi</p>"}, headers={"Authorization": "Bearer t"}
    )
    browser("https://example.com/p")
    route = host.contexts[0].routes[0][1]
    continued = []

    def request(url):
        handled = types.SimpleNamespace(
            request=types.SimpleNamespace(url=url, headers={"accept": "*/*"}),
            continue_=lambda **kw: continued.append((url, kw)),
        )
        route(handled)

    request("https://example.com/api")
    request("https://cdn.example/lib.js")

    assert continued == [
        (
            "https://example.com/api",
            {"headers": {"accept": "*/*", "Authorization": "Bearer t"}},
        ),
        ("https://cdn.example/lib.js", {}),
    ]


def test_a_browser_built_for_an_origin_sends_its_login_there_alone():
    """Handed an address of the site over plain http, as a crawl of an https
    site follows its http links, the browser set the cookies for that origin
    and sent the headers there: the origin a login goes to is fixed when the
    rung is built, and a cookie set for https is Secure."""
    browser, host = _browser(
        {"http://example.com/p": "<p>hi</p>"},
        headers={"Authorization": "Bearer t"},
        cookies={"session": "abc"},
        send_to=["https://example.com/"],
    )
    browser("http://example.com/p")
    route = host.contexts[0].routes[0][1]
    continued = []

    for url in ("http://example.com/api", "https://example.com/api"):
        route(
            types.SimpleNamespace(
                request=types.SimpleNamespace(url=url, headers={}),
                continue_=lambda url=url, **kw: continued.append((url, kw)),
            )
        )

    assert host.contexts[0].cookies == [
        {"name": "session", "value": "abc", "url": "https://example.com"}
    ]
    assert continued == [
        ("http://example.com/api", {}),
        ("https://example.com/api", {"headers": {"Authorization": "Bearer t"}}),
    ]


def test_the_default_ladder_hands_the_browser_its_cookies_apart_from_its_headers(
    monkeypatch,
):
    """A browser writes its Cookie header from its own jar, so cookies are set
    in the context, and the other headers ride the route."""
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    host = FakeHost({"https://example.com/p": "<p>hi</p>"})
    monkeypatch.setattr("sluicer.fetch.browser.HOST", host)
    from sluicer.fetch.rungs import default_rungs

    rungs = default_rungs(
        headers={"X-Team": "a", "Cookie": "theme=dark"}, cookies={"session": "1"}
    )
    dict(rungs)["browser"]("https://example.com/p")

    assert sorted(c["name"] for c in host.contexts[0].cookies) == ["session", "theme"]
    assert [pattern for pattern, _ in host.contexts[0].routes] == ["**/*"]


@pytest.mark.parametrize("given", ["firefox", "nnone", "off"])
def test_a_browser_the_environment_names_and_sluicer_does_not_drive_is_refused(
    monkeypatch, given
):
    """Measured on 0.9.0: SLUICER_BROWSER=firefox, or a typo of none, was
    Chromium in silence."""
    from sluicer.fetch.browser import UnknownBrowser
    from sluicer.fetch.rungs import default_rungs

    monkeypatch.setenv("SLUICER_BROWSER", given)

    with pytest.raises(UnknownBrowser, match=r"chromium .* or none"):
        default_rungs()


@pytest.mark.parametrize(("given", "rungs"), [("", 2), (" Chromium ", 2), ("NONE", 1)])
def test_the_browsers_sluicer_drives_are_still_read(monkeypatch, given, rungs):
    from sluicer.fetch.rungs import default_rungs

    monkeypatch.setenv("SLUICER_BROWSER", given)

    assert len(default_rungs()) == rungs


def test_the_commands_refuse_an_unknown_browser_before_they_start(monkeypatch):
    from click.testing import CliRunner

    from sluicer.cli import main

    asked = []
    monkeypatch.setattr(
        "sluicer.cli.source.fetch_url", lambda url, **kw: asked.append(url)
    )
    monkeypatch.setenv("SLUICER_BROWSER", "firefox")

    result = CliRunner().invoke(main, ["fetch", "https://example.com/"])

    assert asked == []
    assert result.exit_code == 2
    assert "SLUICER_BROWSER='firefox' is not a browser Sluicer drives" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "command",
    [
        ["extract", "{page}"],
        ["inspect", "{page}"],
        ["select", "{page}", "h1"],
        ["markdown", "{page}"],
        ["audit", "{page}"],
        ["compile", "{page}", "--want", "title=Kettle", "-o", "{out}"],
    ],
    ids=lambda c: c[0],
)
def test_an_unknown_browser_is_no_matter_for_a_command_that_fetches_nothing(
    monkeypatch, tmp_path, command
):
    """The hostile review of 0.9.1: SLUICER_BROWSER=firefox made `sluicer
    extract E.html` of a local file exit 2 (0.9.0: 0), where no browser could
    run, while SLUICER_PROXY=ftp://x did not."""
    if command[0] == "markdown":
        pytest.importorskip("trafilatura")
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "E.html"
    page.write_text(
        "<html><head><title>Kettle</title></head><body><h1>Kettle</h1></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setenv("SLUICER_BROWSER", "firefox")
    args = [part.format(page=page, out=tmp_path / "e.json") for part in command]

    result = CliRunner().invoke(main, args)

    assert "SLUICER_BROWSER" not in result.output
    assert result.exit_code in (0, 1), result.output


@pytest.mark.parametrize(
    "command",
    [
        ["extract", "https://example.com/"],
        ["compile", "https://example.com/", "--want", "title=A", "-o", "e.json"],
        ["crawl", "https://example.com/"],
        ["batch", "-"],
        ["map", "https://example.com/"],
    ],
    ids=lambda c: c[0],
)
def test_an_unknown_browser_is_refused_before_an_address_is_fetched(
    monkeypatch, command
):
    from click.testing import CliRunner

    from sluicer.cli import main

    def refuse(*args, **kwargs):
        raise AssertionError("fetched")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", refuse)
    monkeypatch.setattr("sluicer.cli.sites.crawl", refuse, raising=False)
    monkeypatch.setattr("sluicer.cli.sites.extract_many", refuse, raising=False)
    monkeypatch.setattr("sluicer.cli.sites.map_site", refuse, raising=False)
    monkeypatch.setenv("SLUICER_BROWSER", "firefox")

    result = CliRunner().invoke(main, command, input="https://example.com/\n")

    assert result.exit_code == 2, result.output
    assert "SLUICER_BROWSER='firefox' is not a browser Sluicer drives" in result.stderr
    assert "fetched" not in result.output
