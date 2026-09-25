"""The plain HTTP rung, on the standard library, with the limits the ladder
promises.

* **A byte bound.** The body is read in chunks and decoded as it arrives, and
  the transfer stops once it passes the bound, after decompression, so a
  small gzip that inflates to gigabytes costs the bound and no more. A
  ``Content-Length`` past it is refused before the body is read.
* **A whole body or none.** A body that ends before the ``Content-Length``
  its server announced, or whose gzip, deflate or zstd stream ends before
  its end, is a ``ProtocolError``: the start of a page is never returned, or
  kept by a cache, as the page, and its connection is not kept either.
* **A deadline.** One fetch, every redirect hop and every byte of the body
  included, ends by ``HTTP_TIMEOUT_SECONDS``: a server that drips its body a
  few bytes a second is cut off there, not when it is done.
* **Redirects one hop at a time.** Nothing follows one on its own; every
  address a redirect names is judged before it is asked.
* **The web and nothing else.** Every hop must be http or https; there is no
  code here that speaks anything else.
* **A pinned connection.** With ``allow_private`` false, the connection goes
  to the addresses the host was just checked to have, and the name is never
  looked up again, so a name that answers differently the second time (DNS
  rebinding) reaches nothing new. A connection kept from an earlier request
  is used only while the address it reached is still among them.
* **A caller's rule for redirects.** A crawl keeps to its site by refusing a
  hop that leaves it, before the other site is asked anything.
* **No proxy unless asked.** ``HTTPS_PROXY`` and ``HTTP_PROXY`` are never read.
  A proxy is used only when given (``proxy``, or ``SLUICER_PROXY``).
* **One connection per site, kept.** Requests go through the process's pool
  (``sluicer.fetch.wire.CONNECTIONS``), so the pages of a site are asked on
  the connection the first one opened, while the server keeps it open. An
  interim answer -- a 102, a 103 Early Hints -- is read past to the answer it
  precedes, and a connection is kept only once that answer is read to its
  end: nothing of one answer is left on it for the next request to read.
* **The caller's headers stay with the site asked.** Headers a caller sends
  -- a cookie, an authorization, a cache's validators -- go to the origin
  asked for, and are left off a hop a redirect takes elsewhere. Given
  ``send_to``, the origins are fixed when the transport is built: whatever
  address it is later handed -- a link, a robots.txt, a sitemap another host
  serves, the site's own pages over plain http -- is sent them only when its
  scheme, host and port are one of those.

``http_responses`` is the same transport answering bytes, for what is not a
page: a sitemap, which may be gzip the server did not announce as an encoding.

What it sends was measured on the wire: ``Host``, our ``User-Agent``,
``Accept``, ``Accept-Encoding`` (gzip, deflate, and zstd where this Python
has it), and the caller's own headers. Nothing dresses it up as a browser.
"""

from __future__ import annotations

import base64
import functools
import http.client
import os
import ssl
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

from sluicer.declared.headers import charset
from sluicer.document import sniff_encoding
from sluicer.fetch.address import (
    AddressRefused,
    _resolve,
    public_addresses,
    why_not_web,
)
from sluicer.fetch.identity import USER_AGENT, refused_header
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    EmptyBody,
    Fetched,
    RedirectRefused,
    Redirects,
    ResponseTooLarge,
    Rung,
)
from sluicer.fetch.wire import (
    ACCEPT,
    ACCEPT_ENCODING,
    CONNECTIONS,
    Connections,
    Decoder,
    Overflow,
    Proxy,
    Target,
    Timed,
    Truncated,
    within,
)

PROXY_ENV = "SLUICER_PROXY"
"""The proxy every fetch goes through when none is given, if it is set.

Sluicer's own name, so that a proxy set for everything else on the machine is
not used without being asked for. Set it to an empty string, or leave it
unset, for none.
"""

HTTP_TIMEOUT_SECONDS = 20
"""How long the plain HTTP rung may take for one address: the whole of it,
looking the name up, connecting, every redirect hop and the body included.

Every wait on the connection is given what is left of it, not a timeout of
its own: a body sent eight bytes a second never trips a per-read timeout,
and was measured holding a request for as long as the server kept dripping.
"""

MAX_REDIRECTS = 10
"""How many redirects one fetch follows before it calls the chain a loop."""

_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_SWITCHING = 101
_NO_CONTENT = 204
_CHUNK = 65536
# What a path or a query may carry as it is: everything else is escaped, a
# space or a letter outside ASCII as a browser would send it.
_SAFE = "!#$%&'()*+,/:;=?@[]~"


