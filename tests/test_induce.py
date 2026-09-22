from pathlib import Path

import sluicer
from sluicer.document import load
from sluicer.induce import induce

FIXTURES = Path(__file__).parent / "fixtures"


def listing():
    return load((FIXTURES / "listing_no_declared_data.html").read_text())


def test_a_page_that_declares_nothing_still_yields_records():
    records = induce(listing())

    assert len(records) == 4


def test_every_induced_field_says_it_was_induced():
    records = induce(listing())

    for record in records:
        for field in record.fields.values():
            assert field.source == "induced"


def test_the_values_are_the_ones_on_the_page():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "Brake pad set" in values
    assert "41.99" in values


def test_a_link_keeps_its_address():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "/p/1" in values


def test_induction_is_off_unless_asked():
    html = (FIXTURES / "listing_no_declared_data.html").read_text()

    assert sluicer.extract(html).records == []
    assert sluicer.extract(html, induce=True).records


def test_a_page_that_declares_data_is_not_second_guessed():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld"], "declared data stands on its own"


def test_a_part_with_nothing_in_it_is_not_a_field():
    """An empty element said nothing, so it contributes no field."""
    doc = load("<div>" + "<li><h3>t</h3><span></span></li>" * 3 + "</div>")

    records = induce(doc)

    assert [len(record.fields) for record in records] == [1, 1, 1]


def test_a_group_of_empty_shells_yields_no_records():
    """A record with no fields is not a record, so it is not returned."""
    doc = load("<div>" + "<li><span></span></li>" * 3 + "</div>")

    assert induce(doc) == []
