"""The corners of the readers, the summary and the fetch policy.

Each of these is a shape real pages take, written small: an ``itemref``, a
property repeated three times, an address with no host, a type that is only
whitespace. They are here so a change to any reader has to keep answering them.
"""

import pytest

from sluicer import extract
from sluicer.declared.microdata import read_microdata
from sluicer.declared.rdfa import read_rdfa
from sluicer.declared.types import type_name
from sluicer.document import base_url, load, sniff_encoding


def test_itemref_brings_properties_declared_elsewhere_on_the_page():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product" itemref="price">'
        '<span itemprop="name">Pad</span></div>'
        '<p id="price"><span itemprop="price">41.99</span></p>'
    )

    assert read_microdata(doc) == [
        {"@type": "Product", "name": "Pad", "price": "41.99"}
    ]


def test_an_item_that_refers_to_itself_is_read_once():
    doc = load(
        '<div id="a" itemscope itemtype="https://schema.org/Product" itemref="a b">'
        '<span itemprop="name">Pad</span></div>'
        '<span id="b" itemprop="sku">S1</span>'
    )

    assert read_microdata(doc) == [{"@type": "Product", "name": "Pad", "sku": "S1"}]


def test_a_property_declared_three_times_is_a_list_of_three():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Recipe">'
        + "".join(f'<li itemprop="step">Step {n}</li>' for n in range(3))
        + "</div>"
    )

    assert read_microdata(doc)[0]["step"] == ["Step 0", "Step 1", "Step 2"]


def test_a_nested_item_that_says_nothing_is_not_a_value():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Pad</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"></div>'
        '<span itemprop="">no name</span>'
        "</div>"
    )

    assert read_microdata(doc) == [{"@type": "Product", "name": "Pad"}]


def test_items_nested_past_the_bound_stop_instead_of_recursing():
    depth = 40
    opening = (
        '<div itemprop="part" itemscope itemtype="https://schema.org/Thing">' * depth
    )
    doc = load(
        '<div itemscope itemtype="https://schema.org/Thing"><span itemprop="name">top'
        f"</span>{opening}<span itemprop='name'>deep</span>{'</div>' * depth}</div>"
    )

    top = read_microdata(doc)[0]

    assert top["name"] == "top"


def test_an_item_that_is_a_property_of_nothing_is_a_top_level_item():
    doc = load(
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">5</span></div>'
        "<div itemscope></div>"
    )

    assert read_microdata(doc) == [{"@type": "Offer", "price": "5"}]


def test_a_time_without_a_datetime_is_its_text_and_content_wins_over_text():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Event">'
        '<time itemprop="startDate">tomorrow</time>'
        '<span itemprop="name" content="Launch">the launch</span>'
        "</div>"
    )

    item = read_microdata(doc)[0]

    assert item["startDate"] == "tomorrow"
    assert item["name"] == "Launch"


def test_rdfa_repeats_nests_and_bounds_like_microdata():
    depth = 40
    opening = '<div property="part" typeof="Thing">' * depth
    doc = load(
        '<div vocab="https://schema.org/" typeof="Recipe">'
        + "".join(f'<li property="step">S{n}</li>' for n in range(3))
        + "<!-- a comment is not a property -->"
        + '<div property="nutrition" typeof="NutritionInformation"></div>'
        + '<span property="">nameless</span>'
        + f"{opening}<span property='name'>deep</span>{'</div>' * depth}"
        + "</div>"
        + '<div property="orphan" typeof="Thing">'
        + '<span property="name">alone</span></div>'
    )

    found = read_rdfa(doc)

    assert found[0]["step"] == ["S0", "S1", "S2"]
    assert "nutrition" not in found[0]
    assert found[1] == {"@type": "Thing", "name": "alone"}


def test_rdfa_prefixes_are_read_from_every_ancestor_and_odd_tokens_ignored():
    doc = load(
        '<div prefix="ex: https://example.org/ns# broken">'
        '<div typeof="ex:Widget"><span property="ex:size">L</span>'
        '<span property="og:title">left to OpenGraph</span></div></div>'
    )

    assert read_rdfa(doc) == [
        {"@type": "https://example.org/ns#Widget", "https://example.org/ns#size": "L"}
    ]


