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
* ``Content-Usage`` is the IETF aipref working group's preference for AI
  training, AI use and search (draft-ietf-aipref-attach-05 and
  draft-ietf-aipref-vocab-08, drafts and not RFCs): a Structured Fields
  dictionary, ``train-ai=n, search=y``.

Header names are matched without regard to case. A header sent several times
arrives as one value, its repeats joined with ", " as RFC 9110 lets any
intermediary join them; so in ``X-Robots-Tag`` a directive belongs to the last
crawler named before it, whichever repeat it came in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from sluicer.document import join, trimmed

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
    content_usage: dict[str, str]


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
        href = trimmed(text[at + 1 : close])
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
    usage = content_usage(headers.get("content-usage", ""))
    if usage:
        found["content_usage"] = usage
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


# The aipref vocabulary's categories, by their labels, and what its two
# preference tokens mean (draft-ietf-aipref-vocab-08, sections 6.1 and 6.2).
_USAGE_CATEGORIES = ("train-ai", "ai-use", "search")
_PREFERENCES = {"y": "allow", "n": "disallow"}


def content_usage(value: str) -> dict[str, str]:
    """The preferences a ``Content-Usage`` header states, category by category.

    Processed as draft-ietf-aipref-vocab-08 section 6.5 says: the value is
    parsed as a Structured Fields dictionary (RFC 9651); a category whose value
    is the token ``y`` is ``allow`` and ``n`` is ``disallow``; any other value,
    an absent key, and a value that does not parse -- uppercase keys
    included, since the format is case sensitive -- leave the preference
    unknown, and an unknown one is not reported. A key given twice keeps its
    last value, as the dictionary's own rule says.
    """
    return stated(value, _USAGE_CATEGORIES, _PREFERENCES)


def stated(
    value: str, categories: tuple[str, ...], meanings: dict[str, str]
) -> dict[str, str]:
    """The preference each of ``categories`` is given in a dictionary ``value``.

    A category whose value is a token in ``meanings`` has that meaning; any
    other value, an absent category and a value that does not parse leave it
    unknown, and an unknown one is not reported.
    """
    parsed = sf_dictionary(value[:_LONGEST]) if value.strip() else None
    if parsed is None:
        return {}
    found: dict[str, str] = {}
    for category in categories:
        member = parsed.get(category)
        if isinstance(member, _Token) and member.text in meanings:
            found[category] = meanings[member.text]
    return found


class _Token(str):
    """A Structured Fields token, told apart from a string that spells the same."""

    @property
    def text(self) -> str:
        return str(self)


_LCALPHA = frozenset("abcdefghijklmnopqrstuvwxyz")
_KEY_REST = _LCALPHA | frozenset("0123456789_-.*")
_ALPHA = _LCALPHA | frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_TCHAR = _ALPHA | frozenset("0123456789!#$%&'*+-.^_`|~")
_BASE64 = _ALPHA | frozenset("0123456789+/=")


class _Unparsable(ValueError):
    pass


def sf_dictionary(value: str) -> dict[str, object] | None:
    """A Structured Fields dictionary's members, bare values only, or None.

    RFC 9651 section 4.2.2, followed closely enough that what it refuses is
    refused here: a member's value is its bare item -- a ``_Token``, a string,
    a number, a boolean, bytes as text, a date -- or a tuple for an inner list;
    parameters are parsed and dropped. A key given twice keeps its last value.
    """
    parser = _Fields(value.strip(" \t"))
    try:
        return parser.dictionary()
    except (_Unparsable, IndexError):
        return None


