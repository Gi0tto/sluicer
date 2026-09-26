"""Extractors: learnt once, replayed without induction, and loud when a page drifts.

The fixtures under ``fixtures/drift`` are one shop listing as it was, the same
listing after a redesign, and the same listing broken in the ways sites break:
the prices gone, the rows gone, a price slot that now holds a button. And one
product page, with its JSON-LD and without it.
"""

import json
from pathlib import Path

import pytest

from sluicer.extractor import (
    Extractor,
    NothingToLearn,
    compile_extractor,
    heal,
    run_extractor,
)

DRIFT = Path(__file__).parent / "fixtures" / "drift"


def page(name: str) -> tuple[bytes, str]:
    return (DRIFT / name).read_bytes(), f"https://shop.example/{name}"


def shop() -> Extractor:
    return compile_extractor([page("shop_v1.html"), page("shop_v1_page2.html")])


def failed(run) -> list[str]:
    return [check.name for check in run.checks if not check.ok]


def test_a_listing_is_learnt_with_its_rows_and_fields():
    extractor = shop()

    assert extractor.listing is not None
    assert extractor.listing.container == "html>body>div.page>ol.row"
    assert extractor.listing.member == "li.product"
    assert extractor.listing.rows == (5, 6)
    names = [field.name for field in extractor.listing.fields]
    assert names == ["a.title", "a.title@href", "span.price", "span.stock"]


def test_a_field_every_row_carries_is_required_and_its_shape_is_kept():
    fields = {field.name: field for field in shop().listing.fields}

    assert fields["span.price"].missing == 0
    assert fields["span.price"].shape == "NPS"
    assert fields["a.title"].shape == "L"
    assert fields["a.title@href"].shape is None  # addresses have no shape
    assert "£51.77" in fields["span.price"].samples


def test_an_extractor_survives_a_round_trip_through_its_file():
    extractor = shop()

    text = extractor.to_json()

    assert Extractor.from_json(text) == extractor
    assert json.loads(text)["format"] == 1


def test_compiling_is_deterministic():
    assert shop().to_json() == shop().to_json()


def test_the_pages_it_was_learnt_from_pass():
    extractor = shop()

    for name in ("shop_v1.html", "shop_v1_page2.html"):
        run = run_extractor(extractor, *page(name))
        assert run.ok, failed(run)
        assert run.rows[0]["a.title"] in {"A Light in the Attic", "The Requiem Red"}


def test_replaying_needs_no_induction_and_gives_plain_rows():
    run = run_extractor(shop(), *page("shop_v1.html"))

    assert len(run.rows) == 6
    assert run.rows[0] == {
        "a.title": "A Light in the Attic",
        "a.title@href": "https://shop.example/book/1",
        "span.price": "£51.77",
        "span.stock": "In stock",
    }


def test_prices_that_vanish_fail_loudly():
    run = run_extractor(shop(), *page("shop_prices_gone.html"))

    assert not run.ok
    assert failed(run) == ["field"]
    check = next(check for check in run.checks if not check.ok)
    assert "span.price" in check.expected


def test_an_empty_listing_fails_loudly():
    run = run_extractor(shop(), *page("shop_empty.html"))

    assert not run.ok
    assert "rows" in failed(run) or "listing" in failed(run)


def test_a_price_slot_that_now_holds_a_button_fails_loudly():
    run = run_extractor(shop(), *page("shop_price_is_a_button.html"))

    assert not run.ok
    assert "shape" in failed(run)
    assert set(failed(run)) <= {"shape", "values", "reads"}


def test_a_redesign_breaks_the_old_extractor():
    run = run_extractor(shop(), *page("shop_redesigned.html"))

    assert not run.ok
    assert failed(run) == ["listing"]
    assert run.rows == []


def test_healing_maps_every_field_to_its_new_place():
    _healed, changes = heal(shop(), [page("shop_redesigned.html")])

    moved = {c.before: c.after for c in changes if c.kind == "moved"}
    assert moved == {
        "a.title": "h2.name>a",
        "a.title@href": "h2.name>a@href",
        "span.price": "div.cost",
        "span.stock": "span.availability",
    }
    assert [c.kind for c in changes if c.kind in ("vanished", "new")] == []
    assert any(c.kind == "container" for c in changes)


def test_a_healed_extractor_keeps_the_names_downstream_code_reads():
    healed, _changes = heal(shop(), [page("shop_redesigned.html")])

    run = run_extractor(healed, *page("shop_redesigned.html"))

    assert run.ok, failed(run)
    assert run.rows[0] == {
        "a.title": "A Light in the Attic",
        "a.title@href": "https://shop.example/book/1",
        "span.price": "£51.77",
        "span.stock": "In stock",
    }


def test_a_field_nothing_matches_is_reported_as_vanished():
    healed, changes = heal(shop(), [page("shop_prices_gone.html")])

    assert [c.before for c in changes if c.kind == "vanished"] == ["span.price"]
    assert "span.price" not in {field.name for field in healed.listing.fields}


def test_a_product_page_is_learnt_by_what_it_declares():
    extractor = compile_extractor([page("product.html")])

    assert extractor.listing is None
    assert extractor.types == ("Product",)
    assert {"title", "price", "currency", "sku"} <= set(extractor.summary)


