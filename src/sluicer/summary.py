"""One answer per question a caller actually asks of a page.

Records say everything a page declared, in every vocabulary it used. Most
callers want something smaller: the title, the author, the date, the price.
Getting there means knowing that ``headline`` on the ``Article`` beats ``name``
on the ``Organization``, that ``og:title`` beats ``<title>``, and that the price
lives inside ``offers`` -- knowledge every caller would otherwise rewrite.

This is that knowledge, written once, as fixed rules in a fixed order. There
is no scoring and no model: for each question the candidates are tried in the
order below and the first one the page declared wins. Every answer says which
reader it came from and which key, so it can be checked against the records it
was chosen from.
"""

from __future__ import annotations

import html as html_entities
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from sluicer.declared.merge import ABOUT_A_THING, JsonValue, Record
from sluicer.declared.opengraph import VERTICALS
from sluicer.document import Document, base_url, join


@dataclass(frozen=True)
class SummaryField:
    """One answer, the reader that declared it, and the key it was read from."""

    value: str
    source: str
    key: str


Answer: TypeAlias = "SummaryField | None"

FIELDS = (
    "title",
    "description",
    "url",
    "image",
    "author",
    "published",
    "modified",
    "language",
    "site_name",
    "publisher",
    "type",
    "price",
    "currency",
    "availability",
    "brand",
    "sku",
)
"""Every question the summary answers, in the order it reports them."""

# The types that are about the page's subject, most specific first. A page
# declaring a VideoObject and a Recipe is a recipe with a video in it.
_SUBJECTS = frozenset(
    {
        "Product",
        "ProductGroup",
        "Recipe",
        "Event",
        "JobPosting",
        "Book",
        "Movie",
        "TVSeries",
        "TVEpisode",
        "Course",
        "SoftwareApplication",
        "MobileApplication",
        "WebApplication",
        "VideoGame",
        "Dataset",
        "HowTo",
        "Review",
        "Hotel",
        "Restaurant",
        "LocalBusiness",
        "Offer",
        "MusicAlbum",
        "MusicRecording",
        "PodcastEpisode",
    }
)
# What sits around the subject on almost every page, and is never it.
_FURNITURE = frozenset(
    {
        "BreadcrumbList",
        "ListItem",
        "ItemList",
        "SearchAction",
        "SiteNavigationElement",
        "WPHeader",
        "WPFooter",
        "WPSideBar",
        "ImageObject",
        "EntryPoint",
    }
)
# The site and whoever runs it are what a page belongs to, not what it is
# about: a homepage declaring only its Organization is titled by og:title and
# <title>, not by the company's name.
_ABOUT_THE_SITE = frozenset({"WebSite", "Organization", "Person", "Corporation"})

# How many records of one type make a listing rather than a subject.
_A_LISTING = 3

# Meta names outside any vocabulary that pages use for these three questions,
# most specific first. ``citation_*`` is Highwire Press's, which Google Scholar
# reads and every journal writes; the rest are the publishing platforms' own.
_DATE_NAMES = (
    "citation_publication_date",
    "citation_date",
    "citation_online_date",
    "parsely-pub-date",
    "sailthru.date",
    "article.published",
    "publish-date",
    "publishdate",
    "pubdate",
    "date",
)
_AUTHOR_NAMES = ("citation_author", "parsely-author", "sailthru.author", "byl")
_TITLE_NAMES = ("citation_title",)
_BYLINE = re.compile(r"^\s*by\s+", re.IGNORECASE)
_TITLE_SEPARATORS = (" - ", " | ", " \u2013 ", " \u2014 ", " \u00b7 ", " :: ", " / ")

_WHITESPACE = re.compile(r"\s+")
_SCHEMA_ORG = re.compile(r"^https?://(?:www\.)?schema\.org/", re.IGNORECASE)


