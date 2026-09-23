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
        raise ValueError("Unicode strings with encoding declaration are not supported.")

    monkeypatch.setattr(lxml.html, "fromstring", refuse)
    page = b"<html><body><p>hi</p></body></html>"

    doc = load(page)

    assert doc.tree.tag == "html"
    assert len(doc.tree) == 0
    assert doc.html == page


# Bytes are decoded the way a browser decodes them, not the way libxml2 guesses.
# libxml2 settles on Latin-1 at the first non-ASCII byte it meets, so a page
# whose <title> carries a curly quote before its <meta charset="utf-8"> -- the
# Guardian's article template, measured on 2026-09-22 -- came back as mojibake
# in every field. The order below is the one the HTML standard gives: a byte
# order mark, then a declaration, then the bytes themselves.


def _title(data: bytes) -> str | None:
    return load(data).tree.findtext(".//title")


def test_a_character_before_the_charset_declaration_does_not_decide_it():
    page = (
        "<!doctype html><html><head><title>Tom Daley: \u2018I am obsessed\u2019</title>"
        '<meta charset="utf-8"></head><body></body></html>'
    )

    assert _title(page.encode("utf-8")) == "Tom Daley: \u2018I am obsessed\u2019"


def test_a_page_that_declares_nothing_and_is_utf8_is_read_as_utf8():
    page = "<html><head><title>Bremsflüssigkeit \u2013 DOT 4</title></head></html>"

    assert _title(page.encode("utf-8")) == "Bremsflüssigkeit \u2013 DOT 4"


def test_a_page_that_declares_nothing_and_is_not_utf8_is_read_as_windows_1252():
    page = "<html><head><title>Bremsöl \u2013 1 l</title></head></html>"

    assert _title(page.encode("windows-1252")) == "Bremsöl \u2013 1 l"


def test_the_http_equiv_spelling_of_the_declaration_is_honoured():
    page = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=Shift_JIS"><title>ブレーキ</title></head></html>'
    )

    assert _title(page.encode("shift_jis")) == "ブレーキ"


def test_a_byte_order_mark_outranks_the_declaration():
    page = '<html><head><meta charset="iso-8859-1"><title>Bremsöl</title></head></html>'

    assert _title(b"\xef\xbb\xbf" + page.encode("utf-8")) == "Bremsöl"


def test_a_declaration_after_a_long_head_is_still_found():
    """Allrecipes declares its charset at byte 3,996, past the standard's 1,024.

    A browser would find it by re-parsing; reading the whole head before the
    body starts gets the same answer without a second parse.
    """
    page = (
        "<html><head><style>" + "a{color:red}" * 400 + "</style>"
        '<meta charset="windows-1251"><title>Тормоза</title></head></html>'
    )

    assert _title(page.encode("windows-1251")) == "Тормоза"


def test_latin1_is_read_as_windows_1252_the_way_every_browser_reads_it():
    """The standard maps the label ``iso-8859-1`` to windows-1252.

    The two differ only in 0x80-0x9F, which Latin-1 spends on control codes
    nobody writes and windows-1252 spends on the euro sign and curly quotes.
    """
    page = '<html><head><meta charset="iso-8859-1"><title>€ 12</title></head></html>'

    assert _title(page.encode("windows-1252")) == "€ 12"


def test_a_label_nobody_knows_falls_back_to_the_bytes():
    page = '<html><head><meta charset="no-such-thing"><title>Bremsöl</title></head>'

    assert _title(page.encode("utf-8")) == "Bremsöl"


def test_a_charset_inside_a_comment_is_not_a_declaration():
    page = (
        '<html><head><!-- <meta charset="windows-1251"> -->'
        "<title>Bremsöl</title></head></html>"
    )

    assert _title(page.encode("utf-8")) == "Bremsöl"


def test_an_xml_declaration_on_bytes_is_still_honoured():
    page = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Bremsöl</title>'
        "</head></html>"
    )

    assert _title(page.encode("latin-1")) == "Bremsöl"


def test_the_base_url_is_the_page_s_own_base_resolved_against_its_address():
    from sluicer.document import base_url

    doc = load('<html><head><base href="/shop/"></head></html>', url="https://x.eu/a/b")

    assert base_url(doc) == "https://x.eu/shop/"
    assert base_url(load("<p>", url="https://x.eu/a/b")) == "https://x.eu/a/b"
    assert base_url(load("<p>")) is None


def test_content_nested_deeper_than_libxml2_s_default_limit_is_kept():
    deep = "<div>" * 400 + '<span id="deep">here</span>' + "</div>" * 400

    assert (
        load(f"<html><body>{deep}</body></html>").tree.xpath(
            "string(//span[@id='deep'])"
        )
        == "here"
    )
    assert (
        load(f"<html><body>{deep}</body></html>".encode()).tree.xpath(
            "string(//span[@id='deep'])"
        )
        == "here"
    )