def test_a_product_page_that_stops_declaring_fails_loudly():
    extractor = compile_extractor([page("product.html")])

    run = run_extractor(extractor, *page("product_without_jsonld.html"))

    assert not run.ok
    assert "summary" in failed(run)
    assert "type" in failed(run)
    missing = {c.expected for c in run.checks if c.name == "summary" and not c.ok}
    assert any("price" in text for text in missing)


def test_a_listing_can_be_asked_for_even_where_things_are_declared():
    extractor = compile_extractor([page("product.html")], listing=True)

    assert extractor.listing is None  # nothing on the page repeats


def test_nothing_to_learn_is_an_error_that_says_so():
    from sluicer.extractor import NothingToLearn

    with pytest.raises(NothingToLearn):
        compile_extractor([(b"<html><body><p>x</p></body></html>", None)])


def test_pages_with_only_a_title_and_a_language_give_no_extractor():
    """Learnt from them, it checked only what every page has, and a run of it
    passed example.com (inventory.md, B8)."""
    with pytest.raises(NothingToLearn, match="only a title and a language"):
        compile_extractor([page("shop_empty.html")])
    with pytest.raises(NothingToLearn, match="only a title and a language"):
        compile_extractor([page("shop_empty.html")], listing=True)


def test_compile_on_pages_with_only_a_title_writes_nothing(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    out = tmp_path / "e.json"
    result = CliRunner().invoke(
        main, ["compile", str(DRIFT / "shop_empty.html"), "-o", str(out)]
    )

    assert result.exit_code == 1
    assert "only a title and a language" in result.stderr
    assert not out.exists()


def test_a_file_that_is_not_an_extractor_is_refused():
    with pytest.raises(ValueError):
        Extractor.from_json('{"format": 99}')


def test_pages_that_put_their_listing_in_different_places_say_so():
    extractor = compile_extractor(
        [page("shop_v1.html"), page("shop_v1_page2.html"), page("shop_redesigned.html")]
    )

    assert extractor.listing.container == "html>body>div.page>ol.row"
    assert any("2 of 3 pages" in note for note in extractor.notes)


# -- the command line ----------------------------------------------------------


def _cli(*args: str):
    from click.testing import CliRunner

    from sluicer.cli import main

    return CliRunner().invoke(main, list(args))


def test_compile_writes_an_extractor_and_says_what_it_learnt(tmp_path):
    out = tmp_path / "shop.json"

    result = _cli(
        "compile",
        str(DRIFT / "shop_v1.html"),
        str(DRIFT / "shop_v1_page2.html"),
        "-o",
        str(out),
    )

    assert result.exit_code == 0, result.stderr
    assert (
        Extractor.from_json(out.read_text(encoding="utf-8")).listing.member
        == "li.product"
    )
    assert "4 fields" in result.stderr


def test_run_exits_zero_when_the_page_keeps_its_contract(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json(), encoding="utf-8")

    result = _cli("run", str(out), str(DRIFT / "shop_v1.html"))

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["pages"][0]["ok"] is True
    assert len(payload["pages"][0]["rows"]) == 6


def test_run_exits_three_when_a_page_breaks_its_contract(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json(), encoding="utf-8")

    result = _cli(
        "run",
        str(out),
        str(DRIFT / "shop_v1.html"),
        str(DRIFT / "shop_prices_gone.html"),
    )

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert [p["ok"] for p in payload["pages"]] == [True, False]
    assert payload["pages"][1]["failed"][0]["name"] == "field"
    assert "span.price" in result.stderr


def test_heal_prints_what_moved_and_writes_only_when_asked(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json(), encoding="utf-8")
    healed = tmp_path / "healed.json"

    dry = _cli("heal", str(out), str(DRIFT / "shop_redesigned.html"))
    written = _cli(
        "heal", str(out), str(DRIFT / "shop_redesigned.html"), "-o", str(healed)
    )

    assert dry.exit_code == 0, dry.stderr
    assert not healed.exists() or written.exit_code == 0
    moved = [c for c in json.loads(dry.stdout)["changes"] if c["kind"] == "moved"]
    assert {
        "before": "span.price",
        "after": "div.cost",
        "kind": "moved",
        "evidence": {"seen": 5, "samples": 5, "runner_up": 0},
    } in moved
    assert "span.price -> div.cost" in dry.stderr
    assert Extractor.from_json(
        healed.read_text(encoding="utf-8")
    ).listing.container.endswith("section.grid")


def test_heal_exits_three_when_a_field_is_lost_for_good(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json(), encoding="utf-8")

    result = _cli("heal", str(out), str(DRIFT / "shop_prices_gone.html"))

    assert result.exit_code == 3
    assert "vanished: span.price" in result.stderr


def test_compile_with_nothing_to_learn_exits_one(tmp_path):
    bare = tmp_path / "bare.html"
    bare.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")

    result = _cli("compile", str(bare), "-o", str(tmp_path / "x.json"))

    assert result.exit_code == 1
    assert "nothing" in result.stderr


def test_a_summary_answer_that_changes_shape_fails_loudly():
    template = (
        '<html><head><script type="application/ld+json">'
        '{{"@type":"Product","name":"Pad","offers":{{"price":"{price}",'
        '"priceCurrency":"EUR"}}}}</script></head></html>'
    )
    extractor = compile_extractor(
        [(template.format(price="41.90"), None), (template.format(price="9.50"), None)]
    )

    run = run_extractor(extractor, template.format(price="41 EUR"))
    words = run_extractor(extractor, template.format(price="Call us"))

    assert extractor.summary["price"] == "NP"
    assert "shape" in failed(run)
    # Text with no number is no price at all, so the answer is gone: as loud.
    assert not words.ok
    assert "summary" in failed(words)


def test_healing_a_page_that_stopped_declaring_reports_what_was_lost():
    extractor = compile_extractor([page("product.html")])

    _healed, changes = heal(extractor, [page("product_without_jsonld.html")])

    lost = {(c.kind, c.before) for c in changes}
    assert ("summary-lost", "price") in lost
    assert ("type-lost", "Product") in lost


def test_healing_a_listing_that_is_gone_says_the_listing_was_lost():
    extractor = compile_extractor([page("shop_v1.html")])

    _healed, changes = heal(extractor, [page("product.html")])

    assert ("listing-lost", "html>body>div.page>ol.row", None) in {
        (c.kind, c.before, c.after) for c in changes
    }


def test_learning_from_no_page_is_refused():
    from sluicer.extractor import NothingToLearn

    with pytest.raises(NothingToLearn):
        compile_extractor([])


def test_a_path_that_does_not_start_at_the_root_finds_nothing():
    from sluicer.document import load
    from sluicer.extractor import _find

    doc = load("<html><body><ol class='row'></ol></body></html>")

    assert _find(doc, "body>ol.row")[0] is None
    assert _find(doc, "html>body>ol.row[2]")[0] is None
    assert _find(doc, "html>body>ol.row")[0] is not None


def test_run_refuses_a_file_that_is_not_an_extractor(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")

    result = _cli("run", str(bad), str(DRIFT / "shop_v1.html"))

    assert result.exit_code == 2
    assert "not an extractor" in result.stderr


def test_heal_from_pages_with_nothing_on_them_exits_three(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json(), encoding="utf-8")
    bare = tmp_path / "bare.html"
    bare.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")

    result = _cli("heal", str(out), str(bare))

    assert result.exit_code == 3
    assert "nothing to heal from" in result.stderr


def test_compile_names_what_it_learnt_from_a_declared_page(tmp_path):
    out = tmp_path / "product.json"

    result = _cli("compile", str(DRIFT / "product.html"), "-o", str(out))

    assert result.exit_code == 0, result.stderr
    assert "declared Product" in result.stderr
    assert Extractor.from_json(out.read_text(encoding="utf-8")).learnt_from == (
        str(DRIFT / "product.html"),
    )


def test_the_classes_of_html_and_body_are_not_part_of_a_path():
    """Modernizr swaps ``no-js`` for ``js``; templates stamp the page on body."""
    from sluicer.document import load
    from sluicer.extractor import path_of

    doc = load(
        '<html class="no-js"><body class="page-type-list">'
        '<ol class="row"><li>x</li></ol></body></html>'
    )

    assert path_of(doc.tree.xpath("//ol")[0]) == "html>body>ol.row"


def test_a_free_text_answer_keeps_no_shape():
    template = (
        '<html><head><title>{t}</title><meta name="description" content="{t}">'
        "</head></html>"
    )
    extractor = compile_extractor(
        [(template.format(t="Books"), None), (template.format(t="More books"), None)]
    )

    assert extractor.summary == {"title": None, "description": None}


def test_a_moved_field_says_what_its_move_rests_on():
    """Reported, never used to decide: a close runner-up is for a person."""
    _healed, changes = heal(shop(), [page("shop_redesigned.html")])

    price = next(c for c in changes if c.before == "span.price")

    assert price.kind == "moved"
    assert price.evidence == {"seen": 5, "samples": 5, "runner_up": 0}
    assert all(c.evidence is None for c in changes if c.kind in ("new", "vanished"))


# -- learnt from examples: --want ------------------------------------------------


def _two_listings(first_price: str = "£51.77") -> tuple[str, str]:
    """A page repeating two groups: a strip of offers, then the catalogue."""
    offers = "".join(
        f'<div class="offer"><b class="deal">Deal {n}</b>'
        f'<i class="cut">-{n}0%</i></div>'
        for n in range(1, 7)
    )
    books = [
        ("A Light in the Attic", first_price, "In stock"),
        ("Tipping the Velvet", "£53.74", "In stock"),
        ("Soumission", "£50.10", "In stock"),
        ("Sharp Objects", "£47.82", "Out of stock"),
        ("Sapiens", "£54.23", "In stock"),
        ("The Requiem Red", "£22.65", "In stock"),
    ]
    rows = "".join(
        f'<li class="book"><a class="title" href="/b/{n}">{title}</a>'
        f'<img class="cover" alt="{title}" src="/c/{n}.jpg">'
        f'<span class="price">{price}</span><span class="stock">{stock}</span></li>'
        for n, (title, price, stock) in enumerate(books, 1)
    )
    html = (
        "<html><body><aside>" + offers + "</aside>"
        '<main><ol class="books">' + rows + "</ol></main></body></html>"
    )
    return html, "https://shop.example/books"


def test_examples_choose_the_listing_and_name_its_columns():
    learnt = compile_extractor(
        [_two_listings()], want={"title": "A Light in the Attic", "price": "51.77"}
    )
    assert learnt.listing is not None
    assert learnt.listing.member == "li.book"
    assert [(f.name, f.path) for f in learnt.listing.fields] == [
        ("title", "a.title"),
        ("price", "span.price"),
    ]
    assert learnt.listing.fields[1].reads == "amount"
    assert learnt.notes == (
        "title='A Light in the Attic' was in 2 places in a row; the first, "
        "a.title, was taken",
    )


def test_an_example_learnt_extractor_replays_with_the_names_given():
    learnt = compile_extractor(
        [_two_listings()], want={"title": "A Light in the Attic", "price": "£51.77"}
    )
    run = run_extractor(learnt, *_two_listings("£9.99"))
    assert run.ok, failed(run)
    assert run.rows[0] == {"title": "A Light in the Attic", "price": "£9.99"}


def test_the_offers_strip_is_the_listing_when_the_examples_are_there():
    learnt = compile_extractor([_two_listings()], want={"deal": "Deal 3"})
    assert learnt.listing.member == "div.offer"
    assert [f.name for f in learnt.listing.fields] == ["deal"]


def test_an_example_no_row_holds_is_named():
    with pytest.raises(NothingToLearn, match=r"holds price='12.34'"):
        compile_extractor(
            [_two_listings()], want={"title": "Sapiens", "price": "12.34"}
        )


def test_examples_in_two_different_listings_are_read_as_the_pages_own():
    learnt = compile_extractor(
        [_two_listings()], want={"deal": "Deal 1", "title": "Sapiens"}
    )
    assert learnt.listing is None
    assert [f.path.rsplit(">", 2)[-2:] for f in learnt.fields] == [
        ["div.offer[1]", "b.deal"],
        ["li.book[5]", "a.title"],
    ]


def test_examples_may_come_from_any_of_the_pages():
    second = _two_listings()[0].replace("Sapiens", "Dune"), "https://shop.example/p2"
    learnt = compile_extractor([_two_listings(), second], want={"title": "Dune"})
    assert learnt.listing.member == "li.book"
    assert learnt.listing.rows == (6, 6)


def test_a_page_without_the_listing_is_noted_and_left_out():
    empty = "<html><body><p>Nothing here</p></body></html>", "https://shop.example/x"
    learnt = compile_extractor([_two_listings(), empty], want={"title": "Sapiens"})
    assert learnt.notes[-1].endswith("on 1 of 2 pages; the others were ignored")


def test_examples_need_a_name():
    with pytest.raises(ValueError, match="name=value"):
        compile_extractor([_two_listings()], want={" ": "Sapiens"})
    with pytest.raises(ValueError, match="name=value"):
        compile_extractor([_two_listings()], want={})


def test_heal_keeps_the_names_the_examples_gave():
    learnt = compile_extractor([_two_listings()], want={"title": "Sapiens"})
    moved = _two_listings()[0].replace('class="title"', 'class="name"')
    healed, changes = heal(learnt, [(moved, "https://shop.example/books")])
    run = run_extractor(healed, moved, url="https://shop.example/books")
    assert run.ok, failed(run)
    assert run.rows[0] == {"title": "A Light in the Attic"}, "no column added"
    assert [(c.kind, c.before, c.after) for c in changes] == [
        ("moved", "title", "a.name")
    ]
    assert healed.listing.chosen


def test_heal_finds_a_chosen_listing_in_the_furniture_by_its_values():
    learnt = compile_extractor([_two_listings()], want={"deal": "Deal 3"})
    moved = _two_listings()[0].replace('class="deal"', 'class="promo"')
    healed, changes = heal(learnt, [(moved, "https://shop.example/books")])
    assert healed.listing.member == "div.offer"
    assert [(c.kind, c.before, c.after) for c in changes] == [
        ("moved", "deal", "b.promo")
    ]


def test_heal_of_a_chosen_listing_reads_every_page_that_still_has_it():
    learnt = compile_extractor([_two_listings()], want={"title": "Sapiens"})
    closed = "<html><body><p>Closed</p></body></html>", "https://shop.example/x"
    healed, _changes = heal(learnt, [closed, _two_listings()])
    assert healed.listing.member == "li.book"
    assert healed.listing.rows == (6, 6)


def test_heal_of_a_chosen_listing_whose_values_are_gone_loses_it():
    learnt = compile_extractor([_two_listings()], want={"deal": "Deal 3"})
    gone = "<html><body><p>Closed</p></body></html>", "https://shop.example/books"
    with pytest.raises(NothingToLearn):
        heal(learnt, [gone])
    declared = (
        '<html><head><meta property="og:title" content="Shop"></head>'
        "<body><p>Closed</p></body></html>",
        "https://shop.example/books",
    )
    _healed, changes = heal(learnt, [declared])
    assert [c.kind for c in changes] == ["summary-gained", "listing-lost"]


def test_a_chosen_listing_is_kept_through_its_file_and_an_old_file_is_not_one():
    learnt = compile_extractor([_two_listings()], want={"title": "Sapiens"})
    text = learnt.to_json()
    assert '"chosen": true' in text
    assert Extractor.from_json(text) == learnt
    assert '"chosen"' not in shop().to_json()
    assert not Extractor.from_json(shop().to_json()).listing.chosen


def test_a_healed_listing_keeps_the_share_of_empty_rows_it_learnt():
    """heal rebuilt the listing without it, so a page with the spacer rows it
    always had failed the healed extractor."""
    rows = "".join(
        f'<li class="p"><a class="t" href="/{n}">Book {n}</a>'
        f'<span class="c">£{n}.00</span></li><li class="p"></li>'
        for n in range(1, 7)
    )
    page_ = f'<html><body><ol class="r">{rows}</ol></body></html>', "https://s.example/"
    learnt = compile_extractor([page_], listing=True)
    assert learnt.listing.empty == 0.5
    moved = page_[0].replace('class="c"', 'class="cost"'), page_[1]
    healed, _changes = heal(learnt, [moved])
    assert healed.listing.empty == 0.5
    assert run_extractor(healed, *moved).ok


def test_compile_takes_examples_on_the_command_line(tmp_path):
    source = tmp_path / "books.html"
    source.write_text(_two_listings()[0], encoding="utf-8")
    out = tmp_path / "books.json"
    result = _cli(
        "compile",
        str(source),
        "-o",
        str(out),
        "--want",
        "title=Sapiens",
        "--want",
        "price=£54.23",
    )
    assert result.exit_code == 0, result.stderr
    learnt = Extractor.from_json(out.read_text(encoding="utf-8"))
    assert [f.name for f in learnt.listing.fields] == ["title", "price"]
    bad = _cli("compile", str(source), "-o", str(out), "--want", "title")
    assert bad.exit_code == 2
    assert "NAME=VALUE" in bad.stderr
    missing = _cli("compile", str(source), "-o", str(out), "--want", "title=Nope")
    assert missing.exit_code == 1
    assert "no repeated group on these pages holds title='Nope'" in missing.stderr
    own = _cli(
        "compile", str(source), "-o", str(out), "--no-listing", "--want", "t=Sapiens"
    )
    assert own.exit_code == 0, own.stderr
    assert "1 page fields (t at " in own.stderr


# -- a page's own values, learnt from examples ----------------------------------


def _product(title="Brake pad set", price="£41.90", image="/i/1.jpg", extra=""):
    """A product page that declares nothing, with the title said three times."""
    related = "".join(
        f'<li class="rel"><a class="t" href="/p/{n}">Other pad {n}</a></li>'
        for n in range(1, 4)
    )
    html = (
        '<html><head><title>Shop</title><script>var p = {"price": "41.90"}</script>'
        '</head><body><ol class="breadcrumb"><li><a href="/">Home</a></li>'
        f'<li class="active">{title}</li></ol>'
        '<nav class="crumbs"><a href="/">Home</a><span>'
        f"{title}</span></nav>"
        f'<main><div class="item"><h1 class="name">{title}</h1>'
        f'<img class="photo" src="{image}" alt="photo">'
        f'<p class="cost"><span class="price">{price}</span></p>{extra}</div>'
        f'<ul class="related">{related}<li class="rel"><a class="t" href="/p/9">'
        f"{title}</a></li></ul></main></body></html>"
    )
    return html, "https://shop.example/p/1"


def test_a_product_page_that_declares_nothing_is_learnt_by_pointing():
    learnt = compile_extractor(
        [_product()],
        want={
            "title": "Brake pad set",
            "price": "41.90",
            "image": "https://shop.example/i/1.jpg",
        },
    )
    assert learnt.listing is None
    by_name = {f.name: f for f in learnt.fields}
    assert by_name["title"].path.endswith("main>div.item>h1.name"), "not the crumbs"
    assert by_name["price"].path.endswith("p.cost>span.price"), "not the script"
    assert by_name["price"].reads == "amount"
    assert by_name["image"].path.endswith("img.photo@src")
    assert by_name["image"].reads is None
    assert learnt.notes[0].startswith("title='Brake pad set' was in 4 places")


def test_a_learnt_product_page_replays_on_another_of_its_template():
    learnt = compile_extractor(
        [_product()], want={"title": "Brake pad set", "price": "41.90"}
    )
    run = run_extractor(learnt, *_product("Disc set", "£99.00"))
    assert run.ok, failed(run)
    assert run.fields == {"title": "Disc set", "price": "£99.00"}
    assert run.rows == []


def test_a_price_slot_that_holds_a_button_fails_loudly_on_a_product_page():
    learnt = compile_extractor([_product()], want={"price": "41.90"})
    button = run_extractor(learnt, *_product(price="Add to basket"))
    assert not button.ok
    assert failed(button) == ["reads"]
    gone = _product()[0].replace('<span class="price">£41.90</span>', "")
    missing = run_extractor(learnt, gone, url="https://shop.example/p/2")
    assert failed(missing) == ["field"]


def test_page_fields_are_learnt_across_every_page_given():
    pages = [_product(price=f"£{n}.50") for n in range(1, 7)]
    learnt = compile_extractor(pages, want={"price": "1.50"})
    [price] = learnt.fields
    assert price.shape is not None and price.reads == "amount"
    assert price.samples[:2] == ("£1.50", "£2.50")
    run = run_extractor(learnt, *_product(price="£10.50"))
    assert run.ok, failed(run)
    short = compile_extractor(
        [_product(), ("<html><body></body></html>", "https://shop.example/x")],
        want={"price": "41.90"},
    )
    assert short.notes[-1].endswith("on 1 of 2 pages")


def test_no_listing_reads_examples_as_the_pages_own_even_on_a_listing():
    learnt = compile_extractor([_two_listings()], listing=False, want={"t": "Sapiens"})
    assert learnt.listing is None
    assert learnt.fields[0].path.endswith("li.book[5]>a.title")


def test_an_example_that_is_nowhere_is_named_with_why_no_listing_held_it():
    with pytest.raises(NothingToLearn) as raised:
        compile_extractor([_product()], want={"sku": "BP-1"})
    assert str(raised.value) == (
        "no element on these pages holds sku='BP-1', and no repeated group on "
        "these pages holds sku='BP-1'"
    )
    with pytest.raises(NothingToLearn, match=r"^no element on these pages holds"):
        compile_extractor([_product()], listing=False, want={"sku": "BP-1"})


def test_page_fields_are_kept_through_the_file_and_an_old_file_has_none():
    learnt = compile_extractor([_product()], want={"price": "41.90"})
    text = learnt.to_json()
    assert "fields" in json.loads(text)
    assert Extractor.from_json(text) == learnt
    assert "fields" not in json.loads(shop().to_json())
    assert Extractor.from_json(shop().to_json()).fields == ()


def test_heal_keeps_moves_or_loses_each_page_field():
    learnt = compile_extractor(
        [_product()], want={"title": "Brake pad set", "price": "41.90"}
    )
    moved = _product()[0].replace('class="price"', 'class="amount"')
    healed, changes = heal(learnt, [(moved, "https://shop.example/p/1")])
    assert [(c.kind, c.before) for c in changes] == [("moved", "price")]
    assert run_extractor(healed, moved, url="https://shop.example/p/1").ok
    assert {f.name for f in healed.fields} == {"title", "price"}
    blank = _product(price="")[0].replace("Brake pad set", "Something else")
    _healed, lost = heal(learnt, [(blank, "https://shop.example/p/1")])
    assert ("vanished", "price") in [(c.kind, c.before) for c in lost]


def test_a_run_says_its_page_fields_on_the_command_line(tmp_path):
    source = tmp_path / "p.html"
    source.write_text(_product()[0], encoding="utf-8")
    out = tmp_path / "p.json"
    result = _cli("compile", str(source), "-o", str(out), "--want", "price=41.90")
    assert result.exit_code == 0, result.stderr
    assert "1 page fields (price at " in result.stderr
    ran = _cli("run", str(out), str(source))
    assert json.loads(ran.stdout)["pages"][0]["fields"] == {"price": "£41.90"}


def test_a_page_field_in_an_attribute_is_read_there_and_missed_when_gone():
    learnt = compile_extractor([_product()], want={"alt": "photo"})
    [alt] = learnt.fields
    assert alt.path.endswith("img.photo@alt")
    assert run_extractor(learnt, *_product()).fields == {"alt": "photo"}
    stripped = _product()[0].replace(' alt="photo"', "")
    assert failed(run_extractor(learnt, stripped, url="https://shop.example/p")) == [
        "field"
    ]


def test_a_hostile_page_is_searched_only_so_far(monkeypatch):
    monkeypatch.setattr("sluicer.extractor._MOST_ELEMENTS", 3)
    with pytest.raises(NothingToLearn, match="no element on these pages holds"):
        compile_extractor([_product()], listing=False, want={"price": "41.90"})


def test_a_value_split_across_elements_is_found_and_one_in_a_sentence_is_not():
    split = (
        '<html><body><p><span class="p">£41<small>.90</small></span></p></body></html>'
    )
    said = '<html><body><p class="c">Price: £41.90</p></body></html>'
    learnt = compile_extractor([(split, None)], listing=False, want={"price": "41.90"})
    assert learnt.fields[0].path.endswith("p>span.p")
    with pytest.raises(NothingToLearn):
        compile_extractor([(said, None)], listing=False, want={"price": "41.90"})


def test_the_search_never_reads_a_wrapper_holding_the_whole_page(monkeypatch):
    """Measured on a 1.5 MB page: every ancestor of the price is the page's text,
    and reading each as an amount took minutes. Now none longer than the
    example could be is read at all."""
    import sluicer.extractor as extractor_module

    seen: list[int] = []
    real = extractor_module.amount

    def counted(text):
        seen.append(len(text))
        return real(text)

    monkeypatch.setattr(extractor_module, "amount", counted)
    filler = "<p>" + "word " * 20_000 + "</p>"
    page_ = (
        f"<html><body><div><div>{filler}<span class='p'>£41.90</span></div></div>"
        "</body></html>"
    )
    learnt = compile_extractor([(page_, None)], listing=False, want={"price": "41.90"})
    assert learnt.fields[0].path.endswith("span.p")
    assert max(seen) <= 4 * len("41.90") + 256


def test_an_amount_is_never_a_page():
    from sluicer.normalise import amount

    assert amount("£41.90") == "41.90"
    assert amount("£" + "1" * 70) is None


def _spec(n: int, price: str, saving: str | None = None, isbn: str = "978000000000"):
    """A product page that declares nothing, its facts in a table whose rows
    depend on the product: a saving row appears only when there is one, and
    moves the price down. The ISBN shares its item with its label."""
    rows = [f"<tr><th>Title</th><td>Book {n}</td></tr>"]
    if saving is not None:
        rows.append(f"<tr><th>You save</th><td>{saving}</td></tr>")
    rows.append(f"<tr><th>Price:</th><td>{price}</td></tr>")
    html = (
        "<html><head><title>Books</title></head><body><nav><a href='/'>Home</a>"
        f"</nav><main><table class='facts'>{''.join(rows)}</table><ul>"
        f"<li><b>ISBN:</b> {isbn}</li><li>Pages: 3{n}0</li></ul></main>"
        "<footer>Books &amp; more</footer></body></html>"
    )
    return html, f"https://books.example/b/{n}"


def test_a_place_the_other_pages_contradict_is_read_after_its_label():
    """On one of the three pages the price's place holds the saving: the row
    before it moved it. The pages given say so, and the label says where the
    price is on every one of them."""
    pages = [_spec(1, "$12.00"), _spec(2, "$8.50"), _spec(3, "$9.99", "$3.00 (23%)")]
    learnt = compile_extractor(pages, listing=False, want={"price": "$12.00"})
    [price] = learnt.fields
    assert price.anchor is not None and price.anchor.label == "Price:"
    assert any("Price:" in note for note in learnt.notes)
    for n, value, saving in ((4, "$7.25", "$1.00 (12%)"), (5, "$20.00", None)):
        run = run_extractor(learnt, *_spec(n, value, saving))
        assert run.ok, failed(run)
        assert run.fields == {"price": value}


def test_a_place_the_other_pages_agree_with_stays_a_place():
    pages = [_spec(n, f"${n}.00") for n in (1, 2, 3)]
    learnt = compile_extractor(pages, listing=False, want={"price": "$1.00"})
    [price] = learnt.fields
    assert price.anchor is None
    assert price.path.endswith("td")


def test_a_value_that_shares_its_element_with_its_label_is_learnt():
    """``<li><b>ISBN:</b> 978...</li>``: no element's whole text is the value,
    and 0.6 could not learn it at all."""
    pages = [_spec(n, "$1.00", isbn=f"97800000000{n}") for n in (1, 2, 3)]
    learnt = compile_extractor(pages, listing=False, want={"isbn": "978000000001"})
    [isbn] = learnt.fields
    assert isbn.anchor is not None and isbn.anchor.label == "ISBN:"
    run = run_extractor(learnt, *_spec(7, "$1.00", isbn="9780441017775"))
    assert run.ok, failed(run)
    assert run.fields == {"isbn": "9780441017775"}


def test_a_value_after_a_label_in_the_same_text_is_learnt():
    pages = [_spec(n, "$1.00") for n in (1, 2, 3)]
    learnt = compile_extractor(pages, listing=False, want={"pages": "310"})
    [count] = learnt.fields
    assert count.anchor is not None and count.anchor.label == "Pages:"
    assert run_extractor(learnt, *_spec(4, "$1.00")).fields == {"pages": "340"}


def test_a_page_without_the_label_fails_loudly():
    pages = [_spec(1, "$12.00"), _spec(2, "$8.50"), _spec(3, "$9.99", "$3.00 (23%)")]
    learnt = compile_extractor(pages, listing=False, want={"price": "$12.00"})
    html, url = _spec(4, "$5.00")
    run = run_extractor(learnt, html.replace("Price:", "Cost:"), url)
    assert not run.ok
    assert failed(run) == ["field"]
    assert "price" not in run.fields
    doubled = html.replace("<footer>", "<p>Price:</p><footer>")
    assert failed(run_extractor(learnt, doubled, url)) == ["field"]


def test_an_anchored_extractor_is_kept_as_format_two_and_read_back():
    """A 0.6 reader would read the place alone and never the label: a file
    with a label is format 2, which 0.6 refuses; one without stays format 1."""
    pages = [_spec(1, "$12.00"), _spec(2, "$8.50"), _spec(3, "$9.99", "$3.00 (23%)")]
    learnt = compile_extractor(pages, listing=False, want={"price": "$12.00"})
    text = learnt.to_json()
    assert json.loads(text)["format"] == 2
    again = Extractor.from_json(text)
    assert again.fields == learnt.fields
    plain = compile_extractor([_product()], want={"price": "41.90"})
    assert json.loads(plain.to_json())["format"] == 1
    assert Extractor.from_json(plain.to_json()).fields == plain.fields


def test_heal_follows_a_field_to_its_new_label():
    pages = [_spec(1, "$12.00"), _spec(2, "$8.50"), _spec(3, "$9.99", "$3.00 (23%)")]
    learnt = compile_extractor(pages, listing=False, want={"price": "$12.00"})
    redesigned = [
        (html.replace("Price:", "Our price"), url)
        for html, url in (_spec(1, "$12.00"), _spec(2, "$8.50"))
    ]
    assert failed(run_extractor(learnt, *redesigned[0])) == ["field"]
    healed, changes = heal(learnt, redesigned)
    [price] = healed.fields
    assert price.anchor is not None and price.anchor.label == "Our price"
    assert [(c.kind, c.before) for c in changes if c.before == "price"] == [
        ("moved", "price")
    ]
    run = run_extractor(
        healed,
        *(html.replace("Price:", "Our price") for html in [_spec(6, "$4.40")[0]]),
        "https://books.example/b/6",
    )
    assert run.ok, failed(run)
    assert run.fields == {"price": "$4.40"}


def _books(item: str) -> tuple[str, str]:
    titles = ["Sapiens", "Soumission", "Sharp Objects", "The Requiem Red", "Tipping"]
    rows = "".join(item.format(title=t, n=n) for n, t in enumerate(titles, 1))
    return (
        f'<html><body><ol class="books">{rows}</ol></body></html>',
        "https://shop.example/",
    )


def test_heal_refuses_a_move_two_new_places_have_equal_claim_to():
    """The title's old values are in two new places, as many in each, both
    the same kind of element, and on the other redesigned page those places
    say different things: which one is the title is a guess, and heal says so
    instead of making it, leaving the field out."""
    before = (
        '<li class="book"><span class="title">{title}</span>'
        '<span class="price">£{n}.00</span></li>'
    )
    after = (
        '<li class="book"><span class="name">{title}</span>'
        '<span class="also">{title}</span><span class="price">£{n}.00</span></li>'
    )
    other = after.replace('<span class="also">{title}', '<span class="also">Series {n}')
    learnt = compile_extractor([_books(before)], listing=True)
    newer = [
        _books(after),
        (_books(other)[0].replace("Sapiens", "Dune"), "https://shop.example/2"),
    ]
    healed, changes = heal(learnt, newer)
    [title] = [c for c in changes if c.before == "span.title"]
    assert title.kind == "ambiguous"
    assert title.evidence is not None
    assert title.evidence["seen"] == title.evidence["runner_up"]
    assert "span.title" not in [f.name for f in healed.listing.fields]
    from sluicer.extractor import LOSSES

    assert "ambiguous" in LOSSES


def test_a_tie_the_old_element_s_kind_decides_is_a_move():
    """Two places hold the old title's values alike, but only one is a link,
    as the old title was, and its address moved there too."""
    before = (
        '<li class="book"><a class="title" href="/b/{n}">{title}</a>'
        '<span class="price">£{n}.00</span></li>'
    )
    after = (
        '<li class="book"><a class="name" href="/b/{n}">{title}</a>'
        '<span class="also">{title}</span><span class="price">£{n}.00</span></li>'
    )
    learnt = compile_extractor([_books(before)], listing=True)
    _healed, changes = heal(learnt, [_books(after)])
    [title] = [c for c in changes if c.before == "a.title"]
    assert (title.kind, title.after) == ("moved", "a.name")


def test_two_new_places_holding_the_same_values_are_no_tie_to_refuse():
    """A film's poster and its title both link to the film: the two new links
    hold the same addresses, so either reads the old link's values right."""
    before = (
        '<li class="film"><a class="poster" href="/f/{n}"><img alt="p"></a>'
        '<a class="title" href="/f/{n}">{title}</a></li>'
    )
    after = (
        '<li class="film"><a class="pic" href="/f/{n}"><img alt="p"></a>'
        '<a class="name" href="/f/{n}">{title}</a></li>'
    )
    learnt = compile_extractor([_books(before)], listing=True)
    _healed, changes = heal(learnt, [_books(after)])
    links = [c for c in changes if c.before and c.before.endswith("@href")]
    assert links and all(c.kind == "moved" for c in links), [
        (c.kind, c.before, c.after) for c in links
    ]


def test_links_to_the_same_places_with_other_tracking_tags_read_alike():
    """IMDb's poster links carry ?ref_=chttp_i_1 and its title links
    ?ref_=chttp_t_1: both go to the film."""
    before = (
        '<li class="film"><a class="poster" href="/f/{n}"><img alt="p"></a>'
        '<a class="title" href="/f/{n}">{title}</a></li>'
    )
    after = (
        '<li class="film"><a class="pic" href="/f/{n}?ref_=i_{n}"><img alt="p"></a>'
        '<a class="name" href="/f/{n}?ref_=t_{n}">{title}</a></li>'
    )
    learnt = compile_extractor([_books(before)], listing=True)
    _healed, changes = heal(learnt, [_books(after)])
    links = [c for c in changes if c.before and c.before.endswith("@href")]
    assert links and all(c.kind == "moved" for c in links), [
        (c.kind, c.before, c.after) for c in links
    ]


def _contao(type_="contao:Page", context=True) -> tuple[str, str]:
    """A page as Contao writes it: its JSON-LD names its own type by a prefix
    its context defines."""
    words = (
        '{"@vocab": "https://schema.org/", "contao": "https://schema.contao.org/"}'
        if context
        else '"https://schema.org"'
    )
    block = (
        f'{{"@context": {words}, "@type": ["{type_}", "WebPage"],'
        ' "name": "Research group"}'
    )
    return (
        "<html><head><title>Research group</title>"
        f'<script type="application/ld+json">{block}</script></head>'
        "<body><h1>Research group</h1></body></html>",
        "https://institute.example/group",
    )


# As 0.7.1 wrote it for _contao(): a type named as the page wrote it.
CONTAO_071 = {
    "format": 1,
    "sluicer": "0.7.1",
    "learnt_from": ["https://institute.example/group"],
    "summary": {},
    "types": ["WebPage", "contao:Page"],
    "listing": None,
}


def test_a_type_an_extractor_before_0_8_named_as_written_is_the_same_type():
    """0.8 names a type of another vocabulary by its address, and an
    extractor 0.7.1 compiled from a page declaring ``contao:Page`` failed the
    same page unchanged: "a declared contao:Page", none. Heal called it lost,
    and wrote nothing. A file from before 0.8 is read with either spelling;
    heal writes the address."""
    old = Extractor.from_json(json.dumps(CONTAO_071))
    assert compile_extractor([_contao()]).types == (
        "WebPage",
        "https://schema.contao.org/Page",
    )

    run = run_extractor(old, *_contao())
    assert run.ok, [(c.expected, c.got) for c in run.checks if not c.ok]
    healed, changes = heal(old, [_contao()])
    assert [c for c in changes if c.kind.startswith("type")] == []
    assert healed.types == ("WebPage", "https://schema.contao.org/Page")

    # Another vocabulary's Page, or none, is still no contao:Page.
    other = run_extractor(old, *_contao("https://other.example/ns/Page"))
    assert failed(other) == ["type"]
    gone = run_extractor(old, *_contao("Thing"))
    assert failed(gone) == ["type"]
    # And 0.8's own file holds the page to the address alone.
    new = compile_extractor([_contao()])
    assert failed(run_extractor(new, *_contao("contao:Page", context=False))) == [
        "type"
    ]
