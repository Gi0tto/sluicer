"""A product's table of facts is not a listing of the value asked for.

books.toscrape.com's product pages hold their price twice: in a paragraph of
its own, and in a "Product Information" table whose rows are the book's UPC,
type, prices, tax, availability and reviews. Asked for the price, 0.9.0 took
that table as a listing of seven "prices", and a run on another book passed
with its UPC, "Books" and "In stock (20 available)" among them. The fixtures
under ``fixtures/books_product`` are four of those pages, trimmed.
"""

import json
from pathlib import Path

import pytest

from sluicer.extractor import (
    Extractor,
    NothingToLearn,
    compile_extractor,
    run_extractor,
)

BOOKS = Path(__file__).parent / "fixtures" / "books_product"
LEARNT = ("a-light-in-the-attic_1000", "tipping-the-velvet_999", "soumission_998")


def book(name: str) -> tuple[bytes, str]:
    return (
        (BOOKS / f"{name}.html").read_bytes(),
        f"https://books.toscrape.com/catalogue/{name}/index.html",
    )


def test_the_price_in_a_table_of_facts_is_learnt_as_the_pages_own_value():
    extractor = compile_extractor([book(n) for n in LEARNT], want={"price": "£51.77"})

    assert extractor.listing is None
    assert [f.name for f in extractor.fields] == ["price"]
    assert extractor.fields[0].path.endswith("p.price_color")
    assert extractor.fields[0].reads == "amount"
    assert any("labelled facts of one thing" in note for note in extractor.notes)
    run = run_extractor(extractor, *book("sharp-objects_997"))
    assert run.ok
    assert run.rows == []
    assert run.fields == {"price": "£47.82"}


def test_one_page_is_enough_to_tell_a_table_of_facts():
    extractor = compile_extractor(
        [book("a-light-in-the-attic_1000")], want={"upc": "a897fe39b1053632"}
    )

    assert extractor.listing is None
    assert run_extractor(extractor, *book("sharp-objects_997")).fields == {
        "upc": "e00eb4fd7b871a48"
    }


def test_a_listing_asked_for_in_a_table_of_facts_is_refused_and_says_why():
    with pytest.raises(NothingToLearn, match="labelled facts of one thing"):
        compile_extractor(
            [book(n) for n in LEARNT], listing=True, want={"price": "£51.77"}
        )


# The extractor 0.9.0 wrote from the three pages, as it wrote it.
FACTS_AS_A_LISTING = {
    "format": 1,
    "sluicer": "0.9.0",
    "learnt_from": [f"{n}.html" for n in LEARNT],
    "summary": {"title": None, "language": None},
    "types": [],
    "listing": {
        "container": "html>body>div.container-fluid>div.page_inner>div.content>"
        "div[2]>article.product_page>table.table",
        "member": "tr",
        "rows": [7, 7],
        "empty": 0.0,
        "chosen": True,
        "siblings": [1, 1, 1, 1, 2, 1, 1],
        "fields": [
            {
                "name": "price",
                "path": "td",
                "missing": 0.0,
                "shape": None,
                "reads": None,
                "samples": [
                    "a897fe39b1053632",
                    "Books",
                    "£51.77",
                    "£0.00",
                    "In stock (22 available)",
                ],
            }
        ],
    },
    "notes": [],
}


def test_a_table_of_facts_learnt_as_a_listing_fails_every_run():
    extractor = Extractor.from_json(json.dumps(FACTS_AS_A_LISTING))

    run = run_extractor(extractor, *book("sharp-objects_997"))

    assert not run.ok
    broken = [check for check in run.checks if not check.ok]
    assert [check.name for check in broken] == ["listing"]
    assert "labelled facts of one thing" in broken[0].got


def table(rows: list[tuple[str, str]]) -> str:
    cells = "".join(f"<tr><th>{name}</th><td>{price}</td></tr>" for name, price in rows)
    return f"<html><body><h1>Prices</h1><table>{cells}</table></body></html>"


def test_a_table_of_products_headed_by_their_names_is_still_a_listing():
    first = table([("Brake pads", "£41.90"), ("Wiper", "£9.99"), ("Oil", "£7.50")])
    second = table([("Filter", "£12.00"), ("Pump", "£88.10"), ("Fuse", "£1.20")])

    for pages in ([(first, None)], [(first, None), (second, None)]):
        extractor = compile_extractor(pages, want={"price": "£41.90"})
        assert extractor.listing is not None
        run = run_extractor(extractor, second)
        assert run.ok
        assert [row["price"] for row in run.rows] == ["£12.00", "£88.10", "£1.20"]


