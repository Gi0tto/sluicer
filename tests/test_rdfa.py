import pytest

from sluicer.declared.rdfa import read_rdfa
from sluicer.document import load

PRODUCT = (
    "<html><body>"
    '<div vocab="https://schema.org/" typeof="Product">'
    '  <span property="name">Brake pad set</span>'
    '  <span property="sku">BP-1187</span>'
    '  <a property="url" href="/p/1">details</a>'
    '  <img property="image" src="/i/1.jpg" alt="a photo">'
    "</div></body></html>"
)


def test_it_reads_a_subject_and_its_properties():
    found = read_rdfa(load(PRODUCT))

    assert len(found) == 1
    assert found[0]["@type"] == "Product"
    assert found[0]["name"] == "Brake pad set"
    assert found[0]["sku"] == "BP-1187"


def test_an_address_comes_from_the_attribute_not_the_text():
    found = read_rdfa(load(PRODUCT))

    assert found[0]["url"] == "/p/1"
    assert found[0]["image"] == "/i/1.jpg"


def test_a_content_attribute_wins_over_the_text():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Offer">'
        '<span property="price" content="41.99">forty-one ninety-nine</span></div>'
    )

    assert read_rdfa(doc)[0]["price"] == "41.99"


def test_two_subjects_stay_two():
    doc = load(
        "<body>"
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">One</span></div>'
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">Two</span></div>'
        "</body>"
    )

    found = read_rdfa(doc)

    assert [item["name"] for item in found] == ["One", "Two"]


def test_a_property_belongs_to_its_nearest_subject():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">Outer</span>'
        '<div typeof="Offer"><span property="price">1.00</span></div>'
        "</div>"
    )

    found = read_rdfa(doc)

    outer = next(item for item in found if item["@type"] == "Product")
    inner = next(item for item in found if item["@type"] == "Offer")
    assert "price" not in outer
    assert inner["price"] == "1.00"


def test_an_empty_value_is_not_a_value():
    doc = load('<div typeof="Product"><span property="name">   </span></div>')

    assert read_rdfa(doc) == [{"@type": "Product"}]


def test_a_page_with_no_rdfa_returns_nothing():
    assert read_rdfa(load("<html><body><p>hi</p></body></html>")) == []


def test_a_schema_org_type_is_one_name_however_the_page_spelt_it():
    """Product, schema:Product and the full IRI are one term, not three.

    A type from another vocabulary keeps its IRI, so it is never mistaken for
    the schema.org type that happens to share its last word.
    """
    doc = load(
        '<div typeof="https://schema.org/Product"></div>'
        '<div typeof="schema:Product"></div>'
        '<div typeof="http://purl.org/goodrelations/v1#Offering"></div>'
    )

    assert [item["@type"] for item in read_rdfa(doc)] == [
        "Product",
        "Product",
        "http://purl.org/goodrelations/v1#Offering",
    ]


def test_a_curie_whose_prefix_nobody_declared_is_not_a_term():
    """MediaWiki writes typeof="mw:Transclusion" and friends on every page."""
    doc = load(
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">Pad</span>'
        '<span typeof="mw:Transclusion" property="mw:Thing">not a field</span>'
        "</div>"
    )

    assert read_rdfa(doc) == [{"@type": "Product", "name": "Pad"}]


def test_opengraph_tags_are_left_to_the_opengraph_reader():
    doc = load(
        '<html typeof="WebPage" vocab="https://schema.org/"><head>'
        '<meta property="og:title" content="A title">'
        '<meta property="article:published_time" content="2026-09-22">'
        '</head><body><span property="name">Page</span></body></html>'
    )

    assert read_rdfa(doc) == [{"@type": "WebPage", "name": "Page"}]


def test_a_property_is_named_through_its_prefix():
    doc = load(
        '<div prefix="gr: http://purl.org/goodrelations/v1#" typeof="Product">'
        '<span property="gr:name">Brake pad set</span>'
        '<span property="https://schema.org/sku">BP-1187</span>'
        "</div>"
    )

    assert read_rdfa(doc)[0] == {
        "@type": "Product",
        "http://purl.org/goodrelations/v1#name": "Brake pad set",
        "sku": "BP-1187",
    }


