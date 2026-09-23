from sluicer.declared.dublincore import read_dublincore
from sluicer.document import load


def test_it_reads_the_classic_prefix():
    doc = load(
        "<html><head>"
        '<meta name="DC.title" content="Of the Standard of Taste">'
        '<meta name="DC.creator" content="David Hume">'
        "</head><body></body></html>"
    )

    assert read_dublincore(doc) == {
        "title": "Of the Standard of Taste",
        "creator": "David Hume",
    }


def test_it_reads_the_terms_prefix_too():
    doc = load('<html><head><meta name="DCTERMS.created" content="1757"></head></html>')

    assert read_dublincore(doc) == {"created": "1757"}


def test_the_prefix_is_case_insensitive_because_the_web_is():
    doc = load('<html><head><meta name="dc.title" content="Lower"></head></html>')

    assert read_dublincore(doc) == {"title": "Lower"}


def test_an_empty_value_is_not_a_value():
    doc = load('<html><head><meta name="DC.title" content="   "></head></html>')

    assert read_dublincore(doc) == {}


def test_the_first_of_a_repeated_name_wins_as_everywhere_else():
    doc = load(
        "<html><head>"
        '<meta name="DC.subject" content="aesthetics">'
        '<meta name="DC.subject" content="philosophy">'
        "</head></html>"
    )

    assert read_dublincore(doc) == {"subject": "aesthetics"}


def test_a_page_declaring_none_returns_an_empty_mapping():
    assert read_dublincore(load("<html><body>hi</body></html>")) == {}


def test_an_unrelated_meta_is_not_mistaken_for_one():
    doc = load(
        '<html><head><meta name="description" content="not dublin core"></head></html>'
    )

    assert read_dublincore(doc) == {}


def test_the_term_is_case_folded_too_so_one_field_is_one_field():
    """DC.Title is how 1997 spelt it, dc.title is how the copies did."""
    doc = load(
        "<html><head>"
        '<meta name="DC.Title" content="Original spelling">'
        '<meta name="dc.title" content="Later spelling">'
        "</head></html>"
    )

    assert read_dublincore(doc) == {"title": "Original spelling"}
