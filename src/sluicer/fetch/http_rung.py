"""The plain HTTP rung, on curl_cffi, with the limits the ladder promises.

It asks for what scrapling's fetcher had no way to be asked for:

* **A byte bound.** The body is read in chunks and the transfer stops once it
  passes the bound, after decompression, so a small gzip that inflates to
  gigabytes costs the bound and no more.
* **Redirects one hop at a time.** curl never follows one itself; every
  address a redirect names is judged before it is asked.
* **A pinned connection.** With ``allow_private`` false, curl is told which
  addresses the host has -- the ones just checked -- and never looks the name
  up itself, so a name that answers differently the second time (DNS
  rebinding) reaches nothing new.

What it sends was measured on the wire: ``User-Agent`` is ours, and nothing
dresses it up as a browser.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit

from sluicer.document import sniff_encoding
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.address import _numeric, _resolve, public_addresses
from sluicer.fetch.identity import USER_AGENT
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Fetched, ResponseTooLarge, Rung

HTTP_TIMEOUT_SECONDS = 20
"""How long the plain HTTP rung waits for one response."""

MAX_REDIRECTS = 10
"""How many redirects one fetch follows before it calls the chain a loop."""

_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_FILESIZE_EXCEEDED = 63


class TooManyRedirects(Exception):
    """A chain of redirects longer than ``MAX_REDIRECTS``: a loop, most likely."""


def http_rung(
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    error: type[MissingExtra] = MissingExtra,
    allow_empty: bool = False,
) -> Rung:
    """Build the HTTP rung.

    Args:
        allow_private: when false, every hop is judged by ``public_addresses``
            and the connection pinned to what it returned.
        resolve: the name lookup that judgement uses.
        max_bytes: the most a body may weigh before ``ResponseTooLarge``.
        error: what a missing ``fetch`` extra raises, so callers can catch
            the same class for every rung.
        allow_empty: return an empty body rather than fail on it. A page with
            no HTML is a rung that failed; an empty robots.txt or llms.txt is
            an answer, and ``sluicer.fetch.site`` reads those.
    """
    requests = import_extra(
        "curl_cffi.requests", "fetch", doing="Fetching a URL", error=error
    )
    curl_option = import_extra(
        "curl_cffi", "fetch", doing="Fetching a URL", error=error
    ).CurlOpt

    def http(url: str) -> Fetched:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            options: dict[Any, Any] = {curl_option.MAXFILESIZE_LARGE: max_bytes}
            if not allow_private:
                pins = _pins(current, resolve)
                if pins:
                    options[curl_option.RESOLVE] = pins
            status, headers, body = _get(requests, current, options, max_bytes)
            location = headers.get("location")
            if status in _REDIRECTS and location:
                current = urljoin(current, location)
                continue
            charset = _charset(headers.get("content-type") or "")
            html = body.decode(sniff_encoding(body, charset), errors="replace")
            if not html and not allow_empty:
                raise ValueError(f"the http rung returned no HTML for {url!r}")
            return Fetched(url=current, html=html, status=status, rung="http")
        raise TooManyRedirects(f"{url} redirected more than {MAX_REDIRECTS} times")

    return http


def _get(
    requests: Any, url: str, options: dict[Any, Any], max_bytes: int
) -> tuple[int, Any, bytes]:
    """One request, no redirect followed, the body read up to ``max_bytes``."""
    with requests.Session(curl_options=options, impersonate=None) as session:
        try:
            response = session.get(
                url,
                headers={"User-Agent": USER_AGENT},
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


def _charset(content_type: str) -> str | None:
    """The ``charset`` parameter of a ``Content-Type``, or None."""
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            return value.strip().strip("\"'")
    return None
