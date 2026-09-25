"""Sitemaps read as an attack would be written, and a site mapped politely."""

import gzip
import time

import pytest

from fake_site import FakeWeb, page
from sluicer.crawl.sitemaps import (
    SitemapUnreadable,
    map_site,
    parse_sitemap,
)
from sluicer.fetch import AddressRefused, FetchFailed

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*locs, lastmod=None):
    entries = "".join(
        f"<url><loc>{loc}</loc>"
        + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
        + "</url>"
        for loc in locs
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset {NS}>{entries}</urlset>'


def index(*locs):
    entries = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return f"<sitemapindex {NS}>{entries}</sitemapindex>"


# -- reading one file ----------------------------------------------------------


def test_a_urlset_gives_its_pages_and_their_lastmod_as_written():
    body = urlset("https://example.com/a", "https://example.com/b", lastmod="2026-09")

    read = parse_sitemap(body.encode())

    assert read.kind == "urlset"
    assert read.entries == (
        ("https://example.com/a", "2026-09"),
        ("https://example.com/b", "2026-09"),
    )
    assert read.broken is None


def test_a_sitemap_without_a_namespace_or_with_extensions_reads_the_same():
    body = (
        '<urlset xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        "<url><loc> https://example.com/a </loc>"
        "<image:image><image:loc>https://example.com/i.jpg</image:loc></image:image>"
        "</url><url><lastmod>2026</lastmod></url></urlset>"
    )

    assert parse_sitemap(body.encode()).entries == (("https://example.com/a", None),)


def test_an_index_gives_its_sitemaps():
    read = parse_sitemap(index("https://example.com/s1.xml").encode())

    assert read.kind == "sitemapindex"
    assert read.entries == (("https://example.com/s1.xml", None),)


def test_gzip_is_told_by_its_bytes_and_inflated():
    body = gzip.compress(urlset("https://example.com/a").encode())

    assert parse_sitemap(body).entries == (("https://example.com/a", None),)


def test_a_gzip_that_inflates_past_the_bound_is_not_read():
    bomb = gzip.compress(b"<urlset>" + b" " * 5_000_000 + b"</urlset>")

    with pytest.raises(SitemapUnreadable, match="inflates to more than 1000 bytes"):
        parse_sitemap(bomb, max_bytes=1000)
    assert len(bomb) < 10_000


def test_a_broken_or_cut_gzip_says_so():
    whole = gzip.compress(urlset("https://example.com/a").encode())

    with pytest.raises(SitemapUnreadable, match="ends before"):
        parse_sitemap(whole[: len(whole) // 2])
    with pytest.raises(SitemapUnreadable, match="gzip is broken"):
        parse_sitemap(whole[:10] + b"\x00" * 40)


def test_an_external_entity_is_never_read(tmp_path):
    """XXE: the entity names a local file. Resolved, its words would be a URL."""
    secret = tmp_path / "secret.txt"
    secret.write_text("the-secret-words", encoding="utf-8")
    body = (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE urlset [<!ENTITY x SYSTEM "file://{secret}">]>'
        f"<urlset {NS}><url><loc>https://example.com/&x;</loc></url></urlset>"
    )

    with pytest.raises(SitemapUnreadable, match="declares a document type") as refused:
        parse_sitemap(body.encode())

    assert "the-secret-words" not in str(refused.value)


def test_billion_laughs_is_refused_before_anything_expands():
    lol = '<!ENTITY lol0 "lol">' + "".join(
        f'<!ENTITY lol{n} "{f"&lol{n - 1};" * 10}">' for n in range(1, 10)
    )
    body = (
        f"<?xml version='1.0'?><!DOCTYPE urlset [{lol}]>"
        f"<urlset {NS}><url><loc>https://example.com/&lol9;</loc></url></urlset>"
    )
    started = time.perf_counter()

    with pytest.raises(SitemapUnreadable, match="declares a document type"):
        parse_sitemap(body.encode())

    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    "doctype",
    [
        '<!DOCTYPE urlset SYSTEM "http://127.0.0.1:9/evil.dtd">',
        '<!DOCTYPE urlset PUBLIC "-//x//y" "http://127.0.0.1:9/evil.dtd">',
        '<!DOCTYPE urlset [<!ENTITY % p SYSTEM "file:///etc/passwd"> %p;]>',
        "<!DOCTYPE urlset>",
    ],
)
def test_any_document_type_is_refused_whatever_it_points_at(doctype):
    body = f"<?xml version='1.0'?>{doctype}<urlset {NS}></urlset>"

    with pytest.raises(SitemapUnreadable, match="declares a document type"):
        parse_sitemap(body.encode())


def test_a_page_where_a_sitemap_was_expected_is_not_a_sitemap():
    """A soft 404: /sitemap.xml answering 200 with the site's HTML."""
    with pytest.raises(SitemapUnreadable, match="its root is <html>"):
        parse_sitemap(b"<!DOCTYPE html><html><body>Not here</body></html>")
    with pytest.raises(SitemapUnreadable, match="not XML"):
        parse_sitemap(b"<?xml version='1.0'?><<not a tag")
    with pytest.raises(SitemapUnreadable, match="neither XML nor a list"):
        parse_sitemap(b"Not found")
    with pytest.raises(SitemapUnreadable, match="neither XML nor a list"):
        parse_sitemap(b"")


def test_a_text_sitemap_is_one_address_a_line():
    body = b"https://example.com/a\n\n  https://example.com/b  \nnot an address\n"

    read = parse_sitemap(body)

    assert read.kind == "text"
    assert read.entries == (
        ("https://example.com/a", None),
        ("https://example.com/b", None),
    )


def test_a_sitemap_that_breaks_keeps_what_came_before_and_says_why():
    """An unescaped & in a URL is the commonest sitemap bug there is."""
    body = urlset("https://example.com/a", "https://example.com/?a=1&b=2")

    read = parse_sitemap(body.encode())

    assert read.entries == (("https://example.com/a", None),)
    assert read.broken is not None and "stops being XML" in read.broken


def test_a_sitemap_is_read_no_further_than_the_entries_asked_for_and_says_so():
    body = urlset(*(f"https://example.com/{n}" for n in range(10)))
    text = "".join(f"https://example.com/{n}\n" for n in range(10)).encode()

    for read in (
        parse_sitemap(body.encode(), max_entries=3),
        parse_sitemap(text, max_entries=3),
    ):
        assert len(read.entries) == 3
        assert read.broken == "it lists more than 3 entries, and the rest were not read"
    assert parse_sitemap(body.encode(), max_entries=10).broken is None


def test_a_sitemap_past_the_protocols_cap_marks_the_map_cut_short(monkeypatch):
    monkeypatch.setattr("sluicer.crawl.sitemaps.MAX_SITEMAP_URLS", 2)
    fake = site(
        {
            "https://example.com/sitemap.xml": urlset(
                "https://other.example/1",
                "https://example.com/a",
                "https://example.com/b",
            )
        }
    )

    result = mapped(fake)

    assert result.truncated is True
    assert [u.url for u in result.urls] == ["https://example.com/a"]


# -- mapping a site --------------------------------------------------------------

START = "https://example.com/"


def site(pages):
    return FakeWeb(pages)


def mapped(fake, url=START, **options):
    options.setdefault("min_delay", 1.0)
    return map_site(
        url, web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep, **options
    )


def test_the_sitemaps_robots_names_are_read_in_its_order_and_kept_on_site():
    fake = site(
        {
            "https://example.com/robots.txt": (
                "Sitemap: https://example.com/b.xml\n"
                "Sitemap: https://example.com/a.xml.gz\n"
            ),
            "https://example.com/b.xml": urlset(
                "https://example.com/b1",
                "https://other.example/x",
                "https://www.example.com/b2",
                lastmod="2026-09-01",
            ),
            "https://example.com/a.xml.gz": (
                200,
                gzip.compress(
                    urlset("https://example.com/a1", "https://example.com/b1").encode()
                ),
                {"Content-Type": "application/x-gzip"},
            ),
        }
    )

    result = mapped(fake)

    assert result.source == "sitemaps"
    assert [u.url for u in result.urls] == [
        "https://example.com/b1",
        "https://www.example.com/b2",
        "https://example.com/a1",
    ]
    assert result.urls[0].lastmod == "2026-09-01"
    assert result.urls[2].sitemap == "https://example.com/a.xml.gz"
    assert [(r.url, r.kind, r.entries) for r in result.sitemaps] == [
        ("https://example.com/b.xml", "urlset", 3),
        ("https://example.com/a.xml.gz", "urlset", 2),
    ]
    assert result.truncated is False


def test_an_index_is_followed_on_its_own_site_only():
    fake = site(
        {
            "https://example.com/robots.txt": "Sitemap: https://example.com/index.xml",
            "https://example.com/index.xml": index(
                "https://example.com/s1.xml", "https://evil.example/s2.xml"
            ),
            "https://example.com/s1.xml": urlset("https://example.com/p"),
        }
    )

    result = mapped(fake)

    assert [u.url for u in result.urls] == ["https://example.com/p"]
    assert "https://evil.example/s2.xml" not in fake.asked()
    refused = [r for r in result.sitemaps if r.url == "https://evil.example/s2.xml"]
    assert refused[0].error is not None and "its own site" in refused[0].error


def test_without_sitemap_lines_the_usual_places_are_tried_in_order():
    fake = site(
        {
            "https://example.com/robots.txt": "User-agent: *\nDisallow:\n",
            "https://example.com/sitemap_index.xml": urlset("https://example.com/p"),
        }
    )

    result = mapped(fake)

    assert [u.url for u in result.urls] == ["https://example.com/p"]
    assert [(r.url, r.error) for r in result.sitemaps] == [
        ("https://example.com/sitemap.xml", "it answered 404"),
        ("https://example.com/sitemap_index.xml", None),
    ]


def test_the_second_place_is_not_asked_when_the_first_answered():
    fake = site({"https://example.com/sitemap.xml": urlset("https://example.com/p")})

    mapped(fake)

    assert "https://example.com/sitemap_index.xml" not in fake.asked()


def test_a_sitemap_robots_disallows_is_not_asked():
    fake = site(
        {
            "https://example.com/robots.txt": (
                "User-agent: *\nDisallow: /private/\n"
                "Sitemap: https://example.com/private/s.xml\n"
            ),
            "https://example.com/": page("Home", "/a"),
        }
    )

    result = mapped(fake)

    assert "https://example.com/private/s.xml" not in fake.asked()
    assert result.sitemaps[0].error == "its robots.txt disallows it"
    assert result.source == "links"


def test_with_no_sitemap_the_start_pages_links_on_the_site_stand_in():
    fake = site(
        {
            "https://example.com/": page(
                "Home", "/b", "/a", "https://other.example/x", "/b#again"
            )
        }
    )

    result = mapped(fake)

    assert result.source == "links"
    assert [u.url for u in result.urls] == [
        "https://example.com/b",
        "https://example.com/a",
    ]
    assert all(u.sitemap is None and u.lastmod is None for u in result.urls)


def test_every_request_waits_the_sites_delay_after_the_last_one_ended():
    fake = site(
        {
            "https://example.com/robots.txt": (
                "User-agent: *\nCrawl-delay: 3\n"
                "Sitemap: https://example.com/s1.xml\nSitemap: https://example.com/s2.xml\n"
            ),
            "https://example.com/s1.xml": urlset("https://example.com/a"),
            "https://example.com/s2.xml": urlset("https://example.com/b"),
        }
    )

    mapped(fake)

    assert fake.asked() == [
        "https://example.com/robots.txt",
        "https://example.com/s1.xml",
        "https://example.com/s2.xml",
    ]
    assert fake.gaps("example.com") == [3.0, 3.0]


def test_a_site_asking_for_a_longer_delay_than_the_map_waits_is_left_unread():
    fake = site(
        {
            "https://example.com/robots.txt": (
                "User-agent: *\nCrawl-delay: 600\nSitemap: https://example.com/s.xml\n"
            ),
            "https://example.com/": page("Home"),
        }
    )

    result = mapped(fake, max_delay=60)

    assert "longer than the 60 s" in result.sitemaps[0].error
    assert "https://example.com/s.xml" not in fake.asked()


def test_the_limit_and_the_number_of_sitemaps_are_bounds_and_say_so():
    fake = site(
        {
            "https://example.com/robots.txt": "".join(
                f"Sitemap: https://example.com/s{n}.xml\n" for n in range(5)
            ),
            **{
                f"https://example.com/s{n}.xml": urlset(
                    f"https://example.com/{n}a", f"https://example.com/{n}b"
                )
                for n in range(5)
            },
        }
    )

    few = mapped(fake, limit=3)
    two_files = mapped(site(fake.pages), max_sitemaps=2)

    assert [u.url for u in few.urls] == [
        "https://example.com/0a",
        "https://example.com/0b",
        "https://example.com/1a",
    ]
    assert few.truncated is True
    assert len(two_files.sitemaps) == 2 and len(two_files.urls) == 4
    assert two_files.truncated is True


def test_the_time_budget_stops_asking_and_says_so():
    fake = site(
        {
            "https://example.com/robots.txt": "".join(
                f"Sitemap: https://example.com/s{n}.xml\n" for n in range(5)
            ),
            **{
                f"https://example.com/s{n}.xml": urlset(f"https://example.com/{n}")
                for n in range(5)
            },
        }
    )

    result = mapped(fake, time_budget=2.5)

    assert result.truncated is True
    assert 1 <= len(result.sitemaps) < 5


def test_a_sitemap_that_failed_is_reported_and_the_map_goes_on():
    fake = site(
        {
            "https://example.com/robots.txt": (
                "Sitemap: https://example.com/down.xml\n"
                "Sitemap: https://example.com/html.xml\n"
                "Sitemap: https://example.com/ok.xml\n"
            ),
            "https://example.com/down.xml": ConnectionError("connection reset"),
            "https://example.com/html.xml": "<!DOCTYPE html><html><body></body></html>",
            "https://example.com/ok.xml": urlset("https://example.com/p"),
        }
    )

    result = mapped(fake)

    assert [r.error for r in result.sitemaps] == [
        "ConnectionError: connection reset",
        "it is not a sitemap: its root is <html>",
        None,
    ]
    assert [u.url for u in result.urls] == ["https://example.com/p"]


def test_a_robots_file_nobody_could_read_stops_the_map():
    fake = site({"https://example.com/robots.txt": (503, "busy", {})})

    with pytest.raises(FetchFailed, match="503"):
        mapped(fake)


def test_an_address_that_is_not_one_is_refused():
    with pytest.raises(FetchFailed, match="not an http"):
        mapped(site({}), url="ftp://example.com/")


def test_a_private_address_is_refused_before_any_request():
    fake = site({})

    with pytest.raises(AddressRefused):
        mapped(fake, url="http://127.0.0.1:8080/", allow_private=False)

    assert fake.requests == []


def test_a_sitemap_on_a_host_whose_robots_file_is_down_is_reported_unread():
    fake = site(
        {
            "https://example.com/robots.txt": "Sitemap: https://cdn.example/s.xml\n",
            "https://cdn.example/robots.txt": (503, "busy", {}),
            "https://example.com/": page("Home"),
        }
    )

    result = mapped(fake)

    assert "503" in result.sitemaps[0].error
    assert "https://cdn.example/s.xml" not in fake.asked()


def test_a_missing_extra_is_raised_not_reported_as_a_sitemap_that_failed():
    from sluicer.fetch.rungs import FetchExtraMissing

    fake = site({})

    def get(url):
        raise FetchExtraMissing("Loading a page needs playwright", extra="browser")

    web = fake.web()
    web = type(web)(rungs=web.rungs, read=web.read, get=get)
    with pytest.raises(FetchExtraMissing):
        map_site(START, web=web, clock=fake.clock, sleep=fake.clock.sleep)


def test_the_real_web_is_built_from_the_ladder_and_plain_http(monkeypatch):
    """What ``default_web`` wires together, asked over the fake wire: the
    page rung obeys the redirect rule, robots.txt does not."""
    from fake_wire import fake_http
    from sluicer.crawl.web import default_web
    from sluicer.fetch import RedirectRefused

    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    seen = fake_http(
        monkeypatch,
        [
            (301, b"", {"location": "https://cdn.example/robots.txt"}),
            (200, b"User-agent: *\nDisallow: /x\n", {}),
            (301, b"", {"location": "https://elsewhere.example/"}),
            (200, gzip.compress(b"<urlset/>"), {}),
        ],
    )

    web = default_web(redirects=lambda current, target: "it leaves")

    assert [name for name, _ in web.rungs] == ["http", "browser"]
    assert web.read("https://example.com/robots.txt") == "User-agent: *\nDisallow: /x\n"
    with pytest.raises(RedirectRefused):
        dict(web.rungs)["http"]("https://example.com/p")
    assert web.get("https://example.com/s.xml.gz").body.startswith(b"\x1f\x8b")
    assert [t.host for t in seen.targets[:2]] == ["example.com", "cdn.example"]
    assert seen.urls[1] == "/robots.txt"


def test_what_a_sitemap_cannot_mean_is_passed_over():
    """A relative loc, a stray element, the same sitemap named twice."""
    fake = site(
        {
            "https://example.com/robots.txt": (
                "Sitemap: https://example.com/s.xml\nSitemap: https://example.com/s.xml\n"
            ),
            "https://example.com/s.xml": (
                f"<urlset {NS}><note>hello</note><url><loc>/relative</loc></url>"
                "<url><loc>https://example.com/p</loc></url></urlset>"
            ),
        }
    )

    result = mapped(fake, allow_private=False, resolve=lambda host: ["93.184.215.14"])

    assert [u.url for u in result.urls] == ["https://example.com/p"]
    assert fake.asked().count("https://example.com/s.xml") == 1


def test_a_sitemap_on_a_private_address_is_not_asked_when_refused():
    fake = site(
        {
            "https://example.com/robots.txt": "Sitemap: http://10.0.0.7/s.xml\n",
            "https://example.com/": page("Home"),
        }
    )

    result = mapped(fake, allow_private=False, resolve=lambda host: ["93.184.215.14"])

    assert result.sitemaps[0].error.startswith("it is not fetched")
    assert not any("10.0.0.7" in url for url in fake.asked())


def test_whitespace_before_the_xml_declaration_is_read_past():
    """Measured on web-scraping.dev: its sitemap opens with a newline, which
    libxml2 refuses and every search engine reads past."""
    body = "\n  " + urlset("https://example.com/a")

    assert parse_sitemap(body.encode()).entries == (("https://example.com/a", None),)
    assert parse_sitemap(
        b"\xef\xbb\xbf\n" + urlset("https://x.example/").encode()
    ).kind == ("urlset")


def test_a_sitemap_in_utf_16_is_read_by_its_byte_order_mark():
    body = f"<urlset {NS}><url><loc>https://example.com/é</loc></url></urlset>"

    read = parse_sitemap(body.encode("utf-16"))

    assert read.entries == (("https://example.com/é", None),)


@pytest.mark.parametrize(
    "declared",
    [
        # Parameter entities expand inside the document type itself.
        '<!DOCTYPE urlset [<!ENTITY % a "aaaaaaaaaa"><!ENTITY % b "%a;%a;%a;">]>',
        '<!doctype urlset system "http://127.0.0.1:9/evil.dtd">',
        '<!DOCTYPE urlset PUBLIC "-//x//y" "evil.dtd">',
        "<!DOCTYPE urlset><!DOCTYPE urlset>",
        '<!ENTITY x "a stray declaration">',
    ],
)
def test_a_document_type_is_refused_before_the_parser_reads_it(declared, monkeypatch):
    import lxml.etree

    def must_not_parse(*args, **kwargs):
        raise AssertionError("the parser was handed a document type")

    monkeypatch.setattr(lxml.etree, "iterparse", must_not_parse)
    body = f"<?xml version='1.0'?>{declared}<urlset {NS}></urlset>"

    # libxml2 reads UTF-16 without its byte order mark, and UTF-32, too.
    for codec in ("utf-8", "utf-16", "utf-16-le", "utf-32", "utf-32-le"):
        with pytest.raises(SitemapUnreadable, match="declares a document type"):
            parse_sitemap(body.encode(codec))


def test_a_page_built_to_make_the_refusal_slow_is_refused_in_linear_time():
    """Two megabytes of unclosed declarations: a search that restarted at each
    would read them all again for every one of them."""
    body = b"<?xml version='1.0'?>" + b"<!DOCTYPE urlset " * 120_000
    started = time.perf_counter()

    with pytest.raises(SitemapUnreadable, match="declares a document type"):
        parse_sitemap(body)

    assert time.perf_counter() - started < 1.0


def test_the_real_web_sends_the_callers_headers_and_cookies_on_every_request(
    monkeypatch,
):
    """Measured before, against a local server: a crawl given headers= and
    cookies= sent neither, not with its pages, its robots.txt or its sitemaps;
    ``default_web`` took them and built its rungs without them."""
    from fake_wire import fake_http
    from sluicer.crawl.web import default_web

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    seen = fake_http(monkeypatch, [(200, b"<p>" + b"page " * 60, {})] * 3)

    web = default_web(headers={"X-Token": "abc"}, cookies={"s": "1"})
    dict(web.rungs)["http"]("https://example.com/p")
    web.read("https://example.com/robots.txt")
    web.get("https://example.com/sitemap.xml")

    assert [r.headers.get("x-token") for r in seen.requests] == ["abc"] * 3
    assert [r.headers.get("cookie") for r in seen.requests] == ["s=1"] * 3
