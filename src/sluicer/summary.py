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

import datetime
import html as html_entities
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from html.entities import html5 as html5_names
from typing import Any, TypeAlias
from urllib.parse import urlsplit

from lxml.html import HtmlElement

from sluicer.declared.links import canonicals
from sluicer.declared.located import Places, paid, place, xpath_of
from sluicer.declared.merge import ABOUT_A_THING, Field, JsonValue, Overruled, Record
from sluicer.declared.opengraph import NAMESPACES
from sluicer.document import Document, base_url, join
from sluicer.normalise import (
    amount,
    currency as currency_of,
    iso_date,
)


@dataclass(frozen=True)
class SummaryField:
    """One answer, the reader that declared it, and the key it was read from.

    ``value`` is text. ``source`` is a reader name, as on ``Field``, with
    ``"html"`` also covering ``<title>``, ``<html lang>``, ``<link
    rel=canonical>`` and meta names outside any vocabulary. ``key`` is what was
    read: ``Product.offers``, ``og:title``, ``<title>``, ``meta name=author``.
    ``where`` is where on the page it was declared, as ``Field.where``: an
    XPath, for JSON-LD with a pointer to the value after ``#``. None when the
    key is the whole of what is known, as for ``og:title``.
    """

    value: str
    source: str
    key: str
    where: str | None = None


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
# <title>, not by the company's name. So is the journal or newspaper a page
# is published in: a journal that declares its Periodical in the footer of
# every article had the journal's name as every article's title.
_ABOUT_THE_SITE = frozenset(
    {"WebSite", "Organization", "Person", "Corporation", "Periodical", "Newspaper"}
)

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
# The names content systems give an account nobody named: WordPress's "admin",
# Joomla's "Super User", Blogger's "Unknown". None is a person: on the
# scoreboards' pages and trafilatura's evaluation set they gave seven answers,
# six wrong or where the label has no author, and one where the label itself
# reads "Unknown".
# A clock time and nothing else: "10:52", "2:33 PM", "3 pm", "07:01:27 UTC".
_ONLY_A_TIME = re.compile(
    r"^\s*\d{1,2}(?:(?::\d{2}){1,2}(?:\.\d+)?\s*(?:[ap]\.?\s?m\.?)?"
    r"|\s*[ap]\.?\s?m\.?)\s*(?:z|[a-z]{2,4}|[+-]\d{2}:?\d{2})?\s*$",
    re.IGNORECASE,
)
_NO_ONE = frozenset({"admin", "administrator", "super user", "unknown"})
_AUTHOR_NAMES = ("citation_author", "parsely-author", "sailthru.author", "byl")
_TITLE_NAMES = ("citation_title",)
_BYLINE = re.compile(r"^\s*by\s+", re.IGNORECASE)
_TITLE_SEPARATORS = (" - ", " | ", " \u2013 ", " \u2014 ", " \u00b7 ", " :: ", " / ")

# The page's own <title>, not an icon's or a formula's: libxml2's HTML parser
# has no namespaces, so an inline <svg><title> looks like HTML's, and on a
# page with no head title it was the page's.
_PAGE_TITLE = "//title[not(ancestor::svg or ancestor::math)]"
_WHITESPACE = re.compile(r"\s+")
_SCHEMA_ORG = re.compile(r"^https?://(?:www\.)?schema\.org/", re.IGNORECASE)


def summarise(
    doc: Document,
    records: list[Record],
    dublincore: dict[str, str],
    opengraph: dict[str, str],
    twitter: dict[str, str],
    htmlmeta: dict[str, str],
    header_canonicals: list[str] | None = None,
    places: Places | None = None,
) -> dict[str, SummaryField]:
    """Answer each of ``FIELDS`` the page gives an answer to, in that order.

    ``read_summary`` is the same reading, with the page's conflicts beside it.
    """
    return read_summary(
        doc,
        records,
        dublincore,
        opengraph,
        twitter,
        htmlmeta,
        header_canonicals,
        places,
    )[0]


