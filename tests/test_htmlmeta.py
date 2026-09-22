from sluicer.declared.htmlmeta import read_htmlmeta
from sluicer.document import load


def test_the_standard_metadata_names_are_read():
    doc = load(
        "<html><head>"
        '<meta name="author" content="Nancy Peyer">'
        '<meta name="description" content="A sentence about the page.">'
        '<meta name="keywords" content="one, two">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {
        "author": "Nancy Peyer",
        "description": "A sentence about the page.",
        "keywords": "one, two",
    }


def test_a_site_s_own_meta_name_is_not_metadata_about_the_page():
    """A catch-all would fill a record with plumbing and empty the provenance."""
    doc = load('<html><head><meta name="csrf-token" content="abc123"></head></html>')

    assert read_htmlmeta(doc) == {}


def test_the_name_is_matched_without_regard_to_case():
    doc = load('<html><head><meta name="Author" content="Nancy Peyer"></head></html>')

    assert read_htmlmeta(doc) == {"author": "Nancy Peyer"}


def test_a_browser_directive_is_not_a_statement_about_the_page():
    """robots and viewport instruct a client; they say nothing about a subject."""
    doc = load(
        "<html><head>"
        '<meta name="robots" content="index, follow">'
        '<meta name="viewport" content="width=device-width">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {}


def test_an_empty_content_is_not_a_value():
    doc = load(
        "<html><head>"
        '<meta name="author" content="  ">'
        '<meta name="description" content="">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {}


def test_the_first_declaration_of_a_name_wins_across_spellings():
    """Two spellings of one name are one field, so first-wins has to mean it."""
    doc = load(
        "<html><head>"
        '<meta name="Author" content="First">'
        '<meta name="author" content="Second">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {"author": "First"}


def test_a_property_attribute_is_a_vocabulary_this_reader_does_not_know():
    """The HTML standard defines its metadata names for ``name``, not ``property``."""
    doc = load('<html><head><meta property="author" content="RDFa"></head></html>')

    assert read_htmlmeta(doc) == {}


def test_the_rest_of_the_closed_list_is_read():
    doc = load(
        "<html><head>"
        '<meta name="generator" content="WordPress 6.5">'
        '<meta name="application-name" content="Sluicer">'
        '<meta name="theme-color" content="#101010">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {
        "generator": "WordPress 6.5",
        "application-name": "Sluicer",
        "theme-color": "#101010",
    }
