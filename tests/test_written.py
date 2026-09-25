"""Extractors a person writes: every field a selector, every check kept.

A learnt extractor knows where its fields are because pages showed it; a
hand-written one because a person said so, by CSS or XPath. It is replayed
by the same ``run_extractor`` and held to the same checks where they apply:
a selector that finds nothing fails, and one written from pages is held to
the presence, shape and reading those pages showed. A redesign that breaks a
selector is a failed run, never rows that came back empty.
"""

import json
import re
from pathlib import Path

import pytest

from sluicer.extractor import (
    FORMAT_WRITTEN,
    LOSSES,
    Extractor,
    NothingToLearn,
    compile_extractor,
    heal,
    run_extractor,
)
from sluicer.selectors import SelectorError
from sluicer.written import Written, WrittenField

DRIFT = Path(__file__).parent / "fixtures" / "drift"

BOOK = {
    "title": "a.title",
    "price": "span.price::text",
    "link": "a.title::attr(href)",
}


def page(name: str) -> tuple[bytes, str]:
    return (DRIFT / name).read_bytes(), f"https://shop.example/{name}"


def books() -> Extractor:
    return compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")],
        select=BOOK,
        rows="li.product",
    )


def failed(run) -> list[str]:
    return [check.name for check in run.checks if not check.ok]


def listing(rows: list[str]) -> bytes:
    return (
        '<html lang="en"><head><title>Books | Example Shop</title></head><body><ol>'
        + "".join(f'<li class="product">{row}</li>' for row in rows)
        + "</ol></body></html>"
    ).encode()


# -- writing ------------------------------------------------------------------


def test_a_listing_written_by_selectors_learns_its_columns_from_the_pages():
    extractor = books()

    written = extractor.written
    assert written is not None
    assert written.rows == "li.product"
    fields = {f.name: f for f in written.fields}
    assert list(fields) == ["title", "price", "link"]
    assert fields["price"].selector == "span.price::text"
    assert fields["price"].shape == "NPS"
    assert fields["price"].reads == "amount"
    assert fields["price"].missing == 0
    assert "£51.77" in fields["price"].samples
    # An address has no shape and no reading, as a learnt one has none.
    assert (fields["link"].shape, fields["link"].reads) == (None, None)
    assert extractor.listing is None and extractor.fields == ()


@pytest.mark.parametrize(
    ("title", "address"),
    [
        (".//a[@href]", False),
        ("xpath:.//a[@src or @href]", False),
        (".//a/@href", True),
        ("(.//a/@href)[1]", True),
        ("a::attr(href)", True),
        ("a::attr(class)", False),
    ],
)
def test_a_field_is_an_address_when_its_values_are_links(title, address):
    """An address has no shape or reading to hold it to; a link's text does.
    ``.//a[@href]`` names the links that have an href, and reads their text:
    it was taken for an address, so a title that turned into a number
    passed."""
    extractor = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")],
        select={"title": title, "price": "span.price::text"},
        rows="li.product",
    )

    [field, _price] = extractor.written.fields
    assert (field.shape is None) is address
    if not address and "class" not in title:
        numbers = listing(
            [
                f'<a class="title" href="/b/{n}">{n}.00</a>'
                f'<span class="price">£{n}.50</span>'
                for n in range(1, 7)
            ]
        )
        run = run_extractor(extractor, numbers, "https://shop.example/")
        assert not run.ok
        assert "shape" in failed(run)


def test_a_written_extractor_is_a_file_of_format_3_and_reads_back_the_same():
    extractor = books()

    text = extractor.to_json()

    assert json.loads(text)["format"] == FORMAT_WRITTEN == 3
    assert json.loads(text)["select"]["rows"] == "li.product"
    assert Extractor.from_json(text) == extractor


def test_writing_is_deterministic():
    assert books().to_json() == books().to_json()


def test_with_no_page_given_a_selector_is_all_there_is_to_hold_a_page_to():
    extractor = compile_extractor([], select={"name": "h1"})

    assert extractor.written == Written(fields=(WrittenField("name", "h1"),))
    run = run_extractor(extractor, *page("product.html"))
    assert run.ok, failed(run)
    assert run.fields == {"name": "Brake pad set"}


