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

What it cannot do: see the requests the browser makes for the page rather than
the page itself -- a speculation rule's prefetch and prerender, a WebRTC
connection -- and stop a name that answers differently between the check and
the connection (DNS rebinding), since the browser resolves names in its own
network stack. The browser rung puts every connection of a guarded page
through ``sluicer.fetch.browser_proxy`` for both. Service workers fetch
outside any route, so the page is not given them, and WebRTC connects outside
any route, so the page is not given that either: it reached a private address
by STUN and by TURN, measured, and the guard proxy carries no UDP.

The caller's own headers (``send``) go with the requests for the origins it
named (``asked``), each hop of a chain judged again, and with none elsewhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import urljoin, urlsplit

from sluicer.fetch.address import _resolve, why_not_public

MAX_REDIRECTS = 10
"""How many redirects one request may follow inside the browser."""

_NO_SERVICE_WORKERS = (
    "Object.defineProperty(Navigator.prototype, 'serviceWorker', "
    "{get() { return undefined; }, configurable: true});"
)
# Every frame's, a frame a script makes included: an init script runs in each.
_NO_WEBRTC = (
    "for (const name of ['RTCPeerConnection', 'webkitRTCPeerConnection', "
    "'RTCDataChannel', 'RTCIceCandidate', 'RTCSessionDescription', "
    "'WebTransport']) { try { delete globalThis[name]; } catch (e) {} }"
)


class Guard:
    """The route a browser page goes through, and what it saw.

    ``setup`` is handed the page's context before navigation. Afterwards
    ``installed`` says it ran -- scrapling, which the stealth rung hands it
    to, logs and swallows an exception in it, so the rungs check rather than
    trust -- ``redirect`` is where the
    document itself was sent, and ``refused`` lists every address turned away.
    """

    def __init__(
        self,
        resolve: Callable[[str], Iterable[str]] = _resolve,
        send: Mapping[str, str] | None = None,
        asked: Sequence[str] = (),
    ) -> None:
        self.resolve = resolve
        self.send = dict(send or {})
        self.asked = tuple(asked)
        self.installed = False
        self.redirect: str | None = None
        self.refused: list[tuple[str, str]] = []
        self._verdicts: dict[tuple[str, str], str | None] = {}

    def setup(self, page: Any) -> None:
        """Route every request of ``page`` -- a page or a browser context,
        which take the same calls -- through this guard."""
        page.add_init_script(_NO_SERVICE_WORKERS)
        page.add_init_script(_NO_WEBRTC)
        page.route("**/*", self._route)
        page.route_web_socket("**/*", self._socket)
        self.installed = True

    def _headers(self, route: Any, url: str) -> dict[str, str] | None:
        """What a hop to ``url`` sends: the request's own headers, and the
        caller's when it is an origin they were given for; None, the
        request's own unchanged, when there are none to add."""
        if not self.send or not any(same_origin(url, one) for one in self.asked):
            return None
        return {**route.request.headers, **self.send}

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
        response = _fetch(route, url, self._headers(route, url))
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
            response = _fetch(route, target, self._headers(route, target))
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


def _fetch(route: Any, url: str, headers: dict[str, str] | None = None) -> Any:
    """One hop, no redirect followed, or None when nothing answered."""
    try:
        if headers is None:
            return route.fetch(url=url, max_redirects=0)
        return route.fetch(url=url, max_redirects=0, headers=headers)
    except Exception:  # noqa: BLE001 -- any failure to answer is the same event
        return None


def same_origin(url: str, asked: str) -> bool:
    """Whether ``url`` is on the scheme, host and port of ``asked``."""
    try:
        one, two = urlsplit(url), urlsplit(asked)
        return (
            one.scheme.lower() == two.scheme.lower()
            and (one.hostname or "") == (two.hostname or "")
            and _port(one) == _port(two)
        )
    except ValueError:
        return False


def _port(parts: Any) -> int:
    return int(parts.port or (443 if parts.scheme.lower() == "https" else 80))


def _is_the_document(request: Any) -> bool:
    """Whether ``request`` loads the page itself, not something inside it."""
    try:
        return bool(request.is_navigation_request()) and (
            request.frame.parent_frame is None
        )
    except Exception:  # noqa: BLE001 -- a request with no frame is not the page
        return False
