"""Every value says where on the page it was declared, and never somewhere else.

A place is an XPath to the element that declared the value -- for JSON-LD the
``<script>`` block's, with a JSON pointer (RFC 6901) to the value after ``#``.
A path cannot be trusted to find a value, so the place travels with it: a
reference is replaced by the node it names, declared elsewhere, and a blank
item dropped from a list shifts every index after it.
"""

from __future__ import annotations

import json

import sluicer
from sluicer.declared.located import Located, Places, paid, place, pointer, xpath_of
from sluicer.document import load


def _ld(*blocks: object, body: str = "") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    return f"<html><head>{scripts}</head><body>{body}</body></html>"


# -- JSON-LD -----------------------------------------------------------------------


def test_a_jsonld_value_is_placed_by_its_block_and_a_pointer_into_it():
    page = _ld(
        {"@type": "WebSite", "name": "Shop"},
        {
            "@graph": [
                {"@type": "Organization", "name": "Pads Ltd"},
                {"@type": "Product", "name": "Pads"},
            ]
        },
    )
    [site, organisation, product] = sluicer.extract(page).records
    assert site.where == "/html/head/script[1]#"
    assert organisation.where == "/html/head/script[2]#/@graph/0"
    assert product.fields["name"].where == "/html/head/script[2]#/@graph/1/name"


def test_a_top_level_array_is_pointed_into_by_index():
    page = _ld([{"@type": "Thing", "name": "a"}, {"@type": "Product", "name": "b"}])
    assert sluicer.extract(page).records[1].where == "/html/head/script[1]#/1"


def test_a_value_a_reference_fetched_is_placed_at_its_definition():
    # Yoast's graph: the article names its author by reference, and the person
    # is defined in another block.
    page = _ld(
        {"@type": "Article", "headline": "Pads", "author": {"@id": "#p"}},
        {"@graph": [{"@type": "Person", "@id": "#p", "name": "Ada"}]},
    )
    result = sluicer.extract(page)
    author = result.summary["author"]
    assert author.value == "Ada"
    assert author.where == "/html/head/script[2]#/@graph/0"
    [article] = [r for r in result.records if r.type == "Article"]
    assert article.fields["author"].where == "/html/head/script[2]#/@graph/0"


def test_a_definition_nested_inside_another_node_is_pointed_to_there():
    page = _ld(
        {
            "@graph": [
                {"@type": "Product", "name": "Pads", "offers": {"@id": "#o"}},
                {
                    "@type": "Organization",
                    "makesOffer": {"@id": "#o", "@type": "Offer", "price": "41.90"},
                },
            ]
        }
    )
    price = sluicer.extract(page).summary["price"]
    assert price.key == "Product.offers.price"
    assert price.where == "/html/head/script[1]#/@graph/1/makesOffer/price"


def test_a_price_is_pointed_to_inside_the_offer_it_was_read_from():
    offers = [
        {"@type": "Offer", "availability": "https://schema.org/InStock"},
        {
            "@type": "Offer",
            "priceSpecification": [
                {
                    "@type": "UnitPriceSpecification",
                    "price": "41.90",
                    "priceCurrency": "EUR",
                }
            ],
        },
    ]
    summary = sluicer.extract(
        _ld({"@type": "Product", "name": "Pads", "offers": offers})
    ).summary
    assert summary["price"].key == "Product.offers[1].priceSpecification[0].price"
    assert summary["price"].where == (
        "/html/head/script[1]#/offers/1/priceSpecification/0/price"
    )
    assert summary["currency"].where == (
        "/html/head/script[1]#/offers/1/priceSpecification/0/priceCurrency"
    )


def test_a_blank_item_dropped_from_a_list_does_not_shift_a_place():
    page = _ld(
        {
            "@type": "Product",
            "name": "Pads",
            "offers": ["", {"@type": "Offer", "price": "3"}],
        }
    )
    price = sluicer.extract(page).summary["price"]
    # The key is the record's path, which lost the blank; the place is the page's.
    assert price.key == "Product.offers[0].price"
    assert price.where == "/html/head/script[1]#/offers/1/price"


