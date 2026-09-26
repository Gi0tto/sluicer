"""Read what a page's ``<link>`` elements declare about where else it lives.

A page says which address is its own (``canonical``, read from the head
only, and reported as a conflict when it names two), which addresses carry it
in other languages (``alternate`` with ``hreflang``), where its feeds are, which
page comes next and which before in a series, where its AMP version is, and
where to ask for an oEmbed description of it. None of it is about the page's
subject, so none of it is folded into a record; it is reported as it is, with
every address resolved against the page's base.

The link types read are the HTML standard's and the registered ones a search
engine or a feed reader acts on. A ``rel`` is a list of tokens, matched without
regard to case, as the standard says.
"""

from __future__ import annotations

from typing import TypedDict

from sluicer.declared.headers import HeaderLinks
from sluicer.document import (
    RELATED,
    Document,
    base_url,
    clean_address,
    join,
    scan,
    trimmed,
)


class Alternate(TypedDict):
    """The page in another language or region."""

    hreflang: str
    href: str


class Feed(TypedDict):
    """A feed the page declares, and which format it is in."""

    format: str
    href: str
    title: str


class Links(TypedDict, total=False):
    canonical: str
    canonical_conflict: list[str]
    alternates: list[Alternate]
    feeds: list[Feed]
    next: str
    prev: str
    amphtml: str
    oembed: list[str]
    manifest: str


# A feed's MIME type, and the format it names. Not plain ``application/json``:
# WordPress declares its REST API that way on every page, and it is no feed.
_FEEDS = {
    "application/rss+xml": "rss",
    "application/atom+xml": "atom",
    "application/feed+json": "json",
}
_OEMBED = frozenset({"application/json+oembed", "text/xml+oembed"})
# The most any one list holds: a page is not a directory, and a hostile one
# should not make the answer grow with its size.
_MOST = 200
# The relations read below: on <a> only a series' next and previous pages.
_READ_ON_ANCHORS = frozenset({"next", "prev", "previous"})
_READ_ON_LINKS = _READ_ON_ANCHORS | {"amphtml", "manifest", "alternate"}


def canonicals(doc: Document) -> list[str]:
    """The distinct canonical addresses the page's ``<head>`` declares, as written.

    Only the head: Google accepts ``rel=canonical`` "only if it appears in the
    ``<head>`` section", so a canonical in the body -- which a page's own
    content, a comment, can put there -- names nothing. One address repeated
    is one address; two different ones are a conflict, and Google then uses
    neither.
    """
    # Read once per page: the links and the summary both ask.
    held: tuple[str, ...] | None = doc.memo.get(_CANONICALS)
    if held is None:
        # A dict keeps them once each, in page order: a list asked whether it
        # held each new one, and forty thousand canonicals took four seconds.
        found: dict[str, None] = {}
        for link in doc.tree.xpath("//head//link/@rel/parent::*[@href]"):
            if "canonical" in (link.get("rel") or "").lower().split():
                href = clean_address(link.get("href") or "")
                if href:
                    found.setdefault(href)
        held = doc.memo[_CANONICALS] = tuple(found)
    return list(held)


_CANONICALS = "links.canonicals"


def read_links(doc: Document, header: HeaderLinks | None = None) -> Links:
    """Every link relation the page declares, in document order, first wins.

    ``<link>`` anywhere in the document is read, since pages put them in the
    body too; ``rel=next`` and ``rel=prev`` are also read from ``<a>``, where
    pagination usually is. A relation declared twice keeps its first address,
    and a list never repeats one.

    ``header`` is what the response's ``Link`` header declares
    (``sluicer.declared.headers.read_header_links``), read after the markup.
    A canonical there counts with the head's: the same address in both is one
    canonical, two different ones are a conflict.
    """
    base = base_url(doc)
    found: Links = {}
    alternates: list[Alternate] = []
    feeds: list[Feed] = []
    oembed: list[str] = []
    seen: set[tuple[str, str]] = set()
    for element in scan(doc, RELATED):
        if element.tag not in ("link", "a"):
            continue
        rels = set((element.get("rel") or "").lower().split())
        is_link = element.tag == "link"
        if not rels & (_READ_ON_LINKS if is_link else _READ_ON_ANCHORS):
            # Resolved only when a relation read here names it: most <a rel>
            # are nofollow or noopener, and resolving each was a fifth of the
            # time a page took.
            continue
        href = trimmed(element.get("href"))
        if not href or href.startswith(("javascript:", "#")):
            continue
        address = join(base, href)
        kind = (element.get("type") or "").strip().lower().split(";")[0]
        if "next" in rels:
            found.setdefault("next", address)
        if rels & {"prev", "previous"}:
            found.setdefault("prev", address)
        if not is_link:
            continue
        if "amphtml" in rels:
            found.setdefault("amphtml", address)
        if "manifest" in rels:
            found.setdefault("manifest", address)
        if "alternate" not in rels:
            continue
        hreflang = (element.get("hreflang") or "").strip()
        if hreflang and (hreflang.lower(), address) not in seen:
            # x-default and en may name one address, and both are declared.
            seen.add((hreflang.lower(), address))
            alternates.append({"hreflang": hreflang, "href": address})
        elif kind in _FEEDS and ("feed", address) not in seen:
            seen.add(("feed", address))
            title = " ".join((element.get("title") or "").split())
            feeds.append({"format": _FEEDS[kind], "href": address, "title": title})
        elif kind in _OEMBED and ("oembed", address) not in seen:
            # In the set with the rest: asking the list cost its square.
            seen.add(("oembed", address))
            oembed.append(address)
    if header is not None:
        for hreflang, address in header["alternates"]:
            if (hreflang.lower(), address) not in seen:
                seen.add((hreflang.lower(), address))
                alternates.append({"hreflang": hreflang, "href": address})
        if header["next"] is not None:
            found.setdefault("next", header["next"])
        if header["prev"] is not None:
            found.setdefault("prev", header["prev"])
    declared = [join(base, href) for href in canonicals(doc)]
    declared = [*declared, *(header["canonicals"] if header else [])][:_MOST]
    if len(set(declared)) == 1:
        found["canonical"] = declared[0]
    elif declared:
        found["canonical_conflict"] = list(dict.fromkeys(declared))
    if alternates:
        found["alternates"] = alternates[:_MOST]
    if feeds:
        found["feeds"] = feeds[:_MOST]
    if oembed:
        found["oembed"] = oembed[:_MOST]
    return found
