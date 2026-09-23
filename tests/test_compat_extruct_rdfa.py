"""RDFa in extruct's shape: pyRdfa's graph as rdflib writes it, without either.

Every expected graph here is the graph extruct 0.18.0 answers for the same
page, checked against it; extruct's blank node labels and its order are its
own on every run, so what is compared there is the graph, and what is asserted
here is sluicer's labels and order, which are fixed. Where extruct fails, the
test says so.
"""

from __future__ import annotations

import lxml.html
import pytest

from sluicer.compat.extruct import rdfa
from sluicer.compat.extruct.rdfa import RDFaExtractor

XHV = "http://www.w3.org/1999/xhtml/vocab#"
DC = "http://purl.org/dc/terms/"
FOAF = "http://xmlns.com/foaf/0.1/"
XSD = "http://www.w3.org/2001/XMLSchema#"
SCHEMA = "https://schema.org/"


def read(
    html: str, base_url: str | None = "https://e.com/p"
) -> list[dict[str, object]]:
    return RDFaExtractor().extract(html, base_url=base_url)


def test_opengraph_links_and_roles_are_what_real_pages_yield():
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<meta property="og:image" content="a.jpg">'
        '<meta property="og:image" content="b.jpg">'
        '<meta property="twitter:card" content="summary">'
        '<meta property="al:ios:url" content="app://x">'
        '<meta property="description" content="not a term">'
        '<link rel="license" href="/licence"><link rel="stylesheet" href="s.css">'
        '<link rel="https://api.w.org/" href="https://e.com/wp-json/"></head>'
        '<body><div role="main" id="content"><nav role="navigation doc-toc"></nav>'
        "</div></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            "al:ios:url": [{"@value": "app://x"}],
            "http://ogp.me/ns#image": [{"@value": "a.jpg"}, {"@value": "b.jpg"}],
            "http://ogp.me/ns#title": [{"@value": "T"}],
            XHV + "license": [{"@id": "https://e.com/licence"}],
            "https://api.w.org/": [{"@id": "https://e.com/wp-json/"}],
            "https://dev.twitter.com/cards#card": [{"@value": "summary"}],
        },
        {"@id": "https://e.com/p#content", XHV + "role": [{"@id": XHV + "main"}]},
        {
            "@id": "_:b0",
            XHV + "role": [{"@id": XHV + "navigation"}, {"@id": XHV + "doc-toc"}],
        },
    ]


def test_without_a_base_url_the_page_is_the_empty_address():
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<link rel="license" href="/licence"></head></html>'
    )

    assert read(html, base_url=None) == [
        {
            "@id": "",
            "http://ogp.me/ns#title": [{"@value": "T"}],
            XHV + "license": [{"@id": "/licence"}],
        }
    ]


def test_schema_org_under_a_vocabulary_nests_through_blank_nodes():
    html = (
        '<html><body><ol vocab="https://schema.org/" typeof="BreadcrumbList">'
        '<li property="itemListElement" typeof="ListItem">'
        '<a property="item" typeof="WebPage" href="https://e.com/">'
        '<span property="name">Home</span></a><meta property="position" content="1">'
        '</li><li property="itemListElement" typeof="ListItem">'
        '<span property="name">Here</span><meta property="position" content="2">'
        "</li></ol></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            "http://www.w3.org/ns/rdfa#usesVocabulary": [{"@id": SCHEMA}],
        },
        {
            "@id": "_:b0",
            "@type": [SCHEMA + "BreadcrumbList"],
            SCHEMA + "itemListElement": [{"@id": "_:b1"}, {"@id": "_:b2"}],
        },
        {
            "@id": "_:b1",
            "@type": [SCHEMA + "ListItem"],
            SCHEMA + "item": [{"@id": "https://e.com/"}],
            SCHEMA + "position": [{"@value": "1"}],
        },
        {
            "@id": "_:b2",
            "@type": [SCHEMA + "ListItem"],
            SCHEMA + "name": [{"@value": "Here"}],
            SCHEMA + "position": [{"@value": "2"}],
        },
        {
            "@id": "https://e.com/",
            "@type": [SCHEMA + "WebPage"],
            SCHEMA + "name": [{"@value": "Home"}],
        },
    ]