def test_a_type_that_is_only_whitespace_is_no_type():
    assert type_name("   ") is None
    assert type_name("http://schema.org/Product/") == "Product"
    assert type_name("https://www.schema.org/Offer") == "Offer"


def test_a_base_without_an_address_is_the_base_as_written():
    assert base_url(load('<base href="/shop/"><p>x</p>')) == "/shop/"
    assert base_url(load('<base href=" "><p>x</p>', url="https://a.example/")) == (
        "https://a.example/"
    )


def test_a_declaration_nobody_knows_in_an_xml_prolog_falls_through_to_the_head():
    page = (
        '<?xml version="1.0" encoding="no-such-codec"?>'
        '<html><head><meta charset="windows-1251"></head></html>'
    )

    assert sniff_encoding(page.encode("ascii")) == "cp1251"


def test_a_meta_without_a_charset_is_passed_over():
    page = (
        '<html><head><meta http-equiv="Content-Type" content="text/html">'
        '<meta name="x" content="y"><meta charset="koi8-r"></head></html>'
    )

    assert sniff_encoding(page.encode("ascii")) == "koi8-r"


def test_a_utf16_byte_order_mark_decides():
    page = "<html><head><title>Bremsöl</title></head></html>"

    assert sniff_encoding(b"\xff\xfe" + page.encode("utf-16-le")) == "utf-16-le"


def test_summary_reads_the_first_useful_item_of_a_list():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Product","name":["", "Pad"],'
        '"image":[{"x":"1"},{"contentUrl":"/i.jpg"}],'
        '"brand":["", {"name":"Textar"}, "https://x.example/brand"],'
        '"offers":["not an offer", {"@type":"Offer","priceCurrency":"EUR"}]}'
        "</script>"
    )

    summary = extract(html, url="https://s.example/p").summary

    assert summary["title"].value == "Pad"
    assert summary["image"].value == "https://s.example/i.jpg"
    assert summary["brand"].value == "Textar"
    assert summary["currency"].value == "EUR"
    assert "price" not in summary


def test_summary_skips_an_empty_canonical_and_an_empty_lang():
    html = (
        '<html lang=" "><head><link rel="canonical" href=" ">'
        '<link rel="stylesheet" href="/s.css">'
        '<meta property="og:url" content="https://x.example/p"></head></html>'
    )

    summary = extract(html).summary

    assert summary["url"].value == "https://x.example/p"
    assert "language" not in summary


def test_a_person_with_only_a_family_name_is_still_named():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Article","headline":"H","author":{"givenName":" ","familyName":"X"}}'
        "</script>"
    )

    assert extract(html).summary["author"].value == "X"


def test_an_address_without_a_host_or_that_does_not_resolve():
    from sluicer.fetch.address import why_not_public

    def unresolvable(host):
        raise OSError("no such host")

    assert why_not_public("http:///x") == "the address names no host"
    assert why_not_public("https://nowhere.invalid/", unresolvable) is None
    assert (
        why_not_public("https://example.com/", lambda host: ["93.184.215.14"]) is None
    )


def test_the_default_resolver_asks_the_system(monkeypatch):
    import socket

    from sluicer.fetch.address import why_not_public

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("10.1.2.3", 0))],
    )

    assert "10.1.2.3" in why_not_public("https://intranet.example/")


def test_a_fallback_page_is_still_checked_for_where_it_landed():
    from sluicer.fetch import AddressRefused, fetch
    from sluicer.fetch.result import Fetched

    shell = (
        '<html><body><div id="root"></div><script src="/a.js"></script></body></html>'
    )

    def http(url):
        return Fetched(url="http://127.0.0.1/", html=shell, status=200, rung="http")

    def browser(url):
        raise RuntimeError("no browser")

    with pytest.raises(AddressRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", http), ("browser", browser)],
            obey_robots=False,
            allow_private=False,
            resolve=lambda host: ["93.184.215.14"],
        )


