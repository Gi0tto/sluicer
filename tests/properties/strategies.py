"""The pages the properties are run against, drawn rather than written.

A page is drawn as a small tree -- ``Element``s holding text and each other --
and only then rendered to HTML. That is what lets a property render one tree
two ways that a browser reads as the same page (attributes in another order,
names in another case, tokens spaced differently, another encoding) and ask
whether sluicer gives the same answer to both.

The vocabulary of what gets drawn is the readers': schema.org types in every
spelling the readers fold, the property names the summary asks for, the meta
names every document-level reader matches, references between JSON-LD nodes
and ``itemref`` between microdata items drawn over a small pool of ids so that
they collide, cycle and dangle. The values are real-page shapes -- prices,
dates, relative addresses, entities, blank text -- mixed with whatever text
Hypothesis draws.

Nothing here parses anything, and nothing here imports sluicer: a strategy that
borrowed the code under test to decide what to generate would agree with it by
construction.
"""

from __future__ import annotations

import codecs
import contextlib
import encodings.aliases
import json
import random
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from hypothesis import strategies as st

from sluicer.declared.opengraph import (
    ARRAYS as OPENGRAPH_ARRAYS,
    STRUCTURED as OPENGRAPH_STRUCTURED,
)
from sluicer.declared.rights import _CRAWLERS

# -- running what they draw -----------------------------------------------------


@contextlib.contextmanager
def a_callers_stack() -> Iterator[None]:
    """Python's own recursion limit, measured from here.

    Hypothesis raises the limit by two thousand frames while a test runs, so
    that it has room of its own. libxml2 nests elements at most 2,047 deep, so
    under that limit no page can overflow a walk that recurses once a level:
    the property could never find the ``RecursionError`` a caller would get.
    What a caller has is Python's default of a thousand frames, less the few
    it is already using.
    """
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(depth + 950)
    try:
        yield
    finally:
        sys.setrecursionlimit(limit)


# -- the tree ------------------------------------------------------------------

Tokens = tuple[str, ...]
"""An attribute whose value is a set of space-separated tokens."""

AttributeValue = str | Tokens | None
"""Text, a token list, or None for an attribute written with no value."""


@dataclass
class Element:
    """One element: its tag, its attributes in the order drawn, its children.

    ``raw`` elements (``script``, ``style``, ``title``) hold one string that is
    written as it is, never escaped, as their content model says.
    """

    tag: str
    attributes: list[tuple[str, AttributeValue]] = field(default_factory=list)
    children: list[Element | str] = field(default_factory=list)
    raw: bool = False


VOID = frozenset(
    {"meta", "link", "img", "br", "hr", "input", "base", "source", "track", "embed"}
)

# What HTML calls ASCII whitespace, which is what separates the tokens of a
# token list. Python's ``str.split`` also splits on others (a no-break space, a
# vertical tab), which HTML does not; those are not drawn, so a property never
# holds sluicer to a separator the standard does not have.
SEPARATORS = (" ", "  ", "\t", "\n", "\r\n", " \n\t ", "\x0c")


@dataclass(frozen=True)
class Style:
    """How a tree is written out, none of which changes what it means."""

    seed: int = 0
    """Shuffles each element's attributes; 0 keeps them in the order drawn."""
    upper: bool = False
    """Write every tag and attribute name in capitals."""
    separator: str = " "
    """What goes between the tokens of a token-list attribute."""
    padded: bool = False
    """Put the separator before the first token and after the last as well."""
    quote: str = '"'
    """The quote around attribute values: ``"``, ``'`` or "" where it is safe."""


def render(node: Element | str, style: Style | None = None) -> str:
    """Write ``node`` as HTML, the way ``style`` says.

    With a stack of its own: the pages drawn to multiply nest a thousand deep.
    """
    style = style or Style()
    shuffle = random.Random(style.seed) if style.seed else None
    parts: list[str] = []
    pending: list[tuple[Element | str, bool]] = [(node, False)]
    while pending:
        item, raw = pending.pop()
        if isinstance(item, str):
            parts.append(item if raw else escape_text(item))
            continue
        tag = item.tag.upper() if style.upper else item.tag
        parts.append(_start_tag(item, tag, style, shuffle))
        if item.tag in VOID:
            continue
        pending.append((f"</{tag}>", True))
        pending.extend((child, item.raw) for child in reversed(item.children))
    return "".join(parts)


def _start_tag(
    element: Element, tag: str, style: Style, shuffle: random.Random | None
) -> str:
    attributes = list(element.attributes)
    if shuffle is not None:
        shuffle.shuffle(attributes)
    written = ["<" + tag]
    for name, value in attributes:
        written.append(" " + (name.upper() if style.upper else name))
        if value is None:
            continue
        if isinstance(value, tuple):
            text = style.separator.join(value)
            if style.padded:
                text = style.separator + text + style.separator
        else:
            text = value
        written.append("=" + _quoted(text, style.quote))
    return "".join(written) + ">"


def escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _quoted(text: str, quote: str) -> str:
    escaped = text.replace("&", "&amp;")
    unsafe = set(" \t\n\r\x0c\"'=<>`")
    if quote == "" and escaped and not (set(escaped) & unsafe):
        return escaped
    mark = quote or '"'
    return mark + escaped.replace(mark, "&quot;" if mark == '"' else "&#39;") + mark


def styles(**fixed: Any) -> st.SearchStrategy[Style]:
    """Every way of writing a tree that a browser reads as the same page."""
    drawn = {
        "seed": st.integers(0, 2**32),
        "upper": st.booleans(),
        "separator": st.sampled_from(SEPARATORS),
        "padded": st.booleans(),
        "quote": st.sampled_from(['"', "'", ""]),
    }
    drawn.update({name: st.just(value) for name, value in fixed.items()})
    return st.builds(Style, **drawn)