def test_the_pages_given_also_teach_what_they_declare():
    """Written from pages, the extractor learns their summary as any does:
    the page that stopped declaring its price fails, whatever the selectors
    still find."""
    extractor = compile_extractor(
        [page("product.html"), page("product.html")], select={"name": "h1"}
    )

    assert "price" in extractor.summary
    run = run_extractor(extractor, *page("product_without_jsonld.html"))
    assert not run.ok
    assert run.fields == {"name": "Brake pad set"}
    assert "summary" in failed(run)


def test_a_selector_that_gives_nothing_on_a_page_it_is_written_from_is_an_error():
    with pytest.raises(NothingToLearn, match=r"price='span\.cost'"):
        compile_extractor(
            [page("shop_v1.html")], select={"price": "span.cost"}, rows="li.product"
        )
    with pytest.raises(NothingToLearn, match=r"li\.card"):
        compile_extractor([page("shop_v1.html")], select=BOOK, rows="li.card")
    with pytest.raises(NothingToLearn, match=r"sku='\.sku'.*product\.html"):
        compile_extractor([page("product.html")], select={"sku": ".sku"})


@pytest.mark.parametrize(
    ("select", "rows", "said"),
    [
        ({"title": "a[href"}, None, "'a[href'"),
        ({"title": "//a["}, None, "'//a['"),
        ({"title": "xpath:count(//a)"}, None, "a number"),
        ({"title": "a"}, "li::text", "rows are elements"),
        ({"title": "//a"}, "li", "the whole page"),
        ({"title": "(//a)[1]"}, "li", "the whole page"),
    ],
)
def test_a_selector_that_cannot_be_read_is_refused_when_written(select, rows, said):
    with pytest.raises(
        SelectorError, match=said.replace("[", r"\[").replace("(", r"\(")
    ):
        compile_extractor([], select=select, rows=rows)


def test_selectors_and_examples_are_two_ways_of_naming_fields_and_one_is_chosen():
    with pytest.raises(ValueError, match="want"):
        compile_extractor([page("shop_v1.html")], select=BOOK, want={"title": "x"})
    with pytest.raises(ValueError, match="rows"):
        compile_extractor([page("shop_v1.html")], select=BOOK, listing=True)
    with pytest.raises(ValueError, match="select"):
        compile_extractor([page("shop_v1.html")], rows="li.product")
    with pytest.raises(ValueError, match="name"):
        compile_extractor([], select={" ": "h1"})
    with pytest.raises(ValueError, match="name"):
        compile_extractor([], select={})


# -- running ------------------------------------------------------------------


def test_the_pages_it_was_written_from_pass_with_the_rows_the_selectors_give():
    extractor = books()

    run = run_extractor(extractor, *page("shop_v1.html"))

    assert run.ok, failed(run)
    assert run.rows[0] == {
        "title": "A Light in the Attic",
        "price": "£51.77",
        "link": "https://shop.example/book/1",
    }
    assert len(run.rows) == 6


def test_a_redesign_that_breaks_the_selectors_fails_and_gives_no_rows():
    run = run_extractor(books(), *page("shop_redesigned.html"))

    assert not run.ok
    assert failed(run) == ["listing"]
    assert run.rows == []
    [check] = [c for c in run.checks if not c.ok]
    assert check.expected == "rows at li.product"


def test_a_rows_selector_a_page_cannot_answer_fails_that_page():
    """An XPath of rows that selects a comment on one page cannot be read
    there: that page fails its listing check, and neither a run nor a heal
    stops on a traceback."""
    rows = "xpath://li[@class='product'] | //comment()[contains(., 'rows')]"
    extractor = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")], select=BOOK, rows=rows
    )
    html, url = page("shop_v1.html")
    commented = html.replace(b"<ol", b"<!-- rows --><ol", 1)

    run = run_extractor(extractor, commented, url)

    assert not run.ok
    assert failed(run) == ["listing"]
    [check] = [c for c in run.checks if not c.ok]
    assert check.expected == f"rows at {rows}"
    assert "comment" in check.got
    assert run.rows == []
    healed, changes = heal(extractor, [(commented, url)])
    assert [(c.kind, c.before) for c in changes] == [("broken", rows)]
    assert healed.written == extractor.written


