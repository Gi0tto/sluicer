from pathlib import Path

import pytest

from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_parses_html_and_keeps_the_source():
    html = (FIXTURES / "plain.html").read_text(encoding="utf-8")

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

    monkeypatch.setattr(lxml.html, "document_fromstring", refuse)
    page = b"<html><body><p>hi</p></body></html>"

    doc = load(page)

    assert doc.tree.tag == "html"
    assert len(doc.tree) == 0
    assert doc.html == page


# Bytes are decoded the way a browser decodes them, not the way libxml2 guesses.
# libxml2 settles on Latin-1 at the first non-ASCII byte it meets, so a page
# whose <title> carries a curly quote before its <meta charset="utf-8"> -- a
# news site's article template, measured on 2026-09-22 -- came back as
# mojibake in every field. The order below is the one the HTML standard gives: a byte
# order mark, then a declaration, then the bytes themselves.


def _title(data: bytes) -> str | None:
    return load(data).tree.findtext(".//title")


def test_a_character_before_the_charset_declaration_does_not_decide_it():
    page = (
        "<!doctype html><html><head><title>The diver: \u2018I am obsessed\u2019</title>"
        '<meta charset="utf-8"></head><body></body></html>'
    )

    assert _title(page.encode("utf-8")) == "The diver: \u2018I am obsessed\u2019"


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
    """A recipe site declares its charset at byte 3,996, past the standard's 1,024.

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


@pytest.mark.parametrize(
    "label", ["hex_codec", "base64", "rot13", "zlib", "idna", "a\x00", "cp037"]
)
def test_a_label_python_knows_and_no_page_can_be_in_is_passed_over(label):
    """Found by the property that ``extract`` never raises on encoded pages.

    ``hex``, ``base64``, ``rot13`` and ``zlib`` are in Python's codec registry
    and are not text encodings, ``idna`` refuses the ``replace`` a page is
    decoded with, and a NUL makes the lookup itself refuse: each of those was
    a traceback out of ``load``. EBCDIC is text, and reads the ASCII the
    declaration was written in as something else.

    The bytes decide instead. The title is not asserted: libxml2 2.12, at
    lxml's floor, stops reading at the NUL, which is not what this is about.
    """
    from sluicer.document import sniff_encoding

    page = f'<html><head><meta charset="{label}"><title>Bremsöl</title></head>'

    assert sniff_encoding(page.encode("utf-8")) == "utf-8"
    assert load(page.encode("utf-8")).tree is not None


@pytest.mark.parametrize(
    "meta",
    [
        '<meta content="text/html; a>b" charset="windows-1251">',
        "<meta name='x>y' charset=windows-1251>",
    ],
)
def test_a_greater_than_sign_in_a_quoted_value_does_not_end_the_meta(meta):
    """Found by the property that a declaration is read whatever else its
    ``<meta>`` carries, in any attribute order.

    The tag was cut at its first ``>``, quoted or not, so a declaration
    written after such a value was never seen and the page came out as
    windows-1252 mojibake. The standard's prescan reads a quoted value whole.
    """
    page = f"<html><head>{meta}<title>Тормоза</title></head></html>"

    assert _title(page.encode("windows-1251")) == "Тормоза"


def test_a_quote_that_never_closes_holds_the_rest_of_the_head():
    """As the standard's prescan reads it: the value runs on, so a declaration
    written after it is inside it, not a declaration of its own."""
    from sluicer.document import sniff_encoding

    head = b'<meta content="never closed><meta charset="windows-1251">'

    assert sniff_encoding(head + "Тормоза".encode("windows-1251")) == "windows-1252"


def test_a_head_of_unclosed_meta_tags_is_read_in_one_pass():
    """Every ``<meta`` in the head was tried from where it began, and one that
    never closed was scanned to the end of the head each time: 64 KB of
    ``<meta `` took 1.4 seconds to sniff."""
    import time

    from sluicer.document import sniff_encoding

    head = b"<meta " * 13_000

    started = time.perf_counter()
    sniff_encoding(head)

    assert time.perf_counter() - started < 0.2


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

    doc = load(
        '<html><head><base href="/shop/"></head></html>', url="https://shop.example/a/b"
    )

    assert base_url(doc) == "https://shop.example/shop/"
    assert (
        base_url(load("<p>", url="https://shop.example/a/b"))
        == "https://shop.example/a/b"
    )
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


def test_the_charset_a_response_was_sent_with_comes_before_the_page_declaration():
    """The HTML standard's order: byte order mark, transport, then declaration."""
    from sluicer.document import sniff_encoding

    page = b'<meta charset="utf-8"><p>Caf\xe9</p>'

    assert sniff_encoding(page, "windows-1252") == "cp1252"
    assert sniff_encoding(page) == "utf-8"
    assert sniff_encoding(b"\xef\xbb\xbf" + page, "windows-1252") == "utf-8"
    assert sniff_encoding(page, "no-such-charset") == "utf-8"


