"""A web on the far side of a fake socket, for the HTTP rung's tests.

The rung is the standard library's ``http.client`` over a socket the process's
pool dials. Here the pool dials ``FakeSocket``s instead, which answer each
request sent on them with the next reply scripted, as raw HTTP bytes, so the
real ``http.client`` parses real status lines, headers, chunked bodies and
gzip. Nothing opens a socket, and what the rung sent is read back as bytes:
what a server would have seen.

A reply is ``(status, body, headers)`` -- headers a dict or a list of pairs,
rendered with a ``Content-Length`` unless they frame the body otherwise --
raw ``bytes``, or an exception, raised when the request is sent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sluicer.fetch import wire


@dataclass
class Request:
    """One request as it arrived: its line, its headers, which connection."""

    line: str
    headers: dict[str, str]
    names: list[str]
    connection: int

    @property
    def target(self) -> str:
        return self.line.split(" ")[1]


@dataclass
class Seen:
    requests: list[Request] = field(default_factory=list)
    targets: list[wire.Target] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)
    pool: wire.Connections | None = None

    @property
    def urls(self) -> list[str]:
        return [r.target for r in self.requests]

    @property
    def connections(self) -> int:
        return len(self.targets)


def render(reply: Any) -> bytes:
    if isinstance(reply, bytes):
        return reply
    status, body, headers = reply
    pairs = list(headers.items()) if isinstance(headers, dict) else list(headers)
    lines = [f"HTTP/1.1 {status} X"]
    names = {name.lower() for name, _ in pairs}
    for name, value in pairs:
        lines.append(f"{name}: {value}")
    if "content-length" not in names and "transfer-encoding" not in names:
        lines.append(f"Content-Length: {len(body)}")
    return "\r\n".join(lines).encode("latin-1") + b"\r\n\r\n" + body


class FakeSocket:
    """A connection whose far side answers from ``replies``, one per request.

    ``chunk`` is how many bytes one read hands back at most; ``drip`` a pause
    before each, which the deadline must cut short.
    """

    def __init__(
        self,
        seen: Seen,
        replies: list[Any],
        number: int,
        chunk: int | None = None,
        drip: float = 0.0,
    ) -> None:
        self.seen = seen
        self.replies = replies
        self.number = number
        self.chunk = chunk
        self.drip = drip
        self.outgoing = b""
        self.incoming = b""
        self.closed = False
        self.hung_up = False
        self.timeout: float | None = None

    def settimeout(self, value: float | None) -> None:
        self.timeout = value
        if value is not None:
            self.seen.timeouts.append(value)

    def setblocking(self, flag: bool) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        if self.hung_up:
            raise ConnectionResetError("the server closed this connection")
        self.outgoing += data
        while b"\r\n\r\n" in self.outgoing:
            head, self.outgoing = self.outgoing.split(b"\r\n\r\n", 1)
            lines = head.decode("latin-1").split("\r\n")
            pairs = [line.split(": ", 1) for line in lines[1:]]
            self.seen.requests.append(
                Request(
                    lines[0],
                    {name.lower(): value for name, value in pairs},
                    [name for name, _ in pairs],
                    self.number,
                )
            )
            reply = self.replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            self.incoming += render(reply)

    def recv_into(self, buffer: Any, size: int = 0) -> int:
        if self.drip:
            if self.timeout is not None and self.timeout < self.drip:
                time.sleep(self.timeout)
                raise TimeoutError("timed out")
            time.sleep(self.drip)
        size = size or len(buffer)
        size = min(size, self.chunk or size, len(self.incoming))
        buffer[:size] = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return size

    def recv(self, size: int, flags: int = 0) -> bytes:
        # Only the pool's question "did the server close this?" reads here.
        if self.hung_up:
            return b""
        raise BlockingIOError

    def close(self) -> None:
        self.closed = True


def fake_http(
    monkeypatch: Any,
    replies: list[Any],
    chunk: int | None = None,
    drip: float = 0.0,
    peer: str = "93.184.215.14",
    max_idle: int = wire.MAX_IDLE,
) -> Seen:
    """Put a pool that dials fake sockets where the HTTP rung finds its own."""
    seen = Seen()
    sockets: list[FakeSocket] = []

    def dial(target: wire.Target, deadline: float) -> wire.Timed:
        seen.targets.append(target)
        wire.left(deadline)
        sock = FakeSocket(seen, replies, len(sockets), chunk, drip)
        sockets.append(sock)
        address = target.addresses[0] if target.addresses else peer
        return wire.Timed(sock, deadline, None if target.proxy else address)

    pool = wire.Connections(dial=dial, max_idle=max_idle)
    seen.pool = pool
    seen.sockets = sockets  # type: ignore[attr-defined]
    monkeypatch.setattr("sluicer.fetch.http_rung.CONNECTIONS", pool)
    return seen
