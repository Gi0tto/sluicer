"""How a request reaches a site: the socket, TLS, a proxy, and the connections
kept open between requests. The standard library and nothing else.

* **One deadline for everything.** A connection is handed out wrapped so that
  every wait on it -- connecting through a proxy, the TLS handshake, sending,
  each read of the headers and the body -- is given only what is left of the
  fetch's deadline. A server that drips its answer a byte at a time is cut
  off at the deadline, however short each wait is.
* **Only the addresses checked.** Given addresses, ``dial`` connects to those
  and never looks the name up; a kept connection is handed back only while
  the address it is connected to is still one of them.
* **No proxy unless named.** Nothing here reads ``HTTPS_PROXY`` or
  ``HTTP_PROXY``; a proxy is used only when a ``Target`` names one.
* **One pool for the process.** A connection whose answer was read to its end
  and that the server did not close is kept (``Connections``), and the next
  request to the same host, port and scheme is sent on it, so a site asked
  for twenty pages is connected to once rather than twenty times. A kept
  connection the server has since closed is found out before it is used,
  and a request that meets a close anyway is sent once more, on a new one.
* **Decoded within the bound.** A body is decompressed as it arrives and never
  past the room the caller gives it, so a small gzip that inflates to
  gigabytes costs the bound.
"""

from __future__ import annotations

import base64
import contextlib
import importlib
import io
import ipaddress
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import ModuleType
from typing import Any
from urllib.parse import unquote, urlsplit

from sluicer.fetch.address import shown

ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
"""What every request says it would like back: a page, or anything else."""


def _zstd() -> ModuleType | None:
    """Zstandard's decompressor: the standard library's from Python 3.14, else
    ``backports.zstd`` when it is installed, else None."""
    for name in ("compression.zstd", "backports.zstd"):
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    return None


ZSTD = _zstd()

ACCEPT_ENCODING = "gzip, deflate" + (", zstd" if ZSTD is not None else "")
"""The encodings a body may come in: the ones this process can decode within
a bound. Brotli is not among them: the standard library has no decoder."""

MAX_IDLE = 32
"""How many open connections the process keeps between requests, all sites
together; the one left longest is closed first."""

IDLE_SECONDS = 60.0
"""How long a kept connection may wait for its next request. Servers close
theirs sooner or later, and one left longer is more likely closed than not."""

_HEADER_BYTES = 65536


def passing(error: BaseException) -> bool:
    """Whether ``error``, raised on the wire, is one asking again later may
    not meet: a connection refused, reset or closed (a body cut short among
    them), time that ran out, a TLS connection closed mid-handshake, a name
    the resolver could not look up for now."""
    if isinstance(error, (ConnectionError, TimeoutError, ssl.SSLEOFError)):
        return True
    if isinstance(error, socket.gaierror):
        return error.errno == socket.EAI_AGAIN
    return False


class UnreadableEncoding(ValueError):
    """The body came in a content encoding this install cannot decode."""

    def __init__(self, url: str, encoding: str) -> None:
        super().__init__(
            f"{url} answered in the {encoding!r} content encoding, which this "
            f"install cannot decode (it asks for {ACCEPT_ENCODING})"
        )
        self.encoding = encoding


class ProxyRefused(ConnectionError):
    """The proxy would not, or could not, connect us to the site."""


class UnusableProxy(ValueError):
    """A proxy address Sluicer cannot use. Its message names the address
    without its password, which a message would carry into a log."""


@dataclass(frozen=True)
class Proxy:
    """A proxy, read from its address: ``http://``, ``socks5://`` (names
    resolved here) or ``socks5h://`` (names resolved by the proxy), with an
    optional ``user:password@``."""

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @classmethod
    def parse(cls, address: str) -> Proxy:
        """``address`` as a proxy; an ``UnusableProxy`` names what is wrong
        with it, and never its password."""
        try:
            parts = urlsplit(address)
            port = parts.port
        except ValueError as invalid:
            raise UnusableProxy(
                f"{shown(address)!r} is not a proxy address: {invalid}"
            ) from None
        scheme = parts.scheme.lower()
        defaults = {"http": 8080, "socks5": 1080, "socks5h": 1080}
        if scheme not in defaults:
            raise UnusableProxy(
                f"{shown(address)!r} is not a proxy Sluicer speaks to: write "
                "http://host:port, socks5://host:port or socks5h://host:port"
            )
        if not parts.hostname:
            raise UnusableProxy(f"{shown(address)!r} names no proxy host")
        return cls(
            scheme,
            parts.hostname,
            port or defaults[scheme],
            unquote(parts.username) if parts.username is not None else None,
            unquote(parts.password) if parts.password is not None else None,
        )

    def authorization(self) -> str | None:
        """The ``Proxy-Authorization`` an HTTP proxy is sent, or None."""
        if self.username is None:
            return None
        pair = f"{self.username}:{self.password or ''}".encode()
        return "Basic " + base64.b64encode(pair).decode("ascii")