def test_a_list_of_text_is_not_counted_into():
    record = Located({"image": ["a.jpg", "b.jpg"]}, "/html/head/script[1]#")
    # Its items carry no place of their own, so the list's is the finest known.
    assert place(record, None, ("image", 1)) == "/html/head/script[1]#/image"
    # And a step to nothing goes no further than what is there.
    assert place(record, None, ("offers", "price")) == "/html/head/script[1]#"
    assert place("text", "/html/p[1]", ("name",)) == "/html/p[1]"


def test_a_key_with_a_slash_or_a_tilde_is_escaped_as_rfc_6901_says():
    assert pointer("a/b~c", 0) == "/a~1b~0c/0"
    field = sluicer.extract(_ld({"@type": "Thing", "a/b~c": "x"})).records[0]
    assert field.fields["a/b~c"].where == "/html/head/script[1]#/a~1b~0c"


# -- microdata and RDFa -------------------------------------------------------------


MICRODATA = """<html><head></head><body>
<div itemscope itemtype="https://schema.org/Product" itemref="extra">
  <h1 itemprop="name">Pads</h1>
  <span itemprop="color">red</span><span itemprop="color">blue</span>
  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <b itemprop="price">41.90</b><i itemprop="priceCurrency">EUR</i>
  </div>
</div>
<p id="extra" itemprop="sku">BP-1</p>
</body></html>"""


def test_a_microdata_property_is_placed_at_its_element():
    [product] = sluicer.extract(MICRODATA).records
    assert product.where == "/html/body/div[1]"
    assert product.fields["name"].where == "/html/body/div[1]/h1[1]"
    # itemref brings a property from outside the item, and its place with it.
    assert product.fields["sku"].where == "/html/body/p[1]"
    assert product.fields["offers"].where == "/html/body/div[1]/div[1]"


def test_a_property_declared_twice_is_placed_at_its_item():
    [product] = sluicer.extract(MICRODATA).records
    assert product.fields["color"].value == ["red", "blue"]
    assert product.fields["color"].where == "/html/body/div[1]"


def test_a_value_inside_a_nested_item_is_placed_at_its_own_element():
    summary = sluicer.extract(MICRODATA).summary
    assert summary["price"].where == "/html/body/div[1]/div[1]/b[1]"
    assert summary["currency"].where == "/html/body/div[1]/div[1]/i[1]"


def test_an_rdfa_property_is_placed_at_its_element():
    page = (
        '<html><body><div vocab="https://schema.org/" typeof="Event">'
        '<span property="name">Fair</span><p><time property="startDate">2026</time>'
        "</p></div></body></html>"
    )
    [event] = sluicer.extract(page).records
    assert event.where == "/html/body/div[1]"
    assert event.fields["startDate"].where == "/html/body/div[1]/p[1]/time[1]"


# -- the page's own tags ----------------------------------------------------------


def test_an_answer_from_a_tag_is_placed_at_the_tag_and_a_vocabulary_by_its_key():
    page = """<html lang="en"><head><title>Pads</title>
    <meta name="description" content="Pads for cars">
    <meta name="citation_author" content="Ada">
    <meta property="og:site_name" content="Shop">
    </head><body></body></html>"""
    summary = sluicer.extract(page).summary
    assert summary["title"].where == "/html/head/title[1]"
    assert summary["language"].where == "/html"
    assert summary["author"].where == "/html/head/meta[2]"
    # The meta names' readers return values only; the key names the tag.
    assert summary["site_name"].where is None
    assert summary["description"].where is None
    two = page.replace(
        '<meta name="citation_author" content="Ada">',
        '<meta name="citation_author" content="Ada">'
        '<meta name="citation_author" content="Bo">',
    )
    joined = sluicer.extract(two).summary["author"]
    assert joined.value == "Ada, Bo"
    assert joined.where is None, "joined from two tags, it has no one element"


def test_a_later_sibling_never_changes_an_earlier_place():
    alone = load("<html><head><meta name=a content=1></head><body></body></html>")
    two = load(
        "<html><head><meta name=a content=1><meta name=a content=2></head>"
        "<body></body></html>"
    )
    [first] = alone.tree.xpath("//meta")
    [second, _] = two.tree.xpath("//meta")
    assert xpath_of(first) == xpath_of(second) == "/html/head/meta[1]"
    assert xpath_of(alone.tree.xpath("//body")[0]) == "/html/body"