def facts(sku: str, price: str, stock: str) -> str:
    return (
        "<html><body><h1>A part</h1><dl>"
        f"<dt>SKU</dt><dd><b>{sku}</b></dd><dt>Price</dt><dd><b>{price}</b></dd>"
        f"<dt>Stock</dt><dd><b>{stock}</b></dd><dt>Brand</dt><dd><b>Bosch</b></dd>"
        "</dl></body></html>"
    )


def test_terms_and_their_descriptions_are_facts_too():
    pages = [
        (facts("AB-12", "£41.90", "In stock"), None),
        (facts("CD-34", "£9.99", "Sold out"), None),
    ]

    extractor = compile_extractor(pages, want={"price": "£41.90"})

    assert extractor.listing is None
    run = run_extractor(extractor, facts("EF-56", "£7.50", "In stock"))
    assert run.ok
    assert run.fields == {"price": "£7.50"}


# A table of products, each row headed by its name (``<th scope=row>``), is a
# listing whatever its prices look like: 0.9.1's first rule judged the rows by
# their raw shape, and took a table whose prices were "£10" beside "£12.50", or
# said "Sold out", or two snapshots of one category, for one thing's facts.


def products(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><th scope='row'>{name}</th><td class='price'>{price}</td></tr>"
        for name, price in rows
    )
    return (
        "<html><head><title>Products</title></head><body><h1>Products</h1>"
        "<table><thead><tr><th>Product</th><th>Price</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


PARTS = ("Brake pad set", "Oil filter", "Wiper blade", "Air filter", "Spark plug")


def test_whole_pounds_beside_pence_are_one_listings_prices():
    prices = ["£10", "£8", "£12.50", "£15", "£4"]
    page = products(list(zip(PARTS, prices, strict=True)))

    extractor = compile_extractor([(page, None)], want={"price": "£12.50"})

    assert extractor.listing is not None
    assert extractor.listing.rows == (5, 5)
    assert not any("labelled facts" in note for note in extractor.notes)
    assert [row["price"] for row in run_extractor(extractor, page).rows] == prices


def test_items_sold_out_are_still_a_listings_rows():
    prices = ["£41.90", "Sold out", "Sold out", "Sold out", "£4.99"]
    page = products(list(zip(PARTS, prices, strict=True)))

    extractor = compile_extractor([(page, None)], want={"price": "£41.90"})

    assert extractor.listing is not None
    run = run_extractor(extractor, page)
    assert run.ok
    assert [row["price"] for row in run.rows] == prices


def test_two_snapshots_of_one_category_are_a_listing():
    first = products(
        list(zip(PARTS, ["£41.90", "£8.99", "£12.50", "£15.20", "£4.99"], strict=True))
    )
    second = products(
        list(zip(PARTS, ["£39.90", "£8.49", "£12.50", "£14.20", "£4.99"], strict=True))
    )

    for listing in (None, True):
        extractor = compile_extractor(
            [(first, None), (second, None)], listing=listing, want={"price": "£41.90"}
        )
        assert extractor.listing is not None
        run = run_extractor(extractor, second)
        assert run.ok
        assert [row["price"] for row in run.rows][:2] == ["£39.90", "£8.49"]


def test_two_snapshots_where_an_item_sold_out_are_a_listing():
    first = products(
        list(zip(PARTS, ["£41.90", "£8.99", "£12.50", "£15.20", "£4.99"], strict=True))
    )
    second = products(
        list(
            zip(PARTS, ["£39.90", "Sold out", "£12.50", "£14.20", "£4.99"], strict=True)
        )
    )

    extractor = compile_extractor(
        [(first, None), (second, None)], want={"price": "£41.90"}
    )

    assert extractor.listing is not None


# The extractor 0.9.0 wrote from a clean table of three products, as it wrote
# it: too few rows to learn a shape.
PRODUCTS_090 = {
    "format": 1,
    "sluicer": "0.9.0",
    "learnt_from": ["G1.html"],
    "summary": {"title": None},
    "types": [],
    "listing": {
        "container": "html>body>table>tbody",
        "member": "tr",
        "rows": [3, 3],
        "empty": 0.0,
        "chosen": True,
        "siblings": [1, 1, 1],
        "fields": [
            {
                "name": "price",
                "path": "td.price",
                "missing": 0.0,
                "shape": None,
                "reads": None,
                "samples": ["£41.90", "£8.99", "£12.50"],
            }
        ],
    },
    "notes": [],
}


def test_a_listing_090_learnt_from_products_runs_on_a_page_with_one_sold_out():
    extractor = Extractor.from_json(json.dumps(PRODUCTS_090))
    page = products(
        [("Clutch kit", "£141.90"), ("Timing belt", "Sold out"), ("Water pump", "£45")]
    )

    run = run_extractor(extractor, page)

    assert run.ok, [check for check in run.checks if not check.ok]
    assert [row["price"] for row in run.rows] == ["£141.90", "Sold out", "£45"]
