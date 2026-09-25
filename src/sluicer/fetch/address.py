"""Whether an address is somewhere on the public web.

An agent reading untrusted pages can be talked into fetching anything, and the
machine it runs on can usually reach things the web cannot: its own services on
``localhost``, a home router, a cloud's metadata endpoint at ``169.254.169.254``.
A caller who asks for it -- the MCP server does, by default -- gets those
refused before any request is made, and a redirect into them refused before
the page is handed back.

The HTTP rung connects only to the addresses checked here (``public_addresses``),
so a name that resolves differently the second time reaches nothing new. The
browser resolves names itself, in its own network stack: there a name that
answers differently between the check and the connection (DNS rebinding) is
still reached. Egress control belongs in the network.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit


class AddressRefused(Exception):
    """The address is not on the public web, and the caller asked for that; or
    it is not on the web at all, which no caller is given.

    ``url`` is the address refused -- the one asked for, or the one a redirect
    ended on -- and ``reason`` says why.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url} is not fetched: {reason}")
        self.url = url
        self.reason = reason


def _resolve(host: str) -> Iterable[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


WEB_SCHEMES = ("http", "https")
"""The only schemes anything is fetched over, whatever the caller allows.

curl speaks gopher, dict and file too, and a redirect to ``gopher://`` hands a
server's bytes to whatever listens where it points -- a Redis on this machine,
measured -- while ``file://`` reads this machine's own files.
"""


def why_not_web(url: str) -> str | None:
    """The reason ``url`` is not a web address, http or https, or None when it is.

    Asked of every address before it is requested, private ones allowed or
    not: a scheme is never a question of which network is reachable.
    """
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return "the address is not a valid URL"
    if scheme not in WEB_SCHEMES:
        return f"only http and https are fetched, not {scheme or 'no scheme'}"
    return None


def why_not_public(
    url: str, resolve: Callable[[str], Iterable[str]] = _resolve
) -> str | None:
    """The reason ``url`` is not a public web address, or None when it is.

    ``resolve`` maps a host name to the addresses it resolves to; the system
    resolver by default, injected so tests stay off the network.

    The host is read the way the client will read it, not the way it looks:
    ``%31%32%37.0.0.1`` and a backslash before an ``@`` are refused outright,
    since clients disagree about what they mean, and a numeric host is parsed
    by ``inet_aton``'s rules, so ``0177.0.0.1``, ``0x7f.1`` and ``2130706433``
    are all 127.0.0.1. An IPv6 address carrying an IPv4 one is judged by the
    IPv4 one. A name is resolved and every address it resolves to must be
    public, since a client may connect to any of them. A name that does not
    resolve is left to the fetch to fail on: it reaches nothing.
    """
    return _judge(url, resolve)[0]


def public_addresses(
    url: str, resolve: Callable[[str], Iterable[str]] = _resolve
) -> list[str]:
    """The addresses a connection to ``url`` may use, every one of them public.

    What ``why_not_public`` checked, kept, so a client can be told to connect
    there and nowhere else. A host written as an address gives that address.

    Raises:
        AddressRefused: ``why_not_public`` refuses ``url``.
        OSError: the name resolves to nothing. Left to the client, it would
            look the name up again, and that second answer is the one DNS
            rebinding controls.
    """
    reason, addresses = _judge(url, resolve)
    if reason is not None:
        raise AddressRefused(url, reason)
    if not addresses:
        raise OSError(f"{urlsplit(url).hostname} does not resolve to any address")
    return [str(address) for address in addresses]


_Address = ipaddress.IPv4Address | ipaddress.IPv6Address


def _judge(
    url: str, resolve: Callable[[str], Iterable[str]]
) -> tuple[str | None, list[_Address]]:
    """Why ``url`` is refused, or None, and the addresses the verdict is about."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return "the address is not a valid URL", []
    not_web = why_not_web(url)
    if not_web is not None:
        return not_web, []
    if "%" in parts.netloc or "\\" in parts.netloc:
        return "the address writes its host in a way clients read differently", []
    if not host:
        return "the address names no host", []
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return f"{host} is a name for this machine or its network", []
    literal = _numeric(host)
    if literal is not None:
        if _public(literal):
            return None, [literal]
        return f"{host} is not on the public internet", []
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return f"{host} is not a host name", []
    if not _NAME.fullmatch(ascii_host):
        return f"{host} is not a host name", []
    try:
        addresses = [
            ipaddress.ip_address(found.split("%")[0]) for found in resolve(ascii_host)
        ]
    except (OSError, ValueError):
        return None, []
    for address in addresses:
        if not _public(address):
            return f"{host} is {address}, which is not on the public internet", []
    return None, list(dict.fromkeys(addresses))


_NAME = re.compile(r"[a-z0-9_.-]+")
_NUMERIC = re.compile(r"[0-9a-fx.]+")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _numeric(host: str) -> _Address | None:
    """``host`` as an address, the way ``inet_aton`` and IPv6 parsing read it."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if _NUMERIC.fullmatch(host) and any(c.isdigit() for c in host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def _public(address: _Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped
        if embedded is None and address in _NAT64:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        if embedded is None and int(address) >> 32 == 0 and int(address) > 1:
            embedded = ipaddress.IPv4Address(int(address))
        if embedded is not None:
            return embedded.is_global
    return address.is_global