@dataclass(frozen=True)
class Target:
    """Where a request goes: the site's scheme, host and port, the addresses
    it may be reached at (None: whatever the name resolves to), and the proxy
    it goes through, if any."""

    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...] | None = None
    proxy: Proxy | None = None

    @property
    def key(self) -> tuple[str, str, int, Proxy | None, bool]:
        """What two requests must share to share a connection."""
        return (self.scheme, self.host, self.port, self.proxy, self.addresses is None)

    @property
    def absolute_form(self) -> bool:
        """Whether the request line names the whole address: plain HTTP asked
        of an HTTP proxy, which is not tunnelled."""
        return (
            self.proxy is not None
            and self.proxy.scheme == "http"
            and (self.scheme == "http")
        )


def left(deadline: float) -> float:
    """The seconds until ``deadline``; a ``TimeoutError`` once there are none."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("the deadline passed")
    return remaining


def within(deadline: float, work: Callable[[], Any]) -> Any:
    """``work()``, or a ``TimeoutError`` once ``deadline`` passes first.

    For what takes no timeout of its own: the system's name lookup can wait on
    a resolver for as long as it likes. The lookup left behind ends on its own
    and is forgotten.
    """
    done = threading.Event()
    answer: list[Any] = []
    failure: list[BaseException] = []

    def run() -> None:
        try:
            answer.append(work())
        except BaseException as error:  # noqa: BLE001 -- handed to the caller
            failure.append(error)
        finally:
            done.set()

    threading.Thread(target=run, daemon=True, name="sluicer-lookup").start()
    if not done.wait(left(deadline)):
        raise TimeoutError("the deadline passed while the name was looked up")
    if failure:
        raise failure[0]
    return answer[0]


class Timed:
    """A connected socket whose every wait ends by ``deadline``.

    ``deadline`` is set again for each request sent on it. ``peer`` is the
    address it is connected to, or None through a proxy, whose own address
    is the one named, not the site's.
    """

    def __init__(self, sock: Any, deadline: float, peer: str | None) -> None:
        self.sock = sock
        self.deadline = deadline
        self.peer = peer

    def _wait(self) -> None:
        self.sock.settimeout(left(self.deadline))

    def sendall(self, data: bytes) -> None:
        self._wait()
        self.sock.sendall(data)

    def recv_into(self, buffer: Any, size: int = 0) -> int:
        self._wait()
        return int(self.sock.recv_into(buffer, size))

    def makefile(
        self, mode: str = "rb", *args: Any, **kwargs: Any
    ) -> io.BufferedReader:
        """What ``http.client`` reads a response from: this socket, timed."""
        return io.BufferedReader(_Reader(self))

    def alive(self) -> bool:
        """Whether the server has not closed the connection, asked without
        waiting: a kept connection it closed reads as its end, at once."""
        try:
            self.sock.setblocking(False)
            try:
                if isinstance(self.sock, ssl.SSLSocket):
                    data = self.sock.recv(1)
                else:
                    data = self.sock.recv(1, socket.MSG_PEEK)
            except (BlockingIOError, ssl.SSLWantReadError):
                return True
            except OSError:
                return False
            # The end (b""), or bytes nobody asked for: either way not a
            # connection to send a request on.
            del data
            return False
        finally:
            with contextlib.suppress(OSError):
                self.sock.setblocking(True)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()


class _Reader(io.RawIOBase):
    """The raw stream under a response: reads from a ``Timed``, and closing it
    leaves the connection open for the next request."""

    def __init__(self, timed: Timed) -> None:
        self.timed = timed

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        return self.timed.recv_into(buffer)


_TLS: list[ssl.SSLContext] = []
_TLS_LOCK = threading.Lock()


def tls_context() -> ssl.SSLContext:
    """The process's TLS settings: the system's certificates, verified, and
    HTTP/1.1 offered, the one version spoken here."""
    with _TLS_LOCK:
        if not _TLS:
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            _TLS.append(context)
        return _TLS[0]


def _connect(
    addresses: Iterable[str], port: int, deadline: float
) -> tuple[socket.socket, str]:
    """A TCP connection to the first of ``addresses`` that answers, and it."""
    last: OSError | None = None
    for address in addresses:
        try:
            sock = socket.create_connection((address, port), timeout=left(deadline))
        except TimeoutError:
            raise
        except OSError as failure:
            last = failure
            continue
        return sock, address
    raise last or OSError("the host has no address to connect to")


def _resolved(host: str, port: int, deadline: float) -> list[str]:
    """The addresses ``host`` resolves to, by the system, within the deadline."""
    found = within(
        deadline,
        lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM),
    )
    return list(dict.fromkeys(str(info[4][0]) for info in found))


def dial(target: Target, deadline: float) -> Timed:
    """A new connection to ``target``, TLS included for https.

    Direct, it goes to ``target.addresses`` when there are some -- the ones
    the caller checked -- and to what the name resolves to otherwise. Through
    a proxy it goes to the proxy, which is asked for a tunnel to the site:
    ``CONNECT`` of an HTTP proxy for https (plain HTTP is asked of it as a
    whole address, ``Target.absolute_form``), SOCKS5 for either.
    """
    proxy = target.proxy
    peer: str | None
    if proxy is None:
        addresses = target.addresses or _resolved(target.host, target.port, deadline)
        sock, peer = _connect(addresses, target.port, deadline)
    else:
        sock, _ = _connect(
            _resolved(proxy.host, proxy.port, deadline), proxy.port, deadline
        )
        peer = None
        try:
            if proxy.scheme == "http":
                if not target.absolute_form:
                    _tunnel(sock, target, proxy, deadline)
            else:
                _socks5(sock, target, proxy, deadline)
        except BaseException:
            sock.close()
            raise
    if target.scheme == "https":
        try:
            sock.settimeout(left(deadline))
            sock = tls_context().wrap_socket(sock, server_hostname=target.host)
        except BaseException:
            sock.close()
            raise
    return Timed(sock, deadline, peer)


def _authority(target: Target) -> str:
    host = f"[{target.host}]" if ":" in target.host else target.host
    return f"{host}:{target.port}"


def _tunnel(sock: socket.socket, target: Target, proxy: Proxy, deadline: float) -> None:
    """Ask an HTTP proxy for a tunnel to the site, and read its answer."""
    authority = _authority(target)
    lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"]
    authorization = proxy.authorization()
    if authorization is not None:
        lines.append(f"Proxy-Authorization: {authorization}")
    sock.settimeout(left(deadline))
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
    answer = b""
    while b"\r\n\r\n" not in answer:
        sock.settimeout(left(deadline))
        # One byte at a time, so nothing past the proxy's answer -- the
        # site's first TLS bytes -- is read here and lost.
        byte = sock.recv(1)
        if not byte:
            raise ProxyRefused("the proxy closed the connection it was asked to tunnel")
        answer += byte
        if len(answer) > _HEADER_BYTES:
            raise ProxyRefused("the proxy's answer to CONNECT has no end")
    status = answer.split(b"\r\n", 1)[0].decode("latin-1")
    parts = status.split(" ", 2)
    if len(parts) < 2 or not parts[1].startswith("2"):
        raise ProxyRefused(f"the proxy refused the tunnel to {authority}: {status}")


_SOCKS_REPLIES = {
    1: "general failure",
    2: "not allowed by its rules",
    3: "network unreachable",
    4: "host unreachable",
    5: "connection refused",
    6: "TTL expired",
    7: "command not supported",
    8: "address type not supported",
}


def _exactly(sock: socket.socket, size: int, deadline: float) -> bytes:
    data = b""
    while len(data) < size:
        sock.settimeout(left(deadline))
        more = sock.recv(size - len(data))
        if not more:
            raise ProxyRefused("the SOCKS proxy closed the connection")
        data += more
    return data


def _socks5(sock: socket.socket, target: Target, proxy: Proxy, deadline: float) -> None:
    """Ask a SOCKS5 proxy (RFC 1928) to connect to the site, by name for
    ``socks5h``, by address for ``socks5`` -- a checked one when there are."""
    methods = b"\x00\x02" if proxy.username is not None else b"\x00"
    sock.settimeout(left(deadline))
    sock.sendall(b"\x05" + bytes([len(methods)]) + methods)
    version, method = _exactly(sock, 2, deadline)
    if version != 5 or method == 0xFF:
        raise ProxyRefused("the SOCKS proxy accepts none of the ways offered to log in")
    if method == 2:
        # RFC 1929: a user name and a password.
        user = (proxy.username or "").encode()
        password = (proxy.password or "").encode()
        sock.sendall(
            b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password
        )
        if _exactly(sock, 2, deadline)[1] != 0:
            raise ProxyRefused("the SOCKS proxy refused the user name and password")
    if proxy.scheme == "socks5h":
        name = target.host.encode("ascii")
        where = b"\x03" + bytes([len(name)]) + name
    else:
        address = (
            target.addresses[0]
            if target.addresses
            else _resolved(target.host, target.port, deadline)[0]
        )
        packed = ipaddress.ip_address(address).packed
        where = (b"\x01" if len(packed) == 4 else b"\x04") + packed
    sock.sendall(b"\x05\x01\x00" + where + target.port.to_bytes(2, "big"))
    version, reply, _, kind = _exactly(sock, 4, deadline)
    if version != 5 or reply != 0:
        said = _SOCKS_REPLIES.get(reply, f"reply {reply}")
        raise ProxyRefused(f"the SOCKS proxy could not connect to the site: {said}")
    length = {1: 4, 4: 16}.get(kind)
    if length is None:
        length = _exactly(sock, 1, deadline)[0]
    _exactly(sock, length + 2, deadline)


class Connections:
    """The connections the process keeps open between requests.

    ``take`` hands out a kept one for the target, or dials a new one;
    ``give`` keeps one back once its answer was read to the end. A connection
    is used by one request at a time: taken, it belongs to the taker until it
    is given back or closed. ``dial`` and ``clock`` are injected by tests;
    ``max_idle`` of 0 keeps nothing, so every request connects anew.
    """

    def __init__(
        self,
        dial: Callable[[Target, float], Timed] = dial,
        max_idle: int = MAX_IDLE,
        idle_seconds: float = IDLE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.dial = dial
        self.max_idle = max_idle
        self.idle_seconds = idle_seconds
        self.clock = clock
        self._lock = threading.Lock()
        # Oldest first: (target's key, when it was given back, the connection).
        self._idle: list[tuple[Any, float, Timed]] = []
        self.dialled = 0
        """How many connections this pool has opened: what a site saw."""

    def take(self, target: Target, deadline: float) -> tuple[Timed, bool]:
        """A connection to ``target`` and whether it was kept from before."""
        stale: list[Timed] = []
        found: Timed | None = None
        with self._lock:
            now = self.clock()
            for index in range(len(self._idle) - 1, -1, -1):
                key, since, kept = self._idle[index]
                if now - since > self.idle_seconds:
                    stale.append(kept)
                    del self._idle[index]
                    continue
                if key != target.key or found is not None:
                    continue
                if target.addresses is not None and kept.peer not in target.addresses:
                    continue
                found = kept
                del self._idle[index]
        for kept in stale:
            kept.close()
        if found is not None:
            if found.alive():
                found.deadline = deadline
                return found, True
            found.close()
        with self._lock:
            self.dialled += 1
        return self.dial(target, deadline), False

    def give(self, target: Target, connection: Timed) -> None:
        """Keep ``connection`` for the next request to ``target``."""
        closing: list[Timed] = []
        with self._lock:
            self._idle.append((target.key, self.clock(), connection))
            while len(self._idle) > max(self.max_idle, 0):
                closing.append(self._idle.pop(0)[2])
        for old in closing:
            old.close()

    def clear(self) -> None:
        """Close every kept connection."""
        with self._lock:
            idle, self._idle = self._idle, []
        for _, _, connection in idle:
            connection.close()


CONNECTIONS = Connections()
"""The process's pool: every request the HTTP rung makes goes through it."""


