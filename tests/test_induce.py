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


def test_a_crowded_head_does_not_silence_the_page():
    """The reviewer's first constructed page: 14 metas must not be the answer."""
    doc = load((FIXTURES / "listing_under_a_crowded_head.html").read_text())

    records = induce(doc)

    assert len(records) == 5
    assert "Cabin filter" in {
        field.value for field in records[0].fields.values()
    }


def test_the_sidebar_is_not_the_content():
    """The reviewer's second constructed page: the articles, not the widgets."""
    doc = load((FIXTURES / "listing_between_sidebar_and_footer.html").read_text())

    records = induce(doc)

    assert len(records) == 5
    assert "Ana Petrova" in {field.value for field in records[0].fields.values()}


def test_the_next_group_is_read_when_the_best_one_yields_nothing():
    """The best-ranked shape can still hold no field: the ranking is a guess."""
    doc = load(
        "<main>"
        "<ul>"
        + "<li>a line of prose that sits directly in the item, in no element</li>" * 7
        + "</ul>"
        "<div>" + "<div class='c'><h3>Title</h3><span>9.99</span></div>" * 3 + "</div>"
        "</main>"
    )

    records = induce(doc)

    assert len(records) == 3
    assert "Title" in {field.value for field in records[0].fields.values()}


def test_induction_reads_the_best_group_and_not_another_one():
    """Two groups both yield records; the ranked-first one is what comes back."""
    doc = load(
        "<main>"
        "<ul>" + "<li><a href='/t'>x</a></li>" * 6 + "</ul>"
        "<div>"
        + "<article><h3>Real title here</h3><p>Body text</p></article>" * 4
        + "</div>"
        "</main>"
    )

    records = induce(doc)

    assert len(records) == 4
    assert "Real title here" in {field.value for field in records[0].fields.values()}


def test_two_of_a_kind_is_not_induced_either():
    """``induce`` carries the same floor, and carries it as a default."""
    doc = load("<main><ul>" + "<li><h3>t</h3><span>1</span></li>" * 2 + "</ul></main>")

    assert induce(doc) == []
    assert len(induce(doc, minimum=2)) == 2


def test_a_part_with_nothing_in_it_is_not_a_field():
    """An empty element said nothing, so it contributes no field."""
    doc = load("<div>" + "<li><h3>t</h3><span></span></li>" * 3 + "</div>")

    records = induce(doc)

    assert [len(record.fields) for record in records] == [1, 1, 1]


def test_a_group_of_empty_shells_yields_no_records():
    """A record with no fields is not a record, so it is not returned."""
    doc = load("<div>" + "<li><span></span></li>" * 3 + "</div>")

    assert induce(doc) == []
