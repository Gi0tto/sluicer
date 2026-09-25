"""A proxy on this machine's loopback that every connection of a guarded
browser page goes through.

The guard (``sluicer.fetch.browser_guard``) routes the requests a page makes,
and Playwright's routes see those only. The browser makes others on the
page's behalf that no route sees: measured on 0.8.0 with the guard installed,
a speculation rule's prefetch and prerender -- written in the page, sent in a
``Speculation-Rules`` header, added by a script, aimed at another site -- and
a WebRTC connection to a TURN server each reached a private address. Chromium
sends every connection of a context through the context's proxy, those
included, so a guarded page's context is given this one.

* **Judged here.** Every ``CONNECT``, and every plain-HTTP request, names the
  host and port it is for, which ``public_addresses`` judges -- the rule the
  HTTP rung applies -- before anything is connected. A refusal is a 403, and
  nothing is asked of the address refused.
* **Connected to what was checked.** The connection goes to the addresses the
  host was just checked to have, and the name is never looked up again: the
  browser, which resolved names in its own network stack, no longer resolves
  them at all, so a name that answers differently the second time (DNS
  rebinding) reaches nothing new.
* **Loopback is not waved through.** Chromium sends a request for
  ``localhost`` or ``127.0.0.1`` past any proxy unless its bypass list says
  ``<-loopback>``; the context's does.
* **Through the caller's proxy.** A proxy the caller asked for is this one's
  way out: a tunnel through an HTTP proxy, or SOCKS5, as the HTTP rung speaks
  them. Through it the addresses are still judged here, and the connection is
  that proxy's, as for the HTTP rung.
* **No UDP.** WebRTC's UDP, which no HTTP proxy carries, is turned off where
  the browser is launched, so WebRTC has TCP through this proxy and nothing
  else.

It listens on 127.0.0.1 alone and connects only to public addresses, so to
anything else on this machine it is a way to the public web and nowhere
further. One serves each lookup and upstream proxy the process's guarded
browser pages use.
"""

from __future__ import annotations

import collections
import contextlib
import socket
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sluicer.fetch.address import AddressRefused, _resolve, public_addresses
from sluicer.fetch.wire import (
    Proxy,
    ProxyRefused,
    Target,
    _connect,
    _resolved,
    _socks5,
    _tunnel,
)

HEAD_BYTES = 65536
"""The most a request's line and headers may weigh before it is refused."""

CONNECT_SECONDS = 20.0
"""How long connecting to a site may take, the way out through a proxy
included: the HTTP rung's deadline."""

IDLE_SECONDS = 60.0
"""How long a connection may carry nothing before it is closed."""

MAX_PROXIES = 16
"""How many guard proxies the process keeps, one per lookup and way out."""

# What the browser says to this proxy and the site must not hear.
_HOP_BY_HOP = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-connection",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"upgrade",
    }
)


