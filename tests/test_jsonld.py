import re
from pathlib import Path

from hypothesis import given, strategies as st

from sluicer.declared.jsonld import _parse, _without_closing, read_jsonld
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


# --- what a block's context names ----------------------------------------------


def _record(block: str):
    from sluicer import extract

    records = extract(
        f'<html><head><script type="application/ld+json">{block}</script></head></html>'
    ).records
    assert len(records) == 1
    return records[0]


def test_a_word_a_context_gives_another_vocabulary_is_named_by_its_address():
    """A record names a schema.org property by its own name and any other by
    its full address, as RDFa's are named: a FOAF ``name`` read as schema.org's
    was the product's title."""
    record = _record(
        '{"@context": ["https://schema.org", {"name": "http://xmlns.com/foaf/0.1/name",'
        ' "ex": "http://example.com/"}],'
        ' "@type": "Product", "name": "Ann", "ex:colour": "red", "sku": "BP-1"}'
    )

    assert list(record.fields) == [
        "http://xmlns.com/foaf/0.1/name",
        "http://example.com/colour",
        "sku",
    ]
    assert record.fields["http://example.com/colour"].where == (
        "/html/head/script[1]#/ex:colour"
    )


def test_the_w3c_graph_s_prefixed_words_are_named_by_their_addresses():
    """The W3C JSON-LD suite's e004: ``ex:foo`` is http://example.com/foo."""
    from sluicer import extract

    page = (
        '<script type="application/ld+json">{"@context": {"foo": {"@id":'
        ' "http://example.com/foo", "@container": "@list"}},'
        ' "foo": [{"@value": "bar"}]}</script>'
        '<script type="application/ld+json">{"@context": {"ex": "http://example.com/"},'
        ' "@graph": [{"ex:foo": {"@value": "foo"}}, {"ex:bar": {"@value": "bar"}}]}'
        "</script>"
    )

    assert [
        {name: field.value for name, field in record.fields.items()}
        for record in extract(page).records
    ] == [
        {"http://example.com/foo": ["bar"]},
        {"http://example.com/foo": "foo"},
        {"http://example.com/bar": "bar"},
    ]


def test_a_type_a_context_gives_another_vocabulary_is_named_by_its_address():
    record = _record(
        '{"@context": {"@vocab": "http://example.com/"}, "@type": "Product",'
        ' "name": "Pad"}'
    )

    assert (record.type, list(record.fields)) == (
        "http://example.com/Product",
        ["http://example.com/name"],
    )


def test_schema_org_s_words_keep_their_names_however_they_are_written():
    for block in (
        '{"@context": "https://schema.org", "@type": "Product", "name": "Pad"}',
        '{"@context": "http://schema.org/", "@type": "schema:Product",'
        ' "schema:name": "Pad"}',
        '{"@context": {"@vocab": "http://schema.org"}, "@type": "Product",'
        ' "name": "Pad"}',
        '{"@context": {"s": "https://schema.org/"}, "@type": "s:Product",'
        ' "s:name": "Pad"}',
        '{"@type": "http://schema.org/Product", "http://schema.org/name": "Pad"}',
        '{"@type": "Product", "name": "Pad"}',
    ):
        record = _record(block)
        assert (record.type, list(record.fields)) == ("Product", ["name"]), block


def test_a_word_a_context_does_not_define_to_an_address_is_kept_as_written():
    """A remote context not schema.org's is not fetched, a word it would
    define is not known, and a definition naming no address -- one real page
    maps ``articleId`` and ``topics`` to ``"Text"`` -- is not followed."""
    for block, names in (
        ('{"@context": "https://w3id.org/x", "@type": "T", "name": "a"}', ["name"]),
        (
            '{"@context": {"@vocab": "http://schema.org", "articleId":'
            ' {"@id": "Text", "@type": "@id"}}, "@type": "Article", "articleId": "7",'
            ' "headline": "h"}',
            ["articleId", "headline"],
        ),
        ('{"@context": {"ex": "http://example.com/"}, "@type": "T", "a": "1"}', ["a"]),
        ('{"@context": {"a": null}, "@type": "T", "a": "1"}', ["a"]),
    ):
        assert list(_record(block).fields) == names, block


def test_a_word_no_address_can_hold_is_kept_as_written():
    """Two real pages: AP News types a node ``JW Videos``, and another writes
    ``"description "``; neither became an address under schema.org's."""
    record = _record(
        '{"@context": "https://schema.org", "@type": "JW Videos",'
        ' "description ": "d", "a/b": "c"}'
    )

    assert (record.type, list(record.fields)) == ("JW Videos", ["description ", "a/b"])