def test_a_page_with_the_rows_but_none_in_them_fails():
    run = run_extractor(books(), *page("shop_empty.html"))

    assert not run.ok
    assert "listing" in failed(run)


def sales(rows: int, badge: str = "sale", on_sale: int = 3) -> bytes:
    """A listing of ``rows`` books, every ``on_sale``-th one with a badge."""
    return listing(
        [
            f'<a class="title" href="/b/{n}">Book {n}</a>'
            f'<span class="price">£{n}.50</span>'
            + (f'<span class="{badge}">SALE</span>' if n % on_sale == 0 else "")
            for n in range(1, rows + 1)
        ]
    )


def on_sale() -> Extractor:
    """Books, and a sale badge that three rows in ten carry."""
    return compile_extractor(
        [
            (sales(10), "https://shop.example/c1"),
            (sales(10), "https://shop.example/c2"),
        ],
        select={"title": "a.title", "sale": "span.sale::text"},
        rows="li.product",
    )


def test_a_column_few_rows_carry_fails_when_no_row_of_a_long_page_does():
    """A badge three rows in ten carry is absent from ten rows by chance one
    page in thirty-six; from twenty, one in more than a thousand. Its
    selector broken by a redesign, it found nothing in any row, and every
    page passed."""
    extractor = on_sale()
    [_title, sale] = extractor.written.fields
    assert sale.missing == 0.7

    renamed = run_extractor(
        extractor, sales(20, badge="promo"), "https://shop.example/"
    )
    short = run_extractor(extractor, sales(10, badge="promo"), "https://shop.example/")
    none_on_sale = run_extractor(
        extractor, sales(20, on_sale=99), "https://shop.example/"
    )

    assert not renamed.ok
    [check] = [c for c in renamed.checks if not c.ok]
    assert (check.name, check.expected) == ("field", "sale in some rows")
    assert check.got == "in none of 20 rows, a 0.08% chance for a field 30% carried"
    # Ten rows without it are not evidence enough, nor is a page on which
    # it is truly gone told from one of a day with no sale.
    assert short.ok and not none_on_sale.ok


def test_heal_reports_a_column_no_new_row_carries_broken():
    old = on_sale()

    healed, changes = heal(
        old, [(sales(10, badge="promo"), "https://shop.example/")] * 2
    )

    assert [(c.kind, c.before) for c in changes if c.kind in LOSSES] == [
        ("broken", "sale")
    ]
    assert healed.written == old.written


def test_a_column_gone_from_its_rows_fails_as_a_learnt_one_does():
    run = run_extractor(books(), *page("shop_prices_gone.html"))

    assert not run.ok
    assert failed(run) == ["field"]
    [check] = [c for c in run.checks if not c.ok]
    assert check.expected == "price in at least 80% of rows"


def test_a_price_slot_that_now_holds_a_button_fails_its_reading_and_shape():
    run = run_extractor(books(), *page("shop_price_is_a_button.html"))

    assert not run.ok
    assert set(failed(run)) == {"reads", "shape", "values"}


def test_the_checks_a_written_listing_gets_are_the_ones_a_learnt_one_gets():
    """The same drift, the same checks: a learnt and a written extractor of
    one listing fail a price slot that holds a button with the same words."""
    learnt = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")],
        want={"price": "£51.77", "title": "A Light in the Attic"},
    )
    written = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")],
        select={"price": "span.price", "title": "a.title"},
        rows="li.product",
    )

    said = [
        [(c.name, c.expected, c.ok) for c in run.checks if c.name != "listing"]
        for run in (
            run_extractor(extractor, *page("shop_price_is_a_button.html"))
            for extractor in (learnt, written)
        )
    ]
    assert said[0] == [c for c in said[1] if not c[1].endswith("once in each row")]


def test_rows_that_turned_into_empty_shells_fail():
    extractor = books()
    shells = listing(
        ['<a class="title" href="/b">B</a><span class="price">£1.00</span>']
        + ["<span></span>"] * 5
    )

    run = run_extractor(extractor, shells, "https://shop.example/")

    assert not run.ok
    assert "rows" in failed(run)


def test_a_column_that_says_the_same_in_every_row_fails():
    extractor = books()
    loading = listing(
        [
            f'<a class="title" href="/b/{n}">Loading</a>'
            f'<span class="price">£{n}.00</span>'
            for n in range(1, 7)
        ]
    )

    run = run_extractor(extractor, loading, "https://shop.example/")

    assert not run.ok
    assert failed(run) == ["values"]


