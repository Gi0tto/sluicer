"""Microdata in extruct's shape, and the text extruct lays out for a property.

As in ``test_compat_extruct``: every expected answer is extruct 0.18.0's own
for the same page, except where a test names a documented difference.
"""

from __future__ import annotations

import lxml.html
import pytest

from sluicer.compat.extruct.page import Budget
from sluicer.compat.extruct.text import literal, readable
from sluicer.compat.extruct.w3cmicrodata import MicrodataExtractor


def read(html: str, **options: object) -> list[dict[str, object]]:
    base_url = options.pop("base_url", None)
    return MicrodataExtractor(**options).extract(html, base_url=base_url)  # type: ignore[arg-type]


def test_every_kind_of_value_is_read_as_extruct_reads_it():
    html = (
        '<div itemscope itemtype="https://schema.org/Product" itemid=" urn:sku:1 ">'
        '<meta itemprop="sku" content=" A1 "><meta itemprop="gtin" content="">'
        '<img itemprop="image" src=" /i.jpg "><a itemprop="url" href="/p">x</a>'
        '<object itemprop="o" data="d.bin"></object>'
        '<data itemprop="v" value=" 3 ">three</data><meter itemprop="m" value="0.5">'
        '</meter><time itemprop="t" datetime="2020-01-02">Jan</time>'
        '<span itemprop="c" content="cc">shown</span>'
        '<div itemprop="d">A<p>B</p>C <span>D</span><span>E</span>, F'
        "<script>x()</script>G</div>"
        '<span itemprop="n a">twice</span></div>'
    )

    assert read(html, base_url="https://shop.example/c/") == [
        {
            "type": "https://schema.org/Product",
            "id": "urn:sku:1",
            "properties": {
                "sku": " A1 ",
                "gtin": "",
                "image": "https://shop.example/i.jpg",
                "url": "https://shop.example/p",
                "o": "https://shop.example/c/d.bin",
                "v": " 3 ",
                "m": "0.5",
                "t": "2020-01-02",
                "c": "cc",
                "d": "A\n\nB\n\nC D E, FG",
                "n": "twice",
                "a": "twice",
            },
        }
    ]


def test_nested_items_repeated_names_and_items_with_no_property():
    html = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Pad</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">41.90</span></div>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">39.00</span></div>'
        '<div itemprop="brand" itemscope itemtype="https://schema.org/Brand">'
        "Acme <b>Co</b></div></div>"
        '<div itemscope>no type<i itemprop="k">v</i></div>'
        '<div itemscope itemtype="http://a.example/T http://a.example/U">'
        '<i itemprop="k">v</i></div>'
    )

    assert read(html) == [
        {
            "type": "https://schema.org/Product",
            "properties": {
                "name": "Pad",
                "offers": [
                    {
                        "type": "https://schema.org/Offer",
                        "properties": {"price": "41.90"},
                    },
                    {
                        "type": "https://schema.org/Offer",
                        "properties": {"price": "39.00"},
                    },
                ],
                "brand": {"type": "https://schema.org/Brand", "value": "Acme Co"},
            },
        },
        {"properties": {"k": "v"}},
        {
            "type": ["http://a.example/T", "http://a.example/U"],
            "properties": {"k": "v"},
        },
    ]


def test_schema_org_actions_say_their_input_s_name_and_whether_it_is_required():
    html = (
        '<div itemscope itemtype="https://schema.org/WebSite">'
        '<form itemprop="potentialAction" itemscope '
        'itemtype="https://schema.org/SearchAction">'
        '<meta itemprop="target" content="https://e.com/s?q={q}">'
        '<input itemprop="query-input" name="q" required>'
        '<span itemprop="x-output">y</span></form></div>'
    )

    action = read(html)[0]["properties"]["potentialAction"]  # type: ignore[index]

    assert action["properties"] == {
        "target": "https://e.com/s?q={q}",
        "query-input": {"valueRequired": True, "valueName": "q"},
        "x-output": {},
    }


def test_strict_makes_every_type_and_property_a_list():
    html = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Pad</span></div>'
    )

    assert read(html, strict=True) == [
        {"type": ["https://schema.org/Product"], "properties": {"name": ["Pad"]}}
    ]


def test_not_nested_answers_every_item_by_its_place():
    html = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Pad</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">1</span></div></div>'
    )

    assert read(html, nested=False) == [
        {
            "iid": 1,
            "type": "https://schema.org/Product",
            "properties": {"name": "Pad", "offers": {"iid_ref": 2}},
        },
        {"iid": 2, "type": "https://schema.org/Offer", "properties": {"price": "1"}},
    ]


