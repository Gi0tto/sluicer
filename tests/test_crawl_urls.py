"""One spelling per address, which addresses make a site, and a page's links."""

import pytest

from sluicer.crawl.urls import (
    canonical_of,
    links_on,
    names_a_file,
    normalise,
    site_of,
)
from sluicer.document import load


@pytest.mark.parametrize(
    ("written", "compared"),
    [
        ("HTTP://Example.COM/a", "http://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("http://example.com/a#section", "http://example.com/a"),
        ("http://example.com", "http://example.com/"),
        ("http://example.com./a", "http://example.com/a"),
        ("http://example.com/a/./b/../c", "http://example.com/a/c"),
        ("http://example.com/a/..", "http://example.com/"),
        ("http://example.com/../../a", "http://example.com/a"),
        ("http://example.com/caf%c3%a9", "http://example.com/caf%C3%A9"),
        ("http://example.com/café", "http://example.com/caf%C3%A9"),
        ("http://example.com/a b", "http://example.com/a%20b"),
        ("http://example.com/p?b=2&a=1", "http://example.com/p?b=2&a=1"),
        ("http://example.com/p?", "http://example.com/p"),
        ("http://bücher.example/", "http://xn--bcher-kva.example/"),
        ("http://[::1]:8080/a", "http://[::1]:8080/a"),
        ("  http://example.com/a  ", "http://example.com/a"),
    ],
)
def test_an_address_is_written_the_one_way_a_crawl_compares(written, compared):
    assert normalise(written) == compared


def test_a_trailing_slash_makes_another_address():
    """A server may answer /a and /a/ differently, so they are two addresses."""
    assert normalise("http://example.com/a") != normalise("http://example.com/a/")


@pytest.mark.parametrize(
    "refused",
    [
        "mailto:someone@example.com",
        "javascript:void(0)",
        "ftp://example.com/file",
        "https://user:secret@example.com/",
        "http://example.com:99999/",
        "http:///no-host",
        "not an address",
        "http://[::1/",
    ],
)
def test_an_address_a_crawl_cannot_take_is_none(refused):
    assert normalise(refused) is None


def test_a_site_is_its_host_with_or_without_www_over_either_scheme():
    assert site_of("https://www.example.com/a") == "example.com"
    assert site_of("http://example.com/b") == "example.com"
    assert site_of("http://shop.example.com/") == "shop.example.com"
    assert site_of("http://example.com:8080/") == "example.com:8080"
    assert site_of("mailto:x@example.com") == ""


@pytest.mark.parametrize(
    ("url", "is_a_file"),
    [
        ("https://example.com/report.PDF", True),
        ("https://example.com/i/photo.jpg?w=200", True),
        ("https://example.com/feed.xml", True),
        ("https://example.com/catalogue/page-2.html", False),
        ("https://example.com/product/brake-pads", False),
        ("https://example.com/v1.2/", False),
    ],
)
def test_an_address_naming_a_file_is_told_by_its_extension(url, is_a_file):
    assert names_a_file(url) is is_a_file


def _doc(body, url="https://example.com/dir/page", head=""):
    return load(f"<html><head>{head}</head><body>{body}</body></html>", url=url)


def test_links_are_resolved_normalised_and_kept_once_in_document_order():
    doc = _doc(
        '<a href="b">b</a><a href="/a#top">a</a><a href="B">B</a>'
        '<a href="https://example.com/a">a again</a>'
        '<map><area href="/area"></map><a href="mailto:x@example.com">mail</a>'
        '<a href=" /spaced\n ">spaced</a>'
    )

    assert links_on(doc) == [
        "https://example.com/dir/b",
        "https://example.com/a",
        "https://example.com/dir/B",
        "https://example.com/area",
        "https://example.com/spaced",
    ]


def test_links_resolve_against_the_pages_own_base():
    doc = _doc('<a href="x">x</a>', head='<base href="https://cdn.example/root/">')

    assert links_on(doc) == ["https://cdn.example/root/x"]


def test_a_link_marked_nofollow_is_left_out():
    doc = _doc('<a href="/a" rel="nofollow">a</a><a href="/b" rel="next">b</a>')

    assert links_on(doc) == ["https://example.com/b"]


@pytest.mark.parametrize(
    "meta",
    [
        '<meta name="robots" content="noindex, nofollow">',
        '<meta name="ROBOTS" content="none">',
        '<meta name="sluicer" content="nofollow">',
    ],
)
def test_a_page_that_says_nofollow_gives_no_links(meta):
    assert links_on(_doc('<a href="/a">a</a>', head=meta)) == []


def test_a_nofollow_for_another_crawler_is_not_ours():
    doc = _doc('<a href="/a">a</a>', head='<meta name="googlebot" content="nofollow">')

    assert links_on(doc) == ["https://example.com/a"]


def test_a_page_of_many_links_gives_the_first_few_thousand(monkeypatch):
    monkeypatch.setattr("sluicer.crawl.urls.MAX_LINKS_PER_PAGE", 3)
    doc = _doc("".join(f'<a href="/p{n}">p</a>' for n in range(10)))

    assert links_on(doc) == [f"https://example.com/p{n}" for n in range(3)]


def test_the_canonical_is_resolved_and_normalised():
    doc = _doc("", head='<link rel="canonical" href="../Canon#x">')

    assert canonical_of(doc) == "https://example.com/Canon"
    assert canonical_of(_doc("")) is None
    assert canonical_of(_doc("", head='<link rel="canonical" href="  ">')) is None


def test_a_host_no_idna_can_spell_is_not_an_address():
    assert normalise("http://" + "ä" * 64 + ".example/") is None


def test_only_the_links_and_metas_that_say_so_count():
    doc = _doc(
        '<a href="/a">a</a>',
        head=(
            '<link rel="stylesheet" href="/s.css">'
            '<link rel="canonical" href="/c">'
            '<meta name="robots" content="index, follow">'
            '<meta name="description" content="nofollow is a word">'
        ),
    )

    assert canonical_of(doc) == "https://example.com/c"
    assert links_on(doc) == ["https://example.com/a"]


def test_a_canonical_in_the_body_names_nothing_and_two_name_none():
    """As the summary reads it: Google takes rel=canonical only from the head,
    and a head naming two addresses names neither."""
    body = _doc('<link rel="canonical" href="/elsewhere">')
    assert canonical_of(body) is None
    two = _doc(
        "", head='<link rel="canonical" href="/a"><link rel="canonical" href="/b">'
    )
    assert canonical_of(two) is None
    same = _doc(
        "", head='<link rel="canonical" href="/a"><link rel="canonical" href="/a#x">'
    )
    assert canonical_of(same) == "https://example.com/a"


def test_a_canonical_in_the_link_header_counts_with_the_heads():
    header = {"Link": "</c>; rel=canonical"}
    assert canonical_of(_doc(""), header) == "https://example.com/c"
    agreeing = _doc("", head='<link rel="canonical" href="https://example.com/c">')
    assert canonical_of(agreeing, header) == "https://example.com/c"
    disagreeing = _doc("", head='<link rel="canonical" href="/d">')
    assert canonical_of(disagreeing, header) is None


def test_an_x_robots_tag_nofollow_for_everyone_or_for_sluicer_stops_the_walk():
    doc = _doc('<a href="/a">a</a>')
    assert links_on(doc, {"X-Robots-Tag": "nofollow"}) == []
    assert links_on(doc, {"x-robots-tag": "none"}) == []
    assert links_on(doc, {"x-robots-tag": "sluicer: nofollow"}) == []
    assert links_on(doc, {"x-robots-tag": "googlebot: nofollow"}) == [
        "https://example.com/a"
    ]
    assert links_on(doc, {"x-robots-tag": "noindex"}) == ["https://example.com/a"]
    assert links_on(doc, {}) == ["https://example.com/a"]