def test_a_field_that_finds_two_values_in_a_row_where_it_found_one_fails():
    """A sale that adds the old price beside the new one: the first price is
    now the wrong one, and read as if nothing happened it would be."""
    extractor = books()
    sale = listing(
        [
            f'<a class="title" href="/b/{n}">Book {"ABCDEF"[n - 1]}</a>'
            + ('<span class="price">£9.00</span>' if n == 1 else "")
            + f'<span class="price">£{n}.50</span>'
            for n in range(1, 7)
        ]
    )

    run = run_extractor(extractor, sale, "https://shop.example/")

    assert not run.ok
    [check] = [c for c in run.checks if not c.ok]
    assert check.name == "field"
    assert check.expected == "price once in each row"
    assert check.got.startswith("1 of 6 rows")


def test_a_field_the_pages_showed_twice_reads_the_first_and_says_so():
    two = b"<html><body><p class=x>One</p><p class=x>Two</p></body></html>"

    extractor = compile_extractor([(two, None)], select={"x": "p.x"})

    [field] = extractor.written.fields
    assert field.first
    assert any("first" in note for note in extractor.notes)
    run = run_extractor(extractor, two, None)
    assert run.ok and run.fields == {"x": "One"}


def test_a_page_field_found_twice_where_it_was_found_once_fails():
    extractor = compile_extractor([page("product.html")], select={"note": "p"})
    doubled = b"<html><body><h1>Brake pad set</h1><p>Front axle.</p><p>Rear.</p>"

    run = run_extractor(extractor, doubled, None)

    assert not run.ok
    [check] = [c for c in run.checks if not c.ok and c.name == "field"]
    assert check.got == "2 values, where one was expected"
    assert "note" not in run.fields


def test_a_page_field_is_held_to_its_reading_and_shape_when_pages_taught_them():
    pages = [
        (f"<html><body><b class=price>{n}.90 EUR</b></body></html>".encode(), None)
        for n in range(10, 15)
    ]
    extractor = compile_extractor(pages, select={"price": "b.price"})

    [field] = extractor.written.fields
    assert (field.reads, field.shape) == ("amount", "LNP")
    run = run_extractor(extractor, "<b class=price>\u2605 offer</b>", None)
    assert set(failed(run)) == {"reads", "shape"}


def test_a_page_field_that_finds_nothing_fails():
    extractor = compile_extractor([], select={"name": "h1.product"})

    run = run_extractor(extractor, *page("product.html"))

    assert not run.ok
    [check] = run.checks
    assert (check.name, check.expected, check.got) == (
        "field",
        "name at h1.product",
        "not found",
    )


# -- the file -----------------------------------------------------------------


def test_a_file_written_by_hand_needs_only_its_selectors():
    text = json.dumps(
        {
            "format": 3,
            "select": {
                "rows": "li.product",
                "fields": [
                    {"name": "title", "selector": "a.title"},
                    {"name": "price", "selector": "xpath:.//span[@class='price']"},
                ],
            },
        }
    )

    extractor = Extractor.from_json(text)

    run = run_extractor(extractor, *page("shop_v1.html"))
    assert run.ok, failed(run)
    assert run.rows[1] == {"title": "Tipping the Velvet", "price": "£53.74"}
    # Left out, a field is required in every row, as strict as a key can be.
    assert run_extractor(extractor, *page("shop_prices_gone.html")).ok is False