class TooManyRedirects(Exception):
    """A chain of redirects longer than ``MAX_REDIRECTS``: a loop, most likely."""


class ProtocolError(ConnectionError):
    """The server's answer was not HTTP that could be read to its end: a body
    cut short, a header line without end, more headers than any page has."""


@dataclass(frozen=True)
class Response:
    """What the transport got for an address, before anything read it as a page.

    ``url`` is where the redirects ended. ``body`` is the bytes as they arrived,
    decompressed from any ``Content-Encoding`` and never heavier than the bound.
    """

    url: str
    status: int
    content_type: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


def http_responses(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    send: Mapping[str, str] | None = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    proxy: str | None = None,
    connections: Connections | None = None,
    send_to: Iterable[str] | None = None,
) -> Callable[[str], Response]:
    """Build the HTTP transport: an address in, a ``Response`` out.

    Args:
        allow_private: when false, every hop is judged by ``public_addresses``
            and the connection made to what it returned.
        resolve: the name lookup that judgement uses.
        max_bytes: the most a body may weigh before ``ResponseTooLarge``.
        redirects: the caller's rule for a redirect, asked before each hop is
            requested; a hop it refuses raises ``RedirectRefused``.
        send: headers sent beside ours to the origin asked for, and left off
            any hop on another: a cookie, an authorization, a cache's
            validators. Ours cannot be replaced: a ``User-Agent`` among them
            is a ``ValueError``, as is a header the transport itself writes.
        timeout: the seconds one address may take, every hop and the body
            included; past them the transfer is cut and ``TimeoutError``
            raised.
        proxy: the proxy to send every request through (``http://host:port``,
            ``socks5://host:port``, ``socks5h://host:port``, each with an
            optional ``user:password@``); ``SLUICER_PROXY`` when None, and no
            proxy at all when that is unset or empty. The environment's
            ``HTTPS_PROXY`` and ``HTTP_PROXY`` are never used. Another kind
            is a ``ValueError``.
        connections: the pool of open connections; the process's by default.
        send_to: the addresses whose origins -- scheme, host and port --
            ``send`` goes to, fixed here; None sends it to the origin of each
            address the transport is handed, which is right only for a
            caller that names every address itself.
    """
    through = chosen_proxy(proxy)
    named = Proxy.parse(through) if through is not None else None
    extra = dict(send or {})
    for name in extra:
        refusal = refused_header(name)
        if refusal is not None:
            raise ValueError(refusal)
    pool = connections if connections is not None else CONNECTIONS
    fixed = origins(send_to) if send_to is not None else None

    def checked(url: str) -> list[str]:
        return public_addresses(url, resolve)

    def get(url: str) -> Response:
        asked = fixed if fixed is not None else frozenset({_origin(url)})
        current = url
        deadline = time.monotonic() + timeout
        try:
            for _ in range(MAX_REDIRECTS + 1):
                not_web = why_not_web(current)
                if not_web is not None:
                    raise AddressRefused(current, not_web)
                if deadline - time.monotonic() <= 0:
                    raise TimeoutError
                addresses: tuple[str, ...] | None = None
                if not allow_private:
                    addresses = tuple(
                        within(deadline, functools.partial(checked, current))
                    )
                own = extra if _origin(current) in asked else {}
                status, headers, body = _exchange(
                    pool, current, addresses, named, own, max_bytes, deadline
                )
                location = headers.get("location")
                if status in _REDIRECTS and location:
                    target = urljoin(current, location)
                    not_web = why_not_web(target)
                    if not_web is not None:
                        raise AddressRefused(target, not_web)
                    refused = redirects(current, target) if redirects else None
                    if refused is not None:
                        raise RedirectRefused(current, target, refused)
                    current = target
                    continue
                return Response(
                    current,
                    status,
                    headers.get("content-type") or "",
                    body,
                    _all_headers(headers),
                )
        except TimeoutError as late:
            raise TimeoutError(f"{url} took longer than {timeout:g} seconds") from late
        raise TooManyRedirects(f"{url} redirected more than {MAX_REDIRECTS} times")

    return get


