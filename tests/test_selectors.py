"""Selectors a person writes: CSS with ``::text`` and ``::attr()``, and XPath.

Every value a selector gives carries where it came from, the XPath of its
element, as every other value Sluicer reads does; and a selector that cannot
be read is an error that names it, never a selection of nothing.
"""

import pytest

import sluicer
from sluicer.document import load
from sluicer.selectors import Page, Selected, Selection, SelectorError, parse, selector

SHOP = b"""<!doctype html><html><head><title>Books</title>
<base href="https://shop.example/c/"></head><body>
<h1>  Books
  of the week </h1>
<ol class="row">
<li class="product"><a class="title" href="/book/1">A Light in the Attic</a>
<span class="price">\xc2\xa351.77</span></li>
<li class="product sale"><a class="title" href="book/2">Tipping the Velvet</a>
<span class="price">\xc2\xa353.74</span></li>
</ol>
<p id="note">Prices <b>include</b> VAT, <i>always</i>.</p>
<img src="cover.jpg" alt="">
<!-- the footer comes later -->
</body></html>"""


def shop() -> Page:
    return parse(SHOP, url="https://shop.example/c/books")


def element_at(where: str):
    """The one element an XPath names on the shop page, parsed afresh."""
    [found] = load(SHOP, url="https://shop.example/c/books").tree.xpath(where)
    return found


def test_a_css_selector_gives_each_element_s_text_with_its_place():
    titles = shop().css("li.product a.title")

    assert titles.getall() == ["A Light in the Attic", "Tipping the Velvet"]
    assert [t.where for t in titles] == [
        "/html/body/ol[1]/li[1]/a[1]",
        "/html/body/ol[1]/li[2]/a[1]",
    ]
    assert element_at(titles[1].where).text == "Tipping the Velvet"


def test_text_is_read_with_its_spaces_collapsed_as_every_value_is():
    assert shop().css("h1").get() == "Books of the week"
    assert shop().css("h1::text").get() == "Books of the week"


def test_text_is_the_element_s_own_text_nodes_as_scrapy_reads_it():
    """``::text`` is the element's own text, each node a value, as parsel and
    Scrapy read it; a node of spaces alone is no value."""
    note = shop().css("#note::text")

    assert note.getall() == ["Prices", "VAT,", "."]
    assert {n.where for n in note} == {"/html/body/p[1]"}


# What parsel 1.12.0, Scrapy's selectors, gives for each on SHOP, spaces
# collapsed and nodes of spaces alone left out, as Sluicer reads a value.
AS_PARSEL = [
    ("#note::text", ["Prices", "VAT,", "."]),
    ("#note *::text", ["Prices", "include", "VAT,", "always", "."]),
    ("#note ::text", ["Prices", "include", "VAT,", "always", "."]),
    ("h1 ::text", ["Books of the week"]),
    ("#note b::text", ["include"]),
    ("li *::text", ["A Light in the Attic", "£51.77", "Tipping the Velvet", "£53.74"]),
    (
        "li > *::text",
        ["A Light in the Attic", "£51.77", "Tipping the Velvet", "£53.74"],
    ),
    ("ol li::text", []),
    ("ol::attr(class)", ["row"]),
    (
        "ol ::attr(class)",
        ["row", "product", "title", "price", "product sale", "title", "price"],
    ),
]


@pytest.mark.parametrize(("written", "parsel"), AS_PARSEL)
def test_text_and_attributes_after_a_space_are_read_as_parsel_reads_them(
    written, parsel
):
    """After a space, ``::text`` is every text node inside the element and
    ``::attr()`` the attribute of the element and of everything inside it:
    ``div.price ::text`` is ``Price:``, ``12`` and ``EUR``, as parsel reads
    it. Sluicer read it as the text of the elements inside, ``12`` alone,
    and ``h1 ::text`` as nothing at all."""
    assert shop().css(written).getall() == parsel


def test_text_nodes_are_read_in_the_page_s_order_as_parsel_reads_them():
    """An element inside another that is selected too: its text comes where
    the page has it, not after the outer element's own."""
    nested = parse("<div class=x>A<div class=x>B</div>C</div>")

    assert nested.css("div.x::text").getall() == ["A", "B", "C"]


def test_an_attribute_is_read_and_an_address_resolved_against_the_page():
    links = shop().css("a.title::attr(href)")

    assert links.getall() == [
        "https://shop.example/book/1",
        "https://shop.example/c/book/2",
    ]
    assert links[0].where == "/html/body/ol[1]/li[1]/a[1]"
    assert shop().css("li::attr(class)").getall() == ["product", "product sale"]
    assert shop().css('a::attr("class")').get() == "title"


def test_an_element_without_the_attribute_or_with_it_empty_gives_no_value():
    assert shop().css("img::attr(alt)").getall() == []
    assert shop().css("span::attr(href)").getall() == []


def test_an_element_is_kept_even_when_it_holds_no_text():
    """A row with nothing in it is still a row: counted, and empty."""
    assert shop().css("img").getall() == [""]


def test_xpath_gives_elements_text_and_attributes_each_with_its_element():
    page = shop()

    assert page.xpath("//li/a").getall() == [
        "A Light in the Attic",
        "Tipping the Velvet",
    ]
    assert page.xpath("//a/@href").getall()[1] == "https://shop.example/c/book/2"
    assert page.xpath("//a/@href")[1].where == "/html/body/ol[1]/li[2]/a[1]"
    said = page.xpath("//p[@id='note']//text()")
    assert said.getall() == ["Prices", "include", "VAT,", "always", "."]
    # A text after an element is its parent's, not the element's before it.
    assert said[2].where == "/html/body/p[1]"
    assert said[1].where == "/html/body/p[1]/b[1]"