def test_text_content_and_the_html_node_when_asked_for():
    html = (
        '<div itemscope id="it">Item <i itemprop="k">v</i></div><div itemscope></div>'
    )

    found = read(html, add_text_content=True, add_html_node=True)

    assert found[0]["textContent"] == "Item v"
    assert found[0]["htmlNode"].get("id") == "it"  # type: ignore[attr-defined]
    assert "textContent" not in found[1]


def test_an_item_from_a_tree():
    tree = lxml.html.fromstring('<div itemscope><a itemprop="u" href="/p">x</a></div>')

    found = MicrodataExtractor().extract_items(tree, "https://e.com/")

    assert found == [{"properties": {"u": "https://e.com/p"}}]


# The documented differences.


def test_an_item_named_by_itemref_from_further_down_is_nested_where_it_belongs():
    # extruct: [Offer, Product with "offers": None].
    html = (
        '<div id="o" itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">10</span></div>'
        '<div itemscope itemtype="https://schema.org/Product" itemref="o">'
        '<span itemprop="name">P</span></div>'
    )

    assert read(html) == [
        {
            "type": "https://schema.org/Product",
            "properties": {
                "offers": {
                    "type": "https://schema.org/Offer",
                    "properties": {"price": "10"},
                },
                "name": "P",
            },
        }
    ]


def test_an_item_two_items_share_is_in_both():
    # extruct: [Brand, Product "brand": None, Product "brand": None].
    html = (
        '<div id="b" itemprop="brand" itemscope itemtype="https://schema.org/Brand">'
        '<span itemprop="name">Acme</span></div>'
        '<div itemscope itemtype="https://schema.org/Product" itemref="b">'
        '<span itemprop="name">A</span></div>'
        '<div itemscope itemtype="https://schema.org/Product" itemref="b">'
        '<span itemprop="name">B</span></div>'
    )

    brand = {"type": "https://schema.org/Brand", "properties": {"name": "Acme"}}
    assert [item["properties"] for item in read(html)] == [
        {"brand": brand, "name": "A"},
        {"brand": brand, "name": "B"},
    ]


def test_an_item_holding_itself_through_itemref_is_left_out_of_itself():
    html = (
        '<div id="a" itemscope itemtype="https://schema.org/Thing" itemref="b">'
        '<span itemprop="name">A</span></div>'
        '<div id="b" itemprop="part" itemscope itemref="a"><i itemprop="k">v</i></div>'
    )

    found = read(html)

    assert found[0]["properties"]["part"]["properties"]["k"] == "v"  # type: ignore[index]
    assert "part" not in found[0]["properties"]["part"]["properties"]  # type: ignore[index]


def test_an_itemref_to_a_missing_id_or_to_the_item_itself_adds_nothing():
    html = '<div id="me" itemscope itemref="nowhere me"><i itemprop="k">v</i></div>'

    assert read(html) == [{"properties": {"k": "v"}}]


def test_a_time_without_datetime_is_its_text():
    # extruct answers "".
    html = '<div itemscope><time itemprop="d">May 10, 2023</time></div>'

    assert read(html) == [{"properties": {"d": "May 10, 2023"}}]


def test_an_address_attribute_that_is_absent_is_empty():
    # extruct answers the page's own address.
    html = '<div itemscope><a itemprop="u">no href</a><img itemprop="i" src=""></div>'

    assert read(html, base_url="https://e.com/p") == [
        {"properties": {"u": "", "i": "https://e.com/p"}}
    ]


def test_an_address_resolves_against_the_page_s_base_href():
    # extruct resolves against base_url alone: https://e.com/i.jpg.
    html = (
        '<html><head><base href="https://cdn.example.com/"></head><body>'
        '<div itemscope><img itemprop="image" src="i.jpg"></div></body></html>'
    )

    assert read(html, base_url="https://e.com/x") == [
        {"properties": {"image": "https://cdn.example.com/i.jpg"}}
    ]


def test_an_address_urljoin_refuses_is_kept_as_written():
    # extruct raises ValueError.
    html = '<div itemscope><a itemprop="u" href="https://[domain]/p">x</a></div>'

    assert read(html, base_url="https://e.com/") == [
        {"properties": {"u": "https://[domain]/p"}}
    ]


def test_items_nested_past_the_bound_are_left_out():
    # extruct raises RecursionError about four hundred deep.
    html = '<div itemscope><i itemprop="k">top</i>' + (
        '<div itemprop="d" itemscope>' * 100 + "x" + "</div>" * 100
    )

    depth, item = 0, read(html)[0]
    while "properties" in item:
        item = item["properties"]["d"]  # type: ignore[index]
        depth += 1

    # The deepest item read holds its child's text, not its child.
    assert depth == 64
    assert item == {"value": "x"}