def test_a_nested_node_s_words_are_named_in_its_own_context():
    record = _record(
        '{"@context": "https://schema.org", "@type": "Product", "name": "Pad",'
        ' "offers": {"@context": {"ex": "http://example.com/"}, "@type": "Offer",'
        ' "price": "41.90", "ex:note": "n"}}'
    )

    assert record.fields["offers"].value == {
        "@type": "Offer",
        "price": "41.90",
        "http://example.com/note": "n",
    }


def test_a_prefix_is_a_word_whose_address_ends_where_a_name_can_begin():
    """JSON-LD 1.1: ``foo:bar`` expands through ``foo`` only when foo's
    address ends in ``/``, ``#`` or another delimiter."""
    record = _record(
        '{"@context": {"foo": "http://example.com/foo", "ex": "http://example.com/"},'
        ' "@type": "T", "foo:bar": "1", "ex:bar": "2"}'
    )

    assert list(record.fields) == ["foo:bar", "http://example.com/bar"]


def test_a_context_of_terms_defined_through_each_other_costs_a_bounded_amount():
    """Five thousand terms, each the one before with ``:x/``: followed to its
    end, every term walked the chain, past Python's recursion limit. A term
    more than a few definitions from an address is kept as written."""
    import json

    context = {"t0": "http://example.com/"}
    context.update({f"t{n}": f"t{n - 1}:x/" for n in range(1, 5000)})
    record = _record(
        json.dumps({"@context": context, "@type": "T", "t4999": "v", "t2": "w"})
    )

    assert list(record.fields) == ["t4999", "http://example.com/x/x/"]


def _page(block: str) -> str:
    script = f'<script type="application/ld+json">{block}</script>'
    return f"<html><head>{script}</head></html>"


def test_a_word_written_as_its_own_name_wins_over_one_spelt_otherwise():
    """Found by review: ``schema:price`` and ``price`` name one property, and
    the first written won, so the price was 6 where 0.7.1 and every reader
    that goes by the key read 5. The key written as the name wins, wherever
    it stands; among other spellings, the first written."""
    from sluicer import extract

    for offer in (
        '{"@type": "Offer", "schema:price": "6", "price": "5"}',
        '{"@type": "Offer", "price": "5", "schema:price": "6"}',
        '{"@type": "Offer", "http://schema.org/price": "7", "schema:price": "6",'
        ' "price": "5"}',
    ):
        found = extract(
            _page(
                '{"@context": "https://schema.org", "@type": "Product", "name": "N",'
                f' "offers": {offer}}}'
            )
        )
        assert found.records[0].fields["offers"].value == {
            "@type": "Offer",
            "price": "5",
        }, offer
        assert (found.summary["price"].value, found.summary["price"].where) == (
            "5",
            "/html/head/script[1]#/offers/price",
        ), offer

    record = _record(
        '{"@context": "https://schema.org", "@type": "Product",'
        ' "schema:sku": "A", "sku": "B", "schema:gtin": "1",'
        ' "http://schema.org/gtin": "2", "mpn": "", "schema:mpn": "M"}'
    )
    assert {name: (f.value, f.where) for name, f in record.fields.items()} == {
        "sku": ("B", "/html/head/script[1]#/sku"),
        "gtin": ("1", "/html/head/script[1]#/schema:gtin"),
        "mpn": ("M", "/html/head/script[1]#/schema:mpn"),
    }


def test_a_value_named_otherwise_than_written_is_placed_at_the_key_written():
    """Found by review: the pointer named the key the record calls the value
    by, ``/offers/price``, and the page wrote ``schema:price``: a pointer to a
    key the block does not have."""
    from sluicer import extract

    found = extract(
        _page(
            '{"@context": "https://schema.org", "@type": "Product", "name": "N",'
            ' "offers": [{"@type": "Offer", "schema:price": "6",'
            ' "schema:seller": {"@type": "Organization", "schema:name": "S"}}]}'
        )
    )

    assert (found.summary["price"].value, found.summary["price"].where) == (
        "6",
        "/html/head/script[1]#/offers/0/schema:price",
    )
    offers = found.records[0].fields["offers"]
    from sluicer.declared.located import place

    assert place(offers.value, offers.where, [0, "seller", "name"]) == (
        "/html/head/script[1]#/offers/0/schema:seller/schema:name"
    )