def http_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    redirects: Redirects | None = None,
    allow_empty: bool = False,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    proxy: str | None = None,
    send: Mapping[str, str] | None = None,
    connections: Connections | None = None,
    send_to: Iterable[str] | None = None,
) -> Rung:
    """Build the HTTP rung: ``http_responses``, its body read as a page.

    Every argument but ``allow_empty`` is ``http_responses``'s.
    ``allow_empty`` returns an empty body rather than failing on it: a page
    with no HTML is a rung that failed, but an empty robots.txt or llms.txt is
    an answer, and ``sluicer.fetch.site`` reads those. An empty 4xx or 5xx is
    always returned: it is that status's answer about the address, as the
    same status with a body is.
    """
    get = http_responses(
        allow_private,
        resolve,
        max_bytes,
        redirects,
        send=send,
        timeout=timeout,
        proxy=proxy,
        connections=connections,
        send_to=send_to,
    )

    def http(url: str) -> Fetched:
        response = get(url)
        body = response.body
        sent = charset({"content-type": response.content_type})
        html = body.decode(sniff_encoding(body, sent), errors="replace")
        if not html and not allow_empty and response.status < 400:
            raise EmptyBody(url, "http", response.status)
        return Fetched(
            url=response.url,
            html=html,
            status=response.status,
            rung="http",
            headers=response.headers,
        )

    return http


class _Lent:
    """A connection as ``http.client`` is handed it: to send on and read from,
    never to close, since whether it is kept is decided here."""

    def __init__(self, timed: Timed) -> None:
        self.timed = timed

    def sendall(self, data: bytes) -> None:
        self.timed.sendall(data)

    def makefile(self, *args: Any, **kwargs: Any) -> Any:
        return self.timed.makefile(*args, **kwargs)

    def close(self) -> None:
        pass


