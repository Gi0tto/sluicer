"""Read a feed's items: RSS 2.0, RSS 1.0, Atom 1.0 and JSON Feed 1.1.

A feed is the most honest form of declared data there is: it exists only to
be read by machines. ``read_feed`` reads one into a ``Feed`` of ``FeedItem``s
-- title, link, id, dates, authors, categories, enclosures, summary and
content -- each date also normalised as ``sluicer.normalise`` reads it, and
every link resolved against the feed's address, and in Atom against
``xml:base`` as the format says.

The XML is refused before it is parsed when it declares an entity or a
document type that points outside itself (``sluicer.safexml``), and parsed
with entities left alone and the network off. What is not a feed is None: an
HTML page, a sitemap, a JSON document of another kind.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import lxml.etree

from sluicer.document import join
from sluicer.normalise import iso_date
from sluicer.safexml import as_text, declares_what_expands

_ATOM = "http://www.w3.org/2005/Atom"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RSS1 = "http://purl.org/rss/1.0/"
_DC = "http://purl.org/dc/elements/1.1/"
_CONTENT = "http://purl.org/rss/1.0/modules/content/"
_JSON_FEED = re.compile(r"^https?://jsonfeed\.org/version/1(\.\d+)?/?$")
# The most items read from one feed, and the longest text kept of one field:
# a feed is not an archive, and a hostile one should not cost its length.
_MOST_ITEMS = 10_000
_LONGEST = 1_000_000


@dataclass(frozen=True)
class FeedItem:
    """One entry of a feed, each field as the feed wrote it, links resolved.

    ``normalised`` holds ``published`` and ``updated`` as ISO 8601 when they
    read as dates, and nothing when they do not: an RFC 822 ``pubDate`` and an
    Atom timestamp come out alike.
    """

    title: str | None = None
    link: str | None = None
    id: str | None = None
    published: str | None = None
    updated: str | None = None
    summary: str | None = None
    content: str | None = None
    authors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    enclosures: tuple[dict[str, str], ...] = ()
    normalised: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Feed:
    """A feed: its ``format`` (``rss``, ``rdf``, ``atom`` or ``jsonfeed``),
    what it says about itself, and its items in its order."""

    format: str
    title: str | None = None
    link: str | None = None
    description: str | None = None
    language: str | None = None
    updated: str | None = None
    items: tuple[FeedItem, ...] = ()


def read_feed(data: str | bytes, url: str | None = None) -> Feed | None:
    """The feed ``data`` is, or None when it is not one.

    ``url`` is the address the feed came from, which relative links resolve
    against. Never raises: a document that is not a feed, or not well formed,
    is None.
    """
    raw = data.encode("utf-8") if isinstance(data, str) else data
    start = raw.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if start in (b"{", b"["):
        return _json_feed(raw, url)
    if start != b"<" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return None
    root = _root(raw, url, isinstance(data, str))
    if root is None:
        return None
    kind = lxml.etree.QName(root).localname
    namespace = lxml.etree.QName(root).namespace
    if kind == "rss" and namespace is None:
        return _rss(root, url)
    if kind == "RDF" and namespace == _RDF:
        return _rdf(root, url)
    if kind == "feed" and namespace == _ATOM:
        return _atom(root, url)
    return None


def _root(raw: bytes, url: str | None, was_text: bool) -> Any | None:
    if declares_what_expands(as_text(raw)):
        return None
    if was_text:
        # Text handed in has been decoded already; the declaration's encoding
        # would now be a lie libxml2 believes.
        raw = re.sub(
            rb"^(\s*<\?xml[^>]*?)\sencoding=[\"'][^\"']*[\"']", rb"\1", raw, count=1
        )
    parser = lxml.etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
        recover=False,
    )
    try:
        root = lxml.etree.fromstring(raw, parser, base_url=url)
    except (lxml.etree.XMLSyntaxError, ValueError):
        return None
    info = root.getroottree().docinfo
    if info.internalDTD is not None or info.externalDTD is not None:
        return None
    return root


def _text(element: Any) -> str | None:
    if element is None:
        return None
    text = " ".join("".join(element.itertext())[:_LONGEST].split())
    return text or None


def _child(element: Any, name: str, namespace: str | None = None) -> Any:
    return next(iter(_children(element, name, namespace)), None)


def _children(element: Any, name: str, namespace: str | None = None) -> list[Any]:
    return [
        child
        for child in element
        if isinstance(child.tag, str)
        and lxml.etree.QName(child).localname == name
        and lxml.etree.QName(child).namespace == namespace
    ]


def _dates(published: str | None, updated: str | None) -> dict[str, str]:
    found = {}
    for name, value in (("published", published), ("updated", updated)):
        read = iso_date(value) if value else None
        if read:
            found[name] = read
    return found


def _rss(root: Any, url: str | None) -> Feed:
    channel = _child(root, "channel")
    if channel is None:
        return Feed("rss")
    items = []
    for item in _children(channel, "item")[:_MOST_ITEMS]:
        link = _text(_child(item, "link"))
        guid = _child(item, "guid")
        guid_text = _text(guid)
        if (
            link is None
            and guid_text
            and (guid.get("isPermaLink") or "true") != "false"
        ):
            link = guid_text
        published = _text(_child(item, "pubDate")) or _text(_child(item, "date", _DC))
        authors = [
            text
            for element in (
                *_children(item, "author"),
                *_children(item, "creator", _DC),
            )
            if (text := _text(element))
        ]
        enclosures = [
            {
                k: v
                for k, v in (
                    ("url", join(url, e.get("url") or "")),
                    ("type", e.get("type") or ""),
                    ("length", e.get("length") or ""),
                )
                if v
            }
            for e in _children(item, "enclosure")
            if e.get("url")
        ]
        items.append(
            FeedItem(
                title=_text(_child(item, "title")),
                link=join(url, link) if link else None,
                id=guid_text,
                published=published,
                summary=_text(_child(item, "description")),
                content=_raw(_child(item, "encoded", _CONTENT)),
                authors=tuple(dict.fromkeys(authors)),
                categories=tuple(
                    dict.fromkeys(
                        t for c in _children(item, "category") if (t := _text(c))
                    )
                ),
                enclosures=tuple(enclosures),
                normalised=_dates(published, None),
            )
        )
    link = _text(_child(channel, "link"))
    return Feed(
        "rss",
        title=_text(_child(channel, "title")),
        link=join(url, link) if link else None,
        description=_text(_child(channel, "description")),
        language=_text(_child(channel, "language")),
        updated=_text(_child(channel, "lastBuildDate")),
        items=tuple(items),
    )


def _rdf(root: Any, url: str | None) -> Feed:
    channel = _child(root, "channel", _RSS1)
    items = []
    for item in _children(root, "item", _RSS1)[:_MOST_ITEMS]:
        link = _text(_child(item, "link", _RSS1))
        published = _text(_child(item, "date", _DC))
        creator = _text(_child(item, "creator", _DC))
        items.append(
            FeedItem(
                title=_text(_child(item, "title", _RSS1)),
                link=join(url, link) if link else None,
                id=item.get(f"{{{_RDF}}}about"),
                published=published,
                summary=_text(_child(item, "description", _RSS1)),
                content=_raw(_child(item, "encoded", _CONTENT)),
                authors=(creator,) if creator else (),
                normalised=_dates(published, None),
            )
        )
    link = _text(_child(channel, "link", _RSS1)) if channel is not None else None
    return Feed(
        "rdf",
        title=_text(_child(channel, "title", _RSS1)) if channel is not None else None,
        link=join(url, link) if link else None,
        description=(
            _text(_child(channel, "description", _RSS1))
            if channel is not None
            else None
        ),
        items=tuple(items),
    )


def _atom(root: Any, url: str | None) -> Feed:
    items = []
    for entry in _children(root, "entry", _ATOM)[:_MOST_ITEMS]:
        published = _text(_child(entry, "published", _ATOM))
        updated = _text(_child(entry, "updated", _ATOM))
        authors = [
            name
            for author in _children(entry, "author", _ATOM)
            if (name := _text(_child(author, "name", _ATOM)))
        ]
        enclosures = [
            {
                k: v
                for k, v in (
                    ("url", _address(link, url)),
                    ("type", link.get("type") or ""),
                    ("length", link.get("length") or ""),
                )
                if v
            }
            for link in _children(entry, "link", _ATOM)
            if link.get("rel") == "enclosure" and link.get("href")
        ]
        content = _child(entry, "content", _ATOM)
        items.append(
            FeedItem(
                title=_text(_child(entry, "title", _ATOM)),
                link=_alternate(entry, url),
                id=_text(_child(entry, "id", _ATOM)),
                published=published,
                updated=updated,
                summary=_text(_child(entry, "summary", _ATOM)),
                content=_atom_content(content),
                authors=tuple(dict.fromkeys(authors)),
                categories=tuple(
                    dict.fromkeys(
                        term
                        for c in _children(entry, "category", _ATOM)
                        if (term := (c.get("label") or c.get("term") or "").strip())
                    )
                ),
                enclosures=tuple(enclosures),
                normalised=_dates(published, updated),
            )
        )
    return Feed(
        "atom",
        title=_text(_child(root, "title", _ATOM)),
        link=_alternate(root, url),
        description=_text(_child(root, "subtitle", _ATOM)),
        language=root.get("{http://www.w3.org/XML/1998/namespace}lang"),
        updated=_text(_child(root, "updated", _ATOM)),
        items=tuple(items),
    )


def _address(link: Any, url: str | None) -> str:
    """A link's ``href``, resolved against its ``xml:base``, then the feed's."""
    return join(link.base or url, link.get("href") or "")


def _alternate(element: Any, url: str | None) -> str | None:
    """Atom's link to the entry itself: ``rel="alternate"``, or no ``rel``."""
    for link in _children(element, "link", _ATOM):
        if (link.get("rel") or "alternate") == "alternate" and link.get("href"):
            return _address(link, url)
    return None


