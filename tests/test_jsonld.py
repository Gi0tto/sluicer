from pathlib import Path

from sluicer.declared.jsonld import _parse, read_jsonld
from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_a_product_block():
    doc = load((FIXTURES / "product_jsonld.html").read_text(encoding="utf-8"))

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


def test_a_block_with_javascript_comments_is_still_read():
    """extruct strips them, and pages write them; strings keep their slashes."""
    body = (
        '{"@type": "Product", // the product\n'
        ' "name": "Pad // not a comment /* nor this */",'
        ' /* its address */ "url": "https://shop.example/p", // last\n}'
    )

    assert _one(body) == [
        {
            "@type": "Product",
            "name": "Pad // not a comment /* nor this */",
            "url": "https://shop.example/p",
        }
    ]


def test_a_comment_left_open_ends_the_block_and_never_the_reading():
    assert _one('{"@type": "Product", "name": "Pad"} /* left open') == [
        {"@type": "Product", "name": "Pad"}
    ]


def test_mending_a_trailing_comma_leaves_the_text_of_strings_alone():
    """``,\\s*]`` inside a string is text: "Pad, ]" was mended into "Pad]"."""
    body = (
        '{"@type": "Product", "name": "Pad, ]", "description": "A, }",'
        ' "q": "say \\", }", "sku": ["A", "B",],}'
    )

    assert _one(body) == [
        {
            "@type": "Product",
            "name": "Pad, ]",
            "description": "A, }",
            "q": 'say ", }',
            "sku": ["A", "B"],
        }
    ]


def test_the_extruct_layer_reads_a_commented_block_as_extruct_does():
    from sluicer.compat.extruct.jsonld import JsonLdExtractor

    html = (
        '<script type="application/ld+json">{"@type": "Product", // the product\n'
        ' "name": "Pad", "price": 41.90}</script>'
    )

    assert JsonLdExtractor().extract(html) == [
        {"@type": "Product", "name": "Pad", "price": 41.9}
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


def test_a_number_is_read_as_the_text_the_page_wrote():
    raw = '{"price": 41.90, "count": 3, "ratio": NaN}'

    assert _parse(raw) == {"price": "41.90", "count": "3", "ratio": None}


def test_the_extruct_layer_reads_numbers_as_json_reads_them():
    from sluicer.compat.extruct.jsonld import _as_extruct_reads

    parsed = _as_extruct_reads('{"price": 41.90, "count": 3, "ratio": NaN}')
    assert isinstance(parsed, dict)
    assert (parsed["price"], parsed["count"]) == (41.9, 3)
    assert parsed["ratio"] != parsed["ratio"]  # NaN, as json.loads reads it
    assert _as_extruct_reads('{"a": 1,}') == {"a": 1}


def test_a_node_holding_a_graph_beside_its_own_properties_is_a_node_too():
    """A shop writes its Product with the page's other nodes in its ``@graph``.

    Flattened into the graph alone, the Product itself was never read, and a
    product page had no price.
    """
    from sluicer import extract

    block = (
        '{"@context": "https://schema.org", "@type": "Product", "name": "Pad",'
        ' "offers": {"@type": "Offer", "price": "41.90", "priceCurrency": "EUR"},'
        ' "@graph": [{"@type": "BreadcrumbList", "itemListElement": ['
        '{"@type": "ListItem", "position": 1, "name": "Brakes"}]}]}'
    )
    html = (
        f'<html><head><script type="application/ld+json">{block}</script></head></html>'
    )

    found = read_jsonld(load(html))
    result = extract(html)

    assert [item["@type"] for item in found] == ["BreadcrumbList", "Product"]
    assert "@graph" not in found[1]
    assert found[0].where == "/html/head/script[1]#/@graph/0"
    assert found[1].where == "/html/head/script[1]#"
    assert result.summary["title"].value == "Pad"
    assert result.summary["price"].value == "41.90"
    assert result.summary["breadcrumb"].value == "Brakes"


def test_a_graph_s_own_identifier_or_context_is_no_node():
    """Its context is its nodes': see the test below."""
    assert _one(
        '{"@context": "https://schema.org", "@id": "https://shop.example/#graph",'
        ' "@graph": [{"@type": "Product", "name": "Pad"}]}'
    ) == [{"@context": "https://schema.org", "@type": "Product", "name": "Pad"}]


def test_a_node_read_out_of_a_graph_keeps_the_context_it_was_written_in():
    """The W3C JSON-LD suite's tests e004, c004 and r004.

    Read out of its graph without the block's context, ``ex:foo`` no longer
    said ``http://example.com/foo``: to a processor it was an address with the
    scheme ``ex``, and nothing could tell it from a word of any vocabulary. A
    node that has a context of its own keeps it, after the graph's; a graph
    inside a graph passes on both.
    """
    found = _one(
        '{"@context": {"ex": "http://example.com/"}, "@graph": ['
        '{"ex:foo": "a"},'
        ' {"@context": {"b": "http://b.example/"}, "b:x": "y"},'
        ' {"@context": ["https://schema.org"], "@graph": [{"ex:bar": "c"}]}]}'
    )

    assert found == [
        {"@context": {"ex": "http://example.com/"}, "ex:foo": "a"},
        {
            "@context": [{"ex": "http://example.com/"}, {"b": "http://b.example/"}],
            "b:x": "y",
        },
        {
            "@context": [{"ex": "http://example.com/"}, "https://schema.org"],
            "ex:bar": "c",
        },
    ]
    assert [node.where for node in found] == [
        "/html/head/script[1]#/@graph/0",
        "/html/head/script[1]#/@graph/1",
        "/html/head/script[1]#/@graph/2/@graph/0",
    ]


def test_a_node_beside_a_graph_is_in_the_context_of_the_graph_around_it():
    found = _one(
        '{"@context": {"ex": "http://example.com/"}, "@graph": ['
        '{"@type": "Brand", "ex:name": "Only", "@graph": [{"ex:foo": "a"}]}]}'
    )

    assert found == [
        {"@context": {"ex": "http://example.com/"}, "ex:foo": "a"},
        {
            "@context": {"ex": "http://example.com/"},
            "@type": "Brand",
            "ex:name": "Only",
        },
    ]


def test_a_term_a_context_defines_is_never_resolved_as_a_reference():
    """A term defined as ``{"@id": ...}`` is not a reference to a node."""
    found = _one(
        '{"@context": {"@vocab": "https://schema.org/", "maker": {"@id": "#me"}},'
        ' "@graph": [{"@id": "#me", "@type": "Person", "name": "Ann"},'
        ' {"@type": "Product", "maker": {"@id": "#me"}}]}'
    )

    context = {"@vocab": "https://schema.org/", "maker": {"@id": "#me"}}
    assert found[1]["@context"] == context
    assert found[1]["maker"]["name"] == "Ann"


def test_a_node_holding_a_graph_comes_after_the_nodes_in_it():
    """One shop's Brand holds its Products: the Products keep their places."""
    found = _one(
        '{"@type": "Brand", "name": "Only", "@graph": ['
        '{"@type": "Product", "name": "Shirt"}, {"@type": "Product", "name": "Top"}]}'
    )

    assert [item["name"] for item in found] == ["Shirt", "Top", "Only"]