def read_summary(
    doc: Document,
    records: list[Record],
    dublincore: dict[str, str],
    opengraph: dict[str, str],
    twitter: dict[str, str],
    htmlmeta: dict[str, str],
    header_canonicals: list[str] | None = None,
    places: Places | None = None,
    overruled: Overruled | None = None,
) -> tuple[dict[str, SummaryField], list[Conflict]]:
    """The summary, and every question the page answers in two ways.

    The summary answers each of ``FIELDS`` the page gives an answer to, in
    that order.

    The subject is the first declared record whose type is about a thing --
    a product, a recipe, an article -- ahead of any page, site or piece of
    furniture, or the thing such a record declares its ``mainEntity``;
    induced records are never the subject. Document-level
    vocabularies are read from their own findings rather than from whichever
    record they were folded onto, so a breadcrumb that opens the page's
    ``@graph`` cannot lend them its name. ``header_canonicals`` are the
    canonicals the response's ``Link`` header names, resolved. ``places`` pays
    for every answer's ``where``, as for the records'.
    """
    header_canonicals = header_canonicals or []
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

    site_name_answers = [
        og("site_name"),
        _from(site, "name", _text),
        meta(htmlmeta, "html", "application-name", "meta name="),
    ]
    # The site, by every name the page gives it, its address's host among
    # them: a site that signs its own articles has not named an author, a
    # title ending in the site's name carries a suffix, and a record bearing
    # the site's name -- the site's own app, its journal -- is not what one of
    # its pages is about. Not the publisher: on a personal blog the publisher
    # is the author, and rightly so.
    site_names = {
        answer.value.casefold() for answer in site_name_answers if answer
    } | _hosts(doc.url)
    # For choosing the subject the publisher counts too: a record named as the
    # paper that publishes the page -- its app -- is the paper's, not the page's.
    publishers = {
        text.casefold()
        for record in records
        if _about_the_site(record.types)
        and "name" in record.fields
        and (text := _text(record.fields["name"].value))
    }
    subject = _subject(records, site_names | publishers)
    subject = _main_entity(subject) or subject

    # The other descriptions of the subject when the page declares it several
    # times over, one per colour or size: an answer they do not all agree on
    # belongs to one variant, not to the thing the page is about.
    variants = _variants(records, subject)
    # The variants a ProductGroup declares: what the group does not say itself
    # is answered only when every variant says the same.
    members = _members(subject, records)

    def own(prop: str, read: Callable[[JsonValue], str | None] = _text) -> Answer:
        found = _from(subject, prop, read)
        if found is None and members:
            return _shared(members, prop, read)
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
    if members and offers is None:
        pricing = _across(
            [
                _pricing(member, member.fields["offers"].value)
                if "offers" in member.fields
                else _Pricing()
                for member in members
            ]
        )
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
            _element_text(doc, _PAGE_TITLE, "<title>"),
        ],
        "description": [
            own("description"),
            og("description"),
            meta(twitter, "twitter", "description", "twitter:"),
            meta(htmlmeta, "html", "description", "meta name="),
            meta(dublincore, "dublincore", "description", "dc."),
        ],
        "url": [_canonical(doc, header_canonicals), og("url"), own("url", _address)],
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
            _named(doc, ("author",), join=True, unless=site_names),
            _named(doc, _AUTHOR_NAMES, join=True, unless=site_names),
            _orphan_itemprop(doc, "author"),
            meta(dublincore, "dublincore", "creator", "dc."),
            _not_an_address(og("article:author")),
            _orphan_itemprop(doc, "author", meta=False),
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
        "site_name": site_name_answers,
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

    # An author is a name: not the site, and not a number -- a news site
    # writes an id, 105092, where the author goes. But a person's own site
    # bears their name: when a publisher of that name is declared a Person,
    # the site is theirs and so is the story. A Person record alone is not
    # enough, since WordPress declares one for every user, the paper's shared
    # account named as the paper included.
    people = {
        text.casefold()
        for record in records
        if "publisher" in record.fields
        for item in _listed(record.fields["publisher"].value)
        if isinstance(item, dict)
        and "Person" in _listed(item.get("@type"))
        and (text := _text(item.get("name", "")))
    }
    questions["author"] = [
        answer
        for answer in questions["author"]
        if answer
        and (
            answer.value.casefold() not in site_names
            or answer.value.casefold() in people
        )
        and answer.value.casefold() not in _NO_ONE
        and any(c.isalpha() for c in answer.value)
    ]
    # A time with no day is no date: a page that writes "10:52" where its
    # publication date goes has not said which day, and the next is asked.
    questions["published"] = [
        answer
        for answer in questions["published"]
        if answer and not _ONLY_A_TIME.match(answer.value)
    ]
    questions["published"] = _in_own_offset(questions["published"])
    questions["title"] = [
        _without_site(answer, site_names)
        if answer and answer.source not in ABOUT_A_THING
        else answer
        for answer in questions["title"]
    ]

    base = base_url(doc)
    summary: dict[str, SummaryField] = {}
    for name in FIELDS:
        candidates = questions[name]
        if name in ("url", "image"):
            # Resolved before one is chosen: an address that cleans to nothing
            # -- a lone control character -- is no answer, and the next is asked.
            candidates = [_resolved(answer, base) for answer in candidates]
        found = next((answer for answer in candidates if answer), None)
        if found is not None:
            summary[name] = replace(found, where=paid(places, found.where))
    found_conflicts = [
        replace(
            conflict,
            answers=[
                replace(answer, where=paid(places, answer.where))
                for answer in conflict.answers
            ],
        )
        for conflict in _conflicts(_with_overruled(questions, subject, overruled))
    ]
    return summary, found_conflicts


