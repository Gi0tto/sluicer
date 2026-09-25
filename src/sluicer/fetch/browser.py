"""The browser rung: Playwright's Chromium, driven directly, one for the process.

Launching a browser costs a quarter of a second and most of a gigabyte;
loading a page in one already running costs a context. So the process keeps
one browser (``BrowserHost``), started at the first page that needs it and
closed when the process ends, and every page gets a new context of its own:
no cookie, cache or storage of one page is seen by the next.

Playwright's synchronous objects belong to the thread that made them, and
pages are asked for from many -- a crawl's pool, the MCP server's workers --
so the host drives the browser from one thread of its own and hands each
page to it as a job. Pages are loaded one at a time.

What the browser is told, and nothing more: our ``User-Agent``, no service
workers, no proxy unless one was asked for. None of the flags a stealth
browser adds, no borrowed referer, no dark scheme or doubled pixel ratio.
Each page waits for its load, then for the network to go quiet, both within
``BROWSER_TIMEOUT_MS``; a page whose network never goes quiet is read as it
stands then.

With ``allow_private`` false, every request the page makes goes through
``sluicer.fetch.browser_guard``, installed on the page's context before it
navigates; a guard that did not install fails the rung. And every connection
the browser makes for the page -- a speculation rule's prefetch, a WebRTC
TURN server, which no route sees -- goes through
``sluicer.fetch.browser_proxy``, the context's proxy, which judges each one
by the same rule and connects only to the addresses it checked. WebRTC's UDP,
which no proxy carries, is off.

Backends, chosen by the environment:

* ``SLUICER_BROWSER=chromium`` (the default): Playwright's own Chromium,
  installed once with ``playwright install chromium``.
* ``SLUICER_CDP_URL=ws://...`` or ``http://...``: a Chromium already running
  elsewhere, reached over the DevTools protocol (``connect_over_cdp``). The
  guard still judges every request by Sluicer's resolver; the browser
  resolves names in its own network, so "private" means private to this
  host, not to the browser's.
* ``SLUICER_BROWSER=none``: no browser rung at all, for a machine that has
  none. A page that wanted one comes back from plain HTTP.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import queue
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.address import AddressRefused, _resolve
from sluicer.fetch.browser_guard import MAX_REDIRECTS, Guard, same_origin
from sluicer.fetch.http_rung import chosen_proxy
from sluicer.fetch.identity import USER_AGENT
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    Fetched,
    RedirectRefused,
    Redirects,
    ResponseTooLarge,
    Rung,
)
from sluicer.fetch.wire import Proxy

BROWSER_ENV = "SLUICER_BROWSER"
"""Which browser the rung drives: ``chromium`` (the default) or ``none``."""

CDP_ENV = "SLUICER_CDP_URL"
"""The address of a running Chromium to drive over the DevTools protocol,
instead of launching one."""

SANDBOX_ENV = "SLUICER_BROWSER_SANDBOX"
"""``0`` (or ``off``, ``no``, ``false``) launches Chromium without its
sandbox. It is on otherwise: Playwright's own default is off, and the browser
renders pages sent by anyone."""

BROWSER_TIMEOUT_MS = 30_000
"""How long the browser rung waits for one page, in Playwright's milliseconds.