def test_a_page_that_would_copy_more_than_its_budget_gets_the_start():
    names = " ".join(f"n{i}" for i in range(200))
    html = (
        "<div itemscope><i itemprop='first'>kept</i></div>"
        + f"<div itemscope><i itemprop='{names}'>"
        + "x" * 1_000
        + "</i></div>"
    )

    found = read(html)

    assert found == [{"properties": {"first": "kept"}}]


# --- text --------------------------------------------------------------------


def text(html: str) -> str | None:
    return readable(lxml.html.fromstring(html), Budget(len(html)))


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<div>A<p>B</p>C <span>D</span><span>E</span>, F</div>", "A\n\nB\n\nC D E, F"),
        ("<div><b>foo</b><!-- c -->bar</div>", "foo bar"),
        ("<div><b>foo</b>x<!-- c -->y</div>", "foo xy"),
        ("<div><!-- c -->lead<b>b</b></div>", "lead b"),
        ("<div>(<b>x</b>)</div>", "(x)"),
        ("<div>a <b>b</b></div>", "a b"),
        ("<ul><li>one</li><li>two</li></ul>", "one\ntwo"),
        ("<div><h1>T</h1><h2>S</h2></div>", "T\n\nS"),
        ("<div><div>a</div><p>b</p></div>", "a\n\nb"),
        ("<div>x<br>y</div>", "x\ny"),
        ("<div>a<style>p{}</style><link href='l'><meta content='m'>b</div>", "ab"),
        ("<script>var x</script>", ""),
        ("<div>  spaced \n out  </div>", "spaced out"),
    ],
)
def test_text_is_laid_out_as_html_text_lays_it_out(html, expected):
    assert text(html) == expected


def test_text_stops_when_the_budget_is_spent():
    element = lxml.html.fromstring("<div>" + "<b>word</b>" * 50 + "</div>")

    assert readable(element, Budget(0)) is not None
    spent = Budget(0)
    spent.left = 3
    assert readable(element, spent) is None
    spent.left = 30
    assert readable(element, spent) is None
    spent.left = 0
    assert readable(lxml.html.fromstring("<div>x</div>"), spent) is None


def test_a_literal_is_every_text_node_as_written_comments_included():
    element = lxml.html.fromstring(
        "<div> a <!-- note --><b>b</b>\n<script>s</script>t</div>"
    )

    assert literal(element, Budget(100)) == " a  note b\nst"
    spent = Budget(0)
    spent.left = 2
    assert literal(element, spent) is None
    spent.left = 5
    assert literal(element, spent) is None


def test_a_script_or_style_that_is_itself_the_property_has_no_text():
    tree = lxml.html.fromstring("<div><script>var x</script><style>p{}</style></div>")

    assert readable(tree[0], Budget(100)) == ""
    assert readable(tree[1], Budget(100)) == ""


def test_text_stops_wherever_the_budget_runs_out():
    element = lxml.html.fromstring("<div>lead<b>bold</b>tail after the bold</div>")

    for left in (1, 3, 8, 12):
        budget = Budget(0)
        budget.left = left
        assert readable(element, budget) is None
    budget = Budget(0)
    budget.left = 3
    assert literal(lxml.html.fromstring("<div><b>b</b>long tail</div>"), budget) is None


def test_comments_inside_an_item_are_not_its_properties():
    html = '<div itemscope><!-- a note --><i itemprop="k">v</i></div>'

    assert read(html) == [{"properties": {"k": "v"}}]


def test_an_orphan_property_item_is_top_level_where_itemref_names_something_else():
    html = (
        '<div itemscope itemref="r"></div><p id="r"><i itemprop="k">v</i></p>'
        '<section><div itemprop="orphan" itemscope><i itemprop="n">o</i></div>'
        "</section>"
    )

    assert read(html) == [
        {"properties": {"k": "v"}},
        {"properties": {"n": "o"}},
    ]


def test_a_text_the_budget_cannot_pay_for_ends_the_page_s_items():
    # Two hundred properties nested in one another each hold all the text
    # below them: two hundred copies of a thousand characters.
    nested = '<div itemprop="p">' * 200 + "x" * 1_000 + "</div>" * 200
    html = (
        "<div itemscope><i itemprop='first'>kept</i></div>"
        f"<div itemscope>{nested}</div>"
    )

    assert read(html) == [{"properties": {"first": "kept"}}]


def test_an_address_without_a_base_is_as_written():
    html = '<div itemscope><a itemprop="u" href=" /p ">x</a></div>'

    assert read(html) == [{"properties": {"u": "/p"}}]
