"""The HTTP rung against real sockets and a local server.

Run by CI; not part of the unit suite, which opens no sockets and talks to a
fake one. A fake confirms only the shape you already believe in: this asks
the rung what it actually sends, where it actually stops reading, whether a
pinned name really goes where it was pinned, and how many connections twenty
pages of one site cost the server.

    python tests/live/http_check.py
"""

from __future__ import annotations

import contextlib
import gzip
import http.server
import os
import socket
import socketserver
import sys
import threading
import time

LIMIT = 1024 * 1024
BIG = 3 * LIMIT
seen: dict[str, dict[str, str]] = {}
connections: list[object] = []
# Where a redirect off the web points: a bare socket that records what reaches
# it, as a Redis or a memcached on this machine would.
listener = socket.create_server(("127.0.0.1", 0))
reached: list[bytes] = []


class Server(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def setup(self) -> None:
        connections.append(self.client_address)
        super().setup()

    def _send(self, status: int, body: bytes = b"", **headers: str) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        if "Transfer_Encoding" not in headers:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def do_GET(self) -> None:
        seen[self.path] = dict(self.headers)
        if self.path == "/page":
            body = "<html><head><title>Café</title></head><body>ok</body></html>"
            self._send(
                200,
                body.encode("windows-1252"),
                Content_Type="text/html; charset=windows-1252",
            )
        elif self.path == "/hop":
            self._send(302, Location="/page")
        elif self.path == "/to-private":
            self._send(302, Location="http://10.0.0.1/admin")
        elif self.path == "/drip":
            # Eight bytes a second, for longer than the deadline the check sets.
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(8 * 6))
            self.end_headers()
            with contextlib.suppress(OSError):
                for _ in range(6):
                    self.wfile.write(b"<p>drip>")
                    self.wfile.flush()
                    time.sleep(1)
        elif self.path.startswith("/to-"):
            port = listener.getsockname()[1]
            targets = {
                "/to-gopher": f"gopher://127.0.0.1:{port}/_SET%20pwned%201%0D%0A",
                "/to-dict": f"dict://127.0.0.1:{port}/info",
                "/to-file": "file:///etc/hosts",
            }
            self._send(302, Location=targets[self.path])
        elif self.path == "/cut":
            # Announces the whole page and closes after a part of it.
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", "4000")
            self.end_headers()
            self.wfile.write(b"<html><body><p>the start of a page")
            self.wfile.flush()
            self.close_connection = True
        elif self.path == "/cut-gzip":
            whole = gzip.compress(b"<html><body>" + b"<p>words</p>" * 400)
            self._send(
                200,
                whole[: len(whole) // 2],
                Content_Type="text/html",
                Content_Encoding="gzip",
            )
        elif self.path == "/announced":
            self._send(200, b"a" * BIG, Content_Type="text/html")
        elif self.path == "/bomb":
            self._send(
                200,
                gzip.compress(b"c" * BIG * 4),
                Content_Type="text/html",
                Content_Encoding="gzip",
            )
        elif self.path == "/chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            chunk = b"b" * 65536
            try:
                for _ in range(BIG // len(chunk) + 1):
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self._send(404)


class _Quiet(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # a client that stops reading at the bound resets the connection


def _record() -> None:
    while True:
        connection, _ = listener.accept()
        connection.settimeout(2)
        with contextlib.suppress(OSError):
            reached.append(connection.recv(1000))
        connection.close()


def main() -> int:
    from sluicer.fetch import address
    from sluicer.fetch.address import AddressRefused
    from sluicer.fetch.http_rung import ProtocolError, http_rung
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.result import ResponseTooLarge
    from sluicer.fetch.wire import ACCEPT_ENCODING

    server = _Quiet(("127.0.0.1", 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    rung = http_rung(max_bytes=LIMIT)
    failures = []

    page = rung(base + "/page")
    if "Café" not in page.html:
        failures.append(f"the response's own charset was not used: {page.html!r}")
    sent = {name.lower(): value for name, value in seen["/page"].items()}
    if sent.get("user-agent") != USER_AGENT or "referer" in sent:
        failures.append(f"it did not say who it is, or borrowed a referer: {sent}")
    if not sent.get("accept", "").startswith("text/html"):
        failures.append(f"it did not say it takes a page: {sent}")
    if sent.get("accept-encoding") != ACCEPT_ENCODING:
        failures.append(f"it did not offer the encodings it decodes: {sent}")

    before = len(connections)
    for _ in range(20):
        rung(base + "/page")
    if len(connections) - before > 1:
        failures.append(
            f"twenty pages of one site took {len(connections) - before} connections"
        )

    if rung(base + "/hop").url != base + "/page":
        failures.append("a redirect was not followed to where it led")

    started = time.monotonic()
    try:
        http_rung(timeout=1.5)(base + "/drip")
        failures.append("a body dripped past the deadline was waited for to its end")
    except TimeoutError:
        took = time.monotonic() - started
        if took > 2.5:
            failures.append(f"a dripped body was cut after {took:.2f} s, not 1.5")

    threading.Thread(target=_record, daemon=True).start()
    for path in ("/to-gopher", "/to-dict", "/to-file"):
        try:
            off = rung(base + path)
            failures.append(f"{path}: followed to {off.url}: {off.html[:40]!r}")
        except AddressRefused:
            pass
    time.sleep(0.2)
    if reached:
        failures.append(f"a redirect off the web reached a socket with {reached}")

    for path in ("/cut", "/cut-gzip"):
        try:
            cut = rung(base + path)
            failures.append(f"{path}: a body cut short came back: {cut.html[:40]!r}")
        except ProtocolError:
            pass
        except Exception as other:  # noqa: BLE001 -- any other answer is a failure
            failures.append(f"{path}: a body cut short raised {other!r}")

    for path in ("/announced", "/chunked", "/bomb"):
        try:
            rung(base + path)
            failures.append(f"{path}: a body over the bound was returned")
        except ResponseTooLarge:
            pass

    # 127.0.0.1 is private, so to test the pin the check is told to accept it,
    # and a name that exists nowhere is pinned to it: only the pin can reach it.
    public = address._public
    address._public = lambda found: True  # type: ignore[assignment]
    try:
        pinned = http_rung(allow_private=False, resolve=lambda host: ["127.0.0.1"])
        port = server.server_address[1]
        if pinned(f"http://nowhere.invalid:{port}/page").status != 200:
            failures.append("a pinned name did not reach the pinned address")
    finally:
        address._public = public  # type: ignore[assignment]

    guarded = http_rung(allow_private=False)
    try:
        guarded(base.replace("127.0.0.1", "localhost") + "/page")
        failures.append("a private address was fetched with allow_private false")
    except AddressRefused:
        pass
    seen.clear()
    address._public = lambda found: str(found) == "127.0.0.1"  # type: ignore[assignment]
    try:
        guarded(base + "/to-private")
        failures.append("a redirect into a private address was followed")
    except AddressRefused:
        pass
    finally:
        address._public = public  # type: ignore[assignment]

    # A proxy the environment names is not used; one asked for is. The name
    # resolves nowhere, so only a proxy could have been told about it.
    proxy = socket.create_server(("127.0.0.1", 0))
    told: list[bytes] = []

    def _proxied() -> None:
        while True:
            connection, _ = proxy.accept()
            connection.settimeout(2)
            with contextlib.suppress(OSError):
                told.append(connection.recv(200).split(b"\r\n")[0])
            connection.close()

    threading.Thread(target=_proxied, daemon=True).start()
    through = f"http://127.0.0.1:{proxy.getsockname()[1]}"
    named = {name: through for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")}
    before = {name: os.environ.get(name) for name in [*named, "SLUICER_PROXY"]}
    os.environ.update(named)
    os.environ.pop("SLUICER_PROXY", None)
    try:
        with contextlib.suppress(Exception):
            http_rung()("https://nowhere.invalid/")
        time.sleep(0.2)
        if told:
            failures.append(f"the environment's proxy was used unasked: {told}")
        with contextlib.suppress(Exception):
            http_rung(proxy=through)("https://nowhere.invalid/")
        time.sleep(0.2)
        if told != [b"CONNECT nowhere.invalid:443 HTTP/1.1"]:
            failures.append(f"the proxy asked for was not used: {told}")
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "http: charset, identity, one connection for twenty pages, redirects, "
            "the web only, the deadline, bodies cut short, heavy bodies, the pin "
            "and no proxy "
            "unasked all hold"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
