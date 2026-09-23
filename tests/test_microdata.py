from pathlib import Path

import pytest

from sluicer.declared.microdata import read_microdata
from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_itemprops_of_one_itemscope():
    doc = load((FIXTURES / "product_microdata.html").read_text())

    found = read_microdata(doc)

    assert len(found) == 1
    assert found[0]["@type"] == "Product"
    assert found[0]["name"] == "Oil filter"
    assert found[0]["sku"] == "BP-2290"


def test_content_attribute_wins_over_text():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="19.50">'
        "</div>"
    )

    assert read_microdata(doc)[0]["price"] == "19.50"


def test_itemscope_with_only_itemtype_is_kept():
    doc = load('<div itemscope itemtype="https://schema.org/Product"></div>')

    found = read_microdata(doc)

    assert len(found) == 1
    assert found[0] == {"@type": "Product"}


def test_an_empty_itemprop_is_not_a_value():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name"> </span>'
        '<meta itemprop="sku" content="">'
        "</div>"
    )

    assert read_microdata(doc) == [{"@type": "Product"}]


def test_a_nested_offer_does_not_leak_into_the_product():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<h1 itemprop="name">Brake pad set</h1>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">41.99</span>'
        '<span itemprop="priceCurrency">EUR</span>'
        "</div>"
        "</div>"
    )

    found = read_microdata(doc)

    # The offer's price is the offer's, inside the product's ``offers``, and
    # never a ``price`` of the product itself.
    assert found == [
        {
            "@type": "Product",
            "name": "Brake pad set",
            "offers": {"@type": "Offer", "price": "41.99", "priceCurrency": "EUR"},
        },
    ]


def test_a_property_wrapped_in_plain_markup_still_belongs_to_its_scope():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<div class="row"><span itemprop="sku">BP-2290</span></div>'
        "</div>"
    )

    assert read_microdata(doc) == [{"@type": "Product", "sku": "BP-2290"}]


def test_a_property_after_thousands_of_plain_elements_is_still_found():
    """GitHub's repository page: the properties sit deep in a large scope.

    lxml builds a Python object per element on demand and frees it after, so
    ``id()`` of one element is reused by the next; remembering elements by
    ``id()`` forgot properties on exactly the pages big enough to matter.
    """
    filler = "<div><span>x</span><span>y</span></div>" * 3000
    doc = load(
        '<div itemscope itemtype="http://schema.org/SoftwareSourceCode">'
        f"{filler}"
        '<span itemprop="author"><strong itemprop="name">adbar</strong></span>'
        '<article itemprop="text">README</article>'
        "</div>"
    )

    item = read_microdata(doc)[0]

    assert item["name"] == "adbar"
    assert item["text"] == "README"


def test_an_address_is_resolved_against_the_page_the_way_the_standard_says():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<a itemprop="url" href="/p/1">details</a>'
        '<img itemprop="image" src="img/1.jpg">'
        '<span itemprop="name">/not/a/url</span>'
        "</div>",
        url="https://shop.example/c/brakes",
    )

    item = read_microdata(doc)[0]

    assert item["url"] == "https://shop.example/p/1"
    assert item["image"] == "https://shop.example/c/img/1.jpg"
    assert item["name"] == "/not/a/url"


def test_without_a_page_address_an_address_stays_as_written():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<a itemprop="url" href="/p/1">details</a></div>'
    )

    assert read_microdata(doc)[0]["url"] == "/p/1"


_LONG = "x" * 4000
_COPIED_MANY_TIMES = {
    "one element, named by four hundred items with itemref": (
        f'<p id="big" itemprop="d">{_LONG}</p>'
        + '<div itemscope itemref="big"></div>' * 400
    ),
    "one element naming four hundred properties": (
        '<div itemscope><p itemprop="'
        + " ".join(f"p{i}" for i in range(400))
        + f'">{_LONG}</p></div>'
    ),
    "four hundred itemprops nested in each other": (
        "<div itemscope>"
        + '<span itemprop="a">' * 400
        + _LONG
        + "</span>" * 400
        + "</div>"
    ),
    "four hundred links resolved against a long base": (
        f'<base href="http://h.example/{_LONG}/"><div itemscope>'
        + '<a itemprop="u" href="x">x</a>' * 400
        + "</div>"
    ),
}


@pytest.mark.parametrize("html", _COPIED_MANY_TIMES.values(), ids=_COPIED_MANY_TIMES)
def test_a_value_copied_many_times_costs_at_most_ten_times_the_page(html):
    """Found by the property that what a page yields is bounded by its size.

    Each of these made 1.6 MB of JSON from a page of 6 to 18 KB, between 89
    and 271 times the page, and the ratio grows with the page. The budget of
    256 items per top-level item bounded expansions, not what they copied, and
    each referrer here is a top-level item with a budget of its own.
    """
    import json

    found = read_microdata(load(html))

    assert found
    assert len(json.dumps(found)) <= 11 * len(html)