class _Fields:
    def __init__(self, text: str) -> None:
        self.text = text
        self.at = 0

    def _peek(self) -> str:
        return self.text[self.at] if self.at < len(self.text) else ""

    def _take(self) -> str:
        char = self.text[self.at]
        self.at += 1
        return char

    def dictionary(self) -> dict[str, object]:
        members: dict[str, object] = {}
        while self.at < len(self.text):
            key = self._key()
            if self._peek() == "=":
                self.at += 1
                members[key] = self._item_or_inner_list()
            else:
                self._parameters()
                members[key] = True
            while self._peek() in (" ", "\t") and self._peek():
                self.at += 1
            if self.at >= len(self.text):
                return members
            if self._take() != ",":
                raise _Unparsable("members are separated by commas")
            while self._peek() in (" ", "\t") and self._peek():
                self.at += 1
            if self.at >= len(self.text):
                raise _Unparsable("a trailing comma")
        return members

    def _key(self) -> str:
        first = self._peek()
        if not first or (first not in _LCALPHA and first != "*"):
            raise _Unparsable("a key opens with a lowercase letter or *")
        start = self.at
        while self._peek() and self._peek() in _KEY_REST:
            self.at += 1
        return self.text[start : self.at]

    def _item_or_inner_list(self) -> object:
        if self._peek() == "(":
            self.at += 1
            items: list[object] = []
            while True:
                while self._peek() == " ":
                    self.at += 1
                if self._peek() == ")":
                    self.at += 1
                    self._parameters()
                    return tuple(items)
                items.append(self._bare_item())
                self._parameters()
                if self._peek() not in (" ", ")"):
                    raise _Unparsable("inner list items are separated by spaces")
        value = self._bare_item()
        self._parameters()
        return value

    def _parameters(self) -> None:
        while self._peek() == ";":
            self.at += 1
            while self._peek() == " ":
                self.at += 1
            self._key()
            if self._peek() == "=":
                self.at += 1
                self._bare_item()

    def _bare_item(self) -> object:
        first = self._peek()
        if first == "-" or (first.isdigit() and first.isascii()):
            return self._number()
        if first == '"':
            return self._string()
        if first in _ALPHA or first == "*":
            return self._token()
        if first == ":":
            return self._bytes()
        if first == "?":
            self.at += 1
            flag = self._take()
            if flag not in ("0", "1"):
                raise _Unparsable("a boolean is ?0 or ?1")
            return flag == "1"
        if first == "@":
            self.at += 1
            number = self._number()
            if not isinstance(number, int):
                raise _Unparsable("a date is an integer")
            return number
        if first == "%":
            return self._display_string()
        raise _Unparsable("no item starts with this")

    def _number(self) -> int | float:
        start = self.at
        if self._peek() == "-":
            self.at += 1
        digits = self.at
        while self._peek().isdigit() and self._peek().isascii():
            self.at += 1
        whole = self.at - digits
        if whole == 0:
            raise _Unparsable("a number has digits")
        if self._peek() != ".":
            if whole > 15:
                raise _Unparsable("an integer has at most 15 digits")
            return int(self.text[start : self.at])
        if whole > 12:
            raise _Unparsable("a decimal has at most 12 integer digits")
        self.at += 1
        fraction = self.at
        while self._peek().isdigit() and self._peek().isascii():
            self.at += 1
        if not 1 <= self.at - fraction <= 3:
            raise _Unparsable("a decimal has one to three fractional digits")
        return float(self.text[start : self.at])

    def _string(self) -> str:
        self.at += 1
        out: list[str] = []
        while True:
            char = self._take()
            if char == "\\":
                escaped = self._take()
                if escaped not in ('"', "\\"):
                    raise _Unparsable("only a quote or a backslash is escaped")
                out.append(escaped)
            elif char == '"':
                return "".join(out)
            elif not " " <= char <= "~":
                raise _Unparsable("a string is printable ASCII")
            else:
                out.append(char)

    def _token(self) -> _Token:
        start = self.at
        self.at += 1
        while self._peek() and (self._peek() in _TCHAR or self._peek() in ":/"):
            self.at += 1
        return _Token(self.text[start : self.at])

    def _bytes(self) -> str:
        self.at += 1
        start = self.at
        while self._peek() and self._peek() in _BASE64:
            self.at += 1
        if self._take() != ":":
            raise _Unparsable("a byte sequence ends with a colon")
        return self.text[start : self.at - 1]

    def _display_string(self) -> str:
        self.at += 1
        if self._take() != '"':
            raise _Unparsable('a display string opens with %"')
        out = bytearray()
        while True:
            char = self._take()
            if char == '"':
                try:
                    return out.decode("utf-8")
                except UnicodeDecodeError:
                    raise _Unparsable("a display string is UTF-8") from None
            if char == "%":
                pair = self.text[self.at : self.at + 2]
                if len(pair) != 2 or any(c not in "0123456789abcdef" for c in pair):
                    raise _Unparsable("a percent escape is two lowercase hex digits")
                out.append(int(pair, 16))
                self.at += 2
            elif not " " <= char <= "~":
                raise _Unparsable("a display string is printable ASCII")
            else:
                out.extend(char.encode("ascii"))