def test_several_types_are_all_kept():
    doc = load('<div typeof="Product Offer"><span property="sku">A</span></div>')

    assert read_rdfa(doc) == [{"@type": ["Product", "Offer"], "sku": "A"}]


def test_a_property_naming_two_fields_fills_both():
    doc = load('<div typeof="Product"><span property="name title">One</span></div>')

    assert read_rdfa(doc) == [{"@type": "Product", "name": "One", "title": "One"}]


def test_a_repeated_property_is_a_list_as_in_microdata():
    doc = load(
        '<div typeof="Product">'
        '<span property="name">First</span>'
        '<span property="name">Second</span>'
        "</div>"
    )

    assert read_rdfa(doc) == [{"@type": "Product", "name": ["First", "Second"]}]


def test_a_resource_is_a_value_when_the_element_carries_no_address():
    doc = load(
        '<div typeof="Product">'
        '<span property="isbn" resource="urn:isbn:0451450523">ISBN</span>'
        "</div>"
    )

    assert read_rdfa(doc)[0]["isbn"] == "urn:isbn:0451450523"


def test_a_time_declares_its_datetime_not_the_words_around_it():
    doc = load(
        '<div typeof="Article">'
        '<time property="datePublished" datetime="2026-09-22">yesterday</time>'
        "</div>"
    )

    assert read_rdfa(doc)[0]["datePublished"] == "2026-09-22"


def test_a_link_with_no_address_falls_back_to_its_text():
    doc = load('<div typeof="Product"><a property="name">Brake pad set</a></div>')

    assert read_rdfa(doc)[0]["name"] == "Brake pad set"


def test_a_subject_whose_type_is_unusable_still_carries_its_fields():
    doc = load('<div typeof=" "><span property="name">Nameless</span></div>')

    assert read_rdfa(doc) == [{"name": "Nameless"}]


def test_a_property_with_no_name_declares_nothing():
    doc = load(
        '<div typeof="Product">'
        '<span property="">Brake pad set</span>'
        '<span property="sku">BP-1187</span>'
        "</div>"
    )

    assert read_rdfa(doc) == [{"@type": "Product", "sku": "BP-1187"}]


def test_a_nested_subject_is_the_value_of_its_property():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">Brake pad set</span>'
        '<div property="offers" typeof="Offer">'
        '<span property="price">41.99</span>'
        "</div></div>"
    )

    assert read_rdfa(doc) == [
        {
            "@type": "Product",
            "name": "Brake pad set",
            "offers": {"@type": "Offer", "price": "41.99"},
        },
    ]


def test_a_subject_declaring_nothing_at_all_is_not_a_record():
    doc = load('<div typeof=""><span>Brake pad set</span></div>')

    assert read_rdfa(doc) == []


def test_it_reads_rdfa_from_a_page_that_also_carries_microdata():
    """The shape of a real page: two vocabularies over the same book."""
    doc = load(
        '<html><head><meta property="og:title" content="The Wind in the Willows">'
        "</head><body>"
        '<div itemscope itemtype="https://schema.org/Book">'
        '<span itemprop="name">The Wind in the Willows</span>'
        "</div>"
        '<div vocab="https://schema.org/" typeof="Book" resource="/books/OL1M">'
        '<h1 property="name">The Wind in the Willows</h1>'
        '<a property="author" href="/authors/OL2A">Kenneth Grahame</a>'
        '<span property="isbn13" content="9780451450531">0451450531</span>'
        "</div></body></html>"
    )

    assert read_rdfa(doc) == [
        {
            "@type": "Book",
            "name": "The Wind in the Willows",
            "author": "/authors/OL2A",
            "isbn13": "9780451450531",
        }
    ]


def test_a_property_deeper_in_the_markup_still_finds_its_subject():
    """Real pages wrap: the subject is rarely the property's own parent."""
    doc = load(
        '<div typeof="Product"><ul><li>'
        '<span property="name">Brake pad set</span>'
        "</li></ul></div>"
    )

    assert read_rdfa(doc) == [{"@type": "Product", "name": "Brake pad set"}]


def test_an_rdfa_address_is_resolved_against_the_page():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Product">'
        '<a property="url" href="/p/1">details</a>'
        '<span property="sameAs" resource="/wiki/Pad">Pad</span>'
        "</div>",
        url="https://shop.example/c/",
    )

    item = read_rdfa(doc)[0]

    assert item["url"] == "https://shop.example/p/1"
    assert item["sameAs"] == "https://shop.example/wiki/Pad"


