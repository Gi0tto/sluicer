from pathlib import Path

import pytest

from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_parses_html_and_keeps_the_source():
    html = (FIXTURES / "plain.html").read_text()

    doc = load(html, url="https://example.com/a")

    assert doc.url == "https://example.com/a"
    assert doc.html == html
    assert doc.tree.findtext(".//title") == "Plain page"


def test_load_survives_broken_markup():
    doc = load("<html><body><p>unclosed")

    assert doc.tree.findtext(".//p") == "unclosed"


@pytest.mark.parametrize(
    "text",
    [
        "<!doctype html>",
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!-- nothing at all -->",
        "﻿   \n  ",
        "",
        " ",
    ],
    ids=["doctype", "xml-declaration", "comment", "bom-whitespace", "empty", "space"],
)
def test_load_never_raises_on_a_document_lxml_cannot_parse(text):
    doc = load(text)

    assert doc.tree.tag == "html"
    assert len(doc.tree) == 0
    assert doc.tree.text_content() == ""
    assert doc.html == text


def test_load_accepts_bytes_and_honours_the_declared_encoding():
    from sluicer.document import load

    page = (
        '<html><head><meta charset="iso-8859-1">'
        "<title>Bremsöl</title></head><body></body></html>"
    )
    latin1 = page.encode("latin-1")

    doc = load(latin1)

    assert doc.tree.findtext(".//title") == "Bremsöl"


def test_load_still_takes_text():
    from sluicer.document import load

    assert load("<html><body><p>hi</p></body></html>").tree.findtext(".//p") == "hi"


def test_a_parser_that_refuses_bytes_is_still_never_a_traceback(monkeypatch):
    """The ValueError retry is the ``str`` path's, and only the ``str`` path's.

    ``load`` promises it never raises, and the retry that keeps that promise
    re-encodes the document as UTF-8 -- something only a ``str`` can be asked
    to do. Today lxml answers a bytes document with an ``LxmlError``, so the
    ``except ValueError`` branch is reached by strings alone and the
    difference never shows. Nothing enforces that: the day lxml refuses a
    bytes document with a ``ValueError`` of any kind, the bytes reach
    ``.encode`` and the caller gets an ``AttributeError`` out of a function
    documented never to raise -- a promise broken by an annotation that was
    never true rather than by a decision anyone made.

    The parser is faked here for the same reason the optional libraries are
    faked elsewhere in this suite: the branch cannot be reached through the
    real one, and a branch that cannot be reached is a branch nobody watches.
    """
    import lxml.html

    from sluicer.document import load

    def refuse(*args, **kwargs):
        raise ValueError(
            "Unicode strings with encoding declaration are not supported."
        )

    monkeypatch.setattr(lxml.html, "fromstring", refuse)
    page = b"<html><body><p>hi</p></body></html>"

    doc = load(page)

    assert doc.tree.tag == "html"
    assert len(doc.tree) == 0
    assert doc.html == page
