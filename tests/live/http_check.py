"""The HTTP rung against a real curl and a local server.

Run by CI with the fetch extra installed; not part of the unit suite, which
opens no sockets and fakes curl_cffi. A fake confirms only the shape you already
believe in: this asks curl what it actually sends, where it actually stops
reading, and whether a pinned name really goes where it was pinned.

    python tests/live/http_check.py
"""

from __future__ import annotations

import contextlib
import gzip
import http.server
import socket
import socketserver
import sys
import threading
import time

LIMIT = 1024 * 1024
BIG = 3 * LIMIT
seen: dict[str, dict[str, str]] = {}
# Where a redirect off the web points: a bare socket that records what reaches
# it, as a Redis or a memcached on this machine would.
listener = socket.create_server(("127.0.0.1", 0))
reached: list[bytes] = []


class Server(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

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
        elif self.path.startswith("/to-"):
            port = listener.getsockname()[1]
            targets = {
                "/to-gopher": f"gopher://127.0.0.1:{port}/_SET%20pwned%201%0D%0A",
                "/to-dict": f"dict://127.0.0.1:{port}/info",
                "/to-file": "file:///etc/hosts",
            }
            self._send(302, Location=targets[self.path])
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
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.result import ResponseTooLarge

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

    if rung(base + "/hop").url != base + "/page":
        failures.append("a redirect was not followed to where it led")

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

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "http: charset, identity, redirects, the web only, heavy bodies and "
            "the pin all hold"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