def test_the_audit_reads_the_word_written_as_its_own_name_too():
    from sluicer.audit.records import normalise
    from sluicer.declared.jsonld import Terms

    assert normalise(
        {
            "@context": "https://schema.org",
            "@type": "Offer",
            "schema:price": "6",
            "price": "5",
        },
        terms=Terms(),
    ) == {"@type": ["Offer"], "price": "5"}


def test_a_vocabulary_is_read_through_the_contexts_around_it_not_its_own():
    """Found by review: ``{"@vocab": "ex:", "ex": ...}`` was read through
    its own context's ``ex``, where JSON-LD 1.1 reads ``@vocab`` before the
    terms beside it are defined (PyLD 3.3 gives ``ex:name``); a prefix or a
    term of a context around it is read, as PyLD reads it."""
    for context, named in (
        ('{"@vocab": "ex:", "ex": "http://example.com/"}', "ex:"),
        ('[{"ex": "http://example.com/"}, {"@vocab": "ex:"}]', "http://example.com/"),
        ('[{"v": "http://example.com/"}, {"@vocab": "v"}]', "http://example.com/"),
    ):
        record = _record(f'{{"@context": {context}, "@type": "Thing", "name": "N"}}')
        assert (record.type, list(record.fields)) == (
            named + "Thing",
            [named + "name"],
        ), context


def test_schema_org_s_namespace_with_a_fragment_is_schema_org_s():
    """Found by review: ``@vocab`` written ``http://schema.org/#`` named every
    word ``http://schema.org/#name`` and lost the title 0.7.1 read."""
    from sluicer import extract

    found = extract(
        _page(
            '{"@context": {"@vocab": "http://schema.org/#"}, "@type": "Article",'
            ' "headline": "H"}'
        )
    )

    assert (found.records[0].type, list(found.records[0].fields)) == (
        "Article",
        ["headline"],
    )
    assert found.summary["title"].value == "H"


def test_schema_is_schema_org_s_prefix_only_where_the_context_leaves_it_so():
    """Suspected by review: ``schema:Product`` was schema.org's Product
    though the block's context defines ``schema`` as a word that is no
    prefix, making ``schema:Product`` an address of its own (PyLD 3.3 keeps
    it). Where the context says nothing of ``schema`` it is schema.org's, as
    pages mean it."""
    for context in (
        '{"schema": "http://example.com/v"}',
        '{"schema": {"@id": "http://example.com/"}}',
    ):
        record = _record(
            f'{{"@context": {context}, "@type": "schema:Product", "schema:name": "N"}}'
        )
        assert (record.type, list(record.fields)) == (
            "schema:Product",
            ["schema:name"],
        ), context
    for block in (
        '{"@type": "schema:Product", "schema:name": "N"}',
        '{"@context": "https://w3id.org/x", "@type": "schema:Product",'
        ' "schema:name": "N"}',
        '{"@context": {"schema": "https://schema.org/"}, "@type": "schema:Product",'
        ' "schema:name": "N"}',
    ):
        record = _record(block)
        assert (record.type, list(record.fields)) == ("Product", ["name"]), block


# --- a block's wrapper -----------------------------------------------------------

# The pattern that took a closing wrapper off, kept as the oracle: two runs of
# whitespace side by side before the end, which a block that does not end
# there makes backtrack from every place a mark stands.
_OLD_CLOSING = re.compile(r"(?:(?://|/\*)\s*)?(?:\]\]>|-->)\s*(?:\*/)?\s*$")


def test_a_block_ending_in_a_mark_and_then_text_is_read_in_a_moment():
    """Found by review: ``-->``, forty thousand spaces and a letter took the
    closing pattern seconds on every page that carried the block."""
    import time

    block = '{"@type": "Thing", "name": "x"}-->' + " " * 40_000 + "x"
    started = time.perf_counter()
    _parse(block)

    assert time.perf_counter() - started < 1


_WRAPPER_PIECES = ["-->", "]]>", "//", "/*", "*/", " ", "\n", "\t", "x", "-", "]"]


@given(st.lists(st.sampled_from(_WRAPPER_PIECES), max_size=12).map("".join))
def test_a_closing_wrapper_comes_off_as_the_pattern_took_it_off(text):
    assert _without_closing(text) == _OLD_CLOSING.sub("", text)
