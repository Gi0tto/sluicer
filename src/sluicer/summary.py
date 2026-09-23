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

from sluicer.declared.links import canonicals
from sluicer.declared.merge import ABOUT_A_THING, JsonValue, Record
from sluicer.declared.opengraph import NAMESPACES
from sluicer.document import Document, base_url, join


@dataclass(frozen=True)
class SummaryField:
    """One answer, the reader that declared it, and the key it was read from.

    ``value`` is text. ``source`` is a reader name, as on ``Field``, with
    ``"html"`` also covering ``<title>``, ``<html lang>``, ``<link
    rel=canonical>`` and meta names outside any vocabulary. ``key`` is what was
    read: ``Product.offers``, ``og:title``, ``<title>``, ``meta name=author``.
    """

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
    "price_regular",
    "price_low",
    "price_high",
    "currency",
    "availability",
    "brand",
    "sku",
    "gtin",
    "mpn",
    "rating",
    "rating_best",
    "rating_count",
    "breadcrumb",
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
            opengraph, "opengraph", key, "" if key.startswith(NAMESPACES) else "og:"
        )

    # The other descriptions of the subject when the page declares it several
    # times over, one per colour or size: an answer they do not all agree on
    # belongs to one variant, not to the thing the page is about.
    variants = _variants(records, subject)

    def own(prop: str, read: Callable[[JsonValue], str | None] = _text) -> Answer:
        found = _from(subject, prop, read)
        if found is None or not variants:
            return found
        agreed = all(
            (other := _from(variant, prop, read)) is not None
            and other.value == found.value
            for variant in variants
        )
        return found if agreed else None

    offers = subject.fields.get("offers") if subject is not None else None
    pricing = _pricing(subject, offers.value) if subject and offers else _Pricing()
    if variants and subject is not None:
        pricing = _agreed(
            pricing,
            [
                _pricing(v, v.fields["offers"].value)
                if "offers" in v.fields
                else _Pricing()
                for v in variants
            ],
        )
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
            _one_amount(pricing.price),
            _one_amount(og("price:amount")),
            _one_amount(og("product:price:amount")),
        ],
        "price_regular": [_one_amount(pricing.regular)],
        "price_low": [_one_amount(pricing.low)],
        "price_high": [_one_amount(pricing.high)],
        "currency": [
            pricing.currency,
            og("price:currency"),
            og("product:price:currency"),
        ],
        "availability": [
            _short(pricing.availability),
            og("availability"),
            _short(og("product:availability")),
        ],
        "brand": [own("brand", _names), og("brand"), og("product:brand")],
        "sku": [
            own("sku"),
            own("productID"),
            og("product:retailer_item_id"),
            og("sku"),
            og("product:sku"),
        ],
        "gtin": [own(key) for key in _GTIN_KEYS],
        "mpn": [own("mpn")],
        "rating": [_rating(subject, ("ratingValue",))],
        "rating_best": [_rating(subject, ("bestRating",))],
        "rating_count": [_rating(subject, ("ratingCount", "reviewCount"))],
        "breadcrumb": [_breadcrumb(records)],
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
        and all(
            counts[name] < _A_LISTING or _one_of_many(records, name) is record
            for name in record.types
        )
    ]
    return min(ranked, key=lambda entry: entry[:2])[2] if ranked else None


def _variants(records: list[Record], subject: Record | None) -> list[Record]:
    """The other records that describe ``subject`` under its own name.

    Only where the page declares the subject's type a listing's worth of times
    and every one of them bears the subject's name: Zara's Product per colour.
    """
    if subject is None or "name" not in subject.fields:
        return []
    name = _text(subject.fields["name"].value)
    same = [
        record
        for record in records
        if record is not subject
        and set(record.types) == set(subject.types)
        and "name" in record.fields
        and _text(record.fields["name"].value) == name
    ]
    return same if len(same) + 1 >= _A_LISTING else []


def _agreed(pricing: _Pricing, others: list[_Pricing]) -> _Pricing:
    """``pricing`` with every answer the variants do not all share taken out."""

    def kept(name: str) -> SummaryField | None:
        found: SummaryField | None = getattr(pricing, name)
        if found is None:
            return None
        values = {
            getattr(other, name).value if getattr(other, name) else None
            for other in others
        }
        return found if values == {found.value} else None

    return _Pricing(
        *(
            kept(name)
            for name in ("price", "regular", "low", "high", "currency", "availability")
        )
    )


