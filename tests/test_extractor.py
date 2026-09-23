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
    assert failed(run) == ["shape"]


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
    assert Extractor.from_json(out.read_text()).listing.member == "li.product"
    assert "4 fields" in result.stderr


def test_run_exits_zero_when_the_page_keeps_its_contract(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json())

    result = _cli("run", str(out), str(DRIFT / "shop_v1.html"))

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["pages"][0]["ok"] is True
    assert len(payload["pages"][0]["rows"]) == 6


def test_run_exits_three_when_a_page_breaks_its_contract(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json())

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
    out.write_text(shop().to_json())
    healed = tmp_path / "healed.json"

    dry = _cli("heal", str(out), str(DRIFT / "shop_redesigned.html"))
    written = _cli(
        "heal", str(out), str(DRIFT / "shop_redesigned.html"), "-o", str(healed)
    )

    assert dry.exit_code == 0, dry.stderr
    assert not healed.exists() or written.exit_code == 0
    moved = [c for c in json.loads(dry.stdout)["changes"] if c["kind"] == "moved"]
    assert {"before": "span.price", "after": "div.cost", "kind": "moved"} in moved
    assert "span.price -> div.cost" in dry.stderr
    assert Extractor.from_json(healed.read_text()).listing.container.endswith(
        "section.grid"
    )


def test_heal_exits_three_when_a_field_is_lost_for_good(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json())

    result = _cli("heal", str(out), str(DRIFT / "shop_prices_gone.html"))

    assert result.exit_code == 3
    assert "vanished: span.price" in result.stderr


def test_compile_with_nothing_to_learn_exits_one(tmp_path):
    bare = tmp_path / "bare.html"
    bare.write_text("<html><body><p>x</p></body></html>")

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

    run = run_extractor(extractor, template.format(price="Call us"))

    assert extractor.summary["price"] == "NP"
    assert "shape" in failed(run)


def test_healing_a_page_that_stopped_declaring_reports_what_was_lost():
    extractor = compile_extractor([page("product.html")])

    _healed, changes = heal(extractor, [page("product_without_jsonld.html")])

    lost = {(c.kind, c.before) for c in changes}
    assert ("summary-lost", "price") in lost
    assert ("type-lost", "Product") in lost


def test_healing_a_listing_that_is_gone_says_the_container_went():
    extractor = compile_extractor([page("shop_v1.html")])

    _healed, changes = heal(extractor, [page("product.html")])

    assert ("container", "html>body>div.page>ol.row", None) in {
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

    assert _find(doc, "body>ol.row") is None
    assert _find(doc, "html>body>ol.row[2]") is None
    assert _find(doc, "html>body>ol.row") is not None


def test_run_refuses_a_file_that_is_not_an_extractor(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")

    result = _cli("run", str(bad), str(DRIFT / "shop_v1.html"))

    assert result.exit_code == 2
    assert "not an extractor" in result.stderr


def test_heal_from_pages_with_nothing_on_them_exits_three(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(shop().to_json())
    bare = tmp_path / "bare.html"
    bare.write_text("<html><body><p>x</p></body></html>")

    result = _cli("heal", str(out), str(bare))

    assert result.exit_code == 3
    assert "nothing to heal from" in result.stderr


def test_compile_names_what_it_learnt_from_a_declared_page(tmp_path):
    out = tmp_path / "product.json"

    result = _cli("compile", str(DRIFT / "product.html"), "-o", str(out))

    assert result.exit_code == 0, result.stderr
    assert "declared Product" in result.stderr
    assert Extractor.from_json(out.read_text()).learnt_from == (
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
    template = "<html><head><title>{t}</title></head></html>"
    extractor = compile_extractor(
        [(template.format(t="Books"), None), (template.format(t="More books"), None)]
    )

    assert extractor.summary == {"title": None}
