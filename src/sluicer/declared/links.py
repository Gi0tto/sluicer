"""Read what a page's ``<link>`` elements declare about where else it lives.

A page says which address is its own (``canonical``), which addresses carry it
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

from sluicer.document import Document, base_url, join


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


def read_links(doc: Document) -> Links:
    """Every link relation the page declares, in document order, first wins.

    ``<link>`` anywhere in the document is read, since pages put them in the
    body too; ``rel=next`` and ``rel=prev`` are also read from ``<a>``, where
    pagination usually is. A relation declared twice keeps its first address,
    and a list never repeats one.
    """
    base = base_url(doc)
    found: Links = {}
    alternates: list[Alternate] = []
    feeds: list[Feed] = []
    oembed: list[str] = []
    seen: set[tuple[str, str]] = set()
    for element in doc.tree.xpath("//link[@rel][@href] | //a[@rel][@href]"):
        rels = set((element.get("rel") or "").lower().split())
        href = (element.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "#")):
            continue
        address = join(base, href)
        is_link = element.tag == "link"
        kind = (element.get("type") or "").strip().lower().split(";")[0]
        if is_link and "canonical" in rels:
            found.setdefault("canonical", address)
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
        elif kind in _OEMBED and address not in oembed:
            oembed.append(address)
    if alternates:
        found["alternates"] = alternates[:_MOST]
    if feeds:
        found["feeds"] = feeds[:_MOST]
    if oembed:
        found["oembed"] = oembed[:_MOST]
    return found