def test_xml_lang_gives_a_literal_its_language_and_lang_does_not():
    # RDFa Core, as extruct configures pyRdfa: only xml:lang is read.
    html = (
        '<html xml:lang="EN" lang="fr"><head><meta property="og:title" content="T">'
        '<meta property="og:x" content="y" xml:lang=""></head></html>'
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            "http://ogp.me/ns#title": [{"@language": "en", "@value": "T"}],
            "http://ogp.me/ns#x": [{"@value": "y"}],
        }
    ]


def test_a_language_rdflib_refuses_is_kept():
    # extruct raises ValueError: 'en_us' is not a valid language tag.
    html = (
        '<html><head><meta property="og:title" content="T" xml:lang="en_US">'
        "</head></html>"
    )

    assert read(html)[0]["http://ogp.me/ns#title"] == [
        {"@language": "en_us", "@value": "T"}
    ]


def test_a_prefix_attribute_is_read_in_pairs_from_its_end():
    # Nine tokens: pyRdfa pairs them from the end and so declares nothing, and
    # a CURIE with an undeclared prefix is an IRI with that scheme.
    html = (
        '<html prefix="ex: http://example.com/a# ex: http://example.com/b# bad '
        'http://x/ v: http://v.example/ odd"><head xmlns:my="http://my.example/ns#">'
        '<meta property="ex:one" content="1"><meta property="my:two" content="2">'
        '<meta property="EX:three" content="3">'
        '<meta property="unknown:four" content="4">'
        '<meta property=":five" content="5"><meta property="og://six" content="6">'
        "</head></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            "EX:three": [{"@value": "3"}],
            "ex:one": [{"@value": "1"}],
            "http://my.example/ns#two": [{"@value": "2"}],
            XHV + "five": [{"@value": "5"}],
            "og://six": [{"@value": "6"}],
            "unknown:four": [{"@value": "4"}],
        }
    ]


def test_a_prefix_declared_twice_keeps_its_first_declaration():
    html = (
        '<html prefix="ex: http://a.example/ ex: http://b.example/ _: http://c/ '
        '9x: http://d/"><head><meta property="EX:p" content="1"></head></html>'
    )

    assert read(html)[0]["http://a.example/p"] == [{"@value": "1"}]


def test_subjects_chain_rel_rev_and_safe_curies():
    html = (
        '<html><body><div about="#me" rel="foaf:knows">'
        '<span about="#you" property="foaf:name">You</span>'
        '<span typeof="foaf:Person"><span property="foaf:name">Them</span></span></div>'
        '<div about="#me" rev="foaf:made" resource="#thing"></div>'
        '<p about="[bad" property="foaf:x">x</p>'
        '<p about="[foaf:y]" property="foaf:z">z</p></body></html>'
    )

    assert read(html) == [
        {"@id": "https://e.com/p#you", FOAF + "name": [{"@value": "You"}]},
        {
            "@id": "https://e.com/p#me",
            FOAF + "knows": [{"@id": "https://e.com/p#you"}, {"@id": "_:b0"}],
        },
        {
            "@id": "_:b0",
            "@type": [FOAF + "Person"],
            FOAF + "name": [{"@value": "Them"}],
        },
        {
            "@id": "https://e.com/p#thing",
            FOAF + "made": [{"@id": "https://e.com/p#me"}],
        },
        {"@id": "https://e.com/p", FOAF + "x": [{"@value": "x"}]},
        {"@id": FOAF + "y", FOAF + "z": [{"@value": "z"}]},
    ]


def test_an_empty_safe_curie_is_no_subject():
    # extruct raises AttributeError: pyRdfa removes the attribute with a DOM
    # method extruct's lxml elements lack. What pyRdfa means is answered.
    html = (
        '<html><body><p about="[]" property="dc:w">w</p>'
        '<p resource="[]" property="dc:v" href="/h">v</p></body></html>'
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            DC + "v": [{"@id": "https://e.com/h"}],
            DC + "w": [{"@value": "w"}],
        }
    ]