def one(**keys):
    """A ``select`` of one field, ``t`` at ``a``, with ``keys`` in the field."""
    return {
        "select": {"rows": None, "fields": [{"name": "t", "selector": "a", **keys}]}
    }


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"format": 1}, "format 3"),
        ({"format": 2}, "format 3"),
        ({"listing": {"container": "html", "member": "li", "rows": [1, 1]}}, "learnt"),
        ({"fields": [{"name": "x", "path": "html", "shape": None}]}, "learnt"),
        ({"select": {"rows": None, "fields": []}}, "no field"),
        ({"select": {"rows": None}}, "fields"),
        ({"select": {"rows": None, "fields": [{"name": "t"}]}}, "selector"),
        (one(selector="a["), "'a['"),
        ({"select": {"rows": 5, "fields": [{"name": "t", "selector": "a"}]}}, "rows"),
        (
            {"select": {"rows": None, "fields": [{"name": "t", "selector": "a"}] * 2}},
            "two fields",
        ),
        (
            {"select": {"rows": "li", "fields": [{"name": "t", "selector": "//a"}]}},
            "the whole page",
        ),
        (one(missing=2), "missing"),
        (one(shape="X"), "shape"),
        (one(reads="x"), "amount or date"),
        (one(first=1), "first"),
        (
            {"select": {**one()["select"], "rows": "li", "empty": "nan"}},
            "empty",
        ),
    ],
)
def test_a_written_file_that_would_check_less_than_it_says_is_refused(change, said):
    body = json.loads(books().to_json())
    body.update(change)

    with pytest.raises(ValueError, match=re.escape(said)):
        Extractor.from_json(json.dumps(body))


def test_a_learnt_file_is_read_as_before():
    text = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html")]
    ).to_json()

    assert json.loads(text)["format"] == 1
    assert "select" not in json.loads(text)
    assert Extractor.from_json(text).written is None


# -- healing ------------------------------------------------------------------


def test_heal_keeps_selectors_that_still_hold_and_learns_the_pages_again():
    healed, changes = heal(books(), [page("shop_v1_page2.html")])

    assert not any(c.kind in LOSSES for c in changes)
    assert [(c.kind, c.before, c.after) for c in changes if c.kind == "kept"] == [
        ("kept", "title", "a.title"),
        ("kept", "price", "span.price::text"),
        ("kept", "link", "a.title::attr(href)"),
    ]
    assert healed.written.rows == "li.product"
    assert [f.selector for f in healed.written.fields] == list(BOOK.values())


def test_heal_never_rewrites_a_selector_a_person_wrote():
    """A hand-written selector is what a person said, and heal cannot say it
    for them: one the new pages break is reported broken, a loss, and kept as
    written, so the extractor goes on failing until a person rewrites it."""
    old = books()

    healed, changes = heal(old, [page("shop_redesigned.html")])

    assert "broken" in LOSSES
    assert [(c.kind, c.before) for c in changes if c.kind == "broken"] == [
        ("broken", "li.product")
    ]
    assert healed.written == old.written
    assert not run_extractor(healed, *page("shop_redesigned.html")).ok


def test_heal_names_each_field_its_selector_no_longer_finds():
    old = books()

    healed, changes = heal(old, [page("shop_price_is_a_button.html")])

    assert [(c.kind, c.before) for c in changes if c.kind in LOSSES] == [
        ("broken", "price")
    ]
    assert healed.written == old.written


# -- the command line ---------------------------------------------------------


def _cli(*args: str):
    from click.testing import CliRunner

    from sluicer.cli import main

    return CliRunner().invoke(main, list(args))


def _write_books(out: Path, *pages: str):
    return _cli(
        "compile",
        *(str(DRIFT / name) for name in pages),
        "-o",
        str(out),
        "--rows",
        "li.product",
        *(f"--select={name}={text}" for name, text in BOOK.items()),
    )


def test_compile_select_writes_a_hand_written_extractor(tmp_path):
    out = tmp_path / "books.json"

    result = _write_books(out, "shop_v1.html", "shop_v1_page2.html")

    assert result.exit_code == 0, result.stderr
    written = Extractor.from_json(out.read_text(encoding="utf-8")).written
    assert written.rows == "li.product"
    assert [f.selector for f in written.fields] == list(BOOK.values())
    assert "3 fields by selector in rows at li.product" in result.stderr


def test_compile_select_needs_no_page(tmp_path):
    out = tmp_path / "name.json"

    result = _cli("compile", "-o", str(out), "--select", "name=h1")

    assert result.exit_code == 0, result.stderr
    ran = _cli("run", str(out), str(DRIFT / "product.html"))
    assert ran.exit_code == 0, ran.stderr
    assert json.loads(ran.stdout)["pages"][0]["fields"] == {"name": "Brake pad set"}


def test_compile_without_pages_or_selectors_says_what_it_needs(tmp_path):
    result = _cli("compile", "-o", str(tmp_path / "x.json"))

    assert result.exit_code == 2
    assert "pages" in result.stderr and "--select" in result.stderr