# -- the vocabulary ----------------------------------------------------------------

WORDS = (
    "Pad",
    "Brake pad set",
    "Textar",
    "café",
    "Привет",
    "日本語のテキスト",
    "🙂",
    "41.90",
    "£51.77",
    "1,299.00",
    "EUR",
    "2026-09-22",
    "2026-09-22T10:00:00+02:00",
    "In stock",
    "https://schema.org/InStock",
    "http://schema.org/",
    "By Jane Doe",
    "Jane Doe",
    "Guide &#8226; Yoast",
    "Sluice - Wikipedia",
    "Wikipedia",
    "en_US",
    "de-DE",
    "null",
    "true",
    "a&b",
    "a>b",
    "<b>bold</b>",
    "  spaced   out  ",
    "",
    " ",
    "\t\n",
    "\u00a0",
    "line one\nline two",
)

ADDRESSES = (
    "",
    " ",
    "/p/1",
    "p/2",
    "../img/1.jpg",
    "?page=2",
    "#top",
    "//cdn.example/i.jpg",
    "https://x.example/a",
    "HTTPS://X.EXAMPLE/B",
    "https://bücher.example/",
    "https://[domain]/p",
    "http://[::1",
    "http://[x/",
    "mailto:jane@x.example",
    "javascript:void(0)",
    "data:text/plain,x",
    "http://h.example/%zz",
    "www.x.example/p",
)

PAGE_URLS = (
    None,
    "https://shop.example/c/brakes",
    "https://shop.example/",
    "http://[::1",
    "https://[domain]/",
    "not an address",
    "",
)

SCHEMA_TYPES = (
    "Product",
    "ProductGroup",
    "Offer",
    "AggregateOffer",
    "Article",
    "NewsArticle",
    "BlogPosting",
    "Report",
    "Recipe",
    "Event",
    "JobPosting",
    "Person",
    "Organization",
    "Corporation",
    "Brand",
    "WebSite",
    "WebPage",
    "ItemPage",
    "BreadcrumbList",
    "ListItem",
    "ItemList",
    "ImageObject",
    "VideoObject",
    "Review",
    "Thing",
)


def _spellings(name: str) -> tuple[str, ...]:
    return (
        name,
        f"schema:{name}",
        f"http://schema.org/{name}",
        f"https://schema.org/{name}",
        f"https://www.schema.org/{name}/",
    )


TYPE_TOKENS = st.one_of(
    st.sampled_from(SCHEMA_TYPES).flatmap(lambda n: st.sampled_from(_spellings(n))),
    st.sampled_from(
        (
            "https://example.org/ns#Widget",
            "http://xmlns.com/foaf/0.1/Person",
            "h-entry",
            "",
            " ",
        )
    ),
)

PROPERTY_NAMES = (
    "name",
    "headline",
    "description",
    "url",
    "image",
    "thumbnailUrl",
    "contentUrl",
    "author",
    "creator",
    "publisher",
    "brand",
    "sku",
    "offers",
    "price",
    "lowPrice",
    "priceCurrency",
    "priceSpecification",
    "availability",
    "datePublished",
    "dateModified",
    "dateCreated",
    "uploadDate",
    "inLanguage",
    "givenName",
    "familyName",
    "isRelatedTo",
    "itemListElement",
    "recipeIngredient",
    "x",
)

# Every metadata name some document-level reader or summary rule matches, and
# a few none does, so both sides of each match are drawn.
META_KEYS = (
    "og:title",
    "og:description",
    "og:image",
    "og:image:url",
    "og:image:secure_url",
    "og:image:alt",
    "og:url",
    "og:type",
    "og:site_name",
    "og:locale",
    "og:updated_time",
    "og:price:amount",
    "og:price:currency",
    "og:availability",
    "og:brand",
    "og:article:tag",
    "article:published_time",
    "article:modified_time",
    "article:author",
    "book:author",
    "twitter:title",
    "twitter:description",
    "twitter:image",
    "twitter:image:alt",
    "twitter:card",
    "dc.title",
    "dc.creator",
    "dc.date",
    "dc.date.issued",
    "dc.language",
    "dc.publisher",
    "dc.description",
    "dcterms.issued",
    "dcterms.modified",
    "dcterms.created",
    "description",
    "author",
    "keywords",
    "generator",
    "application-name",
    "theme-color",
    "citation_title",
    "citation_author",
    "citation_publication_date",
    "parsely-pub-date",
    "parsely-author",
    "sailthru.author",
    "byl",
    "date",
    "pubdate",
    "robots",
    "viewport",
    "fb:app_id",
    "csrf-token",
)

# The names whose every tag is read, rather than the first: a paper lists each
# author in one -- HTML's own ``author`` too, whose first may be the paper and
# its second the reporter -- and a page's robots directives are gathered from
# all its robots tags, as Google combines them. A later duplicate of these is a
# new value, not a repeat.
JOINED_META_KEYS = frozenset(
    {"author", "citation_author", "parsely-author", "sailthru.author", "byl"}
    | {"robots"}
    | _CRAWLERS
)


def joined_meta(meta: Element) -> bool:
    """Whether a later copy of ``meta`` is a new value rather than a repeat.

    ``JOINED_META_KEYS``, and OpenGraph's arrays and structured properties,
    which ogp.me reads by position: another ``og:image`` is another image,
    and an ``og:image:width`` after it is that image's.
    """
    terms: set[str] = set()
    for name, value in meta.attributes:
        if name in ("name", "property"):
            text = " ".join(value) if isinstance(value, tuple) else str(value)
            terms |= {*text.lower().split(), text.strip().lower()}
    for term in terms:
        if term in JOINED_META_KEYS:
            return True
        key = term.removeprefix("og:")
        if key in OPENGRAPH_ARRAYS or key.rpartition(":")[0] in OPENGRAPH_STRUCTURED:
            return True
    return False


