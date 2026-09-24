"""The plain HTTP rung, on curl_cffi, with the limits the ladder promises.

It asks for what scrapling's fetcher had no way to be asked for:

* **A byte bound.** The body is read in chunks and the transfer stops once it
  passes the bound, after decompression, so a small gzip that inflates to
  gigabytes costs the bound and no more.
* **Redirects one hop at a time.** curl never follows one itself; every
  address a redirect names is judged before it is asked.
* **The web and nothing else.** Every hop must be http or https, and curl is
  told to speak nothing else, so a redirect to ``gopher://``, ``dict://`` or
  ``file://`` is refused, not followed.
* **A pinned connection.** With ``allow_private`` false, curl is told which
  addresses the host has -- the ones just checked -- and never looks the name
  up itself, so a name that answers differently the second time (DNS
  rebinding) reaches nothing new.
* **A caller's rule for redirects.** A crawl keeps to its site by refusing a
  hop that leaves it, before the other site is asked anything.

``http_responses`` is the same transport answering bytes, for what is not a
page: a sitemap, which may be gzip the server did not announce as an encoding.

What it sends was measured on the wire: ``User-Agent`` is ours, and nothing
dresses it up as a browser.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

from sluicer.declared.headers import charset
from sluicer.document import sniff_encoding
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.address import (
    WEB_SCHEMES,
    AddressRefused,
    _numeric,
    _resolve,
    public_addresses,
    why_not_web,
)
from sluicer.fetch.identity import USER_AGENT
from sluicer.fetch.result import (
    MAX_RESPONSE_BYTES,
    EmptyBody,
    Fetched,
    RedirectRefused,
    Redirects,
    ResponseTooLarge,
    Rung,
)

HTTP_TIMEOUT_SECONDS = 20
"""How long the plain HTTP rung waits for one response."""

MAX_REDIRECTS = 10
"""How many redirects one fetch follows before it calls the chain a loop."""

_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_PROTOCOLS = ",".join(WEB_SCHEMES)
_FILESIZE_EXCEEDED = 63


class TooManyRedirects(Exception):
    """A chain of redirects longer than ``MAX_REDIRECTS``: a loop, most likely."""


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
    error: type[MissingExtra] = MissingExtra,
    redirects: Redirects | None = None,
    send: Mapping[str, str] | None = None,
) -> Callable[[str], Response]:
    """Build the HTTP transport: an address in, a ``Response`` out.

    Args:
        allow_private: when false, every hop is judged by ``public_addresses``
            and the connection pinned to what it returned.
        resolve: the name lookup that judgement uses.
        max_bytes: the most a body may weigh before ``ResponseTooLarge``.
        error: what a missing ``fetch`` extra raises, so callers can catch
            the same class for every rung.
        redirects: the caller's rule for a redirect, asked before each hop is
            requested; a hop it refuses raises ``RedirectRefused``.
        send: headers sent with every request beside our User-Agent, which
            they cannot replace: a cache's validators, ``If-None-Match``.
    """
    requests = import_extra(
        "curl_cffi.requests", "fetch", doing="Fetching a URL", error=error
    )
    curl_option = import_extra(
        "curl_cffi", "fetch", doing="Fetching a URL", error=error
    ).CurlOpt

    def get(url: str) -> Response:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            not_web = why_not_web(current)
            if not_web is not None:
                raise AddressRefused(current, not_web)
            options: dict[Any, Any] = {
                curl_option.MAXFILESIZE_LARGE: max_bytes,
                # Ours is the check that refuses; curl's own list is there so
                # that no path we did not think of reaches another protocol.
                curl_option.PROTOCOLS_STR: _PROTOCOLS,
                curl_option.REDIR_PROTOCOLS_STR: _PROTOCOLS,
            }
            if not allow_private:
                pins = _pins(current, resolve)
                if pins:
                    options[curl_option.RESOLVE] = pins
            status, headers, body = _get(requests, current, options, max_bytes, send)
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
        raise TooManyRedirects(f"{url} redirected more than {MAX_REDIRECTS} times")

    return get


def http_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    error: type[MissingExtra] = MissingExtra,
    redirects: Redirects | None = None,
    allow_empty: bool = False,
) -> Rung:
    """Build the HTTP rung: ``http_responses``, its body read as a page.

    The first five arguments are ``http_responses``'s. ``allow_empty`` returns
    an empty body rather than failing on it: a page with no HTML is a rung
    that failed, but an empty robots.txt or llms.txt is an answer, and
    ``sluicer.fetch.site`` reads those.
    """
    get = http_responses(allow_private, resolve, max_bytes, error, redirects)

    def http(url: str) -> Fetched:
        response = get(url)
        body = response.body
        sent = charset({"content-type": response.content_type})
        html = body.decode(sniff_encoding(body, sent), errors="replace")
        if not html and not allow_empty:
            raise EmptyBody(url, "http", response.status)
        return Fetched(
            url=response.url,
            html=html,
            status=response.status,
            rung="http",
            headers=response.headers,
        )

    return http


def _get(
    requests: Any,
    url: str,
    options: dict[Any, Any],
    max_bytes: int,
    send: Mapping[str, str] | None = None,
) -> tuple[int, Any, bytes]:
    """One request, no redirect followed, the body read up to ``max_bytes``."""
    with requests.Session(curl_options=options, impersonate=None) as session:
        try:
            response = session.get(
                url,
                headers={**(send or {}), "User-Agent": USER_AGENT},
                timeout=HTTP_TIMEOUT_SECONDS,
                allow_redirects=False,
                stream=True,
            )
            try:
                body = bytearray()
                for chunk in response.iter_content():
                    body += chunk
                    if len(body) > max_bytes:
                        raise ResponseTooLarge(url, max_bytes)
                return response.status_code, response.headers, bytes(body)
            finally:
                response.close()
        except ResponseTooLarge:
            raise
        except Exception as failure:
            # curl's own refusal (CURLE_FILESIZE_EXCEEDED), which comes first
            # when the length was announced or the transfer outran our count.
            if getattr(failure, "code", None) == _FILESIZE_EXCEEDED or (
                f"curl: ({_FILESIZE_EXCEEDED})" in str(failure)
            ):
                raise ResponseTooLarge(url, max_bytes) from failure
            raise


def _pins(url: str, resolve: Callable[[str], Iterable[str]]) -> list[str]:
    """curl's ``RESOLVE`` entries: this host, at this port, only at these addresses.

    Empty for a host written as an address, which curl never looks up.
    """
    addresses = public_addresses(url, resolve)
    parts = urlsplit(url)
    host = (parts.hostname or "").rstrip(".")
    if _numeric(host.lower()) is not None:
        return []
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    listed = ",".join(f"[{a}]" if ":" in a else a for a in addresses)
    return [f"{host.encode('idna').decode('ascii')}:{port}:{listed}"]


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