def test_incomplete_triples_are_completed_by_the_children_that_name_a_subject():
    html = (
        '<html><body><div about="#a" rev="dc:hasPart"><span about="#b"></span>'
        '<span about="#c"></span></div><div about="#x" rel="dc:relation"><div>'
        '<span about="#y">y</span></div></div>'
        '<div typeof="foaf:Person" about="#t"></div>'
        '<div rel="dc:r" typeof="foaf:Doc" resource="#doc"></div>'
        '<div property="dc:p" typeof="foaf:Doc"><span property="dc:q">inner</span>'
        "</div>"
        '<div property="dc:p2" typeof="foaf:Doc" href="/h"></div></body></html>'
    )

    assert read(html) == [
        {"@id": "https://e.com/p#b", DC + "hasPart": [{"@id": "https://e.com/p#a"}]},
        {"@id": "https://e.com/p#c", DC + "hasPart": [{"@id": "https://e.com/p#a"}]},
        {"@id": "https://e.com/p#x", DC + "relation": [{"@id": "https://e.com/p#y"}]},
        {"@id": "https://e.com/p#t", "@type": [FOAF + "Person"]},
        {"@id": "https://e.com/p#doc", "@type": [FOAF + "Doc"]},
        {
            "@id": "https://e.com/p",
            DC + "p": [{"@id": "_:b0"}],
            DC + "p2": [{"@id": "https://e.com/h"}],
            DC + "r": [{"@id": "https://e.com/p#doc"}],
        },
        {"@id": "_:b0", "@type": [FOAF + "Doc"], DC + "q": [{"@value": "inner"}]},
        {"@id": "https://e.com/h", "@type": [FOAF + "Doc"]},
    ]


def test_typed_literals_are_written_as_rdflib_writes_them():
    html = (
        '<html><body><div about="#x"><span property="dc:i" datatype="xsd:integer">01'
        '</span><span property="dc:b" datatype="xsd:boolean" content="True"></span>'
        '<span property="dc:d" datatype="xsd:double">1.50</span>'
        '<span property="dc:dt" datatype="xsd:date">2020-01-01</span>'
        '<span property="dc:e" datatype="">plain</span>'
        '<span property="dc:u" datatype="nope">untyped</span>'
        '<span property="dc:s" datatype="xsd:string">s</span>'
        '<span property="dc:bad" datatype="xsd:integer">abc</span>'
        '<span property="dc:xml" datatype="rdf:XMLLiteral">a <b class="k">bold</b> tail'
        "</span></div></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#x",
            DC + "b": [{"@type": XSD + "boolean", "@value": True}],
            DC + "bad": [{"@type": XSD + "integer", "@value": "abc"}],
            DC + "d": [{"@type": XSD + "double", "@value": 1.5}],
            DC + "dt": [{"@type": XSD + "date", "@value": "2020-01-01"}],
            DC + "e": [{"@value": "plain"}],
            DC + "i": [{"@type": XSD + "integer", "@value": 1}],
            DC + "s": [{"@type": XSD + "string", "@value": "s"}],
            DC + "u": [{"@value": "untyped"}],
            # pyRdfa's copy of an element carries its tail, written again after.
            DC + "xml": [
                {
                    "@type": rdfa.RDF + "XMLLiteral",
                    "@value": 'a <b class="k">bold</b> tail tail',
                }
            ],
        }
    ]


def test_an_html_literal_and_a_plain_literal_with_a_comment_in_it():
    html = (
        '<html><body><div about="#x" property="dc:h" datatype="rdf:HTML">a <b>b</b>'
        '</div><div about="#x" property="dc:c"><!-- note -->text<script>s</script>'
        "</div></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#x",
            DC + "c": [{"@value": " note texts"}],
            DC + "h": [{"@type": rdfa.RDF + "HTML", "@value": "a <b>b</b>"}],
        }
    ]


def test_inlist_builds_rdf_lists():
    html = (
        '<html><body><div about="#x"><span property="dc:creator" inlist>A</span>'
        '<span property="dc:creator" inlist>B</span>'
        '<a rel="dc:source" inlist href="/s1"></a>'
        '<span rel="dc:relation" inlist></span>'
        "</div></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#x",
            DC + "creator": [{"@list": [{"@value": "A"}, {"@value": "B"}]}],
            DC + "relation": [{"@list": []}],
            DC + "source": [{"@list": [{"@id": "https://e.com/s1"}]}],
        }
    ]


def test_a_list_filled_by_children_that_name_its_members():
    html = (
        '<html><body><div about="#x" rel="dc:parts" inlist>'
        '<span about="#one"></span><span about="#two"></span></div></body></html>'
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#x",
            DC + "parts": [
                {
                    "@list": [
                        {"@id": "https://e.com/p#one"},
                        {"@id": "https://e.com/p#two"},
                    ]
                }
            ],
        }
    ]