def test_run_exits_three_when_a_redesign_breaks_a_selector(tmp_path):
    out = tmp_path / "books.json"
    _write_books(out, "shop_v1.html", "shop_v1_page2.html")

    result = _cli("run", str(out), str(DRIFT / "shop_redesigned.html"))

    assert result.exit_code == 3
    [page_run] = json.loads(result.stdout)["pages"]
    assert page_run["ok"] is False and page_run["rows"] == []
    assert "expected rows at li.product, got not found" in result.stderr


def test_heal_exits_three_and_writes_nothing_for_a_broken_selector(tmp_path):
    out = tmp_path / "books.json"
    _write_books(out, "shop_v1.html", "shop_v1_page2.html")
    healed = tmp_path / "healed.json"

    result = _cli(
        "heal", str(out), str(DRIFT / "shop_redesigned.html"), "-o", str(healed)
    )

    assert result.exit_code == 3
    assert not healed.exists()
    assert "broken: li.product" in result.stderr
    assert "heal does not rewrite a selector" in result.stderr


@pytest.mark.parametrize(
    ("options", "said"),
    [
        (["--select", "title=a[href"], "'a[href'"),
        (["--select", "title"], "NAME=SELECTOR"),
        (["--rows", "li"], "--select"),
        (["--select", "t=h1", "--want", "t=x"], "--want"),
        (["--select", "t=h1", "--listing"], "--rows"),
        (["--select", "t=h1", "--select", "t=h2"], "two fields named 't'"),
        (["--want", "t=Brake", "--want", " t=pad"], "two fields named 't'"),
    ],
)
def test_compile_refuses_a_selector_it_cannot_read_naming_it(tmp_path, options, said):
    result = _cli(
        "compile", str(DRIFT / "product.html"), "-o", str(tmp_path / "x.json"), *options
    )

    assert result.exit_code == 2
    assert said in result.stderr
    assert not (tmp_path / "x.json").exists()


def test_compile_says_which_selector_gives_nothing_on_which_page(tmp_path):
    result = _cli(
        "compile",
        str(DRIFT / "product.html"),
        "-o",
        str(tmp_path / "x.json"),
        "--select",
        "sku=.sku",
    )

    assert result.exit_code == 1
    assert "sku='.sku' gives nothing on" in result.stderr


def test_select_prints_each_value_and_where_it_is():
    result = _cli("select", str(DRIFT / "shop_v1.html"), "li.product span.price")

    assert result.exit_code == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 6
    assert lines[0] == "£51.77\t/html/body/div[1]/ol[1]/li[1]/span[1]"


def test_select_json_gives_value_and_where():
    result = _cli("select", "--json", str(DRIFT / "shop_v1.html"), "//li[1]/a/@href")

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == [
        {"value": "/book/1", "where": "/html/body/div[1]/ol[1]/li[1]/a[1]"}
    ]


def test_select_resolves_addresses_against_url():
    result = _cli(
        "select",
        "--url",
        "https://shop.example/c/",
        str(DRIFT / "shop_v1.html"),
        "li:first-child a::attr(href)",
    )

    assert result.stdout.split("\t")[0] == "https://shop.example/book/1"


def test_select_exits_one_on_nothing_and_two_on_a_selector_it_cannot_read():
    nothing = _cli("select", str(DRIFT / "shop_v1.html"), "table td")
    broken = _cli("select", str(DRIFT / "shop_v1.html"), "td[")

    assert nothing.exit_code == 1
    assert "gives nothing" in nothing.stderr
    assert broken.exit_code == 2
    assert "'td['" in broken.stderr


@pytest.mark.parametrize("key", ["select", "rows"])
def test_a_configuration_file_cannot_name_an_extractor_s_selectors(tmp_path, key):
    """Like --want, --select and --rows describe one extractor: a default
    for them would write every extractor with the same fields."""
    config = tmp_path / "sluicer.toml"
    config.write_text(f'[compile]\n{key} = "h1"\n', encoding="utf-8")

    result = _cli("--config", str(config), "compile", "-o", str(tmp_path / "x.json"))

    assert result.exit_code == 2
    assert key in result.stderr and "one extractor" in result.stderr