It bounds each thing the browser waits on -- the page's load, then the network
going quiet -- not the rung as a whole. One try per rung keeps a slow site to
that and to ``HTTP_TIMEOUT_SECONDS`` for plain HTTP, the body included.
"""

WAIT_SECONDS = 180.0
"""The longest a caller waits for its page, queue included, before the rung
fails: pages are loaded one at a time, and a browser that stopped answering
must not hold its callers for ever."""


def browser_wanted() -> bool:
    """Whether the environment asks for a browser rung at all."""
    return os.environ.get(BROWSER_ENV, "chromium").strip().lower() != "none"


@dataclass
class Loaded:
    """What the browser made of one address."""

    url: str
    html: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)


Job = Callable[[Any], Any]


class BrowserHost:
    """One browser for the process, driven from a thread of its own.

    ``run(job)`` hands ``job`` the browser on that thread and returns what it
    returns, or raises what it raised. The thread, the Playwright driver and
    the browser start at the first job and end with the process (``close``).
    ``open`` is how the browser is started, given Playwright's handle;
    injected by tests, which never start one.
    """

    def __init__(self, open: Callable[[Any], Any] | None = None) -> None:
        self.open = open or _open
        self.launched = 0
        """How many browsers this host has started: one, while nothing crashes."""
        self._jobs: queue.Queue[tuple[Job, Future[Any]] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def run(self, job: Job, wait: float = WAIT_SECONDS) -> Any:
        # In the caller's thread, so a missing extra is the caller's failure
        # and says how to install it; the thread would only report it later.
        import_extra(
            "playwright.sync_api",
            "browser",
            doing="Loading a page in a browser",
            error=_missing(),
        )
        done: Future[Any] = Future()
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._drive, daemon=True, name="sluicer-browser"
                )
                self._thread.start()
            self._jobs.put((job, done))
        try:
            return done.result(timeout=wait)
        except FutureTimeout:
            done.cancel()
            raise TimeoutError(
                f"the browser did not load the page within {wait:g} seconds"
            ) from None

    def close(self) -> None:
        """End the browser and its thread, waiting a little for both."""
        with self._lock:
            thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            self._jobs.put(None)
            thread.join(timeout=10)

    def _drive(self) -> None:
        api = import_extra(
            "playwright.sync_api",
            "browser",
            doing="Loading a page in a browser",
            error=_missing(),
        )
        try:
            with api.sync_playwright() as playwright:
                self._serve(playwright)
        except BaseException as failure:  # noqa: BLE001 -- handed to every waiter
            self._fail_waiting(failure)

    def _serve(self, playwright: Any) -> None:
        browser = None
        try:
            while True:
                item = self._jobs.get()
                if item is None:
                    return
                job, done = item
                if not done.set_running_or_notify_cancel():
                    continue
                try:
                    if browser is None or not browser.is_connected():
                        browser = self.open(playwright)
                        self.launched += 1
                    done.set_result(job(browser))
                except BaseException as failure:  # noqa: BLE001 -- the job's
                    done.set_exception(failure)
        finally:
            if browser is not None:
                # Closing at the end is best effort: the process is leaving.
                with contextlib.suppress(Exception):
                    browser.close()

    def _fail_waiting(self, failure: BaseException) -> None:
        while True:
            try:
                item = self._jobs.get_nowait()
            except queue.Empty:
                return
            if item is not None and item[1].set_running_or_notify_cancel():
                item[1].set_exception(failure)


def _missing() -> type[MissingExtra]:
    from sluicer.fetch.rungs import FetchExtraMissing

    return FetchExtraMissing


def _open(playwright: Any) -> Any:
    """The browser: the one at ``SLUICER_CDP_URL``, or a Chromium launched.

    Launched with no proxy of its own, so neither the system's nor the
    environment's is used; a page's context is given the one asked for. And
    in its sandbox, unless ``SLUICER_BROWSER_SANDBOX`` turns it off: Playwright
    passes ``--no-sandbox`` by default, and a renderer that a page's code
    breaks out of would then be this process's user. A sandbox that cannot
    start -- a container whose seccomp profile refuses the namespaces it
    needs, an Ubuntu that restricts them -- fails the launch with a message
    that says so.
    """
    remote = os.environ.get(CDP_ENV, "").strip()
    if remote:
        return playwright.chromium.connect_over_cdp(remote)
    sandboxed = os.environ.get(SANDBOX_ENV, "").strip().lower() not in {
        "0",
        "off",
        "no",
        "false",
    }
    try:
        return playwright.chromium.launch(
            args=[
                "--no-proxy-server",
                # WebRTC over UDP goes past any proxy, the guard's included:
                # measured, a page reached a STUN server on a private address.
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ],
            chromium_sandbox=sandboxed,
        )
    except Exception as failure:
        if sandboxed and "sandbox" in str(failure).lower():
            raise RuntimeError(
                "Chromium could not start its sandbox here. In a container, run "
                "it with a seccomp profile that allows user namespaces (or "
                "--cap-add SYS_ADMIN); on Ubuntu 23.10 and later, allow them "
                "(sysctl kernel.apparmor_restrict_unprivileged_userns=0). Or set "
                f"{SANDBOX_ENV}=0 to run the browser without it, the machine or "
                f"the container then its only boundary. Chromium said: {failure}"
            ) from failure
        raise


HOST = BrowserHost()
"""The process's browser."""
atexit.register(HOST.close)


def _context_options(proxy: str | None, through: str | None = None) -> dict[str, Any]:
    """A page's context: our name, no service workers, the proxy asked for.

    ``through`` is a guard proxy's address, which is then the context's proxy,
    loopback included -- Chromium passes loopback by a proxy unless its
    bypass list says ``<-loopback>`` -- and the one asked for its way out.
    """
    options: dict[str, Any] = {"user_agent": USER_AGENT, "service_workers": "block"}
    if through is not None:
        options["proxy"] = {"server": through, "bypass": "<-loopback>"}
        return options
    chosen = chosen_proxy(proxy)
    if chosen is not None:
        named = Proxy.parse(chosen)
        # Chromium's socks5 always lets the proxy resolve names: socks5h.
        scheme = "socks5" if named.scheme.startswith("socks5") else named.scheme
        server: dict[str, str] = {"server": f"{scheme}://{named.host}:{named.port}"}
        if named.username is not None:
            server["username"] = named.username
            server["password"] = named.password or ""
        options["proxy"] = server
    return options