def _atom_content(content: Any) -> str | None:
    """Atom's content: its text, or for ``xhtml`` the markup inside its div."""
    if content is None:
        return None
    if (content.get("type") or "") == "xhtml":
        inner = next((c for c in content if isinstance(c.tag, str)), None)
        if inner is not None:
            parts = [lxml.etree.tostring(c, encoding="unicode") for c in inner]
            text = ((inner.text or "") + "".join(parts)).strip()
            return text[:_LONGEST] or None
    return _raw(content)


def _raw(element: Any) -> str | None:
    """An element's text as written, HTML in it kept, not collapsed."""
    if element is None:
        return None
    text = "".join(element.itertext())[:_LONGEST].strip()
    return text or None


def _json_feed(raw: bytes, url: str | None) -> Feed | None:
    try:
        parsed = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, dict) or not _JSON_FEED.match(
        str(parsed.get("version", ""))
    ):
        return None
    base = _string(parsed.get("home_page_url")) or url
    items = []
    for item in _list(parsed.get("items"))[:_MOST_ITEMS]:
        if not isinstance(item, dict):
            continue
        link = _string(item.get("url")) or _string(item.get("external_url"))
        published = _string(item.get("date_published"))
        updated = _string(item.get("date_modified"))
        # Version 1.1 writes authors, a list; 1.0 wrote author, one.
        people = _list(item.get("authors")) or [item.get("author")]
        authors = [
            name
            for person in people
            if isinstance(person, dict) and (name := _string(person.get("name")))
        ]
        enclosures = [
            {
                k: v
                for k, v in (
                    ("url", join(url, _string(a.get("url")) or "")),
                    ("type", _string(a.get("mime_type")) or ""),
                    ("length", str(a.get("size_in_bytes") or "")),
                )
                if v
            }
            for a in _list(item.get("attachments"))
            if isinstance(a, dict) and _string(a.get("url"))
        ]
        tags = _list(item.get("tags"))
        items.append(
            FeedItem(
                title=_string(item.get("title")),
                link=join(url, link) if link else None,
                id=_string(item.get("id")),
                published=published,
                updated=updated,
                summary=_string(item.get("summary")),
                content=_string(item.get("content_html"))
                or _string(item.get("content_text")),
                authors=tuple(dict.fromkeys(authors)),
                categories=tuple(
                    dict.fromkeys(t for tag in tags if (t := _string(tag)))
                ),
                enclosures=tuple(enclosures),
                normalised=_dates(published, updated),
            )
        )
    return Feed(
        "jsonfeed",
        title=_string(parsed.get("title")),
        link=join(url, base) if base else None,
        description=_string(parsed.get("description")),
        language=_string(parsed.get("language")),
        items=tuple(items),
    )


def _list(value: object) -> list[Any]:
    """A JSON value that should be a list, or none when it is not one."""
    return value if isinstance(value, list) else []


def _string(value: object) -> str | None:
    """A JSON value as text, when it is text with something in it."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = value[:_LONGEST].strip()
    return text or None
