from pathlib import Path

import sluicer

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_reports_records_and_which_readers_fired():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, url="https://example.com/p")

    assert result.url == "https://example.com/p"
    assert result.sources == ["jsonld"]
    assert any(r.fields.get("sku") and r.fields["sku"].value == "ATD-1187" for r in result.records)


def test_a_page_declaring_nothing_extracts_nothing_and_says_so():
    result = sluicer.extract((FIXTURES / "plain.html").read_text())

    assert result.records == []
    assert result.sources == []


def test_extraction_is_deterministic():
    html = (FIXTURES / "product_jsonld.html").read_text()

    first = sluicer.extract(html)
    second = sluicer.extract(html)

    assert first == second


def test_a_page_lxml_cannot_parse_extracts_nothing_instead_of_raising():
    result = sluicer.extract("<!doctype html>")

    assert result.records == []
    assert result.sources == []


def test_a_page_whose_type_is_a_list_extracts_instead_of_crashing():
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type": ["Person", "Organization"], "name": "Acme"}'
        "</script></head><body></body></html>"
    )

    result = sluicer.extract(html)

    assert result.sources == ["jsonld"]
    assert result.records[0].type == "Person"
    assert result.records[0].fields["name"].value == "Acme"


def test_all_three_readers_fold_into_one_record_and_each_keeps_its_source():
    html = (FIXTURES / "product_all_three.html").read_text()

    result = sluicer.extract(html, url="https://example.com/p")

    assert result.sources == ["jsonld", "microdata", "opengraph"]
    assert len(result.records) == 1

    record = result.records[0]
    assert record.type == "Product"

    # All three vocabularies declare a description, and they disagree.
    # JSON-LD has precedence, and the value says where it came from.
    assert record.fields["description"] == sluicer.Field(
        value="Described by JSON-LD", source="jsonld"
    )

    # Each reader contributed the field the other two lack.
    assert record.fields["sku"] == sluicer.Field(value="ATD-1187", source="jsonld")
    assert record.fields["mpn"] == sluicer.Field(value="GDB1330", source="microdata")
    assert record.fields["image"] == sluicer.Field(
        value="https://example.com/brake-pad-set.jpg", source="opengraph"
    )


def test_an_xhtml_page_with_an_encoding_declaration_still_extracts():
    html = (FIXTURES / "product_xhtml.html").read_text()

    result = sluicer.extract(html)

    assert result.sources == ["jsonld"]
    assert len(result.records) == 1
    assert result.records[0].type == "Product"
    assert result.records[0].fields["name"].value == "Wiper blade set"
    assert result.records[0].fields["sku"].value == "ATD-3041"


def test_a_declaration_that_disagrees_with_the_bytes_does_not_mangle_the_text():
    html = (FIXTURES / "product_latin1_declared.html").read_text(encoding="utf-8")

    result = sluicer.extract(html)

    assert result.sources == ["jsonld"]
    assert result.records[0].fields["name"].value == "Bremsöl"
    assert result.records[0].fields["sku"].value == "ATD-7712"