def recased(text: str) -> st.SearchStrategy[str]:
    """``text`` with the case of each letter drawn."""
    return st.lists(st.booleans(), min_size=len(text), max_size=len(text)).map(
        lambda flips: "".join(
            c.upper() if flip else c.lower()
            for c, flip in zip(text, flips, strict=True)
        )
    )


words = st.one_of(st.sampled_from(WORDS), st.text(max_size=12))
addresses = st.one_of(st.sampled_from(ADDRESSES), st.text(max_size=8))
page_urls = st.sampled_from(PAGE_URLS)


# -- JSON-LD -------------------------------------------------------------------

IDS = ("#a", "#b", "#c", "#d", "https://x.example/#org", "_:b0", "", "#missing")

ids = st.sampled_from(IDS)

json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-(10**20), 10**20),
    st.floats(),  # NaN and infinities render as JSON's non-standard spellings
    words,
    addresses,
)


def _node(inner: st.SearchStrategy[Any]) -> st.SearchStrategy[dict[str, Any]]:
    """A node object: maybe typed, maybe identified, and its properties."""

    @st.composite
    def build(draw: st.DrawFn) -> dict[str, Any]:
        node: dict[str, Any] = {}
        if draw(st.booleans()):
            types = draw(st.lists(TYPE_TOKENS, min_size=1, max_size=3))
            node["@type"] = (
                types[0] if len(types) == 1 and draw(st.booleans()) else types
            )
        if draw(st.booleans()):
            node["@id"] = draw(ids)
        if draw(st.integers(0, 5)) == 0:
            node["@context"] = draw(st.sampled_from(["https://schema.org", {}, None]))
        for key in draw(st.lists(st.sampled_from(PROPERTY_NAMES), max_size=4)):
            node[key] = draw(inner)
        return node

    return build()


json_values = st.recursive(
    json_scalars,
    lambda inner: st.one_of(
        st.lists(inner, max_size=4),
        _node(inner),
        ids.map(lambda i: {"@id": i}),
        inner.map(lambda v: {"@value": v}),
        st.lists(inner, max_size=3).map(lambda v: {"@list": v}),
        st.lists(inner, max_size=3).map(lambda v: {"@set": v}),
    ),
    max_leaves=16,
)

json_nodes = _node(json_values)

# The shapes the summary reads a subject's answers from, so that its rules --
# the first offer that states a price, a person named in parts, an image that
# is an object -- meet every spelling of what they read.
_scalar_text = st.one_of(words, addresses)
_people = st.one_of(
    words,
    st.fixed_dictionaries(
        {"@type": st.sampled_from(["Person", "Organization"])},
        optional={
            "name": words,
            "givenName": words,
            "familyName": words,
            "url": addresses,
        },
    ),
)
_images = st.one_of(
    addresses,
    st.fixed_dictionaries(
        {"@type": st.just("ImageObject")},
        optional={"url": addresses, "contentUrl": addresses, "@id": addresses},
    ),
)
_offers = st.fixed_dictionaries(
    {},
    optional={
        "@type": st.sampled_from(["Offer", "AggregateOffer"]),
        "price": _scalar_text,
        "lowPrice": _scalar_text,
        "priceCurrency": st.sampled_from(["EUR", "USD", "", " "]),
        "availability": st.sampled_from(
            [
                "https://schema.org/InStock",
                "http://schema.org/OutOfStock",
                "InStock",
                "https://schema.org/",
                "http://schema.org/",
                "",
            ]
        ),
        "priceSpecification": st.fixed_dictionaries(
            {}, optional={"price": _scalar_text, "priceCurrency": st.just("EUR")}
        ),
    },
)


