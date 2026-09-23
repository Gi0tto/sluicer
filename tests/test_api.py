from pathlib import Path

import sluicer
from sluicer.api import _declared_about_its_things

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_reports_records_and_which_readers_fired():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, url="https://example.com/p")

    assert result.url == "https://example.com/p"
    assert result.sources == ["jsonld"]
    assert any(
        r.fields.get("sku") and r.fields["sku"].value == "BP-1187"
        for r in result.records
    )


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
    # JSON-LD has precedence, and the value says where it came from: the
    # reader, and the place on the page.
    assert record.fields["description"] == sluicer.Field(
        value="Described by JSON-LD",
        source="jsonld",
        where="/html/head/script[1]#/description",
    )

    # Each reader contributed the field the other two lack.
    assert record.fields["sku"] == sluicer.Field(
        value="BP-1187", source="jsonld", where="/html/head/script[1]#/sku"
    )
    assert record.fields["mpn"] == sluicer.Field(
        value="GDB1330", source="microdata", where="/html/body/div[1]/span[1]"
    )
    # A meta tag's name is its place.
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
    assert result.records[0].fields["sku"].value == "BP-3041"


def test_a_declaration_that_disagrees_with_the_bytes_does_not_mangle_the_text():
    html = (FIXTURES / "product_latin1_declared.html").read_text(encoding="utf-8")

    result = sluicer.extract(html)

    assert result.sources == ["jsonld"]
    assert result.records[0].fields["name"].value == "Bremsöl"
    assert result.records[0].fields["sku"].value == "BP-7712"


def test_a_document_level_declaration_does_not_switch_induction_off():
    """DC.title says what the page is, not what is in its list."""
    rows = "".join(
        f'<li class="row"><span class="sku">A{n}</span></li>' for n in range(5)
    )
    html = (
        '<html><head><meta name="DC.title" content="Catalogue"></head>'
        f"<body><ul>{rows}</ul></body></html>"
    )

    result = sluicer.extract(html, induce=True)

    assert "induced" in result.sources
    assert len([r for r in result.records if r.fields.get("span.sku")]) == 5


def test_the_gate_asks_which_sources_describe_a_thing():
    """The test above now reaches the gate for real: ``extract`` calls the
    Dublin Core reader, so a page whose only declaration is ``DC.title``
    arrives here carrying a ``dublincore`` field. The rule stays pinned here
    as well, at the gate itself, where the answer for the next document-level
    vocabulary can be put to the question without anyone having to add it to
    a list first -- which is how the Twitter card arrived needing no change
    to ``ABOUT_A_THING`` at all.
    """
    page_level = sluicer.Record(
        fields={"title": sluicer.Field(value="Catalogue", source="dublincore")}
    )
    thing_level = sluicer.Record(
        fields={"sku": sluicer.Field(value="A1", source="jsonld")}
    )

    assert _declared_about_its_things([page_level]) is False
    assert _declared_about_its_things([thing_level]) is True


def test_every_reader_that_fired_is_reported_in_the_order_of_precedence():
    """Seven vocabularies on one page, and ``sources`` names them in order."""
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"From JSON-LD"}</script>'
        '<meta name="DC.title" content="From Dublin Core">'
        '<meta property="og:site_name" content="From OpenGraph">'
        '<meta name="twitter:card" content="summary">'
        '<meta name="description" content="From the bare meta tag">'
        "</head><body>"
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="mpn">From microdata</span></div>'
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="gtin">From RDFa</span></div>'
        "</body></html>"
    )

    result = sluicer.extract(html)

    assert result.sources == [
        "jsonld",
        "microdata",
        "rdfa",
        "dublincore",
        "opengraph",
        "twitter",
        "html",
    ]


def test_the_earlier_vocabulary_wins_the_field():
    html = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"From JSON-LD"}</script>'
        "</head><body>"
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">From RDFa</span></div>'
        "</body></html>"
    )

    record = sluicer.extract(html).records[0]

    assert record.fields["name"].value == "From JSON-LD"
    assert record.fields["name"].source == "jsonld"


def test_opengraph_wins_a_colliding_key_whichever_tag_the_page_wrote_first():
    """The rule is the precedence, not the order the author typed.

    Before the Twitter card was split out, one reader returned both
    vocabularies and picked between them with document order, so these two
    pages gave different answers and both of them said ``opengraph``.
    """
    og_first = (
        "<html><head>"
        '<meta property="og:title" content="From OpenGraph">'
        '<meta name="twitter:title" content="From the Twitter card">'
        "</head><body></body></html>"
    )
    card_first = (
        "<html><head>"
        '<meta name="twitter:title" content="From the Twitter card">'
        '<meta property="og:title" content="From OpenGraph">'
        "</head><body></body></html>"
    )

    for html in (og_first, card_first):
        title = sluicer.extract(html).records[0].fields["title"]
        assert title == sluicer.Field(value="From OpenGraph", source="opengraph")


def test_a_key_only_the_twitter_card_declares_says_so():
    html = (
        "<html><head>"
        '<meta property="og:title" content="From OpenGraph">'
        '<meta name="twitter:card" content="summary_large_image">'
        "</head><body></body></html>"
    )

    result = sluicer.extract(html)

    assert result.sources == ["opengraph", "twitter"]
    assert result.records[0].fields["card"] == sluicer.Field(
        value="summary_large_image", source="twitter"
    )


def test_a_page_whose_only_declaration_is_a_twitter_card_still_induces():
    """A card describes the document, exactly as OpenGraph does.

    ``ABOUT_A_THING`` names the vocabularies that describe a thing, so a
    vocabulary added outside it needs no change to the gate at all.
    """
    rows = "".join(
        f'<li class="row"><span class="sku">A{n}</span></li>' for n in range(5)
    )
    html = (
        '<html><head><meta name="twitter:title" content="Catalogue"></head>'
        f"<body><ul>{rows}</ul></body></html>"
    )

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["twitter", "induced"]
    assert len([r for r in result.records if r.fields.get("span.sku")]) == 5


def test_a_real_vocabulary_beats_a_bare_meta_name():
    html = (
        "<html><head>"
        '<meta property="og:description" content="FROM OPENGRAPH">'
        '<meta name="description" content="FROM THE BARE META TAG">'
        "</head></html>"
    )

    field = sluicer.extract(html).records[0].fields["description"]

    assert field.value == "FROM OPENGRAPH"
    assert field.source == "opengraph"


def test_a_bare_meta_name_fills_what_no_vocabulary_declared():
    """Last in precedence is not the same as unread: it is what reaches pages."""
    html = (
        "<html><head>"
        '<meta property="og:title" content="From OpenGraph">'
        '<meta name="author" content="Nancy Peyer">'
        "</head></html>"
    )

    result = sluicer.extract(html)

    assert result.sources == ["opengraph", "html"]
    assert result.records[0].fields["author"] == sluicer.Field(
        value="Nancy Peyer", source="html"
    )


def test_a_bare_meta_name_does_not_switch_induction_off():
    rows = "".join(
        f'<li class="r"><span class="sku">A{n}</span></li>' for n in range(5)
    )
    html = (
        '<html><head><meta name="description" content="A catalogue."></head>'
        f"<body><ul>{rows}</ul></body></html>"
    )

    assert "induced" in sluicer.extract(html, induce=True).sources