def summarise(
    doc: Document,
    records: list[Record],
    dublincore: dict[str, str],
    opengraph: dict[str, str],
    twitter: dict[str, str],
    htmlmeta: dict[str, str],
) -> dict[str, SummaryField]:
    """Answer each of ``FIELDS`` the page gives an answer to, in that order.

    The subject is the first declared record whose type is about a thing --
    a product, a recipe, an article -- ahead of any page, site or piece of
    furniture; induced records are never the subject. Document-level
    vocabularies are read from their own findings rather than from whichever
    record they were folded onto, so a breadcrumb that opens the page's
    ``@graph`` cannot lend them its name.
    """
    subject = _subject(records)
    site = next((r for r in records if "WebSite" in r.types), None)
    organisation = next(
        (r for r in records if set(r.types) & {"Organization", "Corporation"}), None
    )

    def meta(found: dict[str, str], source: str, key: str, label: str = "") -> Answer:
        text = _clean(found.get(key))
        return SummaryField(text, source, (label or "") + key) if text else None

    def og(key: str) -> Answer:
        # OpenGraph's verticals keep their namespace in the key; og: does not.
        return meta(
            opengraph, "opengraph", key, "" if key.startswith(VERTICALS) else "og:"
        )

    def own(prop: str, read: Callable[[JsonValue], str | None] = _text) -> Answer:
        return _from(subject, prop, read)

    offers = subject.fields.get("offers") if subject is not None else None
    questions: dict[str, list[Answer]] = {
        "title": [
            *_headline_or_name(own("headline"), own("name"), doc, opengraph),
            og("title"),
            meta(twitter, "twitter", "title", "twitter:"),
            meta(dublincore, "dublincore", "title", "dc."),
            _named(doc, _TITLE_NAMES),
            _element_text(doc, "//title", "<title>"),
        ],
        "description": [
            own("description"),
            og("description"),
            meta(twitter, "twitter", "description", "twitter:"),
            meta(htmlmeta, "html", "description", "meta name="),
            meta(dublincore, "dublincore", "description", "dc."),
        ],
        "url": [_canonical(doc), og("url"), own("url", _address)],
        "image": [
            own("image", _address),
            og("image"),
            og("image:url"),
            og("image:secure_url"),
            meta(twitter, "twitter", "image", "twitter:"),
            own("thumbnailUrl", _address),
        ],
        "author": [
            own("author", _names),
            own("creator", _names),
            meta(htmlmeta, "html", "author", "meta name="),
            _named(doc, _AUTHOR_NAMES, join=True),
            _orphan_itemprop(doc, "author"),
            meta(dublincore, "dublincore", "creator", "dc."),
            _not_an_address(og("article:author")),
        ],
        "published": [
            own("datePublished"),
            own("uploadDate"),
            own("dateCreated"),
            og("article:published_time"),
            meta(dublincore, "dublincore", "date.issued", "dc."),
            meta(dublincore, "dublincore", "issued", "dc."),
            meta(dublincore, "dublincore", "date", "dc."),
            meta(dublincore, "dublincore", "created", "dc."),
            _orphan_itemprop(doc, "datePublished"),
            _named(doc, _DATE_NAMES),
        ],
        "modified": [
            own("dateModified"),
            og("article:modified_time"),
            og("updated_time"),
            meta(dublincore, "dublincore", "modified", "dc."),
            _orphan_itemprop(doc, "dateModified"),
        ],
        "language": [
            _language(doc),
            own("inLanguage"),
            _locale(og("locale")),
            meta(dublincore, "dublincore", "language", "dc."),
        ],
        "site_name": [
            og("site_name"),
            _from(site, "name", _text),
            meta(htmlmeta, "html", "application-name", "meta name="),
        ],
        "publisher": [
            own("publisher", _names),
            meta(dublincore, "dublincore", "publisher", "dc."),
            _from(organisation, "name", _text),
        ],
        "type": [_type(subject), og("type")],
        "price": [
            own("offers", _offer(("price", "lowPrice"))) if offers else None,
            og("price:amount"),
        ],
        "currency": [
            own("offers", _offer(("priceCurrency",))) if offers else None,
            og("price:currency"),
        ],
        "availability": [
            _short(own("offers", _offer(("availability",)))) if offers else None,
            og("availability"),
        ],
        "brand": [own("brand", _names), og("brand")],
        "sku": [own("sku")],
    }

    # The site, by every name the page gives it: a site that signs its own
    # articles has not named an author, and a title ending in the site's name
    # carries a suffix, not a word of the title. Not the publisher: on a
    # personal blog the publisher is the author, and rightly so.
    site_names = {
        answer.value.casefold() for answer in questions["site_name"] if answer
    }
    questions["author"] = [
        answer
        for answer in questions["author"]
        if answer and answer.value.casefold() not in site_names
    ]
    questions["title"] = [
        _without_site(answer, site_names)
        if answer and answer.source not in ABOUT_A_THING
        else answer
        for answer in questions["title"]
    ]

    base = base_url(doc)
    summary: dict[str, SummaryField] = {}
    for name in FIELDS:
        found = next((answer for answer in questions[name] if answer), None)
        if found is not None:
            summary[name] = (
                _resolved(found, base) if name in ("url", "image") else found
            )
    return summary