def test_rdfa_1_0_when_the_root_says_so():
    html = (
        '<html version="XHTML+RDFa 1.0" xmlns:dc="http://purl.org/dc/terms/" '
        'xmlns="http://www.w3.org/1999/xhtml"><head><meta property="dc:title" '
        'content="T"></head><body><div about="/node/1" typeof="sioc:Item">'
        '<div property="dc:description">Some <b>bold</b> text</div>'
        '<a rel="next" href="/2">n</a><span role="main">r</span></div></body></html>'
    )

    assert read(html) == [
        {"@id": "https://e.com/p", DC + "title": [{"@value": "T"}]},
        {
            "@id": "https://e.com/node/1",
            DC + "description": [
                {
                    "@type": rdfa.RDF + "XMLLiteral",
                    "@value": 'Some <b xmlns:dc="http://purl.org/dc/terms/" '
                    'xmlns="http://www.w3.org/1999/xhtml">bold</b> text text',
                }
            ],
            XHV + "next": [{"@id": "https://e.com/2"}],
        },
    ]


def test_rdfa_1_0_types_the_parent_s_subject_as_pyrdfa_does():
    html = (
        '<html version="HTML+RDFa 1.0" xmlns:foaf="http://xmlns.com/foaf/0.1/">'
        '<body><div about="#a"><span typeof="foaf:Person"></span>'
        '<span rel="foaf:knows"><i about="#b"></i></span>'
        '<span rev="foaf:made" href="#c"></span><span rev="foaf:x"><i about="#d"></i>'
        "</span></div></body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#a",
            "@type": [FOAF + "Person"],
            FOAF + "knows": [{"@id": "https://e.com/p#b"}],
        },
        {"@id": "https://e.com/p#c", FOAF + "made": [{"@id": "https://e.com/p#a"}]},
        {"@id": "https://e.com/p#d", FOAF + "x": [{"@id": "https://e.com/p#a"}]},
    ]


def test_rdfa_1_1_when_the_root_says_so_too():
    html = '<html version="XHTML+RDFa 1.1"><head><meta property="og:t" content="T">'

    assert read(html)[0]["http://ogp.me/ns#t"] == [{"@value": "T"}]


def test_a_pattern_is_copied_where_it_is_used():
    html = (
        '<html><body><div about="#a"><link rel="rdfa:copy" href="#pat"></div>'
        '<div resource="#pat" typeof="rdfa:Pattern"><span property="dc:title">Shared'
        "</span></div></body></html>"
    )

    assert read(html) == [
        {"@id": "https://e.com/p#a", DC + "title": [{"@value": "Shared"}]}
    ]


def test_xml_base_and_vocab_set_what_follows():
    html = (
        '<html xml:base="https://base.example/dir/#frag"><body>'
        '<a rel="license" href="lic"></a><div xml:base="https://other.example/">'
        '<a rel="license" href="x"></a></div><div vocab="https://schema.org/">'
        '<span property="name">N</span></div><div vocab="">'
        '<span property="name">none</span></div></body></html>'
    )

    assert read(html) == [
        {
            "@id": "https://base.example/dir/",
            XHV + "license": [
                {"@id": "https://base.example/dir/lic"},
                {"@id": "https://other.example/x"},
            ],
            "http://www.w3.org/ns/rdfa#usesVocabulary": [{"@id": SCHEMA}],
            SCHEMA + "name": [{"@value": "N"}],
        }
    ]


def test_named_blank_nodes_are_one_node_per_label():
    html = (
        '<html><body><div about="_:a" property="dc:t">A</div>'
        '<div about="_:a" property="dc:u">U</div><div about="[_:]" property="dc:v">V'
        '</div><div about="_:" property="dc:w">W</div></body></html>'
    )

    assert read(html) == [
        {"@id": "_:b0", DC + "t": [{"@value": "A"}], DC + "u": [{"@value": "U"}]},
        {"@id": "_:b1", DC + "v": [{"@value": "V"}], DC + "w": [{"@value": "W"}]},
    ]


def test_the_same_page_gives_the_same_graph_in_the_same_order():
    html = (
        '<html><body><nav role="navigation"></nav><div role="main"></div></body></html>'
    )

    assert read(html) == read(html)
    assert [node["@id"] for node in read(html)] == ["_:b0", "_:b1"]


def test_a_page_nested_deeper_than_libxml2_s_default_is_read():
    # extruct answers []: libxml2 drops everything below 256 levels.
    html = (
        "<html><body>"
        + "<div>" * 300
        + '<span about="#d" property="dc:title">deep</span>'
        + "</div>" * 300
    )

    assert read(html) == [
        {"@id": "https://e.com/p#d", DC + "title": [{"@value": "deep"}]}
    ]