def test_an_element_whose_name_xpath_cannot_read_is_found_all_the_same():
    """Found by the fuzz profile: a browser's parser makes an element of
    ``<h&#tml>``, and written as a step its name was a broken literal."""
    page = load(
        "<html><body><h&#tml><i>1</i></h&#tml><a[1]>x</a[1]><!-- c -->"
        "<x'y>q</x'y><fb:like>k</fb:like><p>1</p></body></html>"
    )
    elements = [e for e in page.tree.iter() if isinstance(e.tag, str)]
    for element in elements:
        where = xpath_of(element)
        assert "#" not in where, "the first # in a place starts its pointer"
        assert page.tree.xpath(where) == [element], where
    assert xpath_of(elements[-1]) == "/html/body/p[1]"


class _Unwritten:
    """An element lxml cannot write a path for, which no parser makes: what
    ``xpath_of`` falls back on stays right without lxml's help."""

    def __init__(self, tag, parent=None, before=()):
        self.tag, self.parent, self.before = tag, parent, list(before)

    def iterancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def getroottree(self):
        return self

    def getpath(self, element):
        return "/unwritten"

    def getparent(self):
        return self.parent

    def itersiblings(self, preceding=False):
        return iter(reversed(self.before))

    def index(self, child):
        return len(child.before)


def test_a_path_lxml_cannot_write_is_counted_and_a_stray_root_is_the_root():
    root = _Unwritten("h#tml")
    sibling = _Unwritten("p", root)
    element = _Unwritten("p", root, before=[_Unwritten("i", root), sibling])
    assert xpath_of(element) == "/*/p[2]"
    odd = _Unwritten("x#y", root, before=[sibling])
    assert xpath_of(odd) == "/*/node()[not(self::text())][2]"


# -- what the places cost ------------------------------------------------------


def test_a_place_is_paid_for_and_one_too_long_spends_the_rest():
    places = Places(10)
    assert places.pay("/html/a") == "/html/a"
    assert places.pay(lambda: "/html/body") is None
    assert places.left == 0
    assert places.pay("/x") is None, "nothing after a refusal is given either"
    assert paid(None, lambda: "/html/body") == "/html/body", "no budget is no limit"
    asked = []
    assert Places(0).pay(lambda: asked.append(1) or "/x") is None
    assert asked == [], "nothing is spelt once nothing is left"


def test_a_page_nested_deep_answers_with_places_no_longer_than_itself():
    props = "".join(f'<i itemprop="p{n}">v</i>' for n in range(2_000))
    page = (
        "<html><head></head><body>"
        + "<div>" * 200
        + '<div itemscope itemtype="https://schema.org/Thing">'
        + f'<b itemprop="name">N</b>{props}</div>'
        + "</div>" * 200
        + "</body></html>"
    )
    result = sluicer.extract(page)
    [thing] = result.records
    places = [f.where for f in thing.fields.values()]
    spent = sum(len(w) for w in places if w) + len(thing.where or "")
    assert spent <= max(10_000, 2 * len(page))
    assert places[0] is not None and places[-1] is None, "document order decides"
    # The summary pays from its own budget, so a long record cannot starve it.
    assert result.summary["title"].where == thing.fields["name"].where


def test_a_fragment_s_places_are_in_the_page_a_browser_would_build():
    """lxml.html.fromstring renames a fragment's <body> to a <div> or <span>.

    A page with no head and no <html> or doctype at its start -- a fragment, or
    a saved page that opens with a comment -- was read from that renamed body,
    and every XPath went through a div the page never had: /html/div[1]/div[1]
    for what a browser, and lxml's own document parser, put at
    /html/body/div[1].
    """
    import lxml.html

    from sluicer import extract

    product = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Pad</span></div>'
    )
    for html in (
        product + "<p>more</p>",
        "<!-- saved --><p>x</p>" + product,
        "text <b>bold</b> " + product,
    ):
        record = extract(html).records[0]
        tree = lxml.html.document_fromstring(html)

        assert record.where == "/html/body/div[1]", html
        assert tree.xpath(record.where)[0].get("itemtype"), html
        assert tree.xpath(record.fields["name"].where)[0].text == "Pad", html