def _subject(records: list[Record]) -> Record | None:
    """The record the page is about, or None when no declared record is.

    A type declared on three or more records is a listing -- the comments of a
    thread, the products of a category -- and none of its items is what the
    page is about. Measured on WCXB, taking the first of them made a forum
    thread's title "Post #16" and a category page's title its first product.
    Two are allowed: a product and the one related product beside it.
    """
    counts = Counter(name for record in records for name in set(record.types))
    ranked = [
        (rank, index, record)
        for index, record in enumerate(records)
        if (rank := _rank(record)) is not None
        and all(counts[name] < _A_LISTING for name in record.types)
    ]
    return min(ranked, key=lambda entry: entry[:2])[2] if ranked else None


def _rank(record: Record) -> int | None:
    if not record.types or any(f.source == "induced" for f in record.fields.values()):
        return None
    if set(record.types) & _ABOUT_THE_SITE:
        # Yoast writes ["Organization", "Brand"]: one site type is enough.
        return None
    ranks = [_rank_of(name) for name in record.types]
    found = [rank for rank in ranks if rank is not None]
    return min(found) if found else None


def _rank_of(name: str) -> int | None:
    if name in _FURNITURE:
        return None
    if name in _SUBJECTS or name.endswith(("Article", "Posting")) or name == "Report":
        return 0
    if name.endswith("Page"):
        return 2
    return 1


def _from(
    record: Record | None, prop: str, read: Callable[[JsonValue], str | None]
) -> SummaryField | None:
    if record is None or prop not in record.fields:
        return None
    field = record.fields[prop]
    if field.source not in ABOUT_A_THING:
        # A document-level value folded onto this record is not the record's
        # own property, and is asked for under its own key instead.
        return None
    text = read(field.value)
    if field.source == "jsonld" and text:
        # JSON-LD is JSON, but CMSs write HTML entities into it: Yoast titles
        # arrive as "Guide &#8226; Yoast".
        text = _clean(html_entities.unescape(text))
    if not text:
        return None
    return SummaryField(text, field.source, f"{record.type}.{prop}")


def _text(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, list):
        return next((text for item in value if (text := _text(item))), None)
    return _text(value.get("name", "")) if "name" in value else None


def _names(value: JsonValue) -> str | None:
    """Every name ``value`` gives, in order, once each, or None."""
    items = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = _text(item.get("name", "")) if "name" in item else None
            if name is None and ("givenName" in item or "familyName" in item):
                parts = (_text(item.get(k, "")) for k in ("givenName", "familyName"))
                name = " ".join(part for part in parts if part) or None
        else:
            name = _text(item)
        if name and not _is_address(name) and name not in names:
            names.append(name)
    return ", ".join(names) or None


def _address(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, list):
        return next((found for item in value if (found := _address(item))), None)
    for key in ("url", "contentUrl", "@id"):
        if key in value and (found := _address(value[key])):
            return found
    return None


def _offer(keys: tuple[str, ...]) -> Callable[[JsonValue], str | None]:
    """Read ``keys`` from the one offer the summary answers from.

    One offer for every question, so a price and a currency never come from
    two different offers: the first that states a price, or else the first.
    """

    def read(value: JsonValue) -> str | None:
        offer = _the_offer(value)
        if offer is None:
            return None
        for place in (offer, offer.get("priceSpecification")):
            specification = _the_offer(place) if place is not offer else offer
            if specification is None:
                continue
            for key in keys:
                if key in specification and (text := _text(specification[key])):
                    return text
        return None

    return read


def _the_offer(value: JsonValue | None) -> dict[str, JsonValue] | None:
    offers = [
        offer
        for offer in (value if isinstance(value, list) else [value])
        if isinstance(offer, dict)
    ]
    priced = [
        offer
        for offer in offers
        if any(key in offer for key in ("price", "lowPrice", "priceSpecification"))
    ]
    chosen = priced or offers
    return chosen[0] if chosen else None


def _type(record: Record | None) -> SummaryField | None:
    if record is None or record.type is None or record.source is None:
        return None
    return SummaryField(record.type, record.source, "@type")