def _one_or_many(inner: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    return st.one_of(inner, st.lists(inner, max_size=3))


# What a page declares its main entity: a thing nested in a page, with the
# properties the summary reads from a subject, so every answer read through
# it is placed inside it.
_main_entities = st.fixed_dictionaries(
    {"@type": st.sampled_from(SCHEMA_TYPES)},
    optional={
        "name": words,
        "headline": words,
        "author": _one_or_many(_people),
        "datePublished": words,
        "offers": _one_or_many(_offers),
    },
)


summary_subjects = st.fixed_dictionaries(
    {"@type": st.sampled_from(SCHEMA_TYPES)},
    optional={
        "mainEntity": st.one_of(_main_entities, st.lists(_main_entities, max_size=2)),
        "@id": ids,
        "name": words,
        "headline": words,
        "description": words,
        "url": addresses,
        "image": _one_or_many(_images),
        "thumbnailUrl": addresses,
        "author": _one_or_many(_people),
        "creator": _one_or_many(_people),
        "publisher": _one_or_many(_people),
        "brand": _one_or_many(_people),
        "datePublished": words,
        "dateModified": words,
        "uploadDate": words,
        "inLanguage": words,
        "sku": words,
        "offers": _one_or_many(_offers),
    },
)


@st.composite
def jsonld_documents(draw: st.DrawFn) -> Any:
    """What one block holds: a node, a list of them, or an ``@graph``, nested."""
    nodes = draw(
        st.lists(st.one_of(json_nodes, summary_subjects), min_size=1, max_size=4)
    )
    shape = draw(st.sampled_from(["node", "list", "graph", "nested"]))
    if shape == "node":
        return nodes[0]
    if shape == "list":
        return nodes
    graph = {"@context": "https://schema.org", "@graph": nodes}
    return graph if shape == "graph" else [graph, {"@graph": [graph]}]


MEDIA_TYPES = (
    "application/ld+json",
    "application/LD+JSON",
    "  application/ld+json ; charset=utf-8",
    "application/json",
    "text/javascript",
)

# Plain words, so an answer read from a page is the text the page holds.
_plain = st.from_regex(r"[A-Za-z]{1,8}( [A-Za-z]{1,8}){0,2}", fullmatch=True)


@st.composite
def main_entity_pages(draw: st.DrawFn) -> tuple[str, str, bool]:
    """A page that declares itself a WebPage whose ``mainEntity`` is a thing,
    the thing's type, and whether it declares any property beside it.

    In JSON-LD or in microdata, the entity of any drawn type, holding some of
    the properties the summary reads, its author a name or a Person.
    """
    page_type = draw(st.sampled_from(["WebPage", "ItemPage"]))
    kind = draw(st.sampled_from(SCHEMA_TYPES))
    props = draw(
        st.fixed_dictionaries(
            {},
            optional={
                "headline": _plain,
                "name": _plain,
                "author": _plain,
                "datePublished": _plain,
            },
        )
    )
    as_person = draw(st.booleans())
    if draw(st.booleans()):
        entity: dict[str, Any] = {"@type": kind, **props}
        if "author" in props and as_person:
            entity["author"] = {"@type": "Person", "name": props["author"]}
        block = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": page_type,
                "name": draw(_plain),
                "mainEntity": entity,
            }
        )
        return (
            (
                f'<html><head><script type="application/ld+json">{block}</script>'
                "</head><body></body></html>"
            ),
            kind,
            bool(props),
        )
    inner = "".join(
        '<div itemprop="author" itemscope itemtype="https://schema.org/Person">'
        f'<span itemprop="name">{value}</span></div>'
        if key == "author" and as_person
        else f'<span itemprop="{key}">{value}</span>'
        for key, value in props.items()
    )
    return (
        (
            f'<html><body itemscope itemtype="https://schema.org/{page_type}">'
            f'<div itemprop="mainEntity" itemscope itemtype="https://schema.org/{kind}">'
            f"{inner}</div></body></html>"
        ),
        kind,
        bool(props),
    )


# The wrappers CMSs put around a block, all of which a reader should see through.
WRAPPERS = (
    "{}",
    "<!-- {} -->",
    "//<![CDATA[\n{}\n//]]>",
    "/*<![CDATA[*/{}/*]]>*/",
    "\ufeff{}",
    "\n\n  {}  \n",
)


@st.composite
def jsonld_text(draw: st.DrawFn) -> str:
    """One block's text: valid, wrapped, with trailing commas, or broken."""
    document = draw(jsonld_documents())
    text = json.dumps(
        document,
        ensure_ascii=draw(st.booleans()),
        indent=draw(st.sampled_from([None, 2])),
    )
    damage = draw(st.sampled_from(["none", "none", "commas", "truncate", "splice"]))
    if damage == "commas":
        text = text.replace("}", ",}").replace("]", ",]").replace("[,]", "[]")
    elif damage == "truncate":
        text = text[: draw(st.integers(0, len(text)))]
    elif damage == "splice":
        at = draw(st.integers(0, len(text)))
        text = (
            text[:at]
            + draw(st.sampled_from(["'", "//", "/*", "NaN", "\x00"]))
            + text[at:]
        )
    return draw(st.sampled_from(WRAPPERS)).replace("{}", text, 1)


def jsonld_script(text: str, media_type: str = "application/ld+json") -> Element:
    return Element("script", [("type", media_type)], [text], raw=True)


@st.composite
def jsonld_blocks(draw: st.DrawFn) -> Element:
    return jsonld_script(draw(jsonld_text()), draw(st.sampled_from(MEDIA_TYPES)))


# -- microdata -----------------------------------------------------------------

