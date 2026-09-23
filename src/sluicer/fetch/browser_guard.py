"""Keep the browser rung off the addresses its caller refused.

A browser asks for whatever the page tells it to: images, scripts, frames,
``fetch()`` calls, websockets, and every redirect along the way. With
``allow_private`` false, each of those passes through a route that judges its
address first, the same judgement the HTTP rung makes.

The route fetches each request itself, one hop at a time, because a browser
left to follow a redirect does it without asking the route again: measured
with Chromium, a redirect fulfilled from a route is followed straight to its
target. So no redirect is ever handed to the browser. A subresource's chain is
walked here and only its last answer handed over; the document's own redirect
stops the load, and the rung asks for the new address as a fresh fetch, which
is judged like the first.

What it cannot do: the browser still resolves names in its own network stack,
so a name that answers differently between the check and the connection (DNS
rebinding) is reached. Only the HTTP rung pins its connections. Service workers
fetch outside any route, so the page is not given them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit

from sluicer.fetch.address import _resolve, why_not_public

MAX_REDIRECTS = 10
"""How many redirects one request may follow inside the browser."""

_NO_SERVICE_WORKERS = (
    "Object.defineProperty(Navigator.prototype, 'serviceWorker', "
    "{get() { return undefined; }, configurable: true});"
)


class Guard:
    """The route a browser page goes through, and what it saw.

    ``setup`` is handed to the browser before navigation. Afterwards
    ``installed`` says it ran -- scrapling logs and swallows an exception in
    it, so the rung checks rather than trusts -- ``redirect`` is where the
    document itself was sent, and ``refused`` lists every address turned away.
    """

    def __init__(self, resolve: Callable[[str], Iterable[str]] = _resolve) -> None:
        self.resolve = resolve
        self.installed = False
        self.redirect: str | None = None
        self.refused: list[tuple[str, str]] = []
        self._verdicts: dict[tuple[str, str], str | None] = {}

    def setup(self, page: Any) -> None:
        page.add_init_script(_NO_SERVICE_WORKERS)
        page.route("**/*", self._route)
        page.route_web_socket("**/*", self._socket)
        self.installed = True

    def why_refused(self, url: str) -> str | None:
        """Why ``url`` may not be asked, or None; one lookup per host and scheme."""
        try:
            parts = urlsplit(url)
            key = (parts.scheme.lower(), parts.netloc.lower())
        except ValueError:
            return "the address is not a valid URL"
        if key not in self._verdicts:
            self._verdicts[key] = why_not_public(url, self.resolve)
        return self._verdicts[key]

    def _refuse(self, url: str, reason: str) -> None:
        self.refused.append((url, reason))

    def _route(self, route: Any) -> None:
        request = route.request
        url = request.url
        if urlsplit(url).scheme.lower() not in ("http", "https"):
            route.continue_()
            return
        reason = self.why_refused(url)
        if reason is not None:
            self._refuse(url, reason)
            route.abort("blockedbyclient")
            return
        current = url
        response = _fetch(route, url)
        for _ in range(MAX_REDIRECTS + 1):
            if response is None:
                route.abort("failed")
                return
            location = response.headers.get("location")
            if not (300 <= response.status < 400 and location):
                route.fulfill(response=response)
                return
            target = urljoin(current, location)
            if _is_the_document(request):
                # The rung asks for it again, judged like the first address.
                self.redirect = target
                route.abort("blockedbyclient")
                return
            reason = self.why_refused(target)
            if reason is not None:
                self._refuse(target, reason)
                route.abort("blockedbyclient")
                return
            current = target
            response = _fetch(route, target)
        self._refuse(url, f"more than {MAX_REDIRECTS} redirects")
        route.abort("blockedbyclient")

    def _socket(self, socket: Any) -> None:
        # A websocket's address is judged as its http twin would be.
        twin = "http" + socket.url[2:] if socket.url.startswith("ws") else socket.url
        reason = self.why_refused(twin)
        if reason is not None:
            # Left unconnected, the page's socket talks to nothing. Closing it
            # from inside this handler hangs Playwright's sync API: measured.
            self._refuse(socket.url, reason)
            return
        socket.connect_to_server()


def _fetch(route: Any, url: str) -> Any:
    """One hop, no redirect followed, or None when nothing answered."""
    try:
        return route.fetch(url=url, max_redirects=0)
    except Exception:  # noqa: BLE001 -- any failure to answer is the same event
        return None


def _is_the_document(request: Any) -> bool:
    """Whether ``request`` loads the page itself, not something inside it."""
    try:
        return bool(request.is_navigation_request()) and (
            request.frame.parent_frame is None
        )
    except Exception:  # noqa: BLE001 -- a request with no frame is not the page
        return False
