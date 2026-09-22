from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


def test_reads_og_and_twitter_tags():
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
        "card": "summary",
    }


def test_a_page_declaring_nothing_returns_an_empty_mapping():
    assert read_opengraph(load("<html><body>hi</body></html>")) == {}


def test_an_empty_content_is_not_a_value():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="  ">'
        '<meta property="og:description" content="">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {}
