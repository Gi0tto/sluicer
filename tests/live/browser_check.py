"""The browser rung against a real Chromium: what it sends, and to whom.

Run by CI after installing a browser; not part of the unit suite, which drives
a fake host. Two local sites stand for the site asked and another one the page
reaches, on another host name: the caller's headers and cookies must reach the
first and never the second, guarded or not. (Another port of the same host
would be sent the cookies: a cookie belongs to a host, not to a port, in every
browser, RFC 6265 section 8.5. Measured here with the guard, whose requests
carry the context's cookies.) A proxy asked for must be the one used, and one
browser must serve every page of the process.

    python tests/live/browser_check.py
"""

from __future__ import annotations

import contextlib
import http.server
import socket
import socketserver
import sys
import threading
import time
from urllib.parse import urlsplit

heard: dict[str, list[dict[str, str]]] = {"asked": [], "other": []}


def _handler(name: str, page: str) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            said = {k.lower(): v for k, v in self.headers.items()}
            heard[name].append({"path": self.path, **said})
            body = page.encode() if self.path.startswith("/page") else b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _serve(handler: type[http.server.BaseHTTPRequestHandler]) -> int:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return int(server.server_address[1])


OTHER = _serve(_handler("other", ""))


class _Mixed(http.server.BaseHTTPRequestHandler):
    """A site whose /app page a script draws and whose /news pages are plain
    HTML, and which refuses a browser -- one that says it is Chromium --
    with 403."""

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        said = {k.lower() for k in self.headers}
        if self.path.startswith("/app"):
            status, body = (
                200,
                (
                    "<html><body><div id=root></div><script>document.getElementById"
                    "('root').innerHTML='<p>'+'drawn words '.repeat(40)+'</p>'"
                    "</script></body></html>"
                ),
            )
        elif "sec-ch-ua" in said:
            status, body = 403, "<html><body>no browsers</body></html>"
        else:
            status, body = 200, "<html><body>" + "<p>the article</p>" * 30
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


MIXED = _serve(_Mixed)
PAGE = (
    "<html><body><p>" + "Words the page says. " * 20 + "</p>"
    "<script>fetch('/api').catch(() => 0);"
    f"fetch('http://localhost:{OTHER}/lib').catch(() => 0);</script>"
    "</body></html>"
)
ASKED = _serve(_handler("asked", PAGE))


def _judged_public() -> None:
    """127.0.0.1 is private: the guard is taught that these two ports are
    the web, as tests/live/guard_check.py teaches it one."""
    from sluicer.fetch import address

    judge = address._judge

    def by_port(url: str, resolve: object) -> tuple[str | None, list[object]]:
        if urlsplit(url.replace("ws://", "http://", 1)).port in (ASKED, OTHER):
            return None, []
        return judge(url, resolve)  # type: ignore[arg-type]

    address._judge = by_port  # type: ignore[assignment]


def main() -> int:
    from sluicer.fetch.browser import HOST, browser_rung
    from sluicer.fetch.identity import USER_AGENT

    _judged_public()
    failures = []
    url = f"http://127.0.0.1:{ASKED}/page"
    for guarded in (False, True):
        heard["asked"].clear()
        heard["other"].clear()
        rung = browser_rung(
            allow_private=not guarded,
            headers={"X-Team": "reader"},
            cookies={"session": "s3cret"},
        )
        page = rung(url)
        time.sleep(0.3)
        mode = "guarded" if guarded else "unguarded"
        if "Words the page says" not in page.html:
            failures.append(f"{mode}: the page did not load")
        document = next((h for h in heard["asked"] if h["path"] == "/page"), {})
        api = next((h for h in heard["asked"] if h["path"] == "/api"), {})
        for label, request in (("the page", document), ("its /api", api)):
            if request.get("x-team") != "reader":
                failures.append(f"{mode}: {label} went without the header: {request}")
            if "session=s3cret" not in request.get("cookie", ""):
                failures.append(f"{mode}: {label} went without the cookie: {request}")
            if request.get("user-agent") != USER_AGENT:
                failures.append(f"{mode}: {label} did not say who it is: {request}")
        if not heard["other"]:
            failures.append(f"{mode}: the other site was never asked; nothing tested")
        for request in heard["other"]:
            if "x-team" in request or "cookie" in request:
                failures.append(f"{mode}: the other site was sent {request}")

    # Built for one origin and handed an address on another -- as a crawl
    # hands it the site's www. twin or its pages over http -- it sends that
    # address nothing of the login.
    heard["asked"].clear()
    elsewhere = browser_rung(
        headers={"X-Team": "reader"},
        cookies={"session": "s3cret"},
        send_to=[f"http://localhost:{ASKED}/"],
    )
    elsewhere(url)
    time.sleep(0.3)
    if not heard["asked"]:
        failures.append("the page of another origin was never asked; nothing tested")
    for request in heard["asked"]:
        if "x-team" in request or "cookie" in request:
            failures.append(f"a login fixed for another origin was sent {request}")

    # A site remembered for the browser, whose next page the browser is
    # refused and plain HTTP reads whole: the page comes from plain HTTP, and
    # the memory is forgotten.
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.ladder import RungMemory, fetch

    memory = RungMemory()
    ladder = [("http", http_rung()), ("browser", browser_rung())]
    mixed = f"http://127.0.0.1:{MIXED}"
    app = fetch(f"{mixed}/app", rungs=ladder, memory=memory, obey_robots=False)
    news = fetch(f"{mixed}/news/1", rungs=ladder, memory=memory, obey_robots=False)
    if app.rung != "browser":
        failures.append(f"the drawn page was not the browser's: {app.rung}")
    if (news.rung, news.status) != ("http", 200):
        failures.append(
            f"the remembered browser's 403 was the page: {news.rung} {news.status}"
        )
    if memory.recall(f"{mixed}/news/2") is not None:
        failures.append("a browser refused was still remembered for the site")

    # A proxy asked for is the one used: a socket that notes what reaches it.
    proxy = socket.create_server(("127.0.0.1", 0))
    told: list[bytes] = []

    def _listen() -> None:
        while True:
            connection, _ = proxy.accept()
            connection.settimeout(2)
            with contextlib.suppress(OSError):
                told.append(connection.recv(300).split(b"\r\n")[0])
            connection.close()

    threading.Thread(target=_listen, daemon=True).start()
    through = browser_rung(proxy=f"http://127.0.0.1:{proxy.getsockname()[1]}")
    with contextlib.suppress(Exception):
        through("http://nowhere.invalid/page")
    if not any(b"nowhere.invalid" in line for line in told):
        failures.append(f"the proxy asked for was not used: {told}")

    started = time.monotonic()
    plain = browser_rung()
    for _ in range(5):
        plain(url)
    each = (time.monotonic() - started) / 5
    if HOST.launched != 1:
        failures.append(f"{HOST.launched} browsers were started for one process")

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "browser: headers and cookies to the site asked and no other, guarded "
            "and not; a remembered browser refused is forgotten; the proxy asked "
            f"for; one browser, {each:.2f} s a page"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