def _one_of_many(records: list[Record], name: str) -> Record | None:
    """The one record the page is about among many of type ``name``, if there is.

    Two shapes of product page declare a type three times or more and are
    still about one thing, both measured on Zyte's product benchmark. Zara
    declares a Product per colour, each with the same name: one product, and
    the first is it. Argos declares its product with an offer and four
    related products with only a name and a rating: the one with the offer is
    it. A category page, whose products differ in name and each carry an
    offer, is still a listing.
    """
    same = [record for record in records if name in record.types]
    names = {
        _text(record.fields["name"].value) for record in same if "name" in record.fields
    }
    if len(names) == 1 and None not in names and all("name" in r.fields for r in same):
        return same[0]
    offered = [record for record in same if "offers" in record.fields]
    return offered[0] if len(offered) == 1 else None


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


@dataclass(frozen=True)
class _Pricing:
    """The prices the subject's offers declare, each with the path it was read at."""

    price: SummaryField | None = None
    regular: SummaryField | None = None
    low: SummaryField | None = None
    high: SummaryField | None = None
    currency: SummaryField | None = None
    availability: SummaryField | None = None


# A priceType that says a price is not the one a buyer pays now. Google's
# merchant listing documentation: "Active prices have neither a priceType nor a
# validForMemberTier property"; a strikethrough price is StrikethroughPrice,
# and for a transition period ListPrice.
_REGULAR = frozenset({"strikethroughprice", "listprice"})


def _pricing(subject: Record, offers: JsonValue) -> _Pricing:
    """The subject's prices, chosen by the rules Google documents, not by order.

    ``price`` is the first active price: a price with neither a ``priceType``
    nor a ``validForMemberTier``, on an offer or in its ``priceSpecification``.
    ``price_regular`` is the strikethrough price of that same offer. An
    ``AggregateOffer``'s ``lowPrice`` and ``highPrice`` are ``price_low`` and
    ``price_high``, never a plain price, and the offers inside it are read like
    any other. Currency and availability come from the offer the price came
    from, so a price and a currency never come from two offers. Every answer's
    key is the path it was read at: ``Product.offers[1].priceSpecification[0]
    .price``.
    """
    source = subject.fields["offers"].source
    name = subject.type or "Thing"

    def answer(value: JsonValue | None, path: str) -> SummaryField | None:
        text = _text(value) if value is not None else None
        return SummaryField(text, source, f"{name}.{path}") if text else None

    found = _offers_in(offers, "offers")
    price = regular = currency = availability = None
    for offer, path in found:
        for spec, spec_path in _specifications(offer, path):
            if "price" not in spec:
                continue
            kind = _price_kind(spec)
            if kind == "active" and price is None:
                price = answer(spec["price"], f"{spec_path}.price")
                currency = answer(
                    spec.get("priceCurrency"), f"{spec_path}.priceCurrency"
                ) or answer(offer.get("priceCurrency"), f"{path}.priceCurrency")
            elif kind == "regular" and regular is None:
                regular = answer(spec["price"], f"{spec_path}.price")
        if price is not None:
            availability = answer(offer.get("availability"), f"{path}.availability")
            break
        regular = None
    low = high = None
    for offer, path in found:
        if low is None and high is None:
            low = answer(offer.get("lowPrice"), f"{path}.lowPrice")
            high = answer(offer.get("highPrice"), f"{path}.highPrice")
            if (low or high) and currency is None and price is None:
                currency = answer(offer.get("priceCurrency"), f"{path}.priceCurrency")
    if availability is None:
        availability = next(
            (
                a
                for offer, path in found
                if (a := answer(offer.get("availability"), f"{path}.availability"))
            ),
            None,
        )
    if currency is None and price is None and low is None and high is None:
        currency = next(
            (
                c
                for offer, path in found
                if (c := answer(offer.get("priceCurrency"), f"{path}.priceCurrency"))
            ),
            None,
        )
    return _Pricing(price, regular, low, high, currency, availability)


