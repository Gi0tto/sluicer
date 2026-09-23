"""The crawler against a real curl and two local sites, its politeness measured.

Run by CI with the fetch extra installed; not part of the unit suite, which
opens no sockets and fakes the web. A fake clock confirms only the schedule you
already believe in: here the server writes down when each request arrived and
when its answer was sent, and the gaps are read from that.

One site has a sitemap index naming a plain and a gzipped sitemap, a robots.txt
with a Disallow and a Crawl-delay, a link loop, a chain of redirects, a redirect
to the other site, and a slow page. The other site must never be asked.

    python tests/live/crawl_check.py
"""

from __future__ import annotations

import gzip
import http.server
import socketserver
import sys
import tempfile
import threading
import time
from itertools import pairwise
from pathlib import Path

CRAWL_DELAY = 0.5
MIN_DELAY = 0.2
SLOW_SECONDS = 1.0
# The server's clock and the crawler's are one clock, but the server notes an
# answer sent a hair before the crawler has finished reading it.
TOLERANCE = 0.02

log: list[dict[str, object]] = []
in_flight = {"now": 0, "most": 0}
lock = threading.Lock()


def _page(title: str, *links: str) -> bytes:
    anchors = "".join(f'<a href="{link}">{link}</a>' for link in links)
    return (
        f"<html><head><title>{title}</title>"
        '<script type="application/ld+json">'
        f'{{"@type":"Product","name":"{title}"}}</script></head>'
        f"<body>{anchors}{'Real content. ' * 20}</body></html>"
    ).encode()


def _urlset(*locs: str) -> bytes:
    entries = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    ).encode()