def _subject(
    records: list[Record], site_names: frozenset[str] | set[str] = frozenset()
) -> Record | None:
    """The record the page is about, or None when no declared record is.

    A type declared on three or more records is a listing -- the comments of a
    thread, the products of a category -- and none of its items is what the
    page is about. Measured on WCXB, taking the first of them made a forum
    thread's title "Post #16" and a category page's title its first product.
    Two are allowed: a product and the one related product beside it.

    On a page that declares an article, a record bearing one of
    ``site_names`` comes after the article: a paper that declares its own
    app, named as the paper is, ahead of the story had the app as the
    page's title. Only beside an article: a landscaper's page declares the
    business, named as its site, and reviews of it, and the business is what
    that page is about. It is never left out, so a page whose only record is
    named as its site still has a subject.
    """
    counts = Counter(name for record in records for name in set(record.types))
    # Each type's one record is found once, not once per record of that type:
    # asked for every product of a listing, it was the square of the listing,
    # 5.5 seconds for a page of four thousand products.
    chosen: dict[str, Record | None] = {}

    def one_of_many(name: str) -> Record | None:
        if name not in chosen:
            chosen[name] = _one_of_many(records, name)
        return chosen[name]

    candidates = [
        (rank, index, record)
        for index, record in enumerate(records)
        if (rank := _rank(record)) is not None
        and all(
            counts[name] < _A_LISTING or one_of_many(name) is record
            for name in record.types
        )
    ]
    beside_an_article = any(_an_article(record.types) for _, _, record in candidates)
    ranked = [
        (rank, beside_an_article and _named_as(record, site_names), index, record)
        for rank, index, record in candidates
    ]
    return min(ranked, key=lambda entry: entry[:3])[3] if ranked else None


def _main_entity(record: Record | None) -> Record | None:
    """The thing ``record`` declares its ``mainEntity``, when it ranks ahead.

    schema.org's word for the primary entity a page describes: a news page
    that declares a WebPage whose ``mainEntity`` is the NewsArticle, author
    and all, is about the article. Only one item, not a list -- an FAQ page's
    questions are its parts, not its subject -- and only what could have been
    the subject itself: an about page's Organization is the site's.
    """
    declared = record.fields.get("mainEntity") if record is not None else None
    if (
        record is None
        or declared is None
        or declared.source not in ABOUT_A_THING
        or not isinstance(declared.value, dict)
    ):
        return None
    item = declared.value
    types = tuple(k for k in _listed(item.get("@type")) if isinstance(k, str))
    entity = Record(
        type=types[0] if types else None,
        types=types,
        fields={
            key: Field(value, declared.source, place(item, declared.where, (key,)))
            for key, value in item.items()
            if not key.startswith("@")
        },
        source=declared.source,
        where=place(item, declared.where, ()),
    )
    rank, own = _rank(entity), _rank(record)
    return entity if rank is not None and (own is None or rank < own) else None


def _an_article(types: tuple[str, ...]) -> bool:
    return any(
        name.endswith(("Article", "Posting")) or name == "Report" for name in types
    )


def _named_as(record: Record, site_names: frozenset[str] | set[str]) -> bool:
    """Whether ``record`` bears the site's own name."""
    name = record.fields.get("name")
    text = _text(name.value) if name is not None else None
    return text is not None and text.casefold() in site_names


def _hosts(url: str | None) -> set[str]:
    """A page's host, with and without its ``www.``, as a site may name itself."""
    try:
        host = (urlsplit(url).hostname or "") if url else ""
    except ValueError:
        # "http://[::1": a malformed address names no host, and never raises.
        return set()
    if not host:
        return set()
    return {host, host.removeprefix("www.")}