def test_bytes_that_are_utf8_are_read_as_utf8_whatever_they_declare():
    """Found building the multilingual scoreboard: fundus stores its fixtures
    re-encoded as UTF-8 with the page's old declaration kept, and People's
    Daily's <meta charset=GB2312> over UTF-8 bytes read as mojibake, El
    Mundo's iso-8859-15 as "sanciÃ³n"."""
    from sluicer.document import sniff_encoding

    title = "促进航天技术更好惠及人民"
    stale = (
        '<html><head><meta http-equiv="content-type" content="text/html;'
        f'charset=GB2312"/><title>{title}</title></head></html>'
    ).encode()
    assert sniff_encoding(stale) == "utf-8"
    assert load(stale).tree.findtext(".//title") == title
    spanish = '<meta charset="iso-8859-15"><title>sanción</title>'.encode()
    assert load(spanish).tree.findtext(".//title") == "sanción"
    # A server that sends UTF-8 under a Latin-1 header is read as it sent.
    assert sniff_encoding("é".encode(), "iso-8859-1") == "utf-8"


def test_bytes_in_the_encoding_they_declare_are_read_in_it():
    from sluicer.document import sniff_encoding

    chinese = '<meta charset="gb2312"><title>人民网</title>'.encode("gb2312")
    assert sniff_encoding(chinese) == "gb18030"
    assert load(chinese).tree.findtext(".//title") == "人民网"
    french = '<meta charset="windows-1252"><title>Été</title>'.encode("cp1252")
    assert load(french).tree.findtext(".//title") == "Été"
    ascii_only = b'<meta charset="iso-8859-15"><title>Plain</title>'
    assert sniff_encoding(ascii_only) == "iso8859-15"
    # The one text this reads differently from a browser: cp1252 bytes that
    # are valid UTF-8, as "Ã©" written in cp1252 is -- text that already was
    # mojibake before it was saved.
    assert (
        load('<meta charset="windows-1252"><p>Ã©</p>'.encode("cp1252")).tree.findtext(
            ".//p"
        )
        == "é"
    )


def test_an_address_is_read_as_the_url_standard_reads_an_attribute():
    """Found by the property search: ``0``, a carriage return, ``?`` was
    answered as ``https://shop.example/c/0 `` -- the return became a space and
    the empty query took the rest away."""
    from sluicer.document import clean_address, join

    assert clean_address("0\r?") == "0?"
    assert clean_address(" \t/x\n ") == "/x"
    assert clean_address("/a b") == "/a%20b"
    assert clean_address("/a" + chr(0xA0)) == "/a%C2%A0"
    assert clean_address("/café") == "/café"
    assert join("https://shop.example/c/brakes", "0\r?") == "https://shop.example/c/0"
    assert join(None, " /x ") == "/x"


@pytest.mark.parametrize(
    ("href", "resolved"),
    [
        # Each as Node's WHATWG URL resolves it against the same base, 2026-09-24.
        (chr(0xA0) + ":", "https://shop.example/c/%C2%A0:"),
        (chr(0xA0) + "x", "https://shop.example/c/%C2%A0x"),
        (chr(0x3000) + "/p", "https://shop.example/c/%E3%80%80/p"),
        (" /p ", "https://shop.example/p"),
    ],
)
def test_only_controls_and_ascii_spaces_are_trimmed_from_an_attribute(href, resolved):
    """Found by the fuzz profile: a Link header's "<\u00a0:>" was answered as
    https://shop.example/c/: -- str.strip took the no-break space, which a
    browser keeps and encodes. The same strip read seven kinds of address."""
    from sluicer import extract
    from sluicer.document import join, trimmed

    base = "https://shop.example/c/brakes"
    assert join(base, trimmed(href)) == resolved
    header = extract(
        "<html></html>", url=base, headers={"Link": f"<{href}>; rel=canonical"}
    )
    assert header.summary["url"].value == resolved
    linked = extract(
        f'<html><head><link rel="alternate" type="application/rss+xml" href="{href}">'
        "</head></html>",
        url=base,
    )
    assert linked.links["feeds"][0]["href"] == resolved
    microdata = extract(
        '<div itemscope itemtype="https://schema.org/Product">'
        f'<a itemprop="url" href="{href}">x</a><b itemprop="name">P</b></div>',
        url=base,
    )
    assert microdata.records[0].fields["url"].value == resolved


@pytest.mark.parametrize(
    ("address", "resolved"),
    [
        ("0?", "https://shop.example/c/0"),
        ("0#", "https://shop.example/c/0"),
        ("0?#", "https://shop.example/c/0"),
        ("0?#top", "https://shop.example/c/0#top"),
        ("0#top?", "https://shop.example/c/0#top?"),
        ("0?a=1?", "https://shop.example/c/0?a=1?"),
        ("https://other.example/p?", "https://other.example/p"),
        ("?", "https://shop.example/c/brakes"),
    ],
)
def test_an_empty_query_or_fragment_resolves_alike_on_every_python(address, resolved):
    """Python 3.14's urljoin keeps them and 3.13's drops them, as CI found."""
    from sluicer.document import join

    assert join("https://shop.example/c/brakes", address) == resolved


def test_a_fragment_is_parsed_as_a_whole_document():
    """Its tree is the page's <html>, with the <body> a browser would give it.

    ``lxml.html.fromstring`` made the tree a <div> renamed from the <body>, so
    an extractor learnt ``html>div>...`` and then could not find it: its
    search starts at the tree, whose tag was not ``html``.
    """
    from sluicer.document import load

    for page in ("<p>a</p><p>b</p>", b"<!-- saved --><p>a</p>", "text <b>b</b>"):
        doc = load(page)

        assert doc.tree.tag == "html"
        assert [child.tag for child in doc.tree] == ["body"]
