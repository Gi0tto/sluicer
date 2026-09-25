"""The guard proxy every connection of a guarded page goes through.

Driven over socket pairs, with the address check and the way out replaced:
the suite never connects anywhere, and a job of CI holds it to that.
tests/live/guard_check.py drives it with a real Chromium.
"""

from __future__ import annotations

import base64
import socket
import threading

import pytest

from sluicer.fetch import browser_proxy
from sluicer.fetch.address import AddressRefused
from sluicer.fetch.browser_proxy import GuardProxy, guard_proxy


def _login(proxy: GuardProxy) -> bytes:
    pair = f"{proxy.username}:{proxy.password}".encode()
    return b"Proxy-Authorization: Basic " + base64.b64encode(pair) + b"\r\n"


def _served(proxy: GuardProxy, request: bytes, then: bytes = b"") -> bytes:
    """What the proxy answers a browser that sends ``request``, then ``then``."""
    browser, served = socket.socketpair()
    worker = threading.Thread(target=proxy._serve, args=(served,), daemon=True)
    worker.start()
    browser.sendall(request + then)
    browser.shutdown(socket.SHUT_WR)
    answer = b""
    browser.settimeout(5)
    while chunk := browser.recv(65536):
        answer += chunk
    browser.close()
    worker.join(5)
    return answer


class _Site:
    """A site the proxy connects to: one end of a socket pair, which reads
    what it is sent and answers ``reply``."""

    def __init__(self, reply: bytes) -> None:
        self.ours, self.theirs = socket.socketpair()
        self.heard = b""
        self.reply = reply
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.ours.settimeout(5)
        while b"\r\n\r\n" not in self.heard:
            chunk = self.ours.recv(65536)
            if not chunk:
                break
            self.heard += chunk
        self.ours.sendall(self.reply)
        self.ours.close()


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setattr(
        browser_proxy, "public_addresses", lambda url, resolve: ["203.0.113.7"]
    )
    made = GuardProxy(resolve=lambda host: ["203.0.113.7"])
    yield made
    made.close()


def test_a_request_without_the_proxy_s_own_credentials_is_refused(proxy):
    """Found by review: the guard proxy listened on 127.0.0.1 with no
    credentials, so any process on the machine could use it -- and through it
    the caller's own proxy, whose credentials it adds."""
    ask = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n"

    bare = _served(proxy, ask + b"\r\n")
    wrong = _served(proxy, ask + b"Proxy-Authorization: Basic c2x1aWNlcjp4\r\n\r\n")

    assert bare.startswith(b"HTTP/1.1 407 ") and b"Proxy-Authenticate: Basic" in bare
    assert wrong.startswith(b"HTTP/1.1 407 ")
    assert len(proxy.password) >= 32
    assert GuardProxy().password != proxy.password


def test_a_plain_request_reaches_the_site_as_one_request_that_closes(
    proxy, monkeypatch
):
    site = _Site(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi")
    dialled = []

    def connect(addresses, port, deadline):
        dialled.append((addresses, port))
        return site.theirs, addresses[0]

    monkeypatch.setattr(browser_proxy, "_connect", connect)
    request = (
        b"GET http://example.com:8080/a?b=1 HTTP/1.1\r\nHost: example.com:8080\r\n"
        b"Proxy-Connection: keep-alive\r\n" + _login(proxy) + b"\r\n"
    )

    answer = _served(proxy, request)
    site.thread.join(5)

    assert answer.endswith(b"hi")
    assert dialled == [(["203.0.113.7"], 8080)]
    assert site.heard.startswith(b"GET /a?b=1 HTTP/1.1\r\n")
    assert b"Connection: close" in site.heard
    assert b"Proxy-Authorization" not in site.heard
    assert b"Proxy-Connection" not in site.heard


def test_a_tunnel_is_established_and_carries_bytes_both_ways(proxy, monkeypatch):
    site = _Site(b"server hello")
    monkeypatch.setattr(
        browser_proxy, "_connect", lambda addresses, port, deadline: (site.theirs, "")
    )
    request = b"CONNECT example.com:443 HTTP/1.1\r\n" + _login(proxy) + b"\r\n"

    answer = _served(proxy, request, then=b"client hello\r\n\r\n")
    site.thread.join(5)

    assert answer.startswith(b"HTTP/1.1 200 Connection established\r\n\r\n")
    assert answer.endswith(b"server hello")
    assert site.heard == b"client hello\r\n\r\n"


def test_a_private_address_is_refused_and_remembered(monkeypatch):
    def refuse(url, resolve):
        raise AddressRefused(url, "a private address")

    monkeypatch.setattr(browser_proxy, "public_addresses", refuse)
    proxy = GuardProxy()
    try:
        request = b"CONNECT intranet.example:443 HTTP/1.1\r\n" + _login(proxy) + b"\r\n"
        answer = _served(proxy, request)
    finally:
        proxy.close()

    assert answer.startswith(b"HTTP/1.1 403 ")
    assert proxy.refused[-1][0] == "http://intranet.example:443/"


def test_a_site_it_cannot_reach_is_a_bad_gateway(proxy, monkeypatch):
    def fail(addresses, port, deadline):
        raise OSError("connection refused")

    monkeypatch.setattr(browser_proxy, "_connect", fail)
    request = b"CONNECT example.com:443 HTTP/1.1\r\n" + _login(proxy) + b"\r\n"

    assert _served(proxy, request).startswith(b"HTTP/1.1 502 ")


@pytest.mark.parametrize(
    "request_",
    [b"GET /relative HTTP/1.1\r\n\r\n", b"x" * (browser_proxy.HEAD_BYTES + 10), b""],
)
def test_what_is_no_request_it_serves_is_a_bad_request_or_nothing(proxy, request_):
    answer = _served(proxy, request_)

    assert answer == b"" or answer.startswith(b"HTTP/1.1 400 ")


def test_an_http_proxy_as_the_way_out_is_asked_for_the_whole_address(monkeypatch):
    monkeypatch.setattr(
        browser_proxy, "public_addresses", lambda url, resolve: ["203.0.113.7"]
    )
    upstream = browser_proxy.Proxy.parse("http://alice:secret@proxy.example:3128")
    site = _Site(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
    monkeypatch.setattr(
        browser_proxy, "_resolved", lambda host, port, d: ["198.51.100.1"]
    )
    monkeypatch.setattr(
        browser_proxy, "_connect", lambda addresses, port, deadline: (site.theirs, "")
    )
    proxy = GuardProxy(upstream=upstream)
    try:
        request = b"GET http://example.com/p HTTP/1.1\r\nHost: example.com\r\n"
        _served(proxy, request + _login(proxy) + b"\r\n")
    finally:
        proxy.close()
    site.thread.join(5)

    assert site.heard.startswith(b"GET http://example.com/p HTTP/1.1\r\n")
    assert b"Proxy-Authorization: Basic " + base64.b64encode(b"alice:secret") in (
        site.heard
    )


def test_the_process_keeps_one_guard_proxy_per_way_out_and_closes_the_oldest(
    monkeypatch,
):
    monkeypatch.setattr(browser_proxy, "MAX_PROXIES", 2)
    monkeypatch.setattr(browser_proxy, "_PROXIES", type(browser_proxy._PROXIES)())

    def look(host):
        return ["203.0.113.7"]

    first = guard_proxy(look)
    assert guard_proxy(look) is first
    second = guard_proxy(look, "http://a.example:1")
    guard_proxy(look, "http://b.example:1")

    assert next(iter(browser_proxy._PROXIES.values())) is second
    with pytest.raises(OSError):
        first._listener.accept()
