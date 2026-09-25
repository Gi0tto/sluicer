"""The browser guard against a real Chromium and two local servers.

Run by CI after installing a browser; not part of the unit suite, which opens
no sockets. One server stands for the public web and the other for a private
address: the guard is told that the second one's port is not public, and every
way a page can make a browser ask for something is tried against it. The
private server counts what reached it, and the only right count is zero.

    python tests/live/guard_check.py
"""

from __future__ import annotations

import http.server
import ipaddress
import json
import socket
import socketserver
import sys
import threading
import time
from urllib.parse import urlsplit

reached: list[str] = []
# What reached the private address by other ways than HTTP: a TCP connection
# on a port that answers nothing, a UDP datagram, as a TURN or a STUN server
# on this machine's network would see them.
connected: list[str] = []


class _Quiet(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()
        self.wfile.write(body)


class Public(_Quiet):
    def do_GET(self) -> None:
        pages = {
            "/page": (
                "<html><body><p>public page</p>"
                f'<img src="http://127.0.0.1:{PRIVATE}/direct-image">'
                '<img src="/hop-to-hop">'
                f'<iframe src="http://127.0.0.1:{PRIVATE}/frame"></iframe>'
                "<script>"
                f"fetch('http://127.0.0.1:{PRIVATE}/fetch').catch(() => 0);"
                f"try {{ new WebSocket('ws://127.0.0.1:{PRIVATE}/socket'); }}"
                "catch (e) {}"
                "document.body.dataset.sw = String(!!navigator.serviceWorker);"
                "</script></body></html>"
            ).encode(),
        }
        pages.update(_ROUTES_PAST_THE_PAGE)
        if self.path in pages:
            self._send(200, pages[self.path])
        elif self.path == "/rules-header":
            self._send(
                200,
                b"<html><body><p>public page</p></body></html>",
                Speculation_Rules='"/rules.json"',
            )
        elif self.path == "/rules.json":
            rules = {
                "prefetch": [{"source": "list", "urls": [f"{PRIVATE_URL}/header"]}]
            }
            self._send(
                200,
                json.dumps(rules).encode(),
                Content_Type="application/speculationrules+json",
            )
        elif self.path == "/hop-to-hop":
            self._send(302, Location="/hop-to-private")
        elif self.path == "/hop-to-private":
            self._send(302, Location=f"http://127.0.0.1:{PRIVATE}/via-two-hops")
        elif self.path == "/document-redirect":
            self._send(302, Location="/page")
        elif self.path == "/document-to-private":
            self._send(302, Location=f"http://127.0.0.1:{PRIVATE}/document")
        else:
            self._send(404)


class Private(_Quiet):
    def do_GET(self) -> None:
        reached.append(self.path)
        self._send(200, b"<html><body>private</body></html>")


def _serve(handler: type[http.server.BaseHTTPRequestHandler]) -> int:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return int(server.server_address[1])


PUBLIC, PRIVATE = _serve(Public), _serve(Private)
PRIVATE_URL = f"http://127.0.0.1:{PRIVATE}"


def _listen_tcp() -> int:
    listener = socket.create_server(("127.0.0.1", 0))

    def accept() -> None:
        while True:
            connection, _ = listener.accept()
            connected.append("tcp")
            connection.close()

    threading.Thread(target=accept, daemon=True).start()
    return int(listener.getsockname()[1])


def _listen_udp() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))

    def receive() -> None:
        while True:
            listener.recvfrom(2048)
            connected.append("udp")

    threading.Thread(target=receive, daemon=True).start()
    return int(listener.getsockname()[1])


TCP, UDP = _listen_tcp(), _listen_udp()
_RTC = (
    "const pc = new W.RTCPeerConnection({iceServers: ["
    f"{{urls: 'stun:127.0.0.1:{UDP}'}}, {{urls: 'turn:127.0.0.1:{TCP}"
    "?transport=tcp', username: 'u', credential: 'p'}]});"
    "pc.createDataChannel('x'); pc.createOffer().then(o => pc.setLocalDescription(o));"
)
# The ways past the page's own requests, measured on 0.8.0 reaching the private
# address with the guard installed: the browser makes these requests itself,
# where no route sees them.
_ROUTES_PAST_THE_PAGE = {
    path: ("<html><body><p>public page</p>" + body + "</body></html>").encode()
    for path, body in {
        "/speculation": (
            '<script type="speculationrules">'
            + json.dumps(
                {
                    "prefetch": [
                        {"source": "list", "urls": [f"{PRIVATE_URL}/prefetch"]}
                    ],
                    "prerender": [
                        {"source": "list", "urls": [f"{PRIVATE_URL}/prerender"]}
                    ],
                }
            )
            + "</script>"
        ),
        "/speculation-elsewhere": (
            '<script type="speculationrules">'
            + json.dumps(
                {
                    "prefetch": [
                        {
                            "source": "list",
                            "urls": [f"http://localhost:{PRIVATE}/cross-site"],
                        }
                    ]
                }
            )
            + "</script>"
        ),
        "/speculation-by-script": (
            "<script>const s = document.createElement('script');"
            "s.type = 'speculationrules'; s.textContent = JSON.stringify("
            f"{{prefetch: [{{source: 'list', urls: ['{PRIVATE_URL}/scripted']}}]}});"
            "document.head.append(s);</script>"
        ),
        "/webrtc": f"<script>const W = window; {_RTC}</script>",
        "/webrtc-in-a-frame": (
            "<script>const f = document.createElement('iframe');"
            f"document.body.append(f); const W = f.contentWindow; {_RTC}</script>"
        ),
    }.items()
}


def main() -> int:
    from sluicer.fetch import address
    from sluicer.fetch.address import AddressRefused
    from sluicer.fetch.rungs import default_rungs

    # 127.0.0.1 is private, so the check is taught which port is "the web".
    judge = address._judge

    def by_port(url: str, resolve: object) -> tuple[str | None, list[object]]:
        if urlsplit(url.replace("ws://", "http://", 1)).port == PUBLIC:
            return None, [ipaddress.ip_address("127.0.0.1")]
        return judge(url, resolve)  # type: ignore[arg-type]

    address._judge = by_port  # type: ignore[assignment]
    browser = dict(default_rungs(allow_private=False))["browser"]
    failures = []

    page = browser(f"http://127.0.0.1:{PUBLIC}/page")
    if "public page" not in page.html:
        failures.append("the public page itself did not load")
    if 'data-sw="true"' in page.html:
        failures.append("the page was given service workers")

    followed = browser(f"http://127.0.0.1:{PUBLIC}/document-redirect")
    if not followed.url.endswith("/page") or "public page" not in followed.html:
        failures.append(f"the document's redirect was not followed: {followed.url}")

    try:
        browser(f"http://127.0.0.1:{PUBLIC}/document-to-private")
        failures.append("a document redirected to a private address was returned")
    except AddressRefused:
        pass

    if reached:
        failures.append(f"the private server was reached: {sorted(set(reached))}")

    for path in [*_ROUTES_PAST_THE_PAGE, "/rules-header"]:
        reached.clear()
        connected.clear()
        page = browser(f"http://127.0.0.1:{PUBLIC}{path}")
        # What the browser does for a page it may do after the load.
        time.sleep(1.0)
        if "public page" not in page.html:
            failures.append(f"{path}: the public page itself did not load")
        if reached or connected:
            failures.append(
                f"{path}: the private address was reached: {reached + connected}"
            )

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "guard: a real browser reached nothing private, by any of thirteen "
            "routes, speculation rules and WebRTC among them"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
