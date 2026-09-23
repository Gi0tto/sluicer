"""Read what a page's HTTP response declares beside the page.

Three headers carry things Sluicer already reads from markup:

* ``Link`` (RFC 8288) can name the page's canonical address, its versions in
  other languages (``alternate`` with ``hreflang``), and the next and previous
  pages of a series. Google accepts a canonical and ``hreflang`` alternates
  there as it does in the ``<head>``.
* ``X-Robots-Tag`` carries the same directives as ``<meta name="robots">``,
  for the whole response or for one crawler (``googlebot: noindex``), as
  Google documents it.
* ``TDM-Reservation`` and ``TDM-Policy`` are TDMRep's text and data mining
  reservation, the same as its ``<meta>`` tags.

Header names are matched without regard to case. A header sent several times
arrives as one value, its repeats joined with ", " as RFC 9110 lets any
intermediary join them; so in ``X-Robots-Tag`` a directive belongs to the last
crawler named before it, whichever repeat it came in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from sluicer.document import join

# The most read of any one header, and the most links or directives kept: a
# response is not a directory, and a hostile one should not make the answer
# grow with it.
_LONGEST = 65_536
_MOST = 200
_MOST_DIRECTIVES = 50
_MOST_AGENTS = 20
# X-Robots-Tag directives that carry a value after a colon, and so are not a
# crawler's name.
_VALUED = frozenset(
    {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}
)


class LinkValue(TypedDict):
    """One link of a ``Link`` header: its target, relation types and parameters."""

    href: str
    rel: list[str]
    params: dict[str, str]


class HeaderLinks(TypedDict):
    """The link relations a response's ``Link`` header declares about it."""

    canonicals: list[str]
    alternates: list[tuple[str, str]]
    next: str | None
    prev: str | None


class HeaderRights(TypedDict, total=False):
    """The usage directives a response's headers declare."""

    robots: list[str]
    agents: dict[str, list[str]]
    tdm_reservation: str
    tdm_policy: str


def lowered(headers: Mapping[str, str] | None) -> dict[str, str]:
    """``headers`` with their names lowercased, a name given twice joined."""
    found: dict[str, str] = {}
    for name, value in (headers or {}).items():
        key = str(name).strip().lower()
        text = str(value)
        found[key] = f"{found[key]}, {text}" if key in found else text
    return found


def charset(headers: Mapping[str, str]) -> str | None:
    """The ``charset`` parameter of the response's ``Content-Type``, or None."""
    for parameter in headers.get("content-type", "").split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            return value.strip().strip("\"'")
    return None


def parse_link(value: str) -> list[LinkValue]:
    """The links of a ``Link`` header value, as RFC 8288 writes them.

    ``<target>; rel="a b"; hreflang=de, <other>; rel=next``. A ``rel`` given
    twice keeps its first, as the RFC says; any other parameter keeps its
    first too. A link that does not open with ``<`` is skipped up to the next
    comma, and the rest is read.
    """
    text = value[:_LONGEST]
    found: list[LinkValue] = []
    at = 0
    while at < len(text) and len(found) < _MOST:
        while at < len(text) and text[at] in " \t,":
            at += 1
        if at >= len(text):
            break
        if text[at] != "<":
            at = _past_comma(text, at)
            continue
        close = text.find(">", at)
        if close == -1:
            break
        href = text[at + 1 : close].strip()
        at = close + 1
        params: dict[str, str] = {}
        while True:
            while at < len(text) and text[at] in " \t":
                at += 1
            if at >= len(text) or text[at] != ";":
                break
            name, param, at = _param(text, at + 1)
            if name and name not in params:
                params[name] = param
        at = _past_comma(text, at)
        rel = params.pop("rel", "")
        if href:
            found.append({"href": href, "rel": rel.lower().split(), "params": params})
    return found


