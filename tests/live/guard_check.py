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
import socketserver
import sys
import threading
from urllib.parse import urlsplit

reached: list[str] = []


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
        if self.path in pages:
            self._send(200, pages[self.path])
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


def main() -> int:
    from sluicer.fetch import address
    from sluicer.fetch.address import AddressRefused
    from sluicer.fetch.rungs import default_rungs

    # 127.0.0.1 is private, so the check is taught which port is "the web".
    judge = address._judge

    def by_port(url: str, resolve: object) -> tuple[str | None, list[object]]:
        if urlsplit(url.replace("ws://", "http://", 1)).port == PUBLIC:
            return None, []
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
    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print("guard: a real browser reached nothing private, by any of seven routes")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
