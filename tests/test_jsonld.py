from pathlib import Path

from sluicer.declared.jsonld import read_jsonld
from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_a_product_block():
    doc = load((FIXTURES / "product_jsonld.html").read_text())

    found = read_jsonld(doc)

    assert {"Product", "BreadcrumbList"} == {item["@type"] for item in found}
    product = next(i for i in found if i["@type"] == "Product")
    assert product["name"] == "Brake pad set"
    assert product["offers"]["price"] == "41.99"


def test_a_malformed_block_is_skipped_not_fatal():
    doc = load(
        '<html><head>'
        '<script type="application/ld+json">{"@type": "Thing"}</script>'
        '<script type="application/ld+json">{not json at all</script>'
        "</head><body></body></html>"
    )

    found = read_jsonld(doc)

    assert found == [{"@type": "Thing"}]


def test_the_media_type_is_matched_whatever_its_case_spacing_or_parameters():
    doc = load(
        "<html><head>"
        '<script type="application/ld+json;charset=UTF-8">{"@type": "A"}</script>'
        '<script type="application/LD+JSON">{"@type": "B"}</script>'
        '<script type="  application/ld+json  ">{"@type": "C"}</script>'
        "</head><body></body></html>"
    )

    assert [item["@type"] for item in read_jsonld(doc)] == ["A", "B", "C"]


def test_a_script_of_another_media_type_is_not_read():
    doc = load(
        "<html><head>"
        '<script type="application/json">{"@type": "Not linked data"}</script>'
        "</head><body></body></html>"
    )

    assert read_jsonld(doc) == []
