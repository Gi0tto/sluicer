"""``sluicer.compat.extruct``: extruct's interface, and the shapes it answers in.

Every expected answer in these tests is what extruct 0.18.0 answers for the
same page, checked against it, except where a test names one of the
differences ``docs/extruct.md`` lists. extruct itself is never imported here:
``bench/extruct_compat.py`` runs both on real pages, in environments of their own.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path

import lxml.html
import pytest

from sluicer import MicroformatsExtraMissing
from sluicer.compat import extruct
from sluicer.compat.extruct import page as page_module
from sluicer.compat.extruct.dublincore import DublinCoreExtractor
from sluicer.compat.extruct.jsonld import JsonLdExtractor
from sluicer.compat.extruct.microformat import MicroformatExtractor
from sluicer.compat.extruct.opengraph import OpenGraphExtractor
from sluicer.compat.extruct.page import Budget, decode, read_page
from sluicer.compat.extruct.uniform import (
    _udublincore,
    _umicrodata_microformat,
    flatten_dict,
    infer_context,
)

FIXTURES = Path(__file__).parent / "fixtures"
# mf2py 2.0.2's answer for ``<div class="h-card"><span class="p-name">Ann``.
CARD = {"type": ["h-card"], "properties": {"name": ["Ann"]}}
needs_mf2py = pytest.mark.skipif(
    importlib.util.find_spec("mf2py") is None, reason="needs sluicer[microformats]"
)


@pytest.fixture
def mf2py(monkeypatch):
    """Stand in for mf2py, so the suite needs no extra; what it was asked is kept."""
    asked: dict[str, object] = {}

    def parse(doc, **kwargs):
        asked.update(kwargs, doc=doc)
        if "raise" in asked:
            raise ValueError("'domain' does not appear to be an IPv4 or IPv6 address")
        return {"items": [CARD], "rels": {}, "rel-urls": {}}

    module = types.ModuleType("mf2py")
    module.parse = parse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mf2py", module)
    return asked


# --- extract -----------------------------------------------------------------


def test_every_syntax_is_answered_under_extruct_s_key_in_extruct_s_order(mf2py):
    html = (FIXTURES / "product_all_three.html").read_bytes()

    found = extruct.extract(html, base_url="https://example.com/p")

    assert list(found) == [
        "microdata",
        "json-ld",
        "opengraph",
        "microformat",
        "rdfa",
        "dublincore",
    ]
    assert found["json-ld"][0]["sku"] == "BP-1187"
    assert found["microdata"][0] == {
        "type": "https://schema.org/Product",
        "properties": {
            "name": "Brake pad set",
            "description": "Described by microdata",
            "mpn": "GDB1330",
        },
    }
    assert found["opengraph"][0]["properties"][0] == (
        "og:title",
        "Brake pad set, front axle",
    )
    assert found["rdfa"][0]["http://ogp.me/ns#title"] == [
        {"@value": "Brake pad set, front axle"}
    ]
    assert found["dublincore"] == [{"namespaces": {}, "elements": [], "terms": []}]


def test_only_the_syntaxes_asked_for_are_read():
    found = extruct.extract("<p>x</p>", syntaxes=["json-ld", "opengraph"])

    assert found == {"json-ld": [], "opengraph": []}


@pytest.mark.parametrize("syntaxes", [["json-ld", "jsonld"], ("json-ld",), "json-ld"])
def test_syntaxes_must_be_a_list_of_extruct_s_names(syntaxes):
    with pytest.raises(ValueError, match="syntaxes must be a list"):
        extruct.extract("<p>x</p>", syntaxes=syntaxes)


def test_errors_must_be_one_of_extruct_s_three():
    with pytest.raises(ValueError, match="Invalid error command"):
        extruct.extract("<p>x</p>", errors="loud")


def test_the_deprecated_url_argument_still_sets_the_base_and_says_so():
    html = '<div itemscope><a itemprop="u" href="/p">x</a></div>'

    with pytest.warns(DeprecationWarning, match="base_url"):
        found = extruct.extract(html, syntaxes=["microdata"], url="https://e.com/a")

    assert found["microdata"] == [{"properties": {"u": "https://e.com/p"}}]


def test_a_tree_parsed_by_the_caller_is_read_as_it_is():
    tree = lxml.html.fromstring(
        '<html><head><meta property="og:title" content="T"></head>'
        '<body><div itemscope><i itemprop="k">v</i></div></body></html>'
    )

    found = extruct.extract(tree, syntaxes=["opengraph", "microdata", "rdfa"])

    assert found["opengraph"][0]["properties"] == [("og:title", "T")]
    assert found["microdata"] == [{"properties": {"k": "v"}}]
    assert found["rdfa"] == [{"@id": "", "http://ogp.me/ns#title": [{"@value": "T"}]}]


def test_microformats_are_refused_a_tree_as_extruct_refuses_them():
    with pytest.raises(ValueError, match="requires a string"):
        extruct.extract(lxml.html.fromstring("<p>x</p>"))


def test_without_mf2py_strict_raises_the_missing_extra(absent):
    absent("mf2py")

    with pytest.raises(MicroformatsExtraMissing, match="sluicer\\[microformats\\]"):
        extruct.extract("<p>x</p>")


def test_without_mf2py_ignore_leaves_the_key_out(absent):
    absent("mf2py")

    found = extruct.extract("<p>x</p>", errors="ignore")

    assert "microformat" not in found
    assert "json-ld" in found


def test_without_mf2py_log_says_why_and_leaves_the_key_out(absent, caplog):
    absent("mf2py")

    with caplog.at_level(logging.ERROR, logger="sluicer.compat.extruct"):
        found = extruct.extract("<p>x</p>", errors="log", uniform=True)

    assert "microformat" not in found
    assert "Failed to extract microformat" in caplog.text


def test_uniform_mode_reshapes_each_syntax_extruct_reshapes(mf2py):
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<meta property="og:type" content="article">'
        '<meta name="DC.type" content="Text"></head><body>'
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">n</span></div>'
        '<div class="h-card"><span class="p-name">Ann</span></div>'
        '<script type="application/ld+json">{"@type": "Thing"}</script>'
        "</body></html>"
    )

    found = extruct.extract(html, uniform=True)

    assert found["microdata"] == [
        {"@type": "Product", "@context": "https://schema.org", "name": "n"}
    ]
    assert found["opengraph"] == [
        {"og:title": "T", "@type": "article", "@context": {"og": "http://ogp.me/ns#"}}
    ]
    assert found["dublincore"] == [
        {"elements": [], "terms": [], "@context": {}, "@type": "Text"}
    ]
    assert found["microformat"][0]["@type"] == ["h-card"]
    assert found["microformat"][0]["@context"] == "http://microformats.org/wiki/"
    # JSON-LD is not reshaped, in extruct either.
    assert found["json-ld"] == [{"@type": "Thing"}]


def test_uniform_takes_the_schema_context_extruct_takes():
    html = '<div itemscope itemtype="http://a/b http://a/c"><i itemprop="k">v</i></div>'

    found = extruct.extract(
        html, syntaxes=["microdata"], uniform=True, schema_context="https://schema.org"
    )

    assert found["microdata"] == [
        {
            "@type": ["http://a/b", "http://a/c"],
            "@context": "https://schema.org",
            "k": "v",
        }
    ]


def test_return_html_node_holds_each_item_s_element():
    found = extruct.extract(
        '<div itemscope id="it"><i itemprop="k">v</i></div>',
        syntaxes=["microdata"],
        return_html_node=True,
    )

    assert found["microdata"][0]["htmlNode"].get("id") == "it"


def test_a_syntax_that_fails_under_log_or_ignore_is_left_out(monkeypatch, caplog):
    def broken(self, page):
        raise RuntimeError("a bug")

    monkeypatch.setattr(OpenGraphExtractor, "read", broken)

    with pytest.raises(RuntimeError):
        extruct.extract("<p>x</p>", syntaxes=["opengraph"])
    assert extruct.extract("<p>x</p>", syntaxes=["opengraph"], errors="ignore") == {}
    with caplog.at_level(logging.ERROR, logger="sluicer.compat.extruct"):
        assert extruct.extract("<p>x</p>", syntaxes=["opengraph"], errors="log") == {}
    assert "Failed to extract opengraph" in caplog.text


def test_a_json_ld_block_extruct_raises_on_loses_nothing_else():
    # One of the documented differences: extruct raises JSONDecodeError here,
    # and with errors="strict" that loses the OpenGraph too.
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<script type="application/ld+json">  </script>'
        '<script type="application/ld+json">{"@type": "A",</script>'
        '<script type="application/ld+json">{"@type": "B"}</script></head></html>'
    )

    found = extruct.extract(html, syntaxes=["json-ld", "opengraph"])

    assert found["json-ld"] == [{"@type": "B"}]
    assert found["opengraph"][0]["properties"] == [("og:title", "T")]


# --- the page: decoding and budgets --------------------------------------------


def test_utf8_bytes_are_utf8_whatever_the_page_declares():
    data = '<meta charset="iso-8859-1"><p>Café</p>'.encode()

    assert decode(data, "UTF-8") == '<meta charset="iso-8859-1"><p>Café</p>'


def test_bytes_that_are_not_utf8_are_read_as_the_page_declares():
    # A documented difference: extruct answers "Caf�" for both pages.
    declared = b'<meta charset="windows-1252"><p>Caf\xe9 \x93q\x94</p>'
    undeclared = b"<p>Caf\xe9</p>"

    assert decode(declared, "UTF-8").endswith("<p>Café “q”</p>")
    assert decode(undeclared, "UTF-8") == "<p>Café</p>"


def test_an_encoding_the_caller_names_is_believed_when_the_bytes_are_valid_in_it():
    data = "<p>Caf\xe9</p>".encode("latin-1")

    assert decode(data, "latin-1") == "<p>Café</p>"
    assert decode("<p>Привет</p>".encode("koi8-r"), "koi8-r") == "<p>Привет</p>"


def test_a_byte_order_mark_outranks_the_encoding_named():
    data = "﻿<p>Café</p>".encode("utf-16-le")

    assert decode(data, "latin-1").endswith("<p>Café</p>")


def test_an_encoding_nobody_knows_is_not_believed():
    assert decode("<p>Café</p>".encode(), "no-such-codec") == "<p>Café</p>"
    assert decode("<p>Café</p>".encode(), None) == "<p>Café</p>"


def test_opengraph_on_a_declared_windows_1252_page_keeps_its_accent():
    html = (
        '<html><head><meta charset="windows-1252">'
        '<meta property="og:title" content="Caf\xe9"></head></html>'
    ).encode("cp1252")

    found = extruct.extract(html, syntaxes=["opengraph"])

    assert found["opengraph"][0]["properties"] == [("og:title", "Café")]


def test_a_str_carrying_an_xml_declaration_is_read():
    # extruct raises "Unicode strings with encoding declaration are not
    # supported"; the page is read here.
    html = (
        '<?xml version="1.0" encoding="utf-8"?><html><head>'
        '<meta property="og:title" content="T"></head></html>'
    )

    found = extruct.extract(html, syntaxes=["opengraph"])

    assert found["opengraph"][0]["properties"] == [("og:title", "T")]


def test_the_page_s_base_is_resolved_against_the_address_given():
    page = read_page('<base href="/b/"><p>x</p>', "https://e.com/a", "UTF-8")

    assert page.base == "https://e.com/b/"
    assert page.base_url == "https://e.com/a"


def test_a_tree_s_size_is_its_serialisation_s():
    tree = lxml.html.fromstring("<p>hello</p>")

    assert page_module.of_tree(tree, None).size == len("<p>hello</p>")


def test_a_budget_is_ten_times_the_page_and_never_less_than_its_floor():
    assert Budget(10).left == 10_000
    assert Budget(5_000).left == 50_000
    budget = Budget(0)
    assert budget.pay(9_999) is True
    assert budget.pay(2) is False
    assert budget.left == 0


# --- JSON-LD -----------------------------------------------------------------


def test_json_ld_objects_come_as_the_page_wrote_them_numbers_included():
    html = (
        '<script type="application/ld+json">{"@type": "Product", "price": 41.90, '
        '"n": 3, "b": true, "z": null, "@graph": [{"@type": "A"}]}</script>'
        '<script type="application/ld+json">[{"@type": "B"}, {}, null, "s", 0]</script>'
        '<script type="application/ld+json">{}</script>'
        '<script type="application/ld+json">"just a string"</script>'
    )

    assert JsonLdExtractor().extract(html) == [
        {
            "@type": "Product",
            "price": 41.9,
            "n": 3,
            "b": True,
            "z": None,
            "@graph": [{"@type": "A"}],
        },
        {"@type": "B"},
        "s",
    ]


def test_json_ld_in_a_media_type_of_another_spelling_is_read():
    # One of the documented differences: extruct reads only the type spelt
    # "application/ld+json"; a media type is matched ignoring case and its
    # parameters, and JSON-LD 1.1 names a profile parameter.
    html = '<script type="application/LD+JSON; charset=utf-8">{"@type": "C"}</script>'

    assert JsonLdExtractor().extract(html) == [{"@type": "C"}]


# Each block's text, and extruct 0.18.0's answer for a page holding it alone,
# run through extruct itself on 2026-09-25: a list, or None where it raised
# JSONDecodeError. extruct reads a block with ``json.loads``, then with its
# first line dropped when that line is a comment and jstyleson's removal of
# JavaScript's comments and trailing commas; sluicer's own reader forgives
# more, and extruct's interface must not.
AS_EXTRUCT_READS = [
    ('{"@type": "C", "name": "x",}', [{"@type": "C", "name": "x"}]),
    ('{"@type": "C", "sku": ["A", "B",],}', [{"@type": "C", "sku": ["A", "B"]}]),
    ('{"@type": "C", "d": "a\nb"}', [{"@type": "C", "d": "a\nb"}]),
    ('{"@type": "C", // the product\n "name": "Pad"}', [{"@type": "C", "name": "Pad"}]),
    ('{"@type": "C", /* a */ "name": "Pad"}', [{"@type": "C", "name": "Pad"}]),
    ('{"@type": "C", "x": [1, /* c */ ]}', [{"@type": "C", "x": [1]}]),
    ('{"n": "Pad // no /* nor */"}', [{"n": "Pad // no /* nor */"}]),
    ('{"@type": "C", "name": "Pad, ]",}', [{"@type": "C", "name": "Pad, ]"}]),
    ('<!-- foo -->\n{"@type": "C"}', [{"@type": "C"}]),
    ('//<![CDATA[\n{"@type": "C"}\n//]]>\n', [{"@type": "C"}]),
    ('/*<![CDATA[*/{"@type": "C"}/*]]>*/', [{"@type": "C"}]),
    # jstyleson ends a block comment at the first "/" after any "*" in it.
    ('{"@type": "C", /*/ x */ "n": 2}', [{"@type": "C", "n": 2}]),
    ('{"@type": "C", "n": /*/*1{ x/1}', [{"@type": "C", "n": 1}]),
    ('{"@type": "C", "n": /* x * y / 1 */ 2}', None),
    ('{"@type": "C", /* 2*3 x/y */ "n": 2}', None),
    # The W3C suite's tests e014 to e016: a comment around the text, one never
    # closed, one never opened.
    ('<!--\n{"@type": "C", "d": "<!-- -->"}\n-->', None),
    ('<!--\n{"@type": "C"}', None),
    ('{"@type": "C"}\n-->', None),
    ('<!-- {"@type": "C"} -->', None),
    ('//<![CDATA[\n{"@type": "C"}\n//]]>', None),
    ('<![CDATA[{"@type": "C"}]]>', None),
    ('﻿{"@type": "C"}', None),
    ('{"@type": "C", "name": "Pad"} /* left open', None),
    ('{"@type": "C", "name": "Pad"} // last', None),
    ('{"@type": "C"}\n<!-- tail -->', None),
    ("// only a comment\n", None),
]  # fmt: skip


@pytest.mark.parametrize(("text", "extruct_reads"), AS_EXTRUCT_READS)
def test_a_json_ld_block_is_read_as_extruct_reads_it(text, extruct_reads):
    # Where extruct raises, the block is skipped and the page's other blocks
    # are kept: the documented difference, since extruct's raise loses the
    # page's every syntax.
    html = (
        f'<script type="application/ld+json">{text}</script>'
        '<script type="application/ld+json">{"@type": "Kept"}</script>'
    )

    assert JsonLdExtractor().extract(html) == [
        *(extruct_reads or []),
        {"@type": "Kept"},
    ]


def test_a_block_of_comments_never_closed_is_read_in_a_moment():
    """Found by review: a block comment's pattern looked from every "/*" for
    its end, and 60 KB of "/*a" never closed took 2.6 seconds."""
    import time

    for text in ("{" + "/*a" * 40_000, "{" + "//" * 40_000, '{"' + "a" * 80_000):
        started = time.perf_counter()
        JsonLdExtractor().extract(f'<script type="application/ld+json">{text}</script>')
        assert time.perf_counter() - started < 1


def test_a_json_ld_block_extruct_cannot_read_is_one_sluicer_reads():
    """Refusing it is extruct's interface's alone: ``extract`` mends it."""
    from sluicer import extract

    html = (
        '<script type="application/ld+json">'
        '<!--\n{"@type": "Product", "name": "Pad"}\n--></script>'
    )

    assert JsonLdExtractor().extract(html) == []
    assert extract(html).records[0].fields["name"].value == "Pad"


def test_json_ld_from_a_tree():
    tree = lxml.html.fromstring(
        '<html><body><script type="application/ld+json">{"@type": "A"}</script>'
        "</body></html>"
    )

    assert JsonLdExtractor().extract_items(tree) == [{"@type": "A"}]


def test_json_ld_below_libxml2_s_default_depth_is_read():
    # extruct answers [] here: libxml2, as extruct calls it, drops everything
    # below 256 levels.
    deep = "<div>" * 400 + '<script type="application/ld+json">{"n": 1}</script>'

    assert JsonLdExtractor().extract("<html><body>" + deep) == [{"n": 1}]


# --- OpenGraph ---------------------------------------------------------------


def test_opengraph_is_the_head_s_property_tags_in_order_as_written():
    html = (
        '<html prefix="fb: http://ogp.me/ns/fb#">'
        '<head prefix="my: http://example.com/ns#">'
        '<meta property="og:title" content=" T ">'
        '<meta property="og:image" content="a"><meta property="og:image" content="b">'
        '<meta property="og:x" content=""><meta name="og:desc" content="n">'
        '<meta property="fb:app_id" content="1"><meta property="my:thing" content="m">'
        '<meta property="al:ios" content="2">'
        '<meta property="product:price:amount" content="3">'
        '<meta property="OG:Upper" content="4">'
        '<meta property="og:type" content="product">'
        '</head><body><meta property="og:body" content="6"></body></html>'
    )

    assert OpenGraphExtractor().extract(html) == [
        {
            "namespace": {
                "fb": "http://ogp.me/ns/fb#",
                "my": "http://example.com/ns#",
                "og": "http://ogp.me/ns#",
                "product": "http://ogp.me/ns/product#",
            },
            "properties": [
                ("og:title", " T "),
                ("og:image", "a"),
                ("og:image", "b"),
                ("og:x", ""),
                ("fb:app_id", "1"),
                ("my:thing", "m"),
                ("product:price:amount", "3"),
                ("og:type", "product"),
            ],
        }
    ]


def test_a_page_without_opengraph_answers_nothing():
    assert (
        OpenGraphExtractor().extract("<html><head><title>x</title></head></html>") == []
    )
    assert OpenGraphExtractor().extract_items(lxml.html.fromstring("<p>x</p>")) == []


def test_opengraph_uniform_keeps_the_first_non_empty_value():
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<meta property="og:type" content="article">'
        '<meta property="og:image" content=""><meta property="og:image" content="b">'
        '<meta property="og:image" content="c"><meta property="og:locale" content="en">'
        '<meta property="og:locale" content=" "></head></html>'
    )

    found = extruct.extract(html, syntaxes=["opengraph"], uniform=True)

    assert found["opengraph"] == [
        {
            "og:title": "T",
            "og:image": "b",
            "og:locale": "en",
            "@type": "article",
            "@context": {"og": "http://ogp.me/ns#"},
        }
    ]


def test_opengraph_uniform_with_og_array_keeps_every_value():
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<meta property="og:type" content="article">'
        '<meta property="og:image" content=""><meta property="og:image" content="b">'
        '<meta property="og:image" content="c"><meta property="og:video" content="v1">'
        '<meta property="og:video" content="v2"><meta property="og:video" content="v3">'
        "</head></html>"
    )

    found = extruct.extract(
        html, syntaxes=["opengraph"], uniform=True, with_og_array=True
    )

    assert found["opengraph"] == [
        {
            "og:title": "T",
            "og:image": ["b", "c"],
            "og:video": ["v1", "v2", "v3"],
            "@type": "article",
            "@context": {"og": "http://ogp.me/ns#"},
        }
    ]


# --- Dublin Core -------------------------------------------------------------


def test_dublin_core_is_the_names_under_a_dublin_core_prefix():
    # extruct raises KeyError on the <link rel="schema.foo"> with no href.
    html = (
        '<html><head><link rel="schema.DC" href="http://purl.org/dc/elements/1.1/">'
        '<link rel="schema.DCTERMS" href=" http://purl.org/dc/terms/ ">'
        '<link rel="schema.foo"><meta name="DC.title" content="T" lang="en">'
        '<meta name="dcterms.created" scheme="W3CDTF" content="2020">'
        '<meta name="DCTERMS.title" content="T2"><meta name="DC.Type" content="Text">'
        '<link rel="DC.source" href="/s"><meta name="DC.nothing" content="x">'
        "</head></html>"
    )

    assert DublinCoreExtractor().extract(html) == [
        {
            "namespaces": {
                "DC": "http://purl.org/dc/elements/1.1/",
                "DCTERMS": "http://purl.org/dc/terms/",
            },
            "elements": [
                {
                    "name": "DC.title",
                    "content": "T",
                    "lang": "en",
                    "URI": "http://purl.org/dc/elements/1.1/title",
                },
                {
                    "name": "DCTERMS.title",
                    "content": "T2",
                    "URI": "http://purl.org/dc/elements/1.1/title",
                },
                {
                    "name": "DC.Type",
                    "content": "Text",
                    "URI": "http://purl.org/dc/elements/1.1/type",
                },
                {
                    "rel": "DC.source",
                    "href": "/s",
                    "URI": "http://purl.org/dc/elements/1.1/source",
                },
            ],
            "terms": [
                {
                    "name": "dcterms.created",
                    "scheme": "W3CDTF",
                    "content": "2020",
                    "URI": "http://purl.org/dc/terms/created",
                }
            ],
        }
    ]


@pytest.mark.parametrize("name", ["{},", "{a}b", "{", "{}", "{a", "{}uri"])
def test_an_attribute_named_with_braces_is_copied_as_extruct_copies_it(name):
    # lxml reads a key of the form "{ns}local" as a namespaced name when it is
    # looked up, so copying an element's attributes by key raised KeyError or
    # ValueError on these; extruct copies them pair by pair.
    html = (
        f'<html><head><meta name="DC.title" content="x" {name}="y">'
        f'<link rel="DC.source" {name}="z" href="/s"></head></html>'
    )

    assert DublinCoreExtractor().extract(html)[0]["elements"] == [
        {
            "name": "DC.title",
            "content": "x",
            name: "y",
            "URI": "http://purl.org/dc/elements/1.1/title",
        },
        {
            "rel": "DC.source",
            name: "z",
            "href": "/s",
            "URI": "http://purl.org/dc/elements/1.1/source",
        },
    ]


def test_names_that_are_not_dublin_core_are_not_filed_as_it():
    # The documented difference: extruct files every one of these.
    html = (
        '<html><head><meta name="description" content="D"><meta name="title" '
        'content="T"><meta name="citation.date" content="c">'
        '<link rel="license" href="/l"><meta name="og:title" content="o"></head></html>'
    )

    assert DublinCoreExtractor().extract(html) == [
        {"namespaces": {}, "elements": [], "terms": []}
    ]


def test_a_prefix_the_page_declares_for_dublin_core_is_dublin_core():
    html = (
        '<link rel="schema.DCT" href="http://purl.org/dc/terms/">'
        '<meta name="DCT.modified" content="2021">'
    )

    tree = lxml.html.fromstring(html)

    assert DublinCoreExtractor().extract_items(tree)[0]["terms"] == [
        {
            "name": "DCT.modified",
            "content": "2021",
            "URI": "http://purl.org/dc/terms/modified",
        }
    ]


def test_dublin_core_uniform_takes_the_type_out_of_the_elements():
    html = (
        '<html><head><link rel="schema.DC" href="http://purl.org/dc/elements/1.1/">'
        '<meta name="DC.title" content="T"><meta name="DC.type" content="Text">'
        '<meta name="DC.subject" content="S"></head></html>'
    )

    found = extruct.extract(html, syntaxes=["dublincore"], uniform=True)

    assert found["dublincore"] == [
        {
            "elements": [
                {
                    "name": "DC.title",
                    "content": "T",
                    "URI": "http://purl.org/dc/elements/1.1/title",
                },
                {
                    "name": "DC.subject",
                    "content": "S",
                    "URI": "http://purl.org/dc/elements/1.1/subject",
                },
            ],
            "terms": [],
            "@context": {"DC": "http://purl.org/dc/elements/1.1/"},
            "@type": "Text",
        }
    ]


def test_dublin_core_uniform_skips_as_extruct_s_loop_skips():
    elements = [
        {"name": "DC.type", "content": "A"},
        {"name": "DC.type", "content": "B"},
        {"rel": "DC.type", "href": "/t"},
    ]
    raw = [{"namespaces": None, "elements": elements, "terms": []}]

    found = _udublincore(raw)

    # The first is taken and removed, which moves the second into the place
    # the loop has passed; the link has no content, and stays.
    assert found == [
        {
            "elements": [
                {"name": "DC.type", "content": "B"},
                {"rel": "DC.type", "href": "/t"},
            ],
            "terms": [],
            "@context": None,
            "@type": "A",
        }
    ]
    assert raw[0]["elements"] == elements


# --- microformats ------------------------------------------------------------


def test_mf2py_is_asked_as_extruct_asks_it_with_the_page_as_decoded(mf2py):
    html = b'<meta charset="windows-1252"><div class="h-card">Caf\xe9</div>'

    found = MicroformatExtractor().extract(html, base_url="https://e.com/")

    assert found == [CARD]
    assert mf2py == {
        "html_parser": "lxml",
        "url": "https://e.com/",
        "doc": '<meta charset="windows-1252"><div class="h-card">Café</div>',
    }
    assert MicroformatExtractor().extract_items(html) == [CARD]


def test_a_page_mf2py_cannot_read_declares_no_microformats(mf2py):
    # extruct raises ValueError: urlparse refuses an unfilled template's host.
    mf2py["raise"] = True

    assert MicroformatExtractor().extract('<base href="https://[domain]/">') == []


@needs_mf2py
def test_the_real_mf2py_answers_extruct_s_items():
    html = '<div class="h-card"><a class="p-name u-url" href="/ann">Ann</a></div>'

    found = MicroformatExtractor().extract(html, base_url="https://e.com/")

    assert found == [
        {
            "type": ["h-card"],
            "properties": {"name": ["Ann"], "url": ["https://e.com/ann"]},
        }
    ]


# --- uniform, directly -------------------------------------------------------


def test_uniform_leaves_an_untyped_item_unflattened():
    item = {"properties": {"k": "v"}}

    assert flatten_dict(item, "http://schema.org", True) is item
    assert _umicrodata_microformat(item, "http://schema.org") == [item]
    assert _umicrodata_microformat("neither", "http://schema.org") == []


def test_uniform_flattens_children_and_lists_of_items():
    item = {
        "type": ["h-feed"],
        "properties": {"author": [{"type": ["h-card"], "properties": {}}, "text"]},
        "children": [{"type": ["h-entry"], "properties": {"name": ["E"]}}],
    }

    assert flatten_dict(item, "http://microformats.org/wiki/", True) == {
        "@type": ["h-feed"],
        "@context": "http://microformats.org/wiki/",
        "author": [{"@type": ["h-card"]}, "text"],
        "children": [{"@type": ["h-entry"], "name": ["E"]}],
    }


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("https://schema.org/Product", ("https://schema.org", "Product")),
        ("http://a.example/ns#Thing", ("http://a.example/ns", "Thing")),
        ("Product", ("http://schema.org", "Product")),
        ("http://a.example", ("http://schema.org", "http://a.example")),
        ("https://[domain]/Product", ("http://schema.org", "https://[domain]/Product")),
    ],
)
def test_infer_context_splits_a_type_s_vocabulary_from_its_name(declared, expected):
    assert infer_context(declared) == expected


def test_scripts_of_another_type_are_not_json_ld():
    html = (
        '<script type="text/javascript">{"@type": "A"}</script>'
        '<script type="application/ld+json">{"@type": "B"}</script>'
    )

    assert JsonLdExtractor().extract(html) == [{"@type": "B"}]


def test_an_extractor_s_extract_takes_a_tree_too():
    tree = lxml.html.fromstring(
        '<html><head><script type="application/ld+json">{"n": 1}</script></head></html>'
    )

    assert JsonLdExtractor().extract(tree) == [{"n": 1}]  # type: ignore[arg-type]


def test_the_microformats_extractor_refuses_a_tree():
    page = page_module.of_tree(lxml.html.fromstring("<p>x</p>"), None)

    with pytest.raises(ValueError, match="requires a string"):
        MicroformatExtractor().read(page)


def test_an_empty_og_type_gives_no_type():
    html = '<html><head><meta property="og:type" content=""></head></html>'

    found = extruct.extract(html, syntaxes=["opengraph"], uniform=True)

    assert found["opengraph"] == [{"@context": {"og": "http://ogp.me/ns#"}}]