class Decoder:
    """A body's ``Content-Encoding`` undone as it arrives, never past a bound.

    ``feed`` takes the next bytes and the room left, and returns what they
    decode to; more than the room is ``Overflow``. Encodings applied one
    after another are undone in the reverse order, each held to the room.
    """

    def __init__(self, url: str, encoding: str) -> None:
        names = [name.strip().lower() for name in encoding.split(",") if name.strip()]
        self.stages = [
            _stage(url, name) for name in reversed(names) if name != "identity"
        ]

    def feed(self, data: bytes, room: int) -> bytes:
        for stage in self.stages:
            data = stage.feed(data, room)
        return data

    def finish(self, room: int) -> bytes:
        data = b""
        for stage in self.stages:
            data = stage.feed(data, room) + stage.finish(room)
        return data


class Overflow(Exception):
    """A body decoded to more than the room it was given."""


class Truncated(ValueError):
    """A body's compressed stream ended before its end: the framing said the
    body was whole, and what it held was the start of one."""

    def __init__(self, encoding: str) -> None:
        super().__init__(f"its {encoding} stream ended before its end")
        self.encoding = encoding


def _stage(url: str, name: str) -> _Inflate | _Zstd:
    if name in ("gzip", "x-gzip"):
        return _Inflate(16 + zlib.MAX_WBITS)
    if name == "deflate":
        return _Inflate(zlib.MAX_WBITS, raw_fallback=True)
    if name == "zstd" and ZSTD is not None:
        return _Zstd(ZSTD)
    raise UnreadableEncoding(url, name)