def _offers_in(value: JsonValue, path: str) -> list[tuple[dict[str, JsonValue], str]]:
    """Every offer under ``value``, in document order, each with its path.

    An offer that holds ``offers`` of its own -- an ``AggregateOffer`` wrapping
    the sellers' offers -- comes first, then the offers inside it.
    """
    items = value if isinstance(value, list) else [value]
    found: list[tuple[dict[str, JsonValue], str]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        here = f"{path}[{index}]" if isinstance(value, list) else path
        found.append((item, here))
        inner = item.get("offers")
        if inner is not None and len(found) < _MOST_OFFERS:
            found.extend(_offers_in(inner, f"{here}.offers"))
    return found[:_MOST_OFFERS]


# Offers read per subject: a page is not a price list, and a hostile one
# should not make the summary cost more than its records did.
_MOST_OFFERS = 100


def _specifications(
    offer: dict[str, JsonValue], path: str
) -> list[tuple[dict[str, JsonValue], str]]:
    """The offer itself, then each of its ``priceSpecification``, with paths."""
    specs = [(offer, path)]
    declared = offer.get("priceSpecification")
    items = declared if isinstance(declared, list) else [declared]
    for index, item in enumerate(items):
        if isinstance(item, dict):
            where = (
                f"{path}.priceSpecification[{index}]"
                if isinstance(declared, list)
                else f"{path}.priceSpecification"
            )
            specs.append((item, where))
    return specs


def _price_kind(spec: dict[str, JsonValue]) -> str:
    """``active``, ``regular`` (a strikethrough price), or ``other``."""
    if spec.get("validForMemberTier") is not None:
        return "other"
    declared = spec.get("priceType")
    kind = (_text(declared) if declared is not None else "") or ""
    kind = kind.rstrip("/").rsplit("/", 1)[-1]
    if not kind:
        return "active"
    return "regular" if kind.lower() in _REGULAR else "other"


_NUMBER = re.compile(r"\d(?:[\d.,'\s]*\d)?")


def _one_amount(found: SummaryField | None) -> SummaryField | None:
    """``found`` if it holds one number, which is what a price is.

    Almedina's microdata ``price`` is the text of an element holding the price
    and the price it replaced, ``71,91 € 79,90 €``, and MediaMarkt's is
    ``109€109€109``: two and three numbers, which no reader can call one price.
    Refused here, the question falls to the next declaration, which on both
    pages is a clean ``product:price:amount``.
    """
    if found is None:
        return None
    return found if len(_NUMBER.findall(found.value)) == 1 else None


# The identifiers schema.org names for a trade item, most specific first. A
# book's ISBN is its GTIN-13, and is read after the GTINs a page states as such.
_GTIN_KEYS = ("gtin14", "gtin13", "gtin12", "gtin8", "gtin", "isbn")


def _rating(record: Record | None, keys: tuple[str, ...]) -> SummaryField | None:
    """One number of the subject's ``aggregateRating``, as the page wrote it.

    ``rating`` is never rescaled: 4 of 5 and 8 of 10 are answered as 4 and 8,
    with ``rating_best`` beside them when the page says what the best is.
    """
    if record is None or "aggregateRating" not in record.fields:
        return None
    rating = record.fields["aggregateRating"]
    declared = rating.value
    items = declared if isinstance(declared, list) else [declared]
    index, value = next(
        ((n, item) for n, item in enumerate(items) if isinstance(item, dict)),
        (0, None),
    )
    if value is None:
        return None
    where = (
        f"aggregateRating[{index}]" if isinstance(declared, list) else "aggregateRating"
    )
    for key in keys:
        text = _text(value[key]) if key in value else None
        if text:
            return SummaryField(text, rating.source, f"{record.type}.{where}.{key}")
    return None


def _breadcrumb(records: list[Record]) -> SummaryField | None:
    """The page's place in its site, as the names of its ``BreadcrumbList``.

    The last list declared, since a page that declares two usually puts its own
    last; its items ordered by ``position``, never by document order, joined
    with " > ". Items with no name are left out.
    """
    lists = [r for r in records if "BreadcrumbList" in r.types]
    if not lists or "itemListElement" not in lists[-1].fields:
        return None
    crumbs = lists[-1].fields["itemListElement"]
    items = crumbs.value if isinstance(crumbs.value, list) else [crumbs.value]
    named: list[tuple[float, int, str]] = []
    for order, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = _crumb_name(item)
        if name:
            named.append((_position(item.get("position"), order), order, name))
    if not named:
        return None
    path = " > ".join(name for _, _, name in sorted(named))
    return SummaryField(path, crumbs.source, "BreadcrumbList.itemListElement")


def _crumb_name(item: dict[str, JsonValue]) -> str | None:
    for value in (item.get("name"), item.get("item")):
        if isinstance(value, dict):
            value = value.get("name")
        text = _text(value) if isinstance(value, str) else None
        if text and not _is_address(text):
            return text
    return None


def _position(value: JsonValue | None, order: int) -> float:
    try:
        return float(str(value)) if value is not None else float(order)
    except ValueError:
        return float(order)


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
    """The page's canonical address, when its head names exactly one."""
    declared = canonicals(doc)
    if len(declared) != 1:
        return None
    return SummaryField(declared[0], "html", "<link rel=canonical>")


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
    """``https://schema.org/InStock`` is the schema.org term ``InStock``.

    The vocabulary's address alone names no term, and is no answer: an empty
    one would stop the next candidate from being asked.
    """
    if found is None:
        return None
    term = _SCHEMA_ORG.sub("", found.value)
    return SummaryField(term, found.source, found.key) if term else None


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