def test_a_redirect_the_new_host_allows_is_returned():
    from sluicer.fetch import fetch
    from sluicer.fetch.result import Fetched

    rich = (
        '<script type="application/ld+json">{"@type":"Product","name":"P"}</script>'
        + "<p>"
        + "Real content. " * 30
        + "</p>"
    )

    def http(url):
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="", status=404, rung="http")
        return Fetched(
            url="https://other.example/p", html=rich, status=200, rung="http"
        )

    assert fetch("https://example.com/p", rungs=[("http", http)]).url == (
        "https://other.example/p"
    )


def test_empty_standard_input_is_reported():
    from click.testing import CliRunner

    from sluicer.cli import main

    result = CliRunner().invoke(main, ["extract", "-"], input="   ")

    assert result.exit_code == 2
    assert "Standard input contains no HTML" in result.stderr


def test_microformats_without_its_extra_is_a_message_at_the_command_line(monkeypatch):
    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.declared.microformats import MicroformatsExtraMissing

    def missing(*args, **kwargs):
        raise MicroformatsExtraMissing(
            "install sluicer[microformats]", extra="microformats"
        )

    monkeypatch.setattr("sluicer.cli.extract_html", missing)

    result = CliRunner().invoke(
        main, ["extract", "-", "--microformats"], input="<p>x</p>"
    )

    assert result.exit_code == 2
    assert "sluicer[microformats]" in result.stderr


def test_an_address_the_server_refuses_is_an_answer(monkeypatch):
    import sys
    import types

    from sluicer.fetch import AddressRefused

    registered = {}

    class MCPServer:
        def __init__(self, name, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorate(function):
                registered[function.__name__] = function
                return function

            return decorate

    module = types.ModuleType("mcp.server.mcpserver")
    module.MCPServer = MCPServer
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", module)

    def refuse(url, **kwargs):
        raise AddressRefused(url, "127.0.0.1 is not on the public internet")

    monkeypatch.setattr("sluicer.fetch.fetch", refuse)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["fetch_page"]("http://127.0.0.1:8080/admin")

    assert result["error"]["url"] == "http://127.0.0.1:8080/admin"
    assert result["error"]["code"] == "refused_address"


def _timed(html: str) -> float:
    import time

    started = time.perf_counter()
    extract(html)
    return time.perf_counter() - started


def test_items_that_itemref_each_other_cost_a_bounded_amount():
    # Seconds, with a margin of hundreds: the unbounded walk took half an hour.
    """Four items naming each other with itemref took an estimated half hour."""
    ids = [f"p{i}" for i in range(6)]
    parts = [
        '<div itemscope itemtype="https://schema.org/Product" '
        f'itemref="{" ".join(ids)}"><span itemprop="name">top</span></div>'
    ]
    for i in ids:
        others = " ".join(j for j in ids if j != i)
        parts.append(
            f'<div id="{i}" itemprop="isRelatedTo" itemscope '
            f'itemtype="https://schema.org/Product" itemref="{others}">'
            f'<span itemprop="name">{i}</span></div>'
        )

    assert _timed("<html><body>" + "".join(parts) + "</body></html>") < 2


def test_items_that_itemref_each_other_are_walked_a_bounded_number_of_times():
    """Found while bounding what microdata copies: the walk was paid for by no one.

    Each top-level item may expand 256 nested ones, and each expansion walked
    the nested item's markup again, so fifty items naming a core of seven that
    name each other walked 256 times the core fifty times: 2.3 seconds for a
    29 KB page, growing with its square. Every element walked is now paid for
    from the page's budget.
    """
    core = [f"g{i}" for i in range(7)]
    filler = "<i>f</i>" * 500
    parts = [
        f'<div id="{name}" itemprop="r" itemscope '
        f'itemref="{" ".join(other for other in core if other != name)}">'
        f"{filler}</div>"
        for name in core
    ]
    parts += [f'<div itemscope itemref="{" ".join(core)}"></div>'] * 50

    assert _timed("".join(parts)) < 1


def test_thousands_of_references_to_one_large_node_cost_a_bounded_amount():
    """A 119 KB page took 12 seconds and 4 GB when every reference was copied."""
    import json

    n = 4000
    target = {
        "@type": "Thing",
        "@id": "#t",
        "name": "t",
        "tags": [{"x": str(i)} for i in range(n)],
    }
    refs = {
        "@type": "Product",
        "name": "p",
        "isRelatedTo": [{"@id": "#t"} for _ in range(n)],
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@graph": [target, refs]})
        + "</script>"
    )

    from sluicer.declared import jsonld

    sized = []
    real_size = jsonld._size

    def counting(value):
        sized.append(1)
        return real_size(value)

    jsonld._size = counting
    try:
        records = extract(html).records
    finally:
        jsonld._size = real_size

    # The page itself is sized once, and the node its references name once.
    assert len(sized) == 2
    related = records[-1].fields["isRelatedTo"].value
    resolved = [item for item in related if "tags" in item]
    assert 0 < len(resolved) < 50
    assert all(item == {"@id": "#t"} for item in related if "tags" not in item)


def test_hundreds_of_references_to_one_long_string_cost_a_bounded_amount():
    """Found by the property that what a page yields is bounded by its size.

    The budget counted values and not characters, so a node holding one long
    name cost three to copy however long the name: every one of 400 references
    to a 4,000-character name was resolved, 1.6 MB of JSON from a 10 KB page,
    and the ratio grows with the page.
    """
    import json

    from sluicer.declared.jsonld import read_jsonld
    from sluicer.document import load

    graph = [
        {"@id": "#t", "@type": "Thing", "name": "x" * 4000},
        {"@type": "Product", "name": "p", "isRelatedTo": [{"@id": "#t"}] * 400},
    ]
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@graph": graph})
        + "</script>"
    )

    found = read_jsonld(load(html))

    related = next(node for node in found if node["@type"] == "Product")
    resolved = [item for item in related["isRelatedTo"] if "name" in item]
    assert 0 < len(resolved) < 20
    assert len(json.dumps(found)) < 11 * len(html)


