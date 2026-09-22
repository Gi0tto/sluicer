from pathlib import Path

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
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product"></div>'
    )

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

    assert found == [
        {"@type": "Product", "name": "Brake pad set"},
        {"@type": "Offer", "price": "41.99", "priceCurrency": "EUR"},
    ]


def test_a_property_wrapped_in_plain_markup_still_belongs_to_its_scope():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<div class="row"><span itemprop="sku">BP-2290</span></div>'
        "</div>"
    )

    assert read_microdata(doc) == [{"@type": "Product", "sku": "BP-2290"}]
