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
    a.write_text(_product("41.90"), encoding="utf-8")
    b.write_text(_product("39.90"), encoding="utf-8")

    same = CliRunner().invoke(main, ["diff", str(a), str(a)])
    changed = CliRunner().invoke(main, ["diff", str(a), str(b)])
    as_json = CliRunner().invoke(main, ["diff", "--json", str(a), str(b)])
    missing = CliRunner().invoke(main, ["diff", str(a), str(tmp_path / "none.html")])

    assert same.exit_code == 0 and same.stdout == ""
    assert changed.exit_code == 1
    assert "* price: 41.90 -> 39.90  [jsonld Product.offers.price]" in changed.stdout
    assert json.loads(as_json.stdout)[0]["question"] == "price"
    assert missing.exit_code == 2


def _priced(price):
    return (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "Product", "name": "Pads", "offers": {"price": price}})
        + "</script>"
    )


def test_a_price_in_another_currency_is_a_change_not_a_rewrite():
    """£41.90 and $41.90 are the same number and not the same price: read as
    amounts alone, a site that switched its currency was noise."""
    found = compare(extract(_priced("£41.90")), extract(_priced("$41.90")))
    assert [(d.question, d.kind) for d in found] == [("price", "changed")]


def test_a_currency_written_as_its_code_or_its_sign_is_a_rewrite():
    found = compare(extract(_priced("£41.90")), extract(_priced("41.9 GBP")))
    assert [(d.question, d.kind) for d in found] == [("price", "rewritten")]


def test_a_bare_price_is_in_the_currency_its_page_declares():
    declared = _product("41.90")  # priceCurrency EUR
    found = compare(extract(declared), extract(_priced("41.90 EUR")))
    assert ("price", "rewritten") in [(d.question, d.kind) for d in found]
    found = compare(extract(declared), extract(_priced("£41.90")))
    assert ("price", "changed") in [(d.question, d.kind) for d in found]


def test_a_price_json_writes_with_an_exponent_names_no_currency():
    """``1.5e3`` is 1500 as JSON may write it: its ``e`` is the exponent's, not
    a currency sign, and a price written either way is a rewrite."""
    found = compare(extract(_priced("1500")), extract(_priced("1.5e3")))
    assert [(d.question, d.kind) for d in found] == [("price", "rewritten")]
    found = compare(extract(_priced("1500")), extract(_priced("1.5E+3")))
    assert [(d.question, d.kind) for d in found] == [("price", "rewritten")]
    found = compare(extract(_priced("£1500")), extract(_priced("1.5e3")))
    assert [(d.question, d.kind) for d in found] == [("price", "changed")]


def test_diff_refuses_standard_input_for_both_pages():
    """Measured on 0.9.0 (inventory audit, B24): `sluicer diff - -` read
    stdin twice and said "Standard input contains no HTML." of the page it
    had just read."""
    from click.testing import CliRunner

    from sluicer.cli import main

    result = CliRunner().invoke(main, ["diff", "-", "-"], input="<title>A</title>")

    assert result.exit_code == 2
    assert "Standard input is one page" in result.stderr
