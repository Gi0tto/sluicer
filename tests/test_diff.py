import json

from click.testing import CliRunner

from sluicer import extract
from sluicer.cli import main
from sluicer.diff import compare


def _product(price, availability="InStock", extra=""):
    return (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "Product",
                "name": "Pads",
                "offers": {
                    "price": price,
                    "priceCurrency": "EUR",
                    "availability": f"https://schema.org/{availability}",
                },
            }
        )
        + "</script>"
        + extra
    )


def test_a_new_price_and_availability_are_changes_naming_their_source():
    before = extract(_product("41.90"))
    after = extract(_product("39.90", "OutOfStock"))

    found = {d.question: d for d in compare(before, after)}

    assert found["price"].kind == "changed"
    assert (found["price"].before, found["price"].after) == ("41.90", "39.90")
    assert found["price"].after_source == "jsonld Product.offers.price"
    assert found["availability"].after == "OutOfStock"


def test_the_same_price_written_differently_is_rewritten_not_changed():
    found = compare(extract(_product("41.90")), extract(_product("41.9")))

    assert [(d.question, d.kind) for d in found] == [("price", "rewritten")]


def test_a_page_that_starts_reserving_its_rights_is_an_addition():
    reserved = _product("41.90", extra='<meta name="tdm-reservation" content="1">')

    found = compare(extract(_product("41.90")), extract(reserved))

    assert [(d.question, d.kind, d.after) for d in found] == [
        ("rights.tdm_reservation", "added", '"1"')
    ]


def test_two_identical_readings_differ_in_nothing():
    assert compare(extract(_product("41.90")), extract(_product("41.90"))) == []


def test_the_diff_command_exits_as_diff_does(tmp_path):
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    a.write_text(_product("41.90"))
    b.write_text(_product("39.90"))

    same = CliRunner().invoke(main, ["diff", str(a), str(a)])
    changed = CliRunner().invoke(main, ["diff", str(a), str(b)])
    as_json = CliRunner().invoke(main, ["diff", "--json", str(a), str(b)])
    missing = CliRunner().invoke(main, ["diff", str(a), str(tmp_path / "none.html")])

    assert same.exit_code == 0 and same.stdout == ""
    assert changed.exit_code == 1
    assert "* price: 41.90 -> 39.90  [jsonld Product.offers.price]" in changed.stdout
    assert json.loads(as_json.stdout)[0]["question"] == "price"
    assert missing.exit_code == 2