def _variants(records: list[Record], subject: Record | None) -> list[Record]:
    """The other records that describe ``subject`` under its own name.

    Only where the page declares the subject's type a listing's worth of times
    and every one of them bears the subject's name: a shop's Product per colour.
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


def _members(subject: Record | None, records: list[Record]) -> list[Record]:
    """The variants a ``ProductGroup`` declares, each as a record of its own.

    Google documents two shapes for product variants: the group lists them in
    ``hasVariant``, or each is a node of its own pointing at the group with
    ``isVariantOf`` or naming its ``inProductGroupWithID``. A nested variant's
    record is named by its path, ``ProductGroup.hasVariant[1]``, so an answer
    read from it keeps the key it was read at.
    """
    if subject is None:
        return []
    declared = subject.fields.get("hasVariant")
    if declared is not None and declared.source in ABOUT_A_THING:
        items = declared.value if isinstance(declared.value, list) else [declared.value]
        name = subject.type or "Thing"
        found: list[Record] = []
        for index, item in enumerate(items[:_MOST_OFFERS]):
            if not isinstance(item, dict):
                continue
            where = (
                f"{name}.hasVariant[{index}]"
                if isinstance(declared.value, list)
                else f"{name}.hasVariant"
            )
            kind = item.get("@type")
            found.append(
                Record(
                    type=where,
                    types=tuple(
                        k
                        for k in (kind if isinstance(kind, list) else [kind])
                        if isinstance(k, str)
                    ),
                    fields={
                        key: Field(value, declared.source)
                        for key, value in item.items()
                        if not key.startswith("@")
                    },
                    source=declared.source,
                )
            )
        return found
    if "ProductGroup" not in subject.types:
        return []
    group = _from(subject, "productGroupID", _text)
    called = _from(subject, "name", _text)
    return [
        record
        for record in records
        if record is not subject
        and _points_at(
            record, group.value if group else None, called.value if called else None
        )
    ][:_MOST_OFFERS]


def _points_at(record: Record, group: str | None, name: str | None) -> bool:
    """Whether ``record`` says it is a variant of the group with this ID or name."""
    named = _from(record, "inProductGroupWithID", _text)
    if group is not None and named is not None:
        return named.value == group
    parent = record.fields.get("isVariantOf")
    if parent is None or parent.source not in ABOUT_A_THING:
        return False
    if isinstance(parent.value, dict):
        declared_id = parent.value.get("productGroupID")
        if group is not None and declared_id is not None:
            return _text(declared_id) == group
        declared_name = parent.value.get("name")
        return (
            name is not None
            and declared_name is not None
            and _text(declared_name) == name
        )
    return group is not None and _text(parent.value) == group


def _shared(
    members: list[Record], prop: str, read: Callable[[JsonValue], str | None]
) -> SummaryField | None:
    """The first variant's answer, when every variant gives the same one."""
    answers = [_from(member, prop, read) for member in members]
    first = answers[0]
    if first is None or any(a is None or a.value != first.value for a in answers):
        return None
    return first


def _across(pricings: list[_Pricing]) -> _Pricing:
    """What a group's variants say about price, without picking one of them.

    A price, regular price, currency or availability every variant gives the
    same is the group's, with the first variant's key. Prices that differ are a
    range: ``price_low`` and ``price_high`` are the lowest and highest a variant
    declares, each with the key it was read at, when at least two variants
    have one, every one of them reads as an amount, and all are in one currency.
    """

    def same(name: str) -> SummaryField | None:
        found: list[SummaryField | None] = [getattr(p, name) for p in pricings]
        first = found[0]
        if first is None or any(f is None or f.value != first.value for f in found):
            return None
        return first

    price = same("price")
    priced = [p for p in pricings if p.price is not None]
    currencies = {p.currency.value if p.currency else None for p in priced}
    currency = same("currency") or (
        priced[0].currency if priced and len(currencies) == 1 else None
    )
    low = high = None
    if price is None and len(priced) >= 2 and len(currencies) == 1:
        amounts = [amount(p.price.value) if p.price else None for p in priced]
        if all(a is not None for a in amounts):
            ranked = [
                (Decimal(a), p.price) for a, p in zip(amounts, priced, strict=True) if a
            ]
            low = min(ranked, key=lambda entry: entry[0])[1]
            high = max(ranked, key=lambda entry: entry[0])[1]
    return _Pricing(
        price,
        same("regular") if price is not None else None,
        low,
        high,
        currency if price is not None or low is not None else None,
        same("availability"),
    )


