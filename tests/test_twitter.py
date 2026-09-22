from sluicer.declared.twitter import read_twitter
from sluicer.document import load


def test_reads_the_twitter_tags_and_nothing_else():
    doc = load(
        "<html><head>"
        '<meta name="twitter:card" content="summary">'
        '<meta name="twitter:title" content="Brake pad set">'
        '<meta property="og:title" content="Brake pad set, front axle">'
        "</head><body></body></html>"
    )

    assert read_twitter(doc) == {
        "card": "summary",
        "title": "Brake pad set",
    }


def test_a_card_written_with_property_is_still_read():
    """The specification says ``name``; a great deal of the web writes
    ``property``, and every other consumer reads it either way."""
    doc = load(
        '<html><head><meta property="twitter:card" content="summary">'
        "</head><body></body></html>"
    )

    assert read_twitter(doc) == {"card": "summary"}


def test_a_page_declaring_nothing_returns_an_empty_mapping():
    assert read_twitter(load("<html><body>hi</body></html>")) == {}


def test_a_page_carrying_only_og_tags_returns_an_empty_mapping():
    doc = load(
        '<html><head><meta property="og:title" content="Brake pad set">'
        "</head><body></body></html>"
    )

    assert read_twitter(doc) == {}


def test_an_empty_content_is_not_a_value():
    doc = load(
        "<html><head>"
        '<meta name="twitter:title" content="  ">'
        '<meta name="twitter:description" content="">'
        "</head><body></body></html>"
    )

    assert read_twitter(doc) == {}


def test_the_first_declaration_of_a_key_wins():
    doc = load(
        "<html><head>"
        '<meta name="twitter:title" content="First">'
        '<meta name="twitter:title" content="Second">'
        "</head><body></body></html>"
    )

    assert read_twitter(doc) == {"title": "First"}
