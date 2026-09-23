from sluicer import extract
from sluicer.declared.links import read_links
from sluicer.document import load

PAGE = """<html><head>
<link rel="canonical" href="/p/brake-pads">
<link rel="alternate" hreflang="de-DE" href="https://shop.example/de/p/bremsbelaege">
<link rel="alternate" hreflang="x-default" href="https://shop.example/p/brake-pads">
<link rel="alternate" hreflang="en" href="https://shop.example/p/brake-pads">
<link rel="Alternate" type="application/rss+xml" title="  New  parts " href="/feed.xml">
<link rel="alternate" type="application/atom+xml" href="/feed.atom">
<link rel="alternate" type="application/json" href="/wp-json/wp/v2/pages/12">
<link rel="alternate" type="application/json+oembed" href="/oembed?url=x">
<link rel="amphtml" href="/amp/p/brake-pads">
<link rel="manifest" href="/site.webmanifest">
<link rel="canonical" href="/p/brake-pads">
</head><body><a rel="next" href="?page=2">Next</a><a rel="prev" href="?page=0">Back</a>
</body></html>"""


def test_every_link_relation_the_page_declares_is_read_and_resolved():
    links = read_links(load(PAGE, url="https://shop.example/c?page=1"))

    assert links["canonical"] == "https://shop.example/p/brake-pads"
    assert links["alternates"] == [
        {"hreflang": "de-DE", "href": "https://shop.example/de/p/bremsbelaege"},
        {"hreflang": "x-default", "href": "https://shop.example/p/brake-pads"},
        {"hreflang": "en", "href": "https://shop.example/p/brake-pads"},
    ]
    assert links["feeds"] == [
        {
            "format": "rss",
            "href": "https://shop.example/feed.xml",
            "title": "New parts",
        },
        {"format": "atom", "href": "https://shop.example/feed.atom", "title": ""},
    ]
    assert links["oembed"] == ["https://shop.example/oembed?url=x"]
    assert links["amphtml"] == "https://shop.example/amp/p/brake-pads"
    assert links["manifest"] == "https://shop.example/site.webmanifest"
    assert links["next"] == "https://shop.example/c?page=2"
    assert links["prev"] == "https://shop.example/c?page=0"


def test_wordpress_s_rest_api_link_is_not_a_feed():
    """Every WordPress page declares its REST API as rel=alternate application/json."""
    links = read_links(load(PAGE, url="https://shop.example/"))

    assert all("wp-json" not in feed["href"] for feed in links["feeds"])


def test_a_canonical_in_the_body_names_nothing():
    """Google accepts rel=canonical only in the head; a body is the page's content."""
    page = (
        "<html><head></head><body>"
        '<link rel="canonical" href="https://evil.example/x"></body></html>'
    )

    result = extract(page, url="https://site.example/a")

    assert "canonical" not in result.links
    assert "url" not in result.summary


def test_two_different_canonicals_are_a_conflict_with_no_answer():
    page = (
        '<html><head><link rel="canonical" href="/a">'
        '<link rel="canonical" href="/b"></head></html>'
    )

    result = extract(page, url="https://site.example/a")

    assert result.links["canonical_conflict"] == [
        "https://site.example/a",
        "https://site.example/b",
    ]
    assert "canonical" not in result.links
    assert "url" not in result.summary


def test_one_canonical_repeated_is_one_canonical():
    page = (
        '<html><head><link rel="canonical" href="/a">'
        '<link rel="canonical" href="/a"></head></html>'
    )

    assert read_links(load(page, url="https://s.example/"))["canonical"] == (
        "https://s.example/a"
    )


def test_a_page_with_no_link_relations_declares_none():
    assert read_links(load("<p>plain</p>")) == {}


def test_a_hostile_page_cannot_make_the_answer_grow_with_it():
    many = "".join(
        f'<link rel="alternate" hreflang="x{i}" href="/l{i}">' for i in range(5000)
    )

    links = read_links(load(many, url="https://s.example/"))

    assert len(links["alternates"]) == 200


def test_extract_reports_the_links():
    result = extract(PAGE, url="https://shop.example/c?page=1")

    assert result.links["canonical"] == "https://shop.example/p/brake-pads"
    assert len(result.links["alternates"]) == 3
