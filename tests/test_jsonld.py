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