def _one_of_many(records: list[Record], name: str) -> Record | None:
    """The one record the page is about among many of type ``name``, if there is.

    Two shapes of product page declare a type three times or more and are
    still about one thing, both measured on Zyte's product benchmark. One
    shop declares a Product per colour, each with the same name: one product,
    and the first is it. Another declares its product with an offer and four
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
    if _about_the_site(record.types):
        # Yoast writes ["Organization", "Brand"]: one site type is enough.
        return None
    ranks = [_rank_of(name) for name in record.types]
    found = [rank for rank in ranks if rank is not None]
    return min(found) if found else None


def _about_the_site(types: tuple[str, ...]) -> bool:
    """Whether a record with ``types`` describes the site or who publishes it.

    Every kind of organisation counts, as ``Organization`` does: a news page's
    ``NewsMediaOrganization`` is its publisher, not its story.
    """
    return any(
        name in _ABOUT_THE_SITE or name.endswith("Organization") for name in types
    )


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
        text = _clean(_unescaped(text))
    if not text:
        return None
    return SummaryField(text, field.source, f"{record.type}.{prop}", field.where)


# A character reference as ``html.unescape`` finds one: a number, or a name
# with or without its semicolon.
_REFERENCE = re.compile(r"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)")


def _unescaped(text: str) -> str:
    """``text`` with its character references read as an attribute's are.

    HTML lets a hundred-odd old names go without their semicolon, ``&reg``
    and ``&sect`` among them, but in an attribute not before a letter, a digit
    or ``=``, where the text is the rest of a word: that is how a browser keeps
    ``?id=1&region=us&section=a`` in an ``href``. Read as ``html.unescape``
    reads running text, every such address in a page's JSON-LD came out as
    ``?id=1\u00aeion=us\u00a7ion=a``. Anything else is read as it reads it.
    """
    if "&" not in text:
        return text
    return _REFERENCE.sub(_character, text)


def _character(reference: re.Match[str]) -> str:
    written = reference.group(1)
    if written.startswith("#") or written in html5_names:
        return html_entities.unescape(reference.group())
    # The longest old name the reference starts with, as the standard reads it.
    for end in range(len(written) - 1, 1, -1):
        if written[:end] in html5_names:
            after = written[end]
            if after == "=" or (after.isascii() and after.isalnum()):
                return reference.group()
            return html5_names[written[:end]] + written[end:]
    return reference.group()


def _text(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, list):
        return next((text for item in value if (text := _text(item))), None)
    return _text(value.get("name", "")) if "name" in value else None


def _listed(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _names(value: JsonValue) -> str | None:
    """Every name ``value`` gives, in order, once each, or None."""
    items = value if isinstance(value, list) else [value]
    # Once each, in order, without asking a list for each name whether it
    # held it: forty thousand authors took four seconds.
    names: dict[str, None] = {}
    for item in items:
        if isinstance(item, dict):
            name = _text(item.get("name", "")) if "name" in item else None
            if name is None and ("givenName" in item or "familyName" in item):
                parts = (_text(item.get(k, "")) for k in ("givenName", "familyName"))
                name = " ".join(part for part in parts if part) or None
        else:
            name = _text(item)
        if name and name not in names and not _is_address(name):
            names[name] = None
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
class Conflict:
    """A question the page answers in two ways that mean different things.

    ``answers`` is the answer the summary gave, first, then every other
    declaration of the same fact that means something else, in the order
    the summary asks them: a price of 41.90 in JSON-LD and 39.90 in
    OpenGraph. Two declarations that write one meaning differently --
    ``126`` and ``126.00``, one instant at two offsets -- agree, and one
    that cannot be read is no disagreement.
    """

    question: str
    answers: list[SummaryField]


def _moment(text: str) -> tuple[str, datetime.datetime | None] | None:
    """A date's day as written, and its instant when it states one."""
    written = iso_date(text)
    if written is None:
        return None
    instant = None
    if "T" in written:
        try:
            parsed = datetime.datetime.fromisoformat(written.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        instant = parsed if parsed is not None and parsed.tzinfo else None
    return written[:10], instant


def _same_moment(
    one: tuple[str, datetime.datetime | None],
    other: tuple[str, datetime.datetime | None],
) -> bool:
    """Whether two dates name one day: one instant, or one day as written.

    A time a page truncates to the minute, or an offset it writes wrong on
    one of two tags -- the same 06:00:09 at -07:00 and at +00:00 -- is the
    same day, and not what a reader asks. Two instants that are one are one
    date even across midnight, 19:45 at -06:00 being 01:45 the next day in
    UTC.
    """
    if one[1] is not None and other[1] is not None and one[1] == other[1]:
        return True
    return one[0] == other[0]


def _in_own_offset(answers: list[Answer]) -> list[Answer]:
    """``answers`` with the first moved behind a declaration of the same
    instant in the publisher's own time zone, when it is written in UTC.

    A page that says 2020-01-01T01:30Z in one tag and 2019-12-31T20:30-05:00
    in another says one instant twice, and the day it was published where it
    was published is the 31st: UTC is how a platform stores the instant, the
    offset is the publisher's.
    """
    first = next((answer for answer in answers if answer), None)
    moment = _moment(first.value) if first is not None else None
    if first is None or moment is None or moment[1] is None:
        return answers
    if moment[1].utcoffset() != datetime.timedelta(0):
        return answers
    for answer in answers:
        other = _moment(answer.value) if answer else None
        if (
            answer is not None
            and other is not None
            and other[1] is not None
            and other[1] == moment[1]
            and other[1].utcoffset() != datetime.timedelta(0)
        ):
            return [answer, *(a for a in answers if a is not answer)]
    return answers


def _same_text(one: object, other: object) -> bool:
    return one == other


def _decimal(text: str) -> Decimal | None:
    """An amount by its value: 41.90 and 41.9 are one price."""
    written = amount(text)
    return Decimal(written) if written is not None else None


# What each compared question's candidates must be to state the same fact,
# and how two of them are compared. A page's upload or creation date is not
# its publication date, so only the keys that say "published" are compared.
_PUBLISHED = (
    "datePublished",
    "article:published_time",
    "dc.date.issued",
    "dc.issued",
    "meta name=citation_publication_date",
)
_COMPARED: dict[
    str, tuple[Callable[[str], bool], Callable[[str], Any], Callable[[Any, Any], bool]]
] = {
    "price": (lambda key: True, _decimal, _same_text),
    "currency": (lambda key: True, currency_of, _same_text),
    "published": (lambda key: key.endswith(_PUBLISHED), _moment, _same_moment),
    "modified": (lambda key: True, _moment, _same_moment),
}


def _conflicts(questions: dict[str, list[Answer]]) -> list[Conflict]:
    """Each compared question whose declarations of one fact disagree.

    Only where the summary's own answer is one of them and can be read: a
    conflict starts with what the summary said, so a page whose answer was
    its upload date, or a price no reader can call one number, is not
    compared.
    """
    found = []
    for question, (same_fact, meaning, agree) in _COMPARED.items():
        answers = [answer for answer in questions.get(question, []) if answer]
        if not answers or not same_fact(answers[0].key):
            continue
        first = meaning(answers[0].value)
        if first is None:
            continue
        kept: list[tuple[SummaryField, Any]] = [(answers[0], first)]
        for answer in answers[1:]:
            if not same_fact(answer.key):
                continue
            meant = meaning(answer.value)
            # Unread is not different: a value no rule can read is no
            # disagreement with one it can.
            if meant is not None and all(not agree(meant, other) for _, other in kept):
                kept.append((answer, meant))
        if len(kept) > 1:
            found.append(Conflict(question, [answer for answer, _ in kept]))
    return found


def _with_overruled(
    questions: dict[str, list[Answer]],
    subject: Record | None,
    overruled: Overruled | None,
) -> dict[str, list[Answer]]:
    """The questions, with what a later vocabulary declared for the subject
    and a fold set aside added after the answers already asked, for the
    questions a conflict is reported on (``_COMPARED``). Compared only, never
    answered from: a product whose JSON-LD says 41.90 and whose microdata
    says 39.90 is one product with two prices, and the second was dropped
    without a word; the summary is what it was, and the conflict is now
    reported."""
    held = overruled.get(id(subject), {}) if overruled and subject else {}
    if not held or subject is None:
        return questions
    extra: dict[str, list[Answer]] = {}
    for offers in held.get("offers", ()):
        other = Record(
            type=subject.type,
            types=subject.types,
            fields={**subject.fields, "offers": offers},
            source=offers.source,
        )
        pricing = _pricing(other, offers.value)
        for question, answer in (
            ("price", _one_amount(pricing.price)),
            ("currency", pricing.currency),
        ):
            if answer is not None:
                extra.setdefault(question, []).append(answer)
    name = subject.type or "Thing"
    for question, key in (("published", "datePublished"), ("modified", "dateModified")):
        for field_ in held.get(key, ()):
            text = _text(field_.value)
            if text:
                extra.setdefault(question, []).append(
                    SummaryField(text, field_.source, f"{name}.{key}", field_.where)
                )
    return {
        question: [*answers, *extra.get(question, [])]
        for question, answers in questions.items()
    }


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
    held = subject.fields["offers"]
    name = subject.type or "Thing"

    def answer(value: JsonValue | None, path: str) -> SummaryField | None:
        text = _text(value) if value is not None else None
        if not text:
            return None
        return SummaryField(text, held.source, f"{name}.{path}", _inside(held, path))

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


# One number as a price is written, or as JSON writes one: 1.5e3 is one.
_NUMBER = re.compile(r"\d(?:[\d.,'\s]*\d)?(?:[eE][+-]?\d+)?")


def _one_amount(found: SummaryField | None) -> SummaryField | None:
    """``found`` if it holds one number, which is what a price is.

    One shop's microdata ``price`` is the text of an element holding the
    price and the price it replaced, ``71,91 € 79,90 €``, and another's is
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
            path = f"{where}.{key}"
            return SummaryField(
                text, rating.source, f"{record.type}.{path}", _inside(rating, path)
            )
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
    return SummaryField(
        path, crumbs.source, "BreadcrumbList.itemListElement", crumbs.where
    )


def _crumb_name(item: dict[str, JsonValue]) -> str | None:
    for value in (item.get("name"), item.get("item")):
        if isinstance(value, dict):
            value = value.get("name")
        text = _text(value) if isinstance(value, str) else None
        if text and not _is_address(text):
            return text
    return None


def _position(value: JsonValue | None, order: int) -> float:
    """A crumb's ``position``, or where it was written when it states none.

    Not a NaN, which compares false with everything and left ``sorted`` no
    order to keep, nor an infinity, which is no place in a list either.
    """
    try:
        found = float(str(value)) if value is not None else float(order)
    except ValueError:
        return float(order)
    return found if math.isfinite(found) else float(order)


def _type(record: Record | None) -> SummaryField | None:
    if record is None or record.type is None or record.source is None:
        return None
    return SummaryField(record.type, record.source, "@type", record.where)


def _headline_or_name(
    headline: SummaryField | None,
    name: SummaryField | None,
    doc: Document,
    opengraph: dict[str, str],
) -> list[SummaryField | None]:
    """``headline`` then ``name``, unless the page's own title says otherwise.

    An encyclopedia site puts its short description in ``headline`` --
    "hydraulic structure" -- and the article's title in ``name``. When only
    one of the two appears in the title the page shows, in ``<title>`` or
    ``og:title``, that one is the title.
    """
    if headline is None or name is None:
        return [headline, name]
    shown = " ".join(
        text.casefold()
        for text in (
            opengraph.get("title"),
            *(title.text_content() for title in doc.tree.xpath(_PAGE_TITLE)),
        )
        if text
    )
    if name.value.casefold() in shown and headline.value.casefold() not in shown:
        return [name, headline]
    return [headline, name]


def _element_text(doc: Document, path: str, key: str) -> SummaryField | None:
    found = doc.tree.xpath(path)
    text = _clean(found[0].text_content()) if found else None
    return SummaryField(text, "html", key, xpath_of(found[0])) if text else None


def _named(
    doc: Document,
    names: tuple[str, ...],
    join: bool = False,
    unless: frozenset[str] | set[str] = frozenset(),
) -> SummaryField | None:
    """The first of ``names`` a ``<meta name>`` on the page carries.

    ``names`` is tried in its own order, not the page's. With ``join``, every
    tag of the winning name is read -- a paper lists each author in one -- and
    the names are joined once each, in the order written. A text in
    ``unless``, casefolded, is passed over for the next: a paper whose first
    author tag is the paper and whose second is the reporter has the
    reporter as its author.
    """
    found = _meta_names(doc)
    for name in names:
        if name in found:
            # Each name once, at the first tag that gives it. Never empty: a
            # cleaned text ends in something that is not a space, which the
            # byline's "by " cannot take.
            first: dict[str, HtmlElement] = {}
            for text, meta in found[name]:
                named = _BYLINE.sub("", text)
                if named.casefold() not in unless:
                    first.setdefault(named, meta)
            if not first:
                continue
            key = f"meta name={name}"
            if join and len(first) > 1:
                # Joined from several tags, the answer has no one element.
                return SummaryField(", ".join(first), "html", key)
            text, meta = next(iter(first.items()))
            return SummaryField(text, "html", key, xpath_of(meta))
    return None


def _meta_names(doc: Document) -> dict[str, list[tuple[str, HtmlElement]]]:
    """Every ``<meta name>`` with a text, by its name lowercased, in page order.

    Read once per page: the summary asks it four times, for a title, two kinds
    of author and a date.
    """
    found: dict[str, list[tuple[str, HtmlElement]]] | None = doc.memo.get(
        "summary.meta_names"
    )
    if found is None:
        found = doc.memo["summary.meta_names"] = {}
        for meta in doc.tree.xpath("//meta[@name][@content]"):
            text = _clean(meta.get("content"))
            if text:
                name = (meta.get("name") or "").strip().lower()
                found.setdefault(name, []).append((text, meta))
    return found


def _orphan_itemprop(
    doc: Document, prop: str, meta: bool = True
) -> SummaryField | None:
    """An ``itemprop`` outside any item: a ``<meta itemprop>`` as templates put
    in the head, or, with ``meta`` false, any other element's author, ``<span
    itemprop="author">``, asked after every other declaration. A byline that
    is only a label, "Staff", names nobody. (Other elements' dates were
    measured and not kept: on WCXB's development split they added an
    invention and no hit.)

    The microdata standard ignores it, having no item to give it to, so the
    microdata reader does too. It is still the page stating the value. The
    tags are found once per page, for the three questions that ask.
    """
    orphans: list[HtmlElement] | None = doc.memo.get("summary.orphan_itemprops")
    if orphans is None:
        orphans = doc.memo["summary.orphan_itemprops"] = doc.tree.xpath(
            "//*[@itemprop][not(ancestor::*[@itemscope])]"
        )
    for element in orphans:
        if (element.tag == "meta") is not meta:
            continue
        if prop in (element.get("itemprop") or "").split():
            if meta:
                text = _clean(element.get("content"))
                if not text:
                    continue
                return SummaryField(
                    text, "html", f"<meta itemprop={prop}>", xpath_of(element)
                )
            # An element that is an item itself holds a card, not a value.
            if element.get("itemscope") is not None:
                continue
            text = _clean(_itemprop_value(element))
            if not text or len(text) > _ORPHAN_MOST:
                continue
            text = _BYLINE.sub("", text)
            if set(text.casefold().split()) <= _NOBODY_WORDS:
                continue
            key = f"<{element.tag} itemprop={prop}>"
            return SummaryField(text, "html", key, xpath_of(element))
    return None


# The words of a byline that name nobody: its label, not a person.
_NOBODY_WORDS = frozenset({"by", "staff", "team", "editor", "editors", "writer"})
# The longest text an element outside any item is read as a value: a name or
# a date, not a paragraph that happens to carry an itemprop.
_ORPHAN_MOST = 120


def _itemprop_value(element: HtmlElement) -> str | None:
    """An element's microdata value when it is a text, as the standard reads
    it: a <time>'s datetime, a <data>'s value, else its text. An element whose
    value is an address has none here."""
    if element.tag in _AN_ADDRESS:
        return None
    attribute = {"time": "datetime", "data": "value", "meter": "value"}
    value = element.get(attribute[element.tag]) if element.tag in attribute else None
    if value is None and element.tag != "time" and element.tag in attribute:
        return None
    return str(value if value is not None else element.text_content())


# The elements whose microdata value is an address, not a text.
_AN_ADDRESS = frozenset(
    {"a", "area", "link", "img", "audio", "video", "source", "track", "embed"}
    | {"iframe", "object"}
)


def _without_site(found: SummaryField, site_names: set[str]) -> SummaryField | None:
    """``found`` with a trailing " - Site Name" cut, when it names the site."""
    for separator in _TITLE_SEPARATORS:
        head, cut, tail = found.value.rpartition(separator)
        if cut and head.strip() and tail.strip().casefold() in site_names:
            return replace(found, value=head.strip())
    return found


def _canonical(doc: Document, header: list[str]) -> SummaryField | None:
    """The page's canonical address, when its head and ``Link`` header name one.

    ``header`` is the ``Link`` header's canonicals, already resolved; the
    head's are compared resolved too, so ``/p`` and ``https://site/p`` are one
    address. Two different ones are a conflict, and answer nothing.
    """
    written = canonicals(doc)
    base = base_url(doc)
    declared = dict.fromkeys([join(base, href) for href in written] + header)
    if len(declared) != 1:
        return None
    if written:
        return SummaryField(written[0], "html", "<link rel=canonical>")
    return SummaryField(header[0], "http", "Link: rel=canonical")


def _language(doc: Document) -> SummaryField | None:
    for element in doc.tree.xpath("//html[@lang]"):
        lang = _clean(element.get("lang"))
        if lang:
            return SummaryField(lang, "html", "<html lang>", xpath_of(element))
    return None


def _locale(found: SummaryField | None) -> SummaryField | None:
    """``og:locale`` is written ``en_US``; a language tag is ``en-US``."""
    if found is None:
        return None
    return replace(found, value=found.value.replace("_", "-"))


def _resolved(found: SummaryField | None, base: str | None) -> SummaryField | None:
    if found is None or base is None:
        return found
    address = join(base, found.value)
    return replace(found, value=address) if address else None


def _short(found: SummaryField | None) -> SummaryField | None:
    """``https://schema.org/InStock`` is the schema.org term ``InStock``.

    The vocabulary's address alone names no term, and is no answer: an empty
    one would stop the next candidate from being asked.
    """
    if found is None:
        return None
    term = _SCHEMA_ORG.sub("", found.value)
    return replace(found, value=term) if term else None


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


# One step of a key's path: ``offers``, or ``[1]``.
_STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _inside(held: Field, path: str) -> str | None:
    """Where the value ``path`` names inside ``held`` was declared.

    ``path`` is the answer's key without its type -- ``offers[1].price`` --
    and starts at ``held``'s own property.
    """
    steps = [int(n) if n else key for key, n in _STEP.findall(path)][1:]
    return place(held.value, held.where, steps)
