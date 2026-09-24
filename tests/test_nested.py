"""Nested values reach the record whole.

Measured on 2026-09-22 across live pages, the fields that matter most are the
ones a page declares as objects or lists: the author of a news article,
every ingredient and step of a recipe, the price of a product.
Carrying scalars only dropped all of them. A nested value now arrives as the
JSON it was declared as, with every leaf as text, ``@type`` kept, and a
reference to another node on the same page replaced by that node.
"""

import json

from sluicer import extract
from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.microdata import read_microdata
from sluicer.document import load


def _page(*blocks: object) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    return f"<html><head>{scripts}</head><body></body></html>"


def test_a_nested_author_arrives_with_its_type():
    html = _page(
        {
            "@type": "NewsArticle",
            "headline": "A headline",
            "author": {"@type": "Person", "name": "Mara Quill"},
        }
    )

    field = extract(html).records[0].fields["author"]

    assert field.value == {"@type": "Person", "name": "Mara Quill"}
    assert field.source == "jsonld"


def test_a_list_arrives_as_a_list_in_the_order_declared():
    html = _page(
        {
            "@type": "Recipe",
            "name": "Cookies",
            "recipeIngredient": ["1 cup butter", "2 eggs", " ", "3 cups flour"],
        }
    )

    field = extract(html).records[0].fields["recipeIngredient"]

    assert field.value == ["1 cup butter", "2 eggs", "3 cups flour"]


def test_every_leaf_is_text_spelt_the_way_the_page_wrote_it():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Pad","offers":{"@type":"Offer",'
        '"price":41.90,"inStock":true,"quantity":3,"note":null}}'
        "</script>"
    )

    offers = extract(html).records[0].fields["offers"].value

    assert offers == {
        "@type": "Offer",
        "price": "41.90",
        "inStock": "true",
        "quantity": "3",
    }


def test_a_top_level_number_keeps_its_spelling_too():
    html = '<script type="application/ld+json">{"@type":"Offer","price":12.50}</script>'

    assert extract(html).records[0].fields["price"].value == "12.50"


def test_a_reference_to_another_node_is_replaced_by_that_node():
    """Yoast writes every page this way: the article names its author by @id."""
    html = _page(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "Article",
                    "@id": "https://example.com/p#article",
                    "headline": "Structured data",
                    "author": {"@id": "https://example.com/#/person/1"},
                },
                {
                    "@type": "Person",
                    "@id": "https://example.com/#/person/1",
                    "name": "Theo Marsh",
                },
            ],
        }
    )

    author = extract(html).records[0].fields["author"].value

    assert author == {"@type": "Person", "name": "Theo Marsh"}


def test_a_reference_nothing_on_the_page_defines_is_kept_as_a_reference():
    html = _page(
        {"@type": "Article", "headline": "H", "author": {"@id": "https://x/#me"}}
    )

    assert extract(html).records[0].fields["author"].value == {"@id": "https://x/#me"}


def test_a_cycle_of_references_ends_instead_of_recursing_forever():
    html = _page(
        {
            "@graph": [
                {
                    "@type": "WebPage",
                    "@id": "#page",
                    "name": "Page",
                    "isPartOf": {"@id": "#site"},
                },
                {
                    "@type": "WebSite",
                    "@id": "#site",
                    "name": "Site",
                    "hasPart": {"@id": "#page"},
                },
            ]
        }
    )

    page = extract(html).records[0].fields

    assert page["isPartOf"].value == {
        "@type": "WebSite",
        "name": "Site",
        "hasPart": {"@id": "#page"},
    }


def test_a_reference_across_two_blocks_is_resolved_too():
    html = _page(
        {"@type": "Product", "name": "Pad", "brand": {"@id": "#brand"}},
        {"@type": "Brand", "@id": "#brand", "name": "Textar"},
    )

    brand = extract(html).records[0].fields["brand"].value

    assert brand == {"@type": "Brand", "name": "Textar"}


def test_a_json_ld_value_object_is_its_value():
    html = _page(
        {"@type": "Book", "name": {"@value": "Der Process", "@language": "de"}}
    )

    assert extract(html).records[0].fields["name"].value == "Der Process"


def test_an_object_that_says_nothing_is_not_a_value():
    html = _page(
        {"@type": "Product", "name": "Pad", "offers": {"@type": "Offer", "x": " "}}
    )

    assert "offers" not in extract(html).records[0].fields


def test_a_record_that_carries_no_field_is_not_reported():
    html = _page({"@type": "WebPage"}, {"@type": "Product", "name": "Pad"})

    assert [record.type for record in extract(html).records] == ["Product"]


def test_the_reader_resolves_references_in_its_own_output():
    doc = load(
        _page(
            {"@type": "Product", "name": "Pad", "brand": {"@id": "#b"}},
            {"@type": "Brand", "@id": "#b", "name": "Textar"},
        )
    )

    product = read_jsonld(doc)[0]

    assert product["brand"]["name"] == "Textar"


def test_a_nested_microdata_item_is_a_value_of_its_parent():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<h1 itemprop="name">Brake pad set</h1>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">41.99</span>'
        '<span itemprop="priceCurrency">EUR</span>'
        "</div>"
        "</div>"
    )

    assert read_microdata(doc) == [
        {
            "@type": "Product",
            "name": "Brake pad set",
            "offers": {"@type": "Offer", "price": "41.99", "priceCurrency": "EUR"},
        }
    ]


def test_a_repeated_microdata_property_is_a_list():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Recipe">'
        '<span itemprop="name">Cookies</span>'
        '<li itemprop="recipeIngredient">1 cup butter</li>'
        '<li itemprop="recipeIngredient">2 eggs</li>'
        "</div>"
    )

    assert read_microdata(doc)[0]["recipeIngredient"] == ["1 cup butter", "2 eggs"]


def test_one_itemprop_can_name_two_properties():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name alternateName">Pad</span>'
        "</div>"
    )

    item = read_microdata(doc)[0]

    assert item["name"] == "Pad"
    assert item["alternateName"] == "Pad"


def test_the_json_output_carries_the_nested_value(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "page.html"
    page.write_text(
        _page(
            {
                "@type": "Product",
                "name": "Pad",
                "offers": {"@type": "Offer", "price": "41.99"},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["extract", str(page)])

    payload = json.loads(result.stdout)
    offers = payload["records"][0]["fields"]["offers"]
    assert offers == {
        "value": {"@type": "Offer", "price": "41.99"},
        "source": "jsonld",
        "where": "/html/head/script[1]#/offers",
    }


def test_a_reference_inside_a_resolved_reference_stays_a_reference():
    """One hop, so a dense graph is not re-expanded under every record."""
    html = _page(
        {
            "@graph": [
                {"@type": "Article", "headline": "H", "publisher": {"@id": "#org"}},
                {
                    "@type": "Organization",
                    "@id": "#org",
                    "name": "Yoast",
                    "logo": {"@id": "#logo"},
                },
                {"@type": "ImageObject", "@id": "#logo", "url": "https://x/l.png"},
            ]
        }
    )

    publisher = extract(html).records[0].fields["publisher"].value

    assert publisher == {
        "@type": "Organization",
        "name": "Yoast",
        "logo": {"@id": "#logo"},
    }