def test_an_address_urljoin_refuses_is_kept_as_written():
    # extruct raises ValueError.
    html = '<html><body><a rel="license" href="https://[domain]/x">l</a></body></html>'

    assert read(html)[0][XHV + "license"] == [{"@id": "https://[domain]/x"}]


def test_a_page_that_would_copy_more_than_its_budget_gets_the_start():
    names = " ".join(f"dc:n{i}" for i in range(300))
    html = (
        '<html><head><meta property="og:title" content="kept"></head><body>'
        f'<div about="#x" property="{names}">' + "x" * 300 + "</div></body></html>"
    )

    found = read(html)

    # The page's head, then as many of the 300 copies as the budget paid for.
    assert found[0] == {
        "@id": "https://e.com/p",
        "http://ogp.me/ns#title": [{"@value": "kept"}],
    }
    assert 0 < len(found[1]) - 1 < 300


def test_only_the_expanded_form_is_written():
    with pytest.raises(ValueError, match="expanded"):
        RDFaExtractor().extract("<p>x</p>", expanded=False)


def test_rdfa_from_a_tree():
    tree = lxml.html.fromstring(
        '<html><head><meta property="og:t" content="T"></head></html>'
    )

    assert RDFaExtractor().extract_items(tree, base_url="https://e.com/") == [
        {"@id": "https://e.com/", "http://ogp.me/ns#t": [{"@value": "T"}]}
    ]


# --- the pieces --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "scheme"),
    [
        ("https://e.com/", "https"),
        ("  HTTP:x", "http"),
        ("a+b.c-d:x", "a+b.c-d"),
        ("ht\ttp://x", "http"),
        ("1a:x", ""),
        ("/relative", ""),
        ("é:x", ""),
        ("https://[domain]/", "https"),
    ],
)
def test_a_scheme_is_found_as_urlsplit_finds_it_without_raising(value, scheme):
    assert rdfa._scheme(value) == scheme


def test_rdflib_s_rules_for_the_three_native_types():
    assert rdfa._native("true", XSD + "boolean") is True
    assert rdfa._native("0", XSD + "boolean") is False
    assert rdfa._native("1_000", XSD + "integer") == 1000
    assert rdfa._native("1e2", XSD + "integer") == "1e2"
    assert rdfa._native("x", XSD + "double") == "x"
    assert rdfa._native("01", XSD + "decimal") == "01"


def test_an_xml_literal_is_written_again_as_minidom_writes_it():
    written = rdfa._xml_literal('<i a="1" xmlns:x="u"></i> t')

    assert written.value == '<i xmlns:x="u" a="1"/> t'
    assert rdfa._xml_literal("").value == ""
    assert rdfa._xml_literal("<p>unclosed").value == "<p>unclosed"


def test_a_join_keeps_the_mark_urljoin_swallows():
    assert rdfa._join("https://e.com/a", "b?") == "https://e.com/b?"
    assert rdfa._join("https://e.com/a", "https://[x/") == "https://[x/"
    assert rdfa._without_fragment("https://[x/#f") == "https://[x/#f"


def test_rdf_lists_that_are_not_lists_are_written_as_nodes():
    first, rest = rdfa.IRI(rdfa.RDF + "first"), rdfa.IRI(rdfa.RDF + "rest")
    head, other = rdfa.BNode(1), rdfa.BNode(2)
    writer = rdfa._Writer(
        {
            head: [
                (first, rdfa.Literal("a")),
                (rdfa.IRI("http://p"), rdfa.Literal("x")),
            ],
            other: [(first, rdfa.Literal("a"))],
        }
    )

    assert writer.collection(head) is None
    assert writer.collection(other) is None
    assert writer.collection(rdfa.IRI("http://e.com/")) is None
    looping = rdfa._Writer({head: [(first, rdfa.Literal("a")), (rest, head)]})
    assert looping.collection(head) is None


def test_a_type_that_is_a_blank_node_is_written_under_type_as_a_reference():
    html = '<html><body><div about="#x" typeof="_:t"></div></body></html>'

    assert read(html) == [
        {"@id": "https://e.com/p#x", "@type": [{"@id": "_:b0"}]},
        {"@id": "_:b0"},
    ]


