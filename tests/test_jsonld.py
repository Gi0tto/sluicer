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
        "<html><head>"
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


def _one(body: str) -> list:
    return read_jsonld(load(f'<script type="application/ld+json">{body}</script>'))


def test_a_raw_newline_inside_a_string_does_not_lose_the_block():
    """JSON forbids it, every CMS writes it, and a browser's consumers accept it."""
    assert _one('{"@type": "Product", "description": "line one\nline two"}') == [
        {"@type": "Product", "description": "line one\nline two"}
    ]


def test_a_block_wrapped_in_a_comment_or_cdata_is_still_read():
    for body in (
        '<!-- {"@type": "Product", "name": "Pad"} -->',
        '//<![CDATA[\n{"@type": "Product", "name": "Pad"}\n//]]>',
        '/*<![CDATA[*/{"@type": "Product", "name": "Pad"}/*]]>*/',
        '﻿{"@type": "Product", "name": "Pad"}',
    ):
        assert _one(body) == [{"@type": "Product", "name": "Pad"}], body


def test_a_trailing_comma_does_not_lose_the_block():
    assert _one('{"@type": "Product", "name": "Pad", "sku": ["A", "B",],}') == [
        {"@type": "Product", "name": "Pad", "sku": ["A", "B"]}
    ]


def test_not_a_number_is_not_a_value():
    from sluicer import extract

    html = '<script type="application/ld+json">{"@type":"Offer","price":NaN}</script>'

    assert extract(html).records == []


def test_a_hostile_block_is_skipped_rather_than_crashing_the_call():
    from sluicer import extract

    html = (
        '<script type="application/ld+json">'
        + "[" * 100_000
        + "]" * 100_000
        + '</script><script type="application/ld+json">'
        '{"@type": "Product", "name": "Pad"}</script>'
    )

    assert [r.type for r in extract(html).records] == ["Product"]


def test_a_block_nested_nearly_as_deep_as_json_allows_is_still_survivable():
    from sluicer import extract

    deep = '{"a":' * 900 + '"x"' + "}" * 900
    html = (
        f'<script type="application/ld+json">{{"@type":"Thing","n":"1","d":{deep}}}'
        "</script>"
    )

    assert extract(html).records[0].fields["n"].value == "1"


def test_a_block_at_the_edge_of_the_parser_never_escapes_as_a_recursion_error():
    import sys

    from sluicer import extract

    for depth in range(sys.getrecursionlimit() - 60, sys.getrecursionlimit(), 7):
        deep = '{"a":' * depth + '"x"' + "}" * depth
        html = f'<script type="application/ld+json">{deep}</script>'
        extract(html)