class _Inflate:
    """gzip, or deflate as zlib wraps it (or raw, as some servers send it).

    Which deflate it is is decided on its first two bytes, zlib's header: the
    first read may bring one, and one byte was no header yet, so the second
    read failed zlib's check. Every gzip member is read, one after another in
    a loop: a call per member inside the last one's was 3,000 empty members,
    60 KB, and a ``RecursionError``.
    """

    def __init__(self, wbits: int, raw_fallback: bool = False) -> None:
        self.wbits = wbits
        self.raw_fallback = raw_fallback
        self.started = False
        # The first byte of deflate, held until a second says which it is.
        self.held = b""
        self.inflate = zlib.decompressobj(wbits)

    def feed(self, data: bytes, room: int) -> bytes:
        if self.raw_fallback and not self.started:
            data = self.held + data
            if len(data) < 2:
                self.held = data
                return b""
            self.held = b""
        members = self.wbits > 16
        out = b""
        while data:
            if members and self.inflate.eof:
                # Another gzip member follows: read it too, as gzip does.
                self.inflate = zlib.decompressobj(self.wbits)
            try:
                piece = self.inflate.decompress(data, room - len(out) + 1)
            except zlib.error:
                if self.started or not self.raw_fallback:
                    raise
                self.inflate = zlib.decompressobj(-zlib.MAX_WBITS)
                piece = self.inflate.decompress(data, room - len(out) + 1)
            self.started = True
            out += piece
            if len(out) > room:
                raise Overflow
            data = self.inflate.unused_data if members and self.inflate.eof else b""
        return out

    def finish(self, room: int) -> bytes:
        out = self.inflate.flush()
        if len(out) > room:
            raise Overflow
        if self.held or (self.started and not self.inflate.eof):
            # No bytes at all is an empty body; some bytes and no end is the
            # start of one.
            raise Truncated("gzip" if self.wbits > 16 else "deflate")
        return out


class _Zstd:  # pragma: no cover - zstd is Python 3.14's, or backports.zstd
    # CI measures coverage on 3.13; tests/test_fetch_guards.py runs this on 3.14.
    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self.started = False
        self.inflate = module.ZstdDecompressor()

    def feed(self, data: bytes, room: int) -> bytes:
        out = b""
        while data:
            if self.inflate.eof:
                # Another frame follows, read as zstd reads it.
                self.inflate = self.module.ZstdDecompressor()
            out += bytes(self.inflate.decompress(data, room - len(out) + 1))
            self.started = True
            if len(out) > room:
                raise Overflow
            data = self.inflate.unused_data if self.inflate.eof else b""
        return out

    def finish(self, room: int) -> bytes:
        if self.started and not self.inflate.eof:
            raise Truncated("zstd")
        return b""
