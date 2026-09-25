"""A browser host that drives no browser, for the browser rung's tests.

``FakeHost`` stands where ``sluicer.fetch.browser.HOST`` stands: the rung
hands it a job, and the job is run against a fake browser whose contexts and
pages record what they were told -- the context's options, its routes and
cookies, every address loaded -- and answer from ``pages``: an address to
its HTML, or ``"->"`` and where the document is redirected, which a guarded
page sees its guard refuse, as Chromium does when the route aborts it.
"""

from __future__ import annotations

import types
from typing import Any


class FakeHost:
    def __init__(self, pages: dict[str, str], status: int = 200) -> None:
        self.pages = pages
        self.status = status
        self.loads: list[str] = []
        self.contexts: list[FakeContext] = []
        self.closed = 0

    def run(self, job: Any, wait: float = 0.0) -> Any:
        return job(FakeBrowser(self))


class FakeBrowser:
    def __init__(self, host: FakeHost) -> None:
        self.host = host

    def new_context(self, **options: Any) -> FakeContext:
        context = FakeContext(self.host, options)
        self.host.contexts.append(context)
        return context


class FakeContext:
    def __init__(self, host: FakeHost, options: dict[str, Any]) -> None:
        self.host = host
        self.options = options
        self.routes: list[tuple[str, Any]] = []
        self.sockets: list[tuple[str, Any]] = []
        self.scripts: list[str] = []
        self.cookies: list[dict[str, str]] = []
        self.closed = False

    def add_init_script(self, script: str) -> None:
        self.scripts.append(script)

    def route(self, pattern: str, handler: Any) -> None:
        self.routes.append((pattern, handler))

    def route_web_socket(self, pattern: str, handler: Any) -> None:
        self.sockets.append((pattern, handler))

    def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        self.cookies.extend(cookies)

    def new_page(self) -> FakePage:
        return FakePage(self)

    def close(self) -> None:
        self.closed = True
        self.host.closed += 1


class FakePage:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.url = ""
        self.html = ""

    def goto(self, url: str, wait_until: str, timeout: float) -> Any:
        host = self.context.host
        host.loads.append(url)
        answer = host.pages[url]
        if answer.startswith("->"):
            guards = [
                handler.__self__
                for _, handler in self.context.routes
                if hasattr(handler, "__self__")
            ]
            if guards:
                guards[0].redirect = answer[2:]
                raise RuntimeError("Page.goto: net::ERR_BLOCKED_BY_CLIENT")
            url, answer = answer[2:], host.pages[answer[2:]]
        self.url = url
        self.html = answer
        return types.SimpleNamespace(
            status=host.status,
            headers_array=lambda: [
                {"name": "X-Robots-Tag", "value": "noindex"},
                {"name": "Link", "value": "</a>; rel=canonical"},
                {"name": "link", "value": "</b>; rel=next"},
            ],
        )

    def wait_for_load_state(self, state: str, timeout: float) -> None:
        pass

    def content(self) -> str:
        return self.html