def _headline_or_name(
    headline: SummaryField | None,
    name: SummaryField | None,
    doc: Document,
    opengraph: dict[str, str],
) -> list[SummaryField | None]:
    """``headline`` then ``name``, unless the page's own title says otherwise.

    Wikipedia puts its short description in ``headline`` -- "hydraulic
    structure" -- and the article's title in ``name``. When only one of the two
    appears in the title the page shows, in ``<title>`` or ``og:title``, that
    one is the title.
    """
    if headline is None or name is None:
        return [headline, name]
    shown = " ".join(
        text.casefold()
        for text in (
            opengraph.get("title"),
            *(title.text_content() for title in doc.tree.xpath("//title")),
        )
        if text
    )
    if name.value.casefold() in shown and headline.value.casefold() not in shown:
        return [name, headline]
    return [headline, name]


def _element_text(doc: Document, path: str, key: str) -> SummaryField | None:
    found = doc.tree.xpath(path)
    text = _clean(found[0].text_content()) if found else None
    return SummaryField(text, "html", key) if text else None


def _named(
    doc: Document, names: tuple[str, ...], join: bool = False
) -> SummaryField | None:
    """The first of ``names`` a ``<meta name>`` on the page carries.

    ``names`` is tried in its own order, not the page's. With ``join``, every
    tag of the winning name is read -- a paper lists each author in one -- and
    the names are joined once each, in the order written.
    """
    found: dict[str, list[str]] = {}
    for meta in doc.tree.xpath("//meta[@name][@content]"):
        text = _clean(meta.get("content"))
        if text:
            found.setdefault((meta.get("name") or "").strip().lower(), []).append(text)
    for name in names:
        if name in found:
            values = [_BYLINE.sub("", value) for value in found[name]]
            unique = list(dict.fromkeys(value for value in values if value))
            if unique:
                text = ", ".join(unique) if join else unique[0]
                return SummaryField(text, "html", f"meta name={name}")
    return None


def _orphan_itemprop(doc: Document, prop: str) -> SummaryField | None:
    """A ``<meta itemprop>`` outside any item, as templates put in the head.

    The microdata standard ignores it, having no item to give it to, so the
    microdata reader does too. It is still the page stating the value.
    """
    for meta in doc.tree.xpath(
        "//meta[@itemprop][@content][not(ancestor::*[@itemscope])]"
    ):
        if prop in (meta.get("itemprop") or "").split():
            text = _clean(meta.get("content"))
            if text:
                return SummaryField(text, "html", f"<meta itemprop={prop}>")
    return None


def _without_site(found: SummaryField, site_names: set[str]) -> SummaryField | None:
    """``found`` with a trailing " - Site Name" cut, when it names the site."""
    for separator in _TITLE_SEPARATORS:
        head, cut, tail = found.value.rpartition(separator)
        if cut and head.strip() and tail.strip().casefold() in site_names:
            return SummaryField(head.strip(), found.source, found.key)
    return found


def _canonical(doc: Document) -> SummaryField | None:
    for link in doc.tree.xpath("//link[@rel][@href]"):
        if "canonical" in (link.get("rel") or "").lower().split():
            href = _clean(link.get("href"))
            if href:
                return SummaryField(href, "html", "<link rel=canonical>")
    return None


def _language(doc: Document) -> SummaryField | None:
    for element in doc.tree.xpath("//html[@lang]"):
        lang = _clean(element.get("lang"))
        if lang:
            return SummaryField(lang, "html", "<html lang>")
    return None


def _locale(found: SummaryField | None) -> SummaryField | None:
    """``og:locale`` is written ``en_US``; a language tag is ``en-US``."""
    if found is None:
        return None
    return SummaryField(found.value.replace("_", "-"), found.source, found.key)


def _resolved(found: SummaryField, base: str | None) -> SummaryField:
    if base is None:
        return found
    return SummaryField(join(base, found.value), found.source, found.key)


def _short(found: SummaryField | None) -> SummaryField | None:
    """``https://schema.org/InStock`` is the schema.org term ``InStock``."""
    if found is None:
        return None
    return SummaryField(_SCHEMA_ORG.sub("", found.value), found.source, found.key)


def _not_an_address(found: SummaryField | None) -> SummaryField | None:
    """``article:author`` is usually a profile URL, which is not a name."""
    return None if found is None or _is_address(found.value) else found


def _is_address(text: str) -> bool:
    return text.startswith(("http://", "https://", "//", "www."))


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = _WHITESPACE.sub(" ", text).strip()
    return cleaned or None
