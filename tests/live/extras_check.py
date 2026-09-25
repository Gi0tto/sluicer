"""Each fetching extra, installed for real and called for real.

Run by CI's with-extras job after ``uv pip install '.[browser,stealth,...]'``
and a browser install. The suite fakes Playwright and scrapling, and a fake
confirms only the shape you already believe in: this asks the installed
packages to load pages from a local site and reads what the site saw.

    python tests/live/extras_check.py
"""

from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import sys
import threading

heard: list[tuple[str, dict[str, str]]] = []

PLAIN = (
    "<html><head><title>Plain</title></head><body>"
    + "<p>Words a plain page says.</p>" * 20
    + "</body></html>"
)
# A shell that only a browser fills: nothing declared, a script, no text.
SHELL = (
    "<html><head><title>App</title></head><body><div id='root'></div>"
    "<script>document.getElementById('root').textContent = "
    "'Rendered by its script. '.repeat(30);</script></body></html>"
)


class Site(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        heard.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        if self.path == "/robots.txt":
            body, kind = b"User-agent: *\nAllow: /\n", "text/plain"
        elif self.path.startswith("/app"):
            body, kind = SHELL.encode(), "text/html"
        else:
            body, kind = PLAIN.encode(), "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Site)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    from sluicer.fetch import fetch
    from sluicer.fetch.browser import HOST
    from sluicer.fetch.gate import GATE
    from sluicer.fetch.identity import USER_AGENT

    GATE.min_delay = 0.2
    failures = []

    plain = fetch(base + "/plain")
    if plain.rung != "http" or plain.climbs:
        failures.append(f"a plain page climbed: {plain.rung} {plain.climbs}")

    first = fetch(base + "/app/1")
    if first.rung != "browser" or "Rendered by its script" not in first.html:
        failures.append(f"a shell was not rendered by the browser: {first.rung}")
    second = fetch(base + "/app/2")
    if second.rung != "browser":
        failures.append(f"the second shell came from {second.rung}")
    elif not second.climbs or "earlier page" not in second.climbs[0].reason:
        failures.append(f"the second shell climbed again: {second.climbs}")
    if [p for p, _ in heard].count("/app/2") != 1:
        failures.append("the second shell was asked more than once")
    if HOST.launched != 1:
        failures.append(f"{HOST.launched} browsers were started for one process")
    browser_said = [h for p, h in heard if p == "/app/1"][-1]
    if browser_said.get("user-agent") != USER_AGENT or "referer" in browser_said:
        failures.append(f"the browser did not say who it is: {browser_said}")

    from sluicer.fetch.stealth import stealth_rung

    _, stealth = stealth_rung()
    disguised = stealth(base + "/app/stealth")
    if "Rendered by its script" not in disguised.html:
        failures.append("the stealth rung did not render the shell")
    stealth_said = [h for p, h in heard if p == "/app/stealth"][-1]
    if "referer" in stealth_said:
        failures.append(f"the stealth rung borrowed a referer: {stealth_said}")

    done = subprocess.run(
        [sys.executable, "-m", "sluicer", "fetch", base + "/app/3", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if done.returncode != 0:
        failures.append(f"sluicer fetch exited {done.returncode}: {done.stderr}")
    else:
        answer = json.loads(done.stdout)
        if answer["rung"] != "browser" or "Rendered" not in answer["html"]:
            failures.append(f"sluicer fetch did not render: {answer['rung']}")

    for failure in failures:
        print("FAIL:", failure)
    if not failures:
        print(
            "extras: plain HTTP from the base, the browser rendering and "
            "remembered, one browser, stealth with no referer, sluicer fetch"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
