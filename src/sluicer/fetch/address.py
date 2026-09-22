"""Whether an address is somewhere on the public web.

An agent reading untrusted pages can be talked into fetching anything, and the
machine it runs on can usually reach things the web cannot: its own services on
``localhost``, a home router, a cloud's metadata endpoint at ``169.254.169.254``.
A caller who asks for it -- the MCP server does, by default -- gets those
refused before any request is made, and gets a redirect into them refused
before the page is handed back.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit


class AddressRefused(Exception):
    """The address is not on the public web, and the caller asked for that."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url} is not fetched: {reason}")
        self.url = url
        self.reason = reason


def _resolve(host: str) -> Iterable[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def why_not_public(
    url: str, resolve: Callable[[str], Iterable[str]] = _resolve
) -> str | None:
    """The reason ``url`` is not a public web address, or None when it is.

    A name is resolved and every address it resolves to must be public, since
    a client may connect to any of them. A name that does not resolve is left
    to the fetch to fail on: it reaches nothing, private or not.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return f"only http and https are fetched, not {parts.scheme or 'no scheme'}"
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "the address names no host"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return f"{host} is a name for this machine or its network"
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if literal.is_global:
            return None
        return f"{host} is not on the public internet"
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(found.split("%")[0]) for found in resolve(host)
            ]
        except (OSError, ValueError):
            return None
    for address in addresses:
        if not address.is_global:
            return f"{host} is {address}, which is not on the public internet"
    return None