def _exchange(
    pool: Connections,
    url: str,
    addresses: tuple[str, ...] | None,
    proxy: Proxy | None,
    extra: Mapping[str, str],
    max_bytes: int,
    deadline: float,
) -> tuple[int, Any, bytes]:
    """One request for ``url``, no redirect followed, its body read up to
    ``max_bytes`` by ``deadline``: the status, the headers and the body."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise AddressRefused(url, "the address names no host")
    ascii_host = host if ":" in host else host.encode("idna").decode("ascii")
    port = parts.port or (443 if scheme == "https" else 80)
    through_socks = proxy is not None and proxy.scheme == "socks5"
    target = Target(
        scheme,
        ascii_host,
        port,
        addresses if proxy is None or through_socks else None,
        proxy,
    )
    headers = _request_headers(parts, target, extra)
    path = quote(parts.path or "/", safe=_SAFE)
    if parts.query:
        path += "?" + quote(parts.query, safe=_SAFE)
    line = f"{scheme}://{headers[0][1]}{path}" if target.absolute_form else path
    for attempt in (1, 2):
        link, kept = pool.take(target, deadline)
        connection = http.client.HTTPConnection(ascii_host, port)
        connection.auto_open = 0
        connection.sock = _Lent(link)
        try:
            connection.putrequest(
                "GET", line, skip_host=True, skip_accept_encoding=True
            )
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            while 100 <= response.status < 200 and response.status != _SWITCHING:
                # http.client skips a 100 and no other interim answer: a 103
                # came back as the answer, empty, and the real one was left
                # on the kept connection for the next request to read.
                response = _after_interim(response)
            if response.status < 200:
                raise ProtocolError(
                    f"{url} answered {response.status} {response.reason}, which "
                    "nothing asked it for: a request here never asks to upgrade"
                )
        except (ConnectionError, ssl.SSLEOFError):
            link.close()
            # A kept connection the server closed while it waited: the
            # request never reached it, and is sent once more on a new one.
            if kept and attempt == 1:
                continue
            raise
        except http.client.HTTPException as unreadable:
            link.close()
            raise ProtocolError(f"{url} answered with {unreadable!r}") from unreadable
        except BaseException:
            link.close()
            raise
        try:
            body = _body(response, url, max_bytes)
        except http.client.HTTPException as unreadable:
            link.close()
            raise ProtocolError(
                f"{url} sent a body that could not be read: {unreadable!r}"
            ) from unreadable
        except BaseException:
            link.close()
            raise
        if response.will_close or _announces_what_it_cannot_carry(response):
            link.close()
        else:
            pool.give(target, link)
        return response.status, response.msg, body
    raise AssertionError("a request was neither answered nor refused")


class _Rest:
    """The connection as the answer after an interim one reads it: from the
    reader the interim answer was read from, with whatever it read ahead."""

    def __init__(self, reader: Any) -> None:
        self.reader = reader

    def makefile(self, *args: Any, **kwargs: Any) -> Any:
        return self.reader


def _after_interim(interim: http.client.HTTPResponse) -> http.client.HTTPResponse:
    """The answer that follows ``interim`` -- a 102, a 103 -- on its connection.

    Read from the same reader: a new one would start past the bytes the first
    had already taken from the socket, the next answer's among them.
    """
    reader = interim.fp
    # Closing the interim answer, as its collection does, closes its reader.
    interim.fp = None  # type: ignore[assignment]
    rest: Any = _Rest(reader)
    following = http.client.HTTPResponse(rest, method="GET")
    following.begin()
    return following


def _announces_what_it_cannot_carry(response: http.client.HTTPResponse) -> bool:
    """Whether a 204 names a length for a body, which RFC 9110 forbids it.

    http.client reads no body for it, rightly, unless it is chunked; the bytes
    such a server sends after its headers would be read by the next request
    on the connection as the start of its own answer, so the connection is
    not kept. A 304 may name the length the page would have had (RFC 9110,
    8.6), and is kept.
    """
    if response.status != _NO_CONTENT or response.chunked:
        return False
    return (response.getheader("content-length") or "0").strip() != "0"


def _request_headers(
    parts: Any, target: Target, extra: Mapping[str, str]
) -> list[tuple[str, str]]:
    """What a request for ``parts`` sends, in the order sent: ``Host`` first."""
    host = f"[{target.host}]" if ":" in target.host else target.host
    default = 443 if target.scheme == "https" else 80
    authority = host if target.port == default else f"{host}:{target.port}"
    headers = [
        ("Host", authority),
        ("User-Agent", USER_AGENT),
        ("Accept", ACCEPT),
        ("Accept-Encoding", ACCEPT_ENCODING),
    ]
    if target.absolute_form and target.proxy is not None:
        authorization = target.proxy.authorization()
        if authorization is not None:
            headers.append(("Proxy-Authorization", authorization))
    named = {name.lower() for name in extra}
    if parts.username is not None and "authorization" not in named:
        # The address's own user and password, as curl sent them.
        pair = f"{unquote(parts.username)}:{unquote(parts.password or '')}"
        headers.append(
            ("Authorization", "Basic " + base64.b64encode(pair.encode()).decode())
        )
    headers.extend(extra.items())
    return headers


def _body(response: http.client.HTTPResponse, url: str, max_bytes: int) -> bytes:
    """The body of ``response``, decoded, and never past ``max_bytes``."""
    announced = response.length
    if announced is not None and announced > max_bytes:
        # What curl's own bound did: refused before the body is read.
        raise ResponseTooLarge(url, max_bytes)
    decoder = Decoder(url, response.getheader("content-encoding") or "")
    body = bytearray()
    try:
        while True:
            chunk = response.read1(_CHUNK)
            if not chunk:
                break
            body += decoder.feed(chunk, max_bytes - len(body))
        if response.length:
            # read1 answers b"" when the connection ends, however much of the
            # announced length never came: the count is left to its caller.
            raise ProtocolError(
                f"{url} sent a body cut short: {response.length} bytes of the "
                "length it announced never came"
            )
        body += decoder.finish(max_bytes - len(body))
    except Overflow:
        raise ResponseTooLarge(url, max_bytes) from None
    except Truncated as short:
        raise ProtocolError(f"{url} sent a body cut short: {short}") from None
    if len(body) > max_bytes:
        raise ResponseTooLarge(url, max_bytes)
    return bytes(body)


def chosen_proxy(proxy: str | None = None) -> str | None:
    """The proxy a fetch goes through: ``proxy``, else ``SLUICER_PROXY``, and
    None -- no proxy -- when neither names one."""
    named = proxy if proxy is not None else os.environ.get(PROXY_ENV, "")
    return named.strip() or None


def origins(addresses: Iterable[str]) -> frozenset[tuple[str, str, int | None]]:
    """The origins -- scheme, host and port -- of ``addresses``: where a
    caller's headers may go."""
    return frozenset(_origin(address) for address in addresses)


def _origin(url: str) -> tuple[str, str, int | None]:
    """The scheme, host and port a URL is asked of: what headers are kept to."""
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        return (
            scheme,
            (parts.hostname or "").lower(),
            parts.port or (443 if scheme == "https" else 80),
        )
    except ValueError:
        return "", url, None


def _all_headers(headers: Any) -> dict[str, str]:
    """A response's headers as one lowercased name each, repeats joined."""
    pairs = (
        headers.multi_items() if hasattr(headers, "multi_items") else headers.items()
    )
    found: dict[str, str] = {}
    for name, value in pairs:
        key = str(name).lower()
        found[key] = f"{found[key]}, {value}" if key in found else str(value)
    return found