# The elements whose value is an attribute, and which attribute: the standard's
# list, drawn from so every branch of the value rule is met.
VALUE_ELEMENTS = (
    ("meta", "content"),
    ("a", "href"),
    ("link", "href"),
    ("area", "href"),
    ("img", "src"),
    ("audio", "src"),
    ("video", "src"),
    ("source", "src"),
    ("iframe", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("data", "value"),
    ("meter", "value"),
    ("time", "datetime"),
    ("span", "content"),
    ("span", None),
    ("div", None),
    ("time", None),
)

CONTAINERS = ("div", "span", "section", "article", "li", "p")

ITEM_IDS = ("m0", "m1", "m2", "m3", "m4", "m5", "p0", "p1", "nowhere")


@st.composite
def microdata_property(draw: st.DrawFn) -> Element:
    tag, attribute = draw(st.sampled_from(VALUE_ELEMENTS))
    names = tuple(draw(st.lists(st.sampled_from(PROPERTY_NAMES), max_size=3)))
    attributes: list[tuple[str, AttributeValue]] = [("itemprop", names)]
    if attribute is not None and draw(st.integers(0, 4)) > 0:
        value = draw(addresses if attribute in ("href", "src", "data") else words)
        attributes.append((attribute, value))
    if draw(st.integers(0, 3)) == 0:
        attributes.append(("id", draw(st.sampled_from(ITEM_IDS))))
    children: list[Element | str] = [] if tag in VOID else [draw(words)]
    return Element(tag, attributes, children)


@st.composite
def microdata(draw: st.DrawFn, max_items: int = 6) -> list[Element]:
    """Items that nest, name each other with ``itemref``, and name themselves.

    Ids are drawn from a small pool, so an ``itemref`` finds an item, a plain
    element, a duplicate id or nothing; an item can refer to itself and to the
    item that holds it; and items are placed inside each other at random, so a
    property's nearest item is sometimes not the one that meant to own it.
    """
    count = draw(st.integers(1, max_items))
    items: list[Element] = []
    for _ in range(count):
        attributes: list[tuple[str, AttributeValue]] = [("itemscope", None)]
        if draw(st.integers(0, 3)) > 0:
            attributes.append(("id", draw(st.sampled_from(ITEM_IDS))))
        types = tuple(draw(st.lists(TYPE_TOKENS, max_size=2)))
        if types:
            attributes.append(("itemtype", types))
        names = tuple(draw(st.lists(st.sampled_from(PROPERTY_NAMES), max_size=2)))
        if names or draw(st.booleans()):
            attributes.append(("itemprop", names))
        refs = tuple(draw(st.lists(st.sampled_from(ITEM_IDS), max_size=4)))
        if refs:
            attributes.append(("itemref", refs))
        children: list[Element | str] = list(
            draw(st.lists(microdata_property(), max_size=3))
        )
        items.append(Element(draw(st.sampled_from(CONTAINERS)), attributes, children))
    roots: list[Element | str] = []
    for index, item in enumerate(items):
        parent = draw(st.integers(-1, index - 1))
        (roots if parent < 0 else items[parent].children).append(item)
    # Plain elements carrying properties, for itemref to reach from outside.
    for holder in ("p0", "p1"):
        if draw(st.booleans()):
            roots.append(
                Element(
                    "div",
                    [("id", holder)],
                    list(draw(st.lists(microdata_property(), min_size=1, max_size=2))),
                )
            )
    return [root for root in roots if isinstance(root, Element)]


# -- RDFa ------------------------------------------------------------------------

VOCABS = ("https://schema.org/", "http://schema.org/", "", "http://example.org/v#")
PREFIXES = (
    ("ex: https://example.org/ns#",),
    ("dc: http://purl.org/dc/terms/", "schema: https://schema.org/"),
    ("ex: https://example.org/ns# broken",),
    ("EX: https://example.org/upper#",),
)
RDFA_TYPES = (
    "Product",
    "Offer",
    "Article",
    "Person",
    "schema:Product",
    "https://schema.org/Recipe",
    "ex:Widget",
    "foaf:Person",
    "mw:Transclusion",
    "og:thing",
    "Thing",
)
RDFA_PROPERTIES = (
    "name",
    "headline",
    "price",
    "offers",
    "author",
    "datePublished",
    "schema:name",
    "http://schema.org/description",
    "ex:size",
    "dc:title",
    "foaf:name",
    "og:title",
    "http://ogp.me/ns#title",
    "mw:x",
    "x:",
    ":",
)
RDFA_VALUE_ELEMENTS = (
    ("span", None),
    ("a", "href"),
    ("link", "href"),
    ("img", "src"),
    ("time", "datetime"),
    ("meta", "content"),
    ("span", "content"),
    ("span", "resource"),
)


@st.composite
def rdfa(draw: st.DrawFn, depth: int = 0) -> Element:
    """A subject: its context, its types, its properties, subjects inside it."""
    attributes: list[tuple[str, AttributeValue]] = []
    if draw(st.booleans()):
        attributes.append(("vocab", draw(st.sampled_from(VOCABS))))
    if draw(st.integers(0, 3)) == 0:
        attributes.append(("prefix", draw(st.sampled_from(PREFIXES))))
    attributes.append(
        ("typeof", tuple(draw(st.lists(st.sampled_from(RDFA_TYPES), max_size=2))))
    )
    if depth and draw(st.booleans()):
        attributes.append(("property", (draw(st.sampled_from(RDFA_PROPERTIES)),)))
    children: list[Element | str] = []
    for _ in range(draw(st.integers(0, 3))):
        if depth < 2 and draw(st.integers(0, 3)) == 0:
            children.append(draw(rdfa(depth + 1)))
            continue
        tag, attribute = draw(st.sampled_from(RDFA_VALUE_ELEMENTS))
        names = tuple(draw(st.lists(st.sampled_from(RDFA_PROPERTIES), max_size=2)))
        prop: list[tuple[str, AttributeValue]] = [("property", names)]
        if attribute is not None:
            value = draw(words if attribute in ("content", "datetime") else addresses)
            prop.append((attribute, value))
        children.append(Element(tag, prop, [] if tag in VOID else [draw(words)]))
    return Element(draw(st.sampled_from(CONTAINERS)), attributes, children)


# -- the head ------------------------------------------------------------------


@st.composite
def meta_tags(draw: st.DrawFn) -> Element:
    """A ``<meta>`` keyed by ``name``, ``property`` or both, in any case."""
    key = draw(st.sampled_from(META_KEYS).flatmap(recased))
    how = draw(st.sampled_from(["name", "property", "both", "other"]))
    attributes: list[tuple[str, AttributeValue]] = []
    if how in ("name", "both"):
        attributes.append(("name", key))
    if how in ("property", "both"):
        attributes.append(("property", key))
    if how == "other":
        attributes.append(("name", draw(st.sampled_from(META_KEYS))))
        attributes.append(("property", key))
    if draw(st.integers(0, 5)) > 0:
        attributes.append(("content", draw(st.one_of(words, addresses))))
    return Element("meta", attributes)


@st.composite
def head_extras(draw: st.DrawFn) -> list[Element]:
    """The rest of what a head carries that a summary rule reads."""
    extras: list[Element] = []
    for _ in range(draw(st.integers(0, 2))):
        extras.append(Element("title", [], [escape_text(draw(words))], raw=True))
    if draw(st.booleans()):
        rel = draw(
            st.sampled_from(
                [("canonical",), ("Canonical", "alternate"), ("stylesheet",)]
            )
        )
        extras.append(Element("link", [("rel", rel), ("href", draw(addresses))]))
    if draw(st.integers(0, 3)) == 0:
        extras.append(Element("base", [("href", draw(addresses))]))
    if draw(st.integers(0, 3)) == 0:
        extras.append(
            Element(
                "meta",
                [
                    (
                        "itemprop",
                        (
                            draw(
                                st.sampled_from(
                                    ["author", "datePublished", "dateModified"]
                                )
                            ),
                        ),
                    ),
                    ("content", draw(words)),
                ],
            )
        )
    return extras


# -- listings ------------------------------------------------------------------

CLASSES = (
    "card",
    "product",
    "title",
    "price",
    "meta",
    "sku",
    "tag",
    "css-1x2y3z",
    "sc-bdVaJa",
    "kPXmIq",
    "Card_title__a1B2c",
    "md:w-1/2",
    "col-md-6",
)


@st.composite
def listings(draw: st.DrawFn) -> Element:
    """Siblings of one shape, repeated, as a listing a page declares nothing about.

    The shape is drawn once and every member follows it, with the text drawn
    per member and a part sometimes left out, so induction has rows to find.
    """
    container = draw(st.sampled_from(["ul", "ol", "div", "section"]))
    member = (
        "li" if container in ("ul", "ol") else draw(st.sampled_from(["div", "article"]))
    )
    member_classes = tuple(draw(st.lists(st.sampled_from(CLASSES), max_size=2)))
    template = draw(
        st.lists(
            st.tuples(
                st.sampled_from(["span", "a", "img", "b", "p", "div"]),
                st.lists(st.sampled_from(CLASSES), max_size=2).map(tuple),
                st.booleans(),
            ),
            min_size=1,
            max_size=4,
        )
    )
    rows: list[Element | str] = []
    for _ in range(draw(st.integers(3, 6))):
        parts: list[Element | str] = []
        for tag, classes, optional in template:
            if optional and draw(st.booleans()):
                continue
            attributes: list[tuple[str, AttributeValue]] = []
            if classes:
                attributes.append(("class", classes))
            if tag == "a":
                attributes.append(("href", draw(addresses)))
            if tag == "img":
                attributes.append(("src", draw(addresses)))
                attributes.append(("alt", draw(words)))
            inner: list[Element | str] = [] if tag in VOID else [draw(words)]
            if tag == "div" and draw(st.booleans()):
                inner.append(Element("span", [("class", ("sku",))], [draw(words)]))
            parts.append(Element(tag, attributes, inner))
        member_attributes: list[tuple[str, AttributeValue]] = (
            [("class", member_classes)] if member_classes else []
        )
        rows.append(Element(member, member_attributes, parts))
    return Element(container, [], rows)


# -- whole pages -----------------------------------------------------------------


@dataclass
class Page:
    """A drawn page: its tree, and the address it is said to come from."""

    tree: Element
    url: str | None

    def html(self, style: Style | None = None, doctype: bool = True) -> str:
        return ("<!DOCTYPE html>" if doctype else "") + render(self.tree, style)


@st.composite
def pages(draw: st.DrawFn) -> Page:
    """A page carrying some of everything, in no fixed order.

    Each section is drawn or not, and the body's sections are shuffled, so the
    readers meet each other in every order: JSON-LD before and after the
    microdata it folds with, a listing beside declared records, OpenGraph that
    lands on whichever record comes first.
    """
    head: list[Element | str] = []
    head.extend(draw(st.lists(jsonld_blocks(), max_size=2)))
    head.extend(draw(st.lists(meta_tags(), max_size=6)))
    head.extend(draw(head_extras()))
    body: list[Element | str] = []
    body.extend(draw(st.lists(jsonld_blocks(), max_size=1)))
    if draw(st.booleans()):
        body.extend(draw(microdata()))
    if draw(st.integers(0, 2)) == 0:
        body.append(draw(rdfa()))
    if draw(st.booleans()):
        body.append(draw(listings()))
    if draw(st.booleans()):
        body.append(Element("p", [], [draw(words)]))
    body = draw(st.permutations(body)) if body else body
    html_attributes: list[tuple[str, AttributeValue]] = []
    if draw(st.booleans()):
        html_attributes.append(
            ("lang", draw(st.sampled_from(["en", "de-DE", " ", "EN-gb"])))
        )
    tree = Element(
        "html",
        html_attributes,
        [Element("head", [], head), Element("body", [], body)],
    )
    return Page(tree, draw(page_urls))


# -- breaking a page -----------------------------------------------------------

# Pieces that are each a way markup goes wrong, and a few that are each a way it
# declares something it cannot mean.
DEBRIS = (
    "<",
    ">",
    "</",
    "</div>",
    "</span></span>",
    "<div",
    '"',
    "'",
    "=",
    "&",
    "&#",
    "&#x110000;",
    "&bogus;",
    "<!--",
    "-->",
    "<![CDATA[",
    "]]>",
    "<?php echo 1 ?>",
    "<!DOCTYPE html>",
    "<?xml version='1.0' encoding='utf-8'?>",
    "\x00",
    "\ufeff",
    "\ud800",
    "<script>",
    "</script>",
    "<style>",
    "<html>",
    "</html>",
    "<body>",
    "<head>",
    "<table><tr><td>",
    "<svg><title>",
    "<p itemscope itemref='m0 m0 m1'>",
    "<span itemprop='name'>",
    "<div typeof='Product' property='offers'>",
    "<meta property='og:title' content='x'>",
)


@st.composite
def broken(draw: st.DrawFn, text: str) -> str:
    """``text`` with debris dropped into it and, sometimes, cut short."""
    edits = draw(
        st.lists(
            st.tuples(st.integers(0, len(text)), st.sampled_from(DEBRIS)), max_size=5
        )
    )
    for at, piece in sorted(edits, reverse=True):
        text = text[:at] + piece + text[at:]
    if draw(st.integers(0, 4)) == 0:
        text = text[: draw(st.integers(0, len(text)))]
    return text


@st.composite
def broken_pages(draw: st.DrawFn) -> tuple[str, str | None]:
    page = draw(pages())
    return draw(broken(page.html(draw(styles())))), page.url


# -- bytes ------------------------------------------------------------------------

# Every name Python's codec registry answers to. sniff_encoding asks that
# registry about whatever label a page declares, so the labels drawn are the
# registry's own, not just the ones a browser knows, plus the ones a browser
# knows that Python does not, and whatever text Hypothesis draws.
PYTHON_CODEC_NAMES = tuple(
    sorted(set(encodings.aliases.aliases) | set(encodings.aliases.aliases.values()))
)
BROWSER_LABELS = (
    "utf-8",
    "UTF8",
    "unicode-1-1-utf-8",
    "windows-1252",
    "iso-8859-1",
    "latin1",
    "us-ascii",
    "windows-1251",
    "koi8-r",
    "shift_jis",
    "euc-jp",
    "iso-2022-jp",
    "gb2312",
    "gbk",
    "gb18030",
    "big5",
    "euc-kr",
    "utf-16",
    "utf-16le",
    "x-user-defined",
    "utf-7",
    "iso-8859-9",
    "tis-620",
    "x-mac-cyrillic",
    "replacement",
)
charset_labels = st.one_of(
    st.sampled_from(BROWSER_LABELS),
    st.sampled_from(PYTHON_CODEC_NAMES),
    st.text(max_size=10),
).flatmap(recased)


def declaration(label: str, how: str) -> str:
    """One way a page declares its encoding."""
    return {
        "charset": f'<meta charset="{label}">',
        "bare": f"<meta charset={label}>",
        "http-equiv": (
            f'<meta http-equiv="Content-Type" content="text/html; charset={label}">'
        ),
        "http-equiv-quoted": (
            f"<META HTTP-EQUIV=content-type CONTENT='text/html;charset=\"{label}\"'>"
        ),
        "xml": f'<?xml version="1.0" encoding="{label}"?>',
    }[how]


declarations = st.sampled_from(
    ["charset", "bare", "http-equiv", "http-equiv-quoted", "xml"]
)


@st.composite
def encoded_pages(draw: st.DrawFn) -> tuple[bytes, str | None]:
    """A page as bytes: any encoding, declared truly, falsely or not at all."""
    page = draw(pages())
    text = page.html(draw(styles()))
    label = draw(charset_labels)
    how = draw(st.sampled_from(["none", "prefix", "head"]))
    if how == "prefix":
        text = declaration(label, draw(declarations)) + text
    elif how == "head":
        written = declaration(label, draw(declarations))
        text = re.sub(
            "(<head>)", lambda m: m.group(1) + written, text, count=1, flags=re.I
        )
    codec = draw(
        st.sampled_from(
            [
                "utf-8",
                "cp1252",
                "cp1251",
                "cp932",
                "gb18030",
                "utf-16-le",
                "utf-16-be",
                "koi8-r",
            ]
        )
    )
    data = text.encode(codec, errors="replace")
    bom = draw(
        st.sampled_from(
            [b"", b"", codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE]
        )
    )
    return bom + data, page.url


# -- pages built to multiply ---------------------------------------------------
#
# The strategies above draw pages the size real ones are, and a reader that
# copies a value it was handed once is invisible on a page that small. These
# draw the shapes that multiply -- many references to one node, many items
# naming one element, one element naming many properties, properties nested in
# properties, a long address every link is resolved against -- as random graphs
# with random sizes, up to tens of kilobytes. The sizes are drawn and the text
# is built by repetition, so a large page costs nothing to draw.

# Small or large, rarely in between: a multiplier shows when both sides of it
# are large, and a uniform draw makes both large together too seldom to find.
sizes = st.one_of(st.integers(0, 40), st.integers(1000, 4000))
counts = st.one_of(st.integers(0, 4), st.integers(100, 400))


def _filler(length: int, letter: str = "x") -> str:
    return letter * length


@st.composite
def jsonld_graphs(draw: st.DrawFn) -> Element:
    """Nodes that refer to each other, and referrers that name them many times.

    Each node holds a string, a key and a list of drawn sizes; each refers to a
    drawn multiset of the others, itself and ids nobody defines; and a drawn
    number of referrers each name a drawn target, so one node can be named from
    hundreds of places.
    """
    count = draw(st.integers(1, 6))
    targets = [f"#n{i}" for i in range(count)] + ["#nowhere"]
    graph: list[dict[str, Any]] = []
    for i in range(count):
        node: dict[str, Any] = {
            "@id": targets[i],
            "@type": draw(st.sampled_from(SCHEMA_TYPES)),
        }
        node["name"] = _filler(draw(sizes))
        if draw(st.booleans()):
            node[_filler(draw(sizes), "k") or "k"] = "v"
        node["items"] = [{"x": "1"}] * draw(counts)
        refs = draw(st.lists(st.sampled_from(targets), max_size=4))
        node["isRelatedTo"] = [
            {"@id": ref} for ref in refs for _ in range(draw(st.integers(1, 50)))
        ]
        graph.append(node)
    for _ in range(draw(st.integers(0, 4))):
        target = draw(st.sampled_from(targets))
        prop = draw(
            st.sampled_from(["author", "publisher", "brand", "image", "offers"])
        )
        graph.append(
            {
                "@type": draw(st.sampled_from(SCHEMA_TYPES)),
                prop: [{"@id": target}] * draw(counts),
            }
        )
    graph = draw(st.permutations(graph))
    return jsonld_script(json.dumps({"@graph": graph}))


@st.composite
def microdata_graphs(draw: st.DrawFn) -> list[Element]:
    """Items that ``itemref`` each other densely, and many items that name them.

    The dense core is the shape that was exponential; the referrers from
    outside are the shape a budget per top-level item does not see, since each
    referrer is its own top-level item with a budget of its own.
    """
    count = draw(st.integers(1, 7))
    ids = [f"g{i}" for i in range(count)]
    names = tuple(f"p{i}" for i in range(draw(st.integers(1, 40))))
    elements: list[Element] = [
        Element(
            "p",
            [("id", "big"), ("itemprop", names)],
            [_filler(draw(sizes))],
        )
    ]
    for i in range(count):
        refs = tuple(ref for ref in [*ids, "big"] if draw(st.booleans()))
        elements.append(
            Element(
                "div",
                [
                    ("id", ids[i]),
                    ("itemprop", ("r",)),
                    ("itemscope", None),
                    ("itemtype", (_filler(draw(st.integers(0, 200)), "T"),)),
                    ("itemref", refs),
                ],
                [
                    Element(
                        "b", [("itemprop", ("n",))], [_filler(draw(st.integers(1, 50)))]
                    )
                ],
            )
        )
    referrers = draw(counts)
    refs = tuple(ref for ref in [*ids, "big"] if draw(st.booleans())) or ("big",)
    elements.extend(
        Element("div", [("itemscope", None), ("itemref", refs)])
        for _ in range(referrers)
    )
    return elements


@st.composite
def nested_properties(draw: st.DrawFn) -> list[Element]:
    """Properties inside properties, each of whose values is all the text below.

    In microdata and in RDFa, under a long base address the addresses on the
    page are resolved against, with a vocabulary and prefix as long as drawn.
    """
    depth = draw(st.integers(1, 300))
    text = _filler(draw(sizes))
    names = tuple(f"q{i}" for i in range(draw(st.integers(1, 30))))

    def chain(attribute: str) -> Element:
        inner: Element | str = text
        for _ in range(depth):
            inner = Element("span", [(attribute, names)], [inner])
        assert isinstance(inner, Element)
        return inner

    links = draw(counts)
    microdata_item = Element(
        "div",
        [("itemscope", None)],
        [
            chain("itemprop"),
            *(
                Element("a", [("itemprop", ("u",)), ("href", "x")], ["x"])
                for _ in range(links)
            ),
        ],
    )
    rdfa_subject = Element(
        "div",
        [
            ("vocab", "http://v.example/" + _filler(draw(sizes), "v") + "#"),
            ("prefix", ("p:", "http://p.example/" + _filler(draw(sizes), "p") + "#")),
            ("typeof", ("Thing",)),
        ],
        [
            chain("property"),
            *(
                Element("a", [("property", ("u", "p:u")), ("href", "x")], ["x"])
                for _ in range(links)
            ),
            *(
                Element("span", [("property", ("p:a", "b"))], ["x"])
                for _ in range(draw(counts))
            ),
        ],
    )
    return [microdata_item, rdfa_subject]


@st.composite
def listing_bombs(draw: st.DrawFn) -> Element:
    """A listing whose rows are deep, and whose parts sit under long names.

    Induction names every part by the path down to it, and gives every part
    with text of its own the text of everything below it.
    """
    # Deep enough, at the top, to be past Python's own recursion limit.
    depth = draw(st.one_of(st.integers(1, 20), st.integers(1000, 1500)))
    label = _filler(draw(sizes), "c")
    width = draw(counts)

    def row() -> Element:
        inner: Element | str = "x"
        for _ in range(depth):
            inner = Element("b", [], ["x", inner])
        wide = Element(
            "div",
            [("class", (label,))] if label else [],
            [Element("i", [], ["y"]) for _ in range(width)],
        )
        return Element("li", [], [inner, wide])

    return Element("ul", [], [row() for _ in range(draw(st.integers(3, 4)))])


SHAPES = ("jsonld", "microdata", "nested", "listing")


@st.composite
def multiplying_pages(draw: st.DrawFn, shape: str | None = None) -> Page:
    """A drawn page with multiplying shapes dropped into its body.

    ``shape`` names the one to drop in; by default a few are drawn.
    """
    page = draw(pages())
    body = page.tree.children[1]
    assert isinstance(body, Element)
    shapes = (
        [shape]
        if shape
        else draw(
            st.lists(st.sampled_from(SHAPES), min_size=1, max_size=3, unique=True)
        )
    )
    if "jsonld" in shapes:
        body.children.append(draw(jsonld_graphs()))
    if "microdata" in shapes:
        body.children.extend(draw(microdata_graphs()))
    if "nested" in shapes:
        body.children.extend(draw(nested_properties()))
    if "listing" in shapes:
        body.children.append(draw(listing_bombs()))
    head = page.tree.children[0]
    assert isinstance(head, Element)
    if draw(st.booleans()):
        head.children.insert(
            0,
            Element(
                "base",
                [("href", "http://b.example/" + _filler(draw(sizes), "b") + "/")],
            ),
        )
    return page