def _param(text: str, at: int) -> tuple[str, str, int]:
    """One ``name[=value]`` parameter from ``at``, and where it ends."""
    start = at
    while at < len(text) and text[at] not in "=;,":
        at += 1
    name = text[start:at].strip().lower().rstrip("*")
    if at >= len(text) or text[at] != "=":
        return name, "", at
    at += 1
    while at < len(text) and text[at] in " \t":
        at += 1
    if at < len(text) and text[at] == '"':
        at += 1
        chars: list[str] = []
        while at < len(text) and text[at] != '"':
            if text[at] == "\\" and at + 1 < len(text):
                at += 1
            chars.append(text[at])
            at += 1
        return name, "".join(chars), at + 1
    start = at
    while at < len(text) and text[at] not in ";,":
        at += 1
    return name, text[start:at].strip(), at


def _past_comma(text: str, at: int) -> int:
    """Where the next link starts: past the next comma outside quotes."""
    quoted = False
    while at < len(text):
        if text[at] == '"':
            quoted = not quoted
        elif text[at] == "," and not quoted:
            return at + 1
        at += 1
    return at


def read_header_links(headers: Mapping[str, str], url: str | None) -> HeaderLinks:
    """The canonical, alternates, next and previous a ``Link`` header names.

    Targets resolve against ``url``, the address the response came from, which
    is what a ``Link`` header's context is. A link with an ``anchor`` is about
    some other resource, and is not read.
    """
    found: HeaderLinks = {
        "canonicals": [],
        "alternates": [],
        "next": None,
        "prev": None,
    }
    for link in parse_link(headers.get("link", "")):
        if "anchor" in link["params"]:
            continue
        address = join(url, link["href"])
        rels = set(link["rel"])
        if "canonical" in rels and address not in found["canonicals"]:
            found["canonicals"].append(address)
        hreflang = link["params"].get("hreflang", "").strip()
        if "alternate" in rels and hreflang:
            pair = (hreflang, address)
            if pair not in found["alternates"]:
                found["alternates"].append(pair)
        if "next" in rels and found["next"] is None:
            found["next"] = address
        if rels & {"prev", "previous"} and found["prev"] is None:
            found["prev"] = address
    return found


def read_header_rights(headers: Mapping[str, str]) -> HeaderRights:
    """The directives of ``X-Robots-Tag`` and TDMRep's headers, verbatim, lowercased.

    ``X-Robots-Tag: googlebot: noindex`` is ``{"agents": {"googlebot":
    ["noindex"]}}``; a directive with no crawler before it is in ``robots``.
    """
    found: HeaderRights = {}
    general: list[str] = []
    agents: dict[str, list[str]] = {}
    into = general
    for token in headers.get("x-robots-tag", "")[:_LONGEST].split(","):
        directive = " ".join(token.split()).lower()
        name, colon, rest = directive.partition(":")
        if colon and name.strip() not in _VALUED and _a_name(name.strip()):
            if name.strip() not in agents and len(agents) >= _MOST_AGENTS:
                into = []
            else:
                into = agents.setdefault(name.strip(), [])
            directive = rest.strip()
        if directive and directive not in into and len(into) < _MOST_DIRECTIVES:
            into.append(directive)
    if general:
        found["robots"] = general
    agents = {name: rules for name, rules in agents.items() if rules}
    if agents:
        found["agents"] = agents
    reservation = _first(headers.get("tdm-reservation", ""))
    if reservation:
        found["tdm_reservation"] = reservation
    policy = _first(headers.get("tdm-policy", ""))
    if policy:
        found["tdm_policy"] = policy
    return found


def _first(value: str) -> str:
    """The first of a header's joined repeats, its spaces collapsed."""
    return " ".join(value[:_LONGEST].split(", ")[0].split())


def _a_name(text: str) -> bool:
    """Whether ``text`` could be a crawler's name: one token, no spaces."""
    return bool(text) and all(c.isalnum() or c in "-_." for c in text)
