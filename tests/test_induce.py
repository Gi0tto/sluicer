from pathlib import Path

import sluicer
from sluicer.document import load
from sluicer.structure import induce

FIXTURES = Path(__file__).parent / "fixtures"


def listing():
    return load((FIXTURES / "listing_no_declared_data.html").read_text())


def test_a_page_that_declares_nothing_still_yields_records():
    records = induce(listing())

    assert len(records) == 4


def test_every_induced_field_says_it_was_induced():
    records = induce(listing())

    for record in records:
        for field in record.fields.values():
            assert field.source == "induced"


def test_the_values_are_the_ones_on_the_page():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "Brake pad set" in values
    assert "41.99" in values


def test_every_slot_of_the_row_is_named_and_the_names_are_these():
    """The names are the whole interface of an induced record, so they are pinned."""
    records = induce(listing())

    assert {name: field.value for name, field in records[0].fields.items()} == {
        "h3.name": "Brake pad set",
        "span.price": "41.99",
        "a.more": "details",
        "a.more@href": "/p/1",
    }


def test_a_link_keeps_its_address():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "/p/1" in values


def test_induction_is_off_unless_asked():
    html = (FIXTURES / "listing_no_declared_data.html").read_text()

    assert sluicer.extract(html).records == []
    assert sluicer.extract(html, induce=True).records


def test_a_page_that_declares_data_is_not_second_guessed():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld"], "declared data stands on its own"


def test_a_declaration_beats_a_list_on_the_same_page():
    """The page above has no list at all, so it could not test the guard.

    This one declares a product *and* repeats five rows underneath it. The
    declaration is what the page says about itself, and it is what comes back;
    the rows are what we would have noticed, and they are not induced.
    """
    html = (FIXTURES / "product_jsonld_and_a_listing.html").read_text()

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld"]
    assert [record.type for record in result.records] == ["Product"]
    values = {
        field.value for record in result.records for field in record.fields.values()
    }
    assert values == {"Brake pad set", "BP-1187", "Bosch"}
    assert "Oil filter" not in values, "the list was induced behind a declaration"


def test_a_page_with_nothing_to_induce_claims_nothing():
    """Asked to induce, and there is no repetition: the answer stays empty."""
    result = sluicer.extract(
        "<html><body><h1>One thing</h1><p>and one line about it</p></body></html>",
        induce=True,
    )

    assert result.records == []
    assert result.sources == []


def test_induction_says_so_when_it_is_what_answered():
    """A caller has to be able to tell which kind of claim they are holding."""
    html = (FIXTURES / "listing_no_declared_data.html").read_text()

    assert sluicer.extract(html, induce=True).sources == ["induced"]
    assert sluicer.extract(html).sources == []


def test_a_crowded_head_does_not_silence_the_page():
    """The reviewer's first constructed page: 14 metas must not be the answer."""
    doc = load((FIXTURES / "listing_under_a_crowded_head.html").read_text())

    records = induce(doc)

    assert len(records) == 5
    assert "Cabin filter" in {
        field.value for field in records[0].fields.values()
    }


def test_the_sidebar_is_not_the_content():
    """The reviewer's second constructed page: the articles, not the widgets."""
    doc = load((FIXTURES / "listing_between_sidebar_and_footer.html").read_text())

    records = induce(doc)

    assert len(records) == 5
    assert "Ana Petrova" in {field.value for field in records[0].fields.values()}


def test_the_next_group_is_read_when_the_best_one_yields_nothing():
    """The best-ranked shape can still hold no field: the ranking is a guess."""
    doc = load(
        "<main>"
        "<ul>"
        + "<li>a line of prose that sits directly in the item, in no element</li>" * 7
        + "</ul>"
        "<div>" + "<div class='c'><h3>Title</h3><span>9.99</span></div>" * 3 + "</div>"
        "</main>"
    )

    records = induce(doc)

    assert len(records) == 3
    assert "Title" in {field.value for field in records[0].fields.values()}


def test_induction_reads_the_best_group_and_not_another_one():
    """Two groups both yield records; the ranked-first one is what comes back."""
    doc = load(
        "<main>"
        "<ul>" + "<li><a href='/t'>x</a></li>" * 6 + "</ul>"
        "<div>"
        + "<article><h3>Real title here</h3><p>Body text</p></article>" * 4
        + "</div>"
        "</main>"
    )

    records = induce(doc)

    assert len(records) == 4
    assert "Real title here" in {field.value for field in records[0].fields.values()}


def test_two_of_a_kind_is_not_induced_either():
    """``induce`` carries the same floor, and carries it as a default."""
    doc = load("<main><ul>" + "<li><h3>t</h3><span>1</span></li>" * 2 + "</ul></main>")

    assert induce(doc) == []
    assert len(induce(doc, minimum=2)) == 2


def test_a_part_with_nothing_in_it_is_not_a_field():
    """An empty element said nothing, so it contributes no field."""
    doc = load("<div>" + "<li><h3>t</h3><span></span></li>" * 3 + "</div>")

    records = induce(doc)

    assert [len(record.fields) for record in records] == [1, 1, 1]


def test_a_group_of_empty_shells_yields_no_records():
    """A record with no fields is not a record, so it is not returned."""
    doc = load("<div>" + "<li><span></span></li>" * 3 + "</div>")

    assert induce(doc) == []


ROWS = "<li class='row'><h3 class='name'>Row</h3><span class='price'>1.00</span></li>"
SIX_ROWS = f"<body><main><ul>{ROWS * 6}</ul></main></body>"


def test_a_declaration_with_no_fields_declares_nothing():
    """An empty script parses. It still says nothing, and the rule is the repo's
    own: an empty value is not a value."""
    html = (
        "<html><head><script type='application/ld+json'>{}</script></head>"
        f"{SIX_ROWS}</html>"
    )

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld", "induced"], "the parse is true, the gate is not"
    assert len(result.records) == 6


def test_a_type_with_no_properties_declares_nothing_either():
    """`{"@type": "Product"}` names a kind of thing and says nothing about one."""
    html = (
        '<html><head><script type="application/ld+json">{"@type":"Product"}</script>'
        f"</head>{SIX_ROWS}</html>"
    )

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld", "induced"]
    assert len(result.records) == 6


def test_an_itemscope_with_no_properties_declares_nothing_either():
    """The same page, said in microdata: a scope, a type, and no property."""
    html = (
        "<html><body><div itemscope itemtype='https://schema.org/Product'></div>"
        f"{SIX_ROWS}</body></html>"
    )

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["microdata", "induced"]
    assert len(result.records) == 6


def test_site_level_opengraph_says_nothing_about_the_rows():
    """The lobste.rs shape: four og tags describing the site, and twenty stories.

    The og tags parsed, and ``sources`` says so, because that is true. What they
    describe is the site, not the rows, so they do not stand in for a page that
    declared its list -- and the record they made is kept beside the induced
    ones rather than replaced by them.
    """
    html = (FIXTURES / "site_opengraph_and_a_story_list.html").read_text()

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["opengraph", "induced"]
    assert len(result.records) == 21
    assert result.records[0].fields["site_name"].value == "Example community"
    induced = {
        field.value
        for record in result.records[1:]
        for field in record.fields.values()
    }
    assert "The shell is a programming language" in induced