def _load(
    url: str,
    guard: Guard | None,
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    asked: Sequence[str],
    proxy: str | None,
    through: str | None = None,
) -> Job:
    """The job that loads ``url`` in a new context of the browser.

    ``cookies`` are set for each origin in ``asked``: for its host alone, and
    over https only when it is https's -- Playwright marks a cookie set for
    an https address ``Secure``.
    """

    def job(browser: Any) -> Loaded | None:
        context = browser.new_context(**_context_options(proxy, through))
        try:
            if cookies:
                context.add_cookies(
                    [
                        {"name": k, "value": v, "url": origin}
                        for origin in dict.fromkeys(_origin_of(a) for a in asked)
                        for k, v in cookies.items()
                    ]
                )
            if guard is not None:
                guard.setup(context)
            elif headers:
                context.route("**/*", _adding(headers, asked))
            page = context.new_page()
            try:
                response = page.goto(url, wait_until="load", timeout=BROWSER_TIMEOUT_MS)
            except Exception:
                if guard is not None and guard.redirect is not None:
                    return None
                raise
            try:
                page.wait_for_load_state("networkidle", timeout=BROWSER_TIMEOUT_MS)
            except Exception as quiet:
                if "Timeout" not in type(quiet).__name__:
                    raise
            if response is None:
                raise ValueError(f"the browser rung got no response for {url!r}")
            pairs = response.headers_array()
            found: dict[str, str] = {}
            for pair in pairs:
                key = str(pair["name"]).lower()
                value = str(pair["value"])
                found[key] = f"{found[key]}, {value}" if key in found else value
            return Loaded(page.url, page.content(), int(response.status), found)
        finally:
            context.close()

    return job


def _origin_of(address: str) -> str:
    parts = urlsplit(address)
    return f"{parts.scheme}://{parts.netloc}"


def _adding(headers: Mapping[str, str], asked: Sequence[str]) -> Callable[[Any], None]:
    """A route that adds the caller's headers to requests for the origins
    asked, and to none elsewhere: the page's other hosts are not the
    caller's."""

    def route(handled: Any) -> None:
        request = handled.request
        if any(same_origin(request.url, one) for one in asked):
            handled.continue_(headers={**request.headers, **headers})
        else:
            handled.continue_()

    return route


def browser_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    host: BrowserHost | None = None,
    send_to: Iterable[str] | None = None,
) -> Rung:
    """Build the browser rung.

    Args:
        allow_private: when false, every request the page makes is judged
            first (``browser_guard``), and the document's own redirects are
            asked again as new loads, judged like the first.
        resolve: the name lookup that judgement uses.
        max_bytes: the most the page's HTML may weigh.
        redirects: a caller's rule for the document's redirects; asked only
            when guarded, since an unguarded browser follows a redirect itself.
        proxy: as for the HTTP rung; ``SLUICER_PROXY`` when None.
        headers: sent with the requests for the origin asked, and no other.
        cookies: set in the page's context for the origin asked.
        host: the browser; the process's by default.
        send_to: the addresses whose origins -- scheme, host and port --
            ``headers`` and ``cookies`` are for, fixed here; None, the origin
            of each address the rung is handed.
    """
    sent = dict(headers or {})
    crumbs = dict(cookies or {})
    driver = host if host is not None else HOST
    fixed = tuple(send_to) if send_to is not None else None

    def rung(url: str) -> Fetched:
        asked = fixed if fixed is not None else (url,)
        if allow_private:
            loaded = driver.run(_load(url, None, sent, crumbs, asked, proxy))
            return _as_fetched(loaded, url, max_bytes)
        through = _guard_proxy(resolve, proxy)
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            guard = Guard(resolve, send=sent, asked=asked)
            loaded = driver.run(
                _load(current, guard, sent, crumbs, asked, proxy, through)
            )
            if not guard.installed:
                raise RuntimeError(
                    "the browser rung could not guard the page's requests, so it "
                    "made none it could vouch for"
                )
            if guard.redirect is not None:
                # The document was sent elsewhere: ask for it as a new load.
                target = guard.redirect
                ruled = redirects(current, target) if redirects else None
                if ruled is not None:
                    raise RedirectRefused(current, target, ruled)
                refused = guard.why_refused(target)
                if refused is not None:
                    raise AddressRefused(target, refused)
                current = target
                continue
            return _as_fetched(loaded, current, max_bytes)
        raise RuntimeError(f"{url} redirected more than {MAX_REDIRECTS} times")

    return rung


def _guard_proxy(
    resolve: Callable[[str], Iterable[str]], proxy: str | None
) -> str | None:
    """The address of the guard proxy a guarded page's context goes through,
    the proxy asked for its way out; None for a browser elsewhere
    (``SLUICER_CDP_URL``), which cannot reach this machine's loopback, and
    whose pages the guard's routes alone judge."""
    if os.environ.get(CDP_ENV, "").strip():
        return None
    from sluicer.fetch.browser_proxy import guard_proxy

    return guard_proxy(resolve, chosen_proxy(proxy)).address


def _as_fetched(loaded: Loaded | None, url: str, max_bytes: int) -> Fetched:
    """The page the browser loaded, once its HTML is within the bound."""
    if loaded is None:
        raise ValueError(f"the browser rung returned no HTML for {url!r}")
    if len(loaded.html) > max_bytes or len(loaded.html.encode()) > max_bytes:
        raise ResponseTooLarge(loaded.url or url, max_bytes)
    return Fetched(
        url=loaded.url or url,
        html=loaded.html,
        status=loaded.status,
        rung="browser",
        headers=loaded.headers,
    )
