from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


def test_reads_the_og_tags_and_nothing_else():
    """``card`` used to come back from here, and that was the defect.

    One reader returned both vocabularies and labelled every value
    ``source="opengraph"``, so a field the Twitter card declared reported a
    reader that had not won it. The assertion below is the corrected one:
    ``twitter:card`` belongs to ``read_twitter``.
    """
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="Brake pad set">'
        '<meta property="og:type" content="product">'
        '<meta name="twitter:card" content="summary">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {
        "title": "Brake pad set",
        "type": "product",
    }


def test_a_page_declaring_nothing_returns_an_empty_mapping():
    assert read_opengraph(load("<html><body>hi</body></html>")) == {}


def test_a_page_carrying_only_a_twitter_card_returns_an_empty_mapping():
    doc = load(
        '<html><head><meta name="twitter:title" content="Brake pad set">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {}


def test_an_empty_content_is_not_a_value():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="  ">'
        '<meta property="og:description" content="">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {}


def test_the_first_declaration_of_a_key_wins():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="First">'
        '<meta property="og:title" content="Second">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {"title": "First"}


def test_the_protocol_s_vertical_namespaces_are_opengraph_too():
    """article:published_time is how a third of real pages state a date."""
    doc = load(
        "<html><head>"
        '<meta property="og:type" content="article">'
        '<meta property="article:published_time" content="2018-07-10T09:00:00Z">'
        '<meta property="article:author" content="Kimber Streams">'
        '<meta property="article:section" content="Laptops">'
        "</head></html>"
    )

    got = read_opengraph(doc)

    assert got["type"] == "article"
    assert got["article:published_time"] == "2018-07-10T09:00:00Z"
    assert got["article:author"] == "Kimber Streams"
    assert got["article:section"] == "Laptops"


def test_a_vertical_that_is_not_the_protocol_s_is_left_alone():
    """Only the namespaces the OpenGraph protocol defines; not every colon."""
    doc = load('<html><head><meta property="fb:app_id" content="1234"></head></html>')

    assert read_opengraph(doc) == {}
