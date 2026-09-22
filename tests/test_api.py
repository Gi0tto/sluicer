from pathlib import Path

import sluicer

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_reports_records_and_which_readers_fired():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, url="https://example.com/p")

    assert result.url == "https://example.com/p"
    assert result.sources == ["jsonld"]
    assert any(r.fields.get("sku") and r.fields["sku"].value == "BP-1187" for r in result.records)


def test_a_page_declaring_nothing_extracts_nothing_and_says_so():
    result = sluicer.extract((FIXTURES / "plain.html").read_text())

    assert result.records == []
    assert result.sources == []


def test_extraction_is_deterministic():
    html = (FIXTURES / "product_jsonld.html").read_text()

    first = sluicer.extract(html)
    second = sluicer.extract(html)

    assert first == second