@dataclass(frozen=True)
class Asked:
    """One request to the proxy: a tunnel (``CONNECT``) or a plain-HTTP
    request, for ``host`` and ``port``."""

    method: str
    host: str
    port: int
    # For a plain-HTTP request: its path and query, its HTTP version, the
    # address it named whole, and its header lines as sent.
    path: str = ""
    version: str = "HTTP/1.1"
    target: str = ""
    headers: tuple[bytes, ...] = ()

    @property
    def tunnel(self) -> bool:
        return self.method == "CONNECT"

    @property
    def url(self) -> str:
        """The address judged: the host and port, as a URL names them."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/"

    def head(self, absolute: bool, authorization: str | None = None) -> bytes:
        """The request as the site -- or, ``absolute``, an HTTP proxy -- is
        sent it: one request, then the connection closes."""
        line = f"{self.method} {self.target if absolute else self.path} {self.version}"
        kept = [
            header
            for header in self.headers
            if header.split(b":", 1)[0].strip().lower() not in _HOP_BY_HOP
        ]
        if absolute and authorization is not None:
            kept.append(f"Proxy-Authorization: {authorization}".encode("latin-1"))
        kept.append(b"Connection: close")
        return b"\r\n".join([line.encode("latin-1"), *kept]) + b"\r\n\r\n"


def asked_of(head: bytes) -> Asked | None:
    """What a request's line and headers ask the proxy for, or None when it
    is not a request this proxy serves: a ``CONNECT`` to a host and port, or
    a plain-HTTP request naming its whole address."""
    lines = head.split(b"\r\n")
    try:
        method, target, version = lines[0].decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError):
        return None
    if not version.startswith("HTTP/1."):
        return None
    if method == "CONNECT":
        where = _authority(target)
        if where is None:
            return None
        return Asked(method, where[0], where[1])
    try:
        parts = urlsplit(target)
        port = parts.port or 80
    except ValueError:
        return None
    if parts.scheme.lower() != "http" or not parts.hostname:
        return None
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return Asked(
        method,
        parts.hostname,
        port,
        path,
        version,
        target,
        tuple(line for line in lines[1:] if line),
    )


def _authority(target: str) -> tuple[str, int] | None:
    """The host and port of a ``CONNECT`` target, ``host:port`` or
    ``[v6]:port``; None when it is neither."""
    if target.startswith("["):
        host, _, rest = target[1:].partition("]")
        port = rest.removeprefix(":")
    else:
        host, _, port = target.rpartition(":")
    if not host or not (port.isascii() and port.isdigit()) or not 0 < int(port) < 65536:
        return None
    return host, int(port)


class GuardProxy:
    """The proxy, listening on a port of 127.0.0.1 from the moment it is built.

    ``address`` is what a browser context is given; ``refused`` the latest
    addresses it turned away, each with why. ``resolve`` is the lookup the
    guard judges by, and ``upstream`` the caller's proxy, when there is one.
    """

    def __init__(
        self,
        resolve: Callable[[str], Iterable[str]] = _resolve,
        upstream: Proxy | None = None,
    ) -> None:
        self.resolve = resolve
        self.upstream = upstream
        self.refused: collections.deque[tuple[str, str]] = collections.deque(maxlen=100)
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.address = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        threading.Thread(
            target=self._accept, daemon=True, name="sluicer-guard-proxy"
        ).start()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._listener.close()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(
                target=self._serve, args=(client,), daemon=True, name="sluicer-guard"
            ).start()

    def _serve(self, client: socket.socket) -> None:
        try:
            client.settimeout(IDLE_SECONDS)
            head, early = _read_head(client)
            asked = asked_of(head) if head is not None else None
            if asked is None:
                _answer(client, 400, "not a request this proxy serves")
                return
            try:
                addresses = public_addresses(asked.url, self.resolve)
            except (AddressRefused, OSError) as refused:
                self.refused.append((asked.url, str(refused)))
                _answer(client, 403, str(refused))
                return
            try:
                site = self._connect(asked, addresses)
            except (OSError, ProxyRefused) as failed:
                _answer(client, 502, f"could not connect: {failed}")
                return
            with site:
                site.settimeout(IDLE_SECONDS)
                if asked.tunnel:
                    client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                else:
                    # An HTTP proxy is asked for the whole address, as a browser
                    # asks one; the site itself, or SOCKS, for its path.
                    upstream = self.upstream
                    if upstream is not None and upstream.scheme == "http":
                        site.sendall(asked.head(True, upstream.authorization()))
                    else:
                        site.sendall(asked.head(False))
                if early:
                    site.sendall(early)
                _pipe(client, site)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                client.close()

    def _connect(self, asked: Asked, addresses: list[str]) -> socket.socket:
        """A connection to the site ``asked`` is for, at ``addresses``, or to
        the caller's proxy, told to connect there."""
        deadline = time.monotonic() + CONNECT_SECONDS
        upstream = self.upstream
        if upstream is None:
            return _connect(addresses, asked.port, deadline)[0]
        sock, _ = _connect(
            _resolved(upstream.host, upstream.port, deadline), upstream.port, deadline
        )
        target = Target("https", asked.host, asked.port, tuple(addresses), upstream)
        try:
            if upstream.scheme != "http":
                _socks5(sock, target, upstream, deadline)
            elif asked.tunnel:
                _tunnel(sock, target, upstream, deadline)
        except BaseException:
            sock.close()
            raise
        return sock


def _read_head(client: socket.socket) -> tuple[bytes | None, bytes]:
    """A request's line and headers, and whatever came after them; None for
    the head when the connection ended first or it weighed too much."""
    data = b""
    while b"\r\n\r\n" not in data:
        more = client.recv(4096)
        if not more or len(data) > HEAD_BYTES:
            return None, b""
        data += more
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def _answer(client: socket.socket, status: int, reason: str) -> None:
    words = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}[status]
    body = f"{reason}\n".encode("utf-8", "replace")
    head = (
        f"HTTP/1.1 {status} {words}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    )
    with contextlib.suppress(OSError):
        client.sendall(head.encode("ascii") + body)


def _pipe(client: socket.socket, site: socket.socket) -> None:
    """Carry bytes both ways until the site is done, then close both: one
    plain-HTTP request per connection, so none is carried to a site it was
    not judged for."""

    def copy(source: socket.socket, sink: socket.socket) -> None:
        with contextlib.suppress(OSError):
            while data := source.recv(65536):
                sink.sendall(data)

    upward = threading.Thread(target=copy, args=(client, site), daemon=True)
    upward.start()
    copy(site, client)
    for sock in (client, site):
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
    upward.join(IDLE_SECONDS)


_PROXIES: collections.OrderedDict[tuple[Any, Proxy | None], GuardProxy] = (
    collections.OrderedDict()
)
_LOCK = threading.Lock()


def guard_proxy(
    resolve: Callable[[str], Iterable[str]] = _resolve, upstream: str | None = None
) -> GuardProxy:
    """The process's guard proxy for ``resolve`` and the caller's proxy
    ``upstream`` (an address ``Proxy.parse`` reads), started when first asked
    for; the least recently asked of more than ``MAX_PROXIES`` is closed."""
    key = (resolve, Proxy.parse(upstream) if upstream else None)
    closing: list[GuardProxy] = []
    with _LOCK:
        found = _PROXIES.get(key)
        if found is None:
            found = _PROXIES[key] = GuardProxy(resolve, key[1])
        _PROXIES.move_to_end(key)
        while len(_PROXIES) > MAX_PROXIES:
            closing.append(_PROXIES.popitem(last=False)[1])
    for old in closing:
        old.close()
    return found
