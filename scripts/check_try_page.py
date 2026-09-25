"""Open the try page in a real browser and hold its answers to the native ones.

    python scripts/check_try_page.py            (Playwright and its Chromium installed)

docs/try/ is served from a temporary folder, with the files the site gets
(scripts/docs_try.py), by a static file server on 127.0.0.1: the page needs
nothing else. In a new browser context, so the browser's cache is empty, the
page is opened, Pyodide starts, and every page the npm package's tests read
is pasted in, with its address and options, as a reader would. The answer the
page shows must be the one the Python package in this checkout gives on the
same text.

It also proves what the page promises: every request it makes is a GET for a
file, to this server or to Pyodide's CDN; none is made once Sluicer is ready,
so nothing of a pasted page leaves the browser; and the page raised no error.
It prints how long the page took to be ready and what it downloaded, which
docs/javascript.md reports. Exits 1 on any failure.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

import sluicer

ROOT = Path(__file__).resolve().parent.parent
CDN = "cdn.jsdelivr.net"
# Loading Pyodide and lxml on a slow runner takes well under this.
READY_WITHIN_MS = 120_000


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch:
        site = Path(scratch)
        shutil.copytree(ROOT / "docs" / "try", site / "try")
        for uri, path in _hook().try_files().items():
            shutil.copyfile(path, site / uri)
        server = _serve(site)
        try:
            return _check(f"http://127.0.0.1:{server.server_port}/try/")
        finally:
            server.shutdown()


def _check(address: str) -> int:
    failures: list[str] = []
    cases = _cases()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        requests: list[Any] = []
        errors: list[str] = []
        page.on("request", lambda request: requests.append(request))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                errors.append(message.text) if message.type == "error" else None
            ),
        )

        page.goto(address)
        page.wait_for_selector(
            "#status[data-state=ready], #status[data-state=failed]",
            timeout=READY_WITHIN_MS,
        )
        if page.get_attribute("#status", "data-state") != "ready":
            failures.append(f"the page did not start: {page.text_content('#status')}")
            return _report(failures)
        ready_ms = float(page.get_attribute("#status", "data-ready-ms") or "nan")
        loaded = list(requests)

        same = 0
        for name, case in cases.items():
            page.fill("#html", case["text"])
            page.fill("#url", case["url"] or "")
            page.set_checked("#induce", bool(case["options"].get("induce")))
            page.set_checked("#visible", bool(case["options"].get("visible")))
            page.click("#run")
            shown = json.loads(page.text_content("#json") or "null")
            found = sluicer.extract(case["text"], url=case["url"], **case["options"])
            native = json.loads(json.dumps(asdict(found)))
            if shown == native:
                same += 1
            else:
                failures.append(f"{name}: the page's answer is not the native one")

        page.fill("#html", "")
        page.click("#example")
        # Not wait_for_function: its text is evaluated, which the page's
        # policy refuses.
        expect(page.locator("#html")).not_to_have_value("")
        page.click("#run")
        example = (ROOT / "examples" / "brake-pads.html").read_text(encoding="utf-8")
        if page.input_value("#html") != example:
            failures.append("the example button does not load examples/brake-pads.html")
        if "41.90" not in (page.text_content("#summary") or ""):
            failures.append("the summary table does not show the example's price")

        after = requests[len(loaded) :]
        failures += [
            f"a request once Sluicer was ready: {r.method} {r.url}" for r in after
        ]
        server = urlsplit(address).netloc
        for request in loaded:
            where = urlsplit(request.url).netloc
            if request.method != "GET" or request.post_data:
                failures.append(f"not a plain GET: {request.method} {request.url}")
            if where not in (server, CDN):
                failures.append(
                    f"a request to neither the site nor {CDN}: {request.url}"
                )
        failures += [f"the page reported an error: {error}" for error in errors]

        by_host: dict[str, int] = {}
        for request in loaded:
            response = request.response()
            size = request.sizes()["responseBodySize"] if response else 0
            host = urlsplit(request.url).netloc
            by_host[host] = by_host.get(host, 0) + size

        page.reload()
        page.wait_for_selector("#status[data-state=ready]", timeout=READY_WITHIN_MS)
        again_ms = float(page.get_attribute("#status", "data-ready-ms") or "nan")
        browser.close()

    print(f"{len(cases)} pages pasted, {same} answered as the native package answers")
    print(
        f"ready in {ready_ms / 1000:.2f} s with an empty cache, "
        f"{again_ms / 1000:.2f} s reloaded"
    )
    print(
        f"{len(loaded)} requests before Sluicer was ready, to "
        f"{', '.join(sorted(by_host))}; {len(after)} after"
    )
    for host, size in sorted(by_host.items()):
        print(f"  {host}: {size:,} bytes over the wire")
    print(f"  together: {sum(by_host.values()):,} bytes")
    return _report(failures)


def _cases() -> dict[str, dict[str, Any]]:
    """The npm package's test pages, as a reader would paste them: as text,
    with their address and the options the page offers."""
    cases: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "js" / "test" / "expected" / "extract").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if set(case["options"]) - {"induce", "visible"}:
            continue  # headers: a pasted page has none
        raw = (ROOT / case["page"]).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        cases[path.stem] = {
            "text": text,
            "url": case["url"],
            "options": case["options"],
        }
    return cases


def _hook() -> Any:
    spec = importlib.util.spec_from_file_location(
        "docs_try", ROOT / "scripts" / "docs_try.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serve(site: Path) -> ThreadingHTTPServer:
    handler = functools.partial(_Quiet, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def _report(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