_LONG = "x" * 4000
_SUBJECT = '<div vocab="https://schema.org/" typeof="Thing">'
_COPIED_MANY_TIMES = {
    "four hundred properties nested in each other": (
        _SUBJECT + '<span property="a">' * 400 + _LONG + "</span>" * 400 + "</div>"
    ),
    "one element naming four hundred properties": (
        _SUBJECT
        + '<p property="'
        + " ".join(f"p{i}" for i in range(400))
        + f'">{_LONG}</p></div>'
    ),
    "four hundred terms under a long vocab": (
        f'<div vocab="http://v.example/{_LONG}#" typeof="Thing">'
        + "".join(f'<span property="a{i}">x</span>' for i in range(400))
        + "</div>"
    ),
    "four hundred terms under a long prefix": (
        f'<div prefix="p: http://p.example/{_LONG}#" typeof="Thing">'
        + "".join(f'<span property="p:a{i}">x</span>' for i in range(400))
        + "</div>"
    ),
    "four hundred links resolved against a long base": (
        f'<base href="http://h.example/{_LONG}/">'
        + _SUBJECT
        + '<a property="u" href="x">x</a>' * 400
        + "</div>"
    ),
}


@pytest.mark.parametrize("html", _COPIED_MANY_TIMES.values(), ids=_COPIED_MANY_TIMES)
def test_a_value_copied_many_times_costs_at_most_ten_times_the_page(html):
    """Found by the property that what a page yields is bounded by its size.

    Each of these made 1.6 MB of JSON from a page of 6 to 17 KB, between 96
    and 269 times the page, and the ratio grows with the page.
    """
    import json

    found = read_rdfa(load(html))

    assert found
    assert len(json.dumps(found)) <= 11 * len(html)


def test_prefixes_and_vocab_are_the_nearest_declared():
    """The nearest ``vocab`` decides and an empty one means none; the nearest
    ``prefix`` naming a prefix decides, the first mapping of it in one
    attribute, a name matched ignoring case; RDFa's initial context last."""
    doc = load(
        '<div vocab="http://outer.example/" prefix="a: http://a1.example/'
        ' A: http://a2.example/ b: http://b1.example/" typeof="Thing">'
        '<span property="x a:x b:x schema:x">1</span>'
        '<div vocab="" prefix="b: http://b2.example/ b: http://b3.example/">'
        '<span property="y a:y b:y">2</span>'
        '<p><span property="z B:z">3</span></p></div></div>'
    )

    assert read_rdfa(doc) == [
        {
            "@type": "http://outer.example/Thing",
            "http://outer.example/x": "1",
            "http://a1.example/x": "1",
            "http://b1.example/x": "1",
            "x": "1",
            "y": "2",
            "http://a1.example/y": "2",
            "http://b2.example/y": "2",
            "z": "3",
            "http://b2.example/z": "3",
        }
    ]


def _prefixed(n: int) -> str:
    """``n`` prefixes declared once, and ``n`` properties under them."""
    prefix = " ".join(f"p{i}: http://e.example/{i}/" for i in range(n))
    props = '<span property="name p1:x">v</span>' * n
    return (
        f'<html><body><div prefix="{prefix}" vocab="https://schema.org/"'
        f' typeof="Thing">{props}</div></body></html>'
    )


def test_prefixes_are_read_once_not_once_for_each_property():
    """Found by security review: every property read every prefix of every
    element around it again: 478 KB of a page took 26 seconds."""
    import sys
    import time

    def work(n: int) -> int:
        doc = load(_prefixed(n))
        count = 0

        def tick(frame, event, arg):
            nonlocal count
            if event in ("call", "c_call"):
                count += 1

        sys.setprofile(tick)
        try:
            read_rdfa(doc)
        finally:
            sys.setprofile(None)
        return count

    work(10)
    assert work(1_000) / work(500) < 2.5

    doc = load(_prefixed(8_000))
    started = time.perf_counter()
    found = read_rdfa(doc)
    assert time.perf_counter() - started < 1.5
    assert found[0]["http://e.example/1/x"] == ["v"] * 8_000