# --- the edges, each checked against extruct ----------------------------------


def test_a_root_naming_an_object_is_still_the_page():
    html = (
        '<html href="/x" rel="license"><head><meta property="og:t" content="T">'
        "</head></html>"
    )

    assert read(html) == [
        {"@id": "https://e.com/p", XHV + "license": [{"@id": "https://e.com/x"}]},
        {"@id": "https://e.com/x", "http://ogp.me/ns#t": [{"@value": "T"}]},
    ]


def test_a_root_naming_a_resource_is_that_resource():
    html = '<html resource="/r"><head><meta property="og:t" content="T"></head></html>'

    assert read(html) == [
        {"@id": "https://e.com/r", "http://ogp.me/ns#t": [{"@value": "T"}]}
    ]


def test_a_root_whose_about_is_no_resource_hands_its_children_a_blank_node():
    html = (
        '<html about="[bad" property="og:lost" content="x"><head>'
        '<meta property="og:t" content="T"><link rel="license" href="/l"></head></html>'
    )

    assert read(html) == [
        {
            "@id": "_:b0",
            "http://ogp.me/ns#t": [{"@value": "T"}],
            XHV + "license": [{"@id": "https://e.com/l"}],
        }
    ]


def test_a_term_matches_in_any_case():
    html = (
        '<html><head><link rel="LICENSE" href="/l"><link rel="describedBy" href="/d">'
        "</head></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            XHV + "license": [{"@id": "https://e.com/l"}],
            "http://www.w3.org/2007/05/powder-s#describedby": [
                {"@id": "https://e.com/d"}
            ],
        }
    ]


def test_a_vocabulary_that_is_the_empty_address_is_no_vocabulary():
    html = (
        '<html><body><div vocab=" "><span property="name">N</span></div></body></html>'
    )

    assert read(html, base_url=None) == []


def test_a_curie_into_a_relative_namespace_is_under_the_base():
    html = (
        '<html prefix="p: rel/"><body><div about="p:x" property="og:t">T</div>'
        '<span about="[:y]" property="og:u">U</span></body></html>'
    )

    assert read(html) == [
        {"@id": "https://e.com/prel/x", "http://ogp.me/ns#t": [{"@value": "T"}]},
        {"@id": XHV + "y", "http://ogp.me/ns#u": [{"@value": "U"}]},
    ]


def test_odd_property_names():
    # extruct raises ValueError on og://[x: its reference check asks urlsplit.
    html = (
        '<html><head><meta property=": 1x:y og://[x og:t" content="v">'
        '<meta property="og:a" datatype=" " content="c"></head></html>'
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p",
            "http://ogp.me/ns#a": [{"@value": "c"}],
            "http://ogp.me/ns#t": [{"@value": "v"}],
            XHV: [{"@value": "v"}],
            "og://[x": [{"@value": "v"}],
        }
    ]


def test_blank_nodes_as_properties_state_nothing():
    html = (
        '<html><body><div about="#a" rel="_:x" rev="_:y" property="_:z" href="/h">t'
        '</div><div about="#b" property="dc:x" resource="[bad"></div></body></html>'
    )

    assert read(html) == []


def test_an_empty_safe_curie_with_space_around_it_is_no_subject_either():
    html = '<html><body><p about=" [] " property="og:t">t</p></body></html>'

    assert read(html) == [
        {"@id": "https://e.com/p", "http://ogp.me/ns#t": [{"@value": "t"}]}
    ]


def test_typeof_beside_rel_or_property_types_the_right_resource():
    html = (
        '<html><body><div about="#a" rel="dc:r" typeof="foaf:D" href="/h"></div>'
        '<div rel="dc:s" typeof="foaf:E"><span property="dc:t">in</span></div>'
        '<div about="#p" property="dc:q" typeof="foaf:F">f</div></body></html>'
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#a",
            "@type": [FOAF + "D"],
            DC + "r": [{"@id": "https://e.com/h"}],
        },
        {"@id": "https://e.com/p", DC + "s": [{"@id": "_:b0"}]},
        {"@id": "_:b0", "@type": [FOAF + "E"], DC + "t": [{"@value": "in"}]},
        {
            "@id": "https://e.com/p#p",
            "@type": [FOAF + "F"],
            DC + "q": [{"@value": "f"}],
        },
    ]