class _Quiet(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Site(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        started = time.monotonic()
        with lock:
            in_flight["now"] += 1
            in_flight["most"] = max(in_flight["most"], in_flight["now"])
        try:
            status, body, headers = self.answer()
            if self.path == "/slow":
                time.sleep(SLOW_SECONDS)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        finally:
            with lock:
                in_flight["now"] -= 1
                log.append(
                    {
                        "site": self.server.server_address[1],
                        "path": self.path,
                        "start": started,
                        "end": time.monotonic(),
                        "agent": self.headers.get("User-Agent"),
                    }
                )

    def answer(self) -> tuple[int, bytes, dict[str, str]]:
        html = {"Content-Type": "text/html; charset=utf-8"}
        if self.server.server_address[1] == OTHER_PORT:
            return 200, _page("Elsewhere"), html
        pages: dict[str, tuple[int, bytes, dict[str, str]]] = {
            "/robots.txt": (
                200,
                (
                    "User-agent: *\nDisallow: /private/\n"
                    f"Crawl-delay: {CRAWL_DELAY}\n"
                    f"Sitemap: {MAIN}/sitemap_index.xml\n"
                ).encode(),
                {"Content-Type": "text/plain"},
            ),
            "/sitemap_index.xml": (
                200,
                (
                    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"<sitemap><loc>{MAIN}/sitemap-pages.xml</loc></sitemap>"
                    f"<sitemap><loc>{MAIN}/sitemap-more.xml.gz</loc></sitemap>"
                    f"<sitemap><loc>{OTHER}/sitemap.xml</loc></sitemap>"
                    "</sitemapindex>"
                ).encode(),
                {"Content-Type": "application/xml"},
            ),
            "/sitemap-pages.xml": (
                200,
                _urlset(f"{MAIN}/", f"{MAIN}/a", f"{MAIN}/b", f"{MAIN}/private/secret"),
                {"Content-Type": "application/xml"},
            ),
            # Gzip the server does not announce as an encoding, as a file is.
            "/sitemap-more.xml.gz": (
                200,
                gzip.compress(_urlset(f"{MAIN}/slow", f"{MAIN}/c", f"{OTHER}/x")),
                {"Content-Type": "application/gzip"},
            ),
            "/": (
                200,
                _page(
                    "Home",
                    "/a",
                    "/b",
                    "/old",
                    "/away",
                    "/private/secret",
                    "/slow",
                    "/manual.pdf",
                ),
                html,
            ),
            "/a": (200, _page("A", "/b", "/"), html),
            "/b": (200, _page("B", "/a", "/c"), html),
            "/c": (200, _page("C", "/"), html),
            "/old": (301, b"", {"Location": "/mid"}),
            "/mid": (302, b"", {"Location": "/new"}),
            "/new": (200, _page("New", "/"), html),
            "/away": (302, b"", {"Location": f"{OTHER}/landing"}),
            "/slow": (200, _page("Slow", "/c"), html),
            "/private/secret": (200, _page("Secret"), html),
        }
        return pages.get(self.path, (404, b"not found", {"Content-Type": "text/plain"}))


def _serve() -> int:
    server = _Quiet(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return int(server.server_address[1])


MAIN_PORT, OTHER_PORT = _serve(), _serve()
MAIN, OTHER = f"http://127.0.0.1:{MAIN_PORT}", f"http://127.0.0.1:{OTHER_PORT}"
EXPECTED = ["/", "/a", "/b", "/old", "/away", "/private/secret", "/slow", "/c"]


def _requests(port: int) -> list[dict[str, object]]:
    with lock:
        return [entry for entry in log if entry["site"] == port]


def _polite(run: str, failures: list[str]) -> None:
    """Every gap between two requests to the site, measured by the site."""
    asked = sorted(_requests(MAIN_PORT), key=lambda entry: float(entry["start"]))
    gaps = [float(nxt["start"]) - float(prev["end"]) for prev, nxt in pairwise(asked)]
    short = [round(gap, 3) for gap in gaps if gap < CRAWL_DELAY - TOLERANCE]
    if short:
        failures.append(f"{run}: requests closer than the Crawl-delay: {short}")
    print(
        f"{run}: {len(asked)} requests, the shortest gap "
        f"{min(gaps, default=0):.3f} s against a Crawl-delay of {CRAWL_DELAY} s"
    )


def main() -> int:
    from sluicer.crawl import crawl, map_site
    from sluicer.fetch.identity import USER_AGENT

    failures: list[str] = []
    main_url = f"{MAIN}/"

    mapped = map_site(main_url, min_delay=MIN_DELAY)
    listed = [address.url.removeprefix(MAIN) for address in mapped.urls]
    if listed != ["/", "/a", "/b", "/private/secret", "/slow", "/c"]:
        failures.append(f"map: the sitemaps gave {listed}")
    kinds = [(read.url.removeprefix(MAIN), read.kind) for read in mapped.sitemaps]
    if ("/sitemap-more.xml.gz", "urlset") not in kinds:
        failures.append(f"map: the gzipped sitemap was not read: {kinds}")
    _polite("map", failures)

    log.clear()
    started = time.monotonic()
    whole = list(crawl(main_url, max_pages=20, min_delay=MIN_DELAY))
    seconds = time.monotonic() - started
    taken = [page.url.removeprefix(MAIN) for page in whole]
    if taken != EXPECTED:
        failures.append(f"crawl: took {taken}, not {EXPECTED}")
    codes = {
        page.url.removeprefix(MAIN): page.error.code for page in whole if page.error
    }
    if codes != {
        "/away": "redirected_off_site",
        "/private/secret": "refused_by_robots",
    }:
        failures.append(f"crawl: the pages that failed were {codes}")
    landed = {page.url.removeprefix(MAIN): page.landed for page in whole}
    if landed.get("/old") != f"{MAIN}/new":
        failures.append(f"crawl: the redirect chain landed on {landed.get('/old')}")
    paths = [str(entry["path"]) for entry in _requests(MAIN_PORT)]
    if "/private/secret" in paths:
        failures.append("crawl: a page robots.txt disallows was asked")
    repeated = sorted({path for path in paths if paths.count(path) > 1})
    if repeated:
        failures.append(f"crawl: asked more than once: {repeated}")
    _polite("crawl", failures)

    slow = next(entry for entry in _requests(MAIN_PORT) if entry["path"] == "/slow")
    after = min(
        float(entry["start"])
        for entry in _requests(MAIN_PORT)
        if float(entry["start"]) > float(slow["start"])
    )
    if after - float(slow["end"]) < CRAWL_DELAY - TOLERANCE:
        failures.append("crawl: the slow page's delay was counted from its start")
    print(
        f"crawl: {len(whole)} pages in {seconds:.1f} s; after the {SLOW_SECONDS} s "
        f"page the next request waited {after - float(slow['end']):.3f} s"
    )

    with tempfile.TemporaryDirectory() as folder:
        state = Path(folder) / "crawl.jsonl"
        log.clear()
        list(crawl(main_url, max_pages=4, min_delay=MIN_DELAY, state=state))
        first = [str(entry["path"]) for entry in _requests(MAIN_PORT)]
        log.clear()
        resumed = crawl(main_url, max_pages=20, min_delay=MIN_DELAY, state=state)
        rest = [page.url.removeprefix(MAIN) for page in resumed]
        second = [str(entry["path"]) for entry in _requests(MAIN_PORT)]
        again = sorted((set(first) & set(second)) - {"/robots.txt"})
        if again:
            failures.append(f"resume: asked again after resuming: {again}")
        written = [
            line.split('"url": "', 1)[1].split('"', 1)[0].removeprefix(MAIN)
            for line in state.read_text().splitlines()
        ]
        if written != EXPECTED or resumed.resumed != 4:
            failures.append(f"resume: the file holds {written}, the rest was {rest}")
        print(f"resume: 4 pages, then {len(rest)} more, none asked twice")

    if _requests(OTHER_PORT):
        paths = [entry["path"] for entry in _requests(OTHER_PORT)]
        failures.append(f"the other site was asked: {paths}")
    if in_flight["most"] > 1:
        failures.append(f"{in_flight['most']} requests were in flight at once")
    agents = {entry["agent"] for entry in log}
    if agents != {USER_AGENT}:
        failures.append(f"a request did not say who it is: {agents}")

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "crawl: sitemaps, robots, Crawl-delay, redirects, the loop, the slow "
            "page and resuming all hold, and the other site was never asked"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