def test_a_group_of_selectors_reads_the_page_once_in_its_order():
    assert shop().css("span.price, h1").getall() == [
        "Books of the week",
        "£51.77",
        "£53.74",
    ]
    assert shop().css("h1, h1").getall() == ["Books of the week"]


def test_selections_chain_inside_each_element():
    rows = shop().css("li.product")

    assert [row.css("span.price::text").get() for row in rows] == ["£51.77", "£53.74"]
    assert [row.xpath(".//a/@href").get() for row in rows] == [
        "https://shop.example/book/1",
        "https://shop.example/c/book/2",
    ]
    assert rows.css("a::text").getall() == [
        "A Light in the Attic",
        "Tipping the Velvet",
    ]
    assert rows[1].select("@class").get() == "product sale"


def test_get_gives_the_first_value_or_the_default():
    assert shop().css("span.price").get() == "£51.77"
    assert shop().css("table").get() is None
    assert shop().css("table").get("none") == "none"
    assert shop().css("table").getall() == []
    assert isinstance(shop().css("table"), Selection)


def test_a_selected_value_is_its_value_and_place_and_nothing_else():
    first = shop().css("h1")[0]

    assert isinstance(first, Selected)
    assert (first.value, first.where) == ("Books of the week", "/html/body/h1[1]")
    assert first == shop().css("h1")[0]
    assert "Books of the week" in repr(first)


def test_select_tells_css_from_xpath_by_how_it_begins():
    page = shop()

    for written in ("//h1", "/html/body/h1", "(//h1)[1]", "./body/h1", "xpath:.//h1"):
        assert page.select(written).get() == "Books of the week", written
    assert page.select("h1").get() == "Books of the week"
    assert page.select(".row > li:first-child a").get() == "A Light in the Attic"
    assert page.select("css:h1::text").get() == "Books of the week"
    assert selector("//h1").kind == "xpath"
    assert selector(".price").kind == "css"
    assert selector("  h1  ").text == "h1"


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("a[href", "is not a CSS selector"),
        ("h1::before", "::text and ::attr(name)"),
        ("a::attr()", "one attribute"),
        ("h1::text, h2", "the same thing"),
        ("a:unknown", "is not a CSS selector"),
        ("", "empty"),
        ("   ", "empty"),
    ],
)
def test_a_css_selector_that_cannot_be_read_is_an_error_naming_it(written, said):
    with pytest.raises(SelectorError) as raised:
        shop().css(written)

    assert said in str(raised.value)
    if written.strip():
        assert repr(written.strip()) in str(raised.value)


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("//a[", "is not an XPath"),
        ("count(//a)", "a number"),
        ("string(//h1)", "a text of its own"),
        ("//comment()", "a comment"),
        ("//x:item", "is not an XPath"),
        ("//a[unknown(.)]", "is not an XPath"),
    ],
)
def test_an_xpath_that_cannot_be_read_is_an_error_naming_it(written, said):
    with pytest.raises(SelectorError) as raised:
        shop().xpath(written)

    assert said in str(raised.value)
    assert repr(written) in str(raised.value)


@pytest.mark.parametrize("written", ["//h1\x00", "h1[title='\x00']", "//h1[@x='\x01']"])
def test_a_selector_with_a_character_xpath_cannot_hold_is_an_error_naming_it(written):
    """lxml refuses a NUL or a control character anywhere in an XPath with a
    ValueError of its own, which escaped as not a SelectorError: over MCP, an
    unexpected tool error, not bad_input."""
    with pytest.raises(SelectorError) as raised:
        selector(written)

    assert repr(written) in str(raised.value)
    with pytest.raises(SelectorError):
        shop().select(written)


def test_a_selector_error_is_a_value_error():
    assert issubclass(SelectorError, ValueError)


def test_css_guessed_from_how_it_begins_says_how_to_write_an_xpath():
    with pytest.raises(SelectorError, match="xpath:"):
        shop().select("descendant::a")


def test_there_is_nothing_to_select_inside_a_text_or_an_attribute():
    text = shop().css("h1::text")[0]

    with pytest.raises(SelectorError, match="not an element"):
        text.css("b")


def test_the_page_is_read_as_extract_reads_it():
    """Bytes are decoded by the page's own charset, or the one the response
    was sent with, as ``extract`` decodes them."""
    latin = "<html><body><h1>Caf\xe9</h1></body></html>".encode("latin-1")

    assert parse(latin, headers={"Content-Type": "text/html; charset=latin-1"}).css(
        "h1"
    ).get() == ("Café")
    assert parse("<h1>Plain</h1>").css("h1").get() == "Plain"
    assert parse(SHOP, url="https://x.example/").url == "https://x.example/"


def test_the_package_offers_parse_and_its_types():
    assert sluicer.parse is parse
    assert sluicer.Page is Page
    assert sluicer.SelectorError is SelectorError


def test_many_places_are_spelt_without_counting_every_sibling_each_time():
    """Four thousand rows among four thousand siblings, each spelt: the places
    of one page share the counting, so it stays linear."""
    rows = "".join(f"<li>{n}</li>" for n in range(4000))
    page = parse(f"<html><body><ul>{rows}</ul></body></html>")

    selected = page.css("li")

    assert len(selected) == 4000
    assert selected[3999].where == "/html/body/ul[1]/li[4000]"