def test_a_statement_made_twice_is_one_and_a_node_named_twice_is_written_once():
    html = (
        '<html><head><meta property="og:t" content="T">'
        '<meta property="og:t" content="T">'
        '</head><body><div about="_:k" property="dc:a">1</div>'
        '<div about="#q" rel="dc:b" resource="_:k"></div>'
        '<div about="#r" rel="dc:c" resource="_:k"></div></body></html>'
    )

    assert read(html) == [
        {"@id": "https://e.com/p", "http://ogp.me/ns#t": [{"@value": "T"}]},
        {"@id": "https://e.com/p#q", DC + "b": [{"@id": "_:b0"}]},
        {"@id": "_:b0", DC + "a": [{"@value": "1"}]},
        {"@id": "https://e.com/p#r", DC + "c": [{"@id": "_:b0"}]},
    ]


def test_a_list_started_twice_and_never_filled_is_empty():
    html = (
        '<html><body><div about="#x"><span rel="dc:r" inlist></span>'
        '<span rel="dc:r" inlist></span></div></body></html>'
    )

    assert read(html) == [{"@id": "https://e.com/p#x", DC + "r": [{"@list": []}]}]


def test_xmlns_declarations_that_declare_nothing():
    html = (
        '<html xmlns:_="http://u/" xmlns:a:b="http://v/"><head>'
        '<meta property="_:t" content="T"><meta property="a:b:c" content="C">'
        "</head></html>"
    )

    assert read(html) == [{"@id": "https://e.com/p", "a:b:c": [{"@value": "C"}]}]


def test_rdfa_1_0_skips_blank_node_properties_and_keeps_a_child_s_own_prefix():
    html = (
        '<html version="HTML+RDFa 1.0" xmlns:dc="http://purl.org/dc/terms/"><body>'
        '<div about="#a" rel="_:x" rev="_:y" property="_:z">t</div><div about="#b">'
        '<div property="dc:d"><b xmlns:dc="http://purl.org/dc/terms/">x</b></div></div>'
        "</body></html>"
    )

    assert read(html) == [
        {
            "@id": "https://e.com/p#b",
            DC + "d": [
                {
                    "@type": rdfa.RDF + "XMLLiteral",
                    "@value": '<b xmlns:dc="http://purl.org/dc/terms/">x</b>',
                }
            ],
        }
    ]


def test_an_empty_href_is_the_base_and_an_absolute_one_needs_no_base():
    empty = '<html><body><a rel="license" href="">x</a></body></html>'
    absolute = (
        '<html><body><a rel="license" href="https://x.example/l">x</a></body></html>'
    )

    assert read(empty) == [
        {"@id": "https://e.com/p", XHV + "license": [{"@id": "https://e.com/p"}]}
    ]
    assert read(absolute, base_url=None) == [
        {"@id": "", XHV + "license": [{"@id": "https://x.example/l"}]}
    ]


def test_a_type_rdflib_s_list_rule_allows_on_a_list_node():
    first, rest = rdfa.IRI(rdfa.RDF + "first"), rdfa.IRI(rdfa.RDF + "rest")
    typed = rdfa.IRI(rdfa.RDF + "type")
    head = rdfa.BNode(1)
    writer = rdfa._Writer(
        {
            head: [
                (typed, rdfa.IRI(rdfa.RDF + "List")),
                (first, rdfa.Literal("a")),
                (rest, rdfa.IRI(rdfa.RDF + "nil")),
            ]
        }
    )

    assert writer.collection(head) == [rdfa.Literal("a")]


@pytest.mark.parametrize(
    "html",
    [
        # Spent by an element: every element pays once as it is entered.
        "<html><body>" + "<i></i>" * 20 + "</body></html>",
        # Spent by a literal's text, by a content attribute, by markup.
        '<html><body><div about="#x" property="dc:t">'
        + "x" * 50
        + "</div></body></html>",
        '<html><body><div about="#x" property="dc:t" content="' + "x" * 50 + '"></div>',
        '<html version="HTML+RDFa 1.0"><body><div about="#x" property="dc:t"><b>x</b>'
        + "<i></i>" * 20
        + "</div></body></html>",
    ],
)
def test_every_cost_is_paid_for_and_a_spent_budget_ends_the_reading(html):
    page = rdfa.read_page(html, "https://e.com/p", "UTF-8")
    graph = rdfa._Graph(rdfa.Budget(0))
    graph.budget.left = 12

    with pytest.raises(rdfa._Spent):
        rdfa._Processor(page, graph).run()