def test_a_reference_is_still_resolved_when_the_page_is_small():
    import json

    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@graph": [
                    {"@type": "Product", "name": "p", "brand": {"@id": "#b"}},
                    {"@type": "Brand", "@id": "#b", "name": "Textar"},
                ]
            }
        )
        + "</script>"
    )

    assert extract(html).records[0].fields["brand"].value == {
        "@type": "Brand",
        "name": "Textar",
    }


def test_a_template_placeholder_address_is_kept_as_written_not_raised():
    """``https://[domain]/p`` is what an unfilled template writes."""
    html = (
        '<link rel="canonical" href="https://[domain]/p"><title>t</title>'
        '<div itemscope itemtype="https://schema.org/Product">'
        '<a itemprop="url" href="https://[site-url]/p">x</a></div>'
    )

    result = extract(html, url="https://example.com/")

    assert result.summary["url"].value == "https://[domain]/p"
    assert result.records[0].fields["url"].value == "https://[site-url]/p"
    assert extract('<base href="http://[x/"><title>t</title>').summary


def test_the_filter_reads_a_host_the_way_the_client_will():
    from sluicer.fetch.address import why_not_public

    public = lambda host: ["93.184.215.14"]  # noqa: E731
    for url in (
        "http://%31%32%37.0.0.1/",
        "http://0177.0.0.1/",
        "http://0x7f.1/",
        "http://2130706433/",
        "http://127.1/",
        "http://127.0.0.1\\@nonexistent.invalid/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::127.0.0.1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[::1]/",
    ):
        assert why_not_public(url, public) is not None, url
    assert why_not_public("https://bücher.example/", public) is None


def test_a_malformed_address_is_a_failed_fetch_not_a_traceback():
    from sluicer.fetch import FetchFailed, fetch

    with pytest.raises(FetchFailed) as raised:
        fetch("http://[::1/", rungs=[("http", lambda url: None)])

    assert "not a valid address" in str(raised.value)


def test_a_robots_file_that_answers_5xx_is_asked_again_next_time():
    from sluicer.fetch import FetchFailed, fetch
    from sluicer.fetch.result import Fetched

    answers = iter([503, 404])
    page = '<script type="application/ld+json">{"@type":"Product","name":"P"}</script>'

    def http(url):
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="busy", status=next(answers), rung="http")
        return Fetched(url=url, html=page, status=200, rung="http")

    with pytest.raises(FetchFailed) as raised:
        fetch("https://busy.example/p", rungs=[("http", http)])
    assert "503" in str(raised.value)
    assert fetch("https://busy.example/p", rungs=[("http", http)]).status == 200


def test_a_body_tag_inside_a_head_comment_does_not_end_the_head():
    page = (
        '<html><head><!-- scripts go after <body> --><meta charset="windows-1251">'
        "<title>Привет</title></head></html>"
    )

    assert load(page.encode("windows-1251")).tree.findtext(".//title") == "Привет"


def test_a_lone_surrogate_in_an_xml_declared_string_is_not_a_traceback():
    page = '<?xml version="1.0" encoding="utf-8"?><html><body>\\ud800</body></html>'

    assert load(page).tree is not None


def test_the_title_the_page_shows_decides_between_headline_and_name():
    """Wikipedia's headline is its short description; its name is the title."""
    html = (
        "<html><head><title>Sluice - Wikipedia</title>"
        '<script type="application/ld+json">'
        '{"@type":"Article","name":"Sluice","headline":"hydraulic structure"}'
        "</script></head></html>"
    )

    assert extract(html).summary["title"].value == "Sluice"


def test_an_uppercase_scheme_is_still_an_address():
    from click.testing import CliRunner

    from sluicer.cli import main

    seen = []

    def fake(url, **kwargs):
        from sluicer.fetch.result import Fetched

        seen.append(url)
        return Fetched(url=url, html="<title>t</title>", status=200, rung="http")

    import sluicer.cli

    original = sluicer.cli.fetch_url
    sluicer.cli.fetch_url = fake
    try:
        CliRunner().invoke(main, ["extract", "HTTPS://example.com/p"])
    finally:
        sluicer.cli.fetch_url = original

    assert seen == ["HTTPS://example.com/p"]


def test_price_currency_and_availability_come_from_one_offer():
    html = (
        '<script type="application/ld+json">{"@type":"Product","name":"P",'
        '"offers":[{"price":"10"},{"price":"12","priceCurrency":"EUR"}]}</script>'
    )

    summary = extract(html).summary

    assert summary["price"].value == "10"
    assert "currency" not in summary


def test_the_type_says_the_reader_that_declared_the_record():
    html = (
        '<meta property="og:title" content="T">'
        '<script type="application/ld+json">{"@type":"Product"}</script>'
    )

    assert extract(html).summary["type"].source == "jsonld"


def test_a_json_ld_list_or_set_object_is_its_items():
    html = (
        '<script type="application/ld+json">{"@type":"Recipe","name":"R",'
        '"recipeIngredient":{"@list":["a","b"]},"keywords":{"@set":["k"]}}</script>'
    )

    fields = extract(html).records[0].fields

    assert fields["recipeIngredient"].value == ["a", "b"]
    assert fields["keywords"].value == ["k"]


def test_an_empty_vocab_resets_the_vocabulary():
    doc = load(
        '<div vocab="http://example.org/v#"><div vocab="" typeof="Thing">'
        '<span property="name">n</span></div></div>'
    )

    assert read_rdfa(doc) == [{"@type": "Thing", "name": "n"}]


def test_every_record_says_which_reader_declared_it():
    rows = "".join(
        f"<li class='r'><a href='/p{n}'>Product {n}</a>"
        f"<span class='p'>{n}.99</span></li>"
        for n in range(4)
    )
    declared = extract(
        '<script type="application/ld+json">{"@type":"Product","name":"P"}</script>'
        '<div itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">1</span></div>'
    )
    induced = extract(f"<ul>{rows}</ul>", induce=True)
    document_only = extract('<meta property="og:title" content="T">')

    assert [r.source for r in declared.records] == ["jsonld", "microdata"]
    assert {r.source for r in induced.records} == {"induced"}
    assert [r.source for r in document_only.records] == [None]


def test_the_filter_refuses_what_is_not_an_address_at_all():
    from sluicer.fetch.address import why_not_public

    public = lambda host: ["93.184.215.14"]  # noqa: E731

    assert why_not_public("http://[::1/", public) == "the address is not a valid URL"
    assert "not a host name" in why_not_public("http://a..b/", public)
    assert "not a host name" in why_not_public("http://a b.example/", public)
    assert why_not_public("http://1.2.3.4.5/", public) is None
    assert why_not_public("http://8.8.8.8/", public) is None
