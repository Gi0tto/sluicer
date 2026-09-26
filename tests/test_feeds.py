"""Reading a feed's items: RSS 2.0, RSS 1.0, Atom 1.0 and JSON Feed 1.1."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from sluicer.cli import main
from sluicer.feeds import Feed, FeedItem, read_feed

URL = "https://blog.example/feed.xml"

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Brake notes</title>
    <link>https://blog.example/</link>
    <description>On brakes</description>
    <language>en-gb</language>
    <lastBuildDate>Tue, 03 Jun 2025 10:00:00 GMT</lastBuildDate>
    <item>
      <title>New  pads</title>
      <link>/posts/pads</link>
      <guid isPermaLink="false">post-1</guid>
      <pubDate>Tue, 03 Jun 2025 10:00:00 GMT</pubDate>
      <dc:creator>Ada</dc:creator>
      <author>ada@blog.example (Ada)</author>
      <category>Pads</category><category>Pads</category><category>Discs</category>
      <description>Short &amp; sweet</description>
      <content:encoded><![CDATA[<p>Long <b>body</b></p>]]></content:encoded>
      <enclosure url="/audio/1.mp3" type="audio/mpeg" length="123"/>
    </item>
    <item>
      <title>Guid only</title>
      <guid>https://blog.example/posts/2</guid>
      <pubDate>not a date</pubDate>
    </item>
  </channel>
</rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="fr" xml:base="https://atom.example/blog/">
  <title>Freins</title>
  <subtitle>Sur les freins</subtitle>
  <link rel="self" href="feed.xml"/>
  <link href="index.html"/>
  <updated>2025-06-03T10:00:00Z</updated>
  <entry xml:base="2025/">
    <title>Plaquettes</title>
    <link rel="alternate" href="pads.html"/>
    <link rel="enclosure" href="pads.mp3" type="audio/mpeg" length="42"/>
    <id>tag:atom.example,2025:1</id>
    <published>2025-06-01T08:00:00+02:00</published>
    <updated>2025-06-02T08:00:00+02:00</updated>
    <author><name>Marie</name></author>
    <category term="pads" label="Plaquettes"/><category term="discs"/>
    <summary type="text">Court</summary>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Long</p></div></content>
  </entry>
</feed>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://rdf.example/">
    <title>RDF notes</title><link>https://rdf.example/</link>
    <description>Old style</description>
  </channel>
  <item rdf:about="https://rdf.example/1">
    <title>One</title><link>https://rdf.example/1</link>
    <dc:date>2025-06-03</dc:date><dc:creator>Lin</dc:creator>
  </item>
</rdf:RDF>"""

JSON_FEED = {
    "version": "https://jsonfeed.org/version/1.1",
    "title": "JSON notes",
    "home_page_url": "https://json.example/",
    "language": "en",
    "items": [
        {
            "id": 1,
            "url": "/posts/1",
            "title": "Pads",
            "content_html": "<p>Body</p>",
            "summary": "Short",
            "date_published": "2025-06-03T10:00:00Z",
            "authors": [{"name": "Ada"}, {"name": "Ada"}, "not a person"],
            "tags": ["pads", 7, None],
            "attachments": [
                {"url": "/a.mp3", "mime_type": "audio/mpeg", "size_in_bytes": 9},
                {"mime_type": "no url"},
            ],
        },
        "not an item",
        {"title": "Old author", "author": {"name": "Bo"}, "content_text": "plain"},
    ],
}


def test_rss_is_read_item_by_item_with_links_resolved():
    feed = read_feed(RSS, url=URL)
    assert (feed.format, feed.title, feed.link, feed.language) == (
        "rss",
        "Brake notes",
        "https://blog.example/",
        "en-gb",
    )
    first, second = feed.items
    assert first == FeedItem(
        title="New pads",
        link="https://blog.example/posts/pads",
        id="post-1",
        published="Tue, 03 Jun 2025 10:00:00 GMT",
        summary="Short & sweet",
        content="<p>Long <b>body</b></p>",
        authors=("ada@blog.example (Ada)", "Ada"),
        categories=("Pads", "Discs"),
        enclosures=(
            {
                "url": "https://blog.example/audio/1.mp3",
                "type": "audio/mpeg",
                "length": "123",
            },
        ),
        normalised={"published": "2025-06-03T10:00:00+00:00"},
    )
    assert second.link == "https://blog.example/posts/2", "a permalink guid is the link"
    assert second.normalised == {}, "a date that does not read is not normalised"


def test_atom_is_read_with_xml_base_as_the_format_says():
    feed = read_feed(ATOM, url="https://atom.example/feed.xml")
    assert (feed.format, feed.title, feed.link, feed.language, feed.description) == (
        "atom",
        "Freins",
        "https://atom.example/blog/index.html",
        "fr",
        "Sur les freins",
    )
    [entry] = feed.items
    assert entry.link == "https://atom.example/blog/2025/pads.html"
    assert entry.enclosures == (
        {
            "url": "https://atom.example/blog/2025/pads.mp3",
            "type": "audio/mpeg",
            "length": "42",
        },
    )
    assert entry.authors == ("Marie",)
    assert entry.categories == ("Plaquettes", "discs")
    assert entry.content == '<p xmlns="http://www.w3.org/1999/xhtml">Long</p>'
    assert entry.normalised == {
        "published": "2025-06-01T08:00:00+02:00",
        "updated": "2025-06-02T08:00:00+02:00",
    }


def test_rss_1_is_read_as_rdf():
    feed = read_feed(RDF, url="https://rdf.example/feed")
    assert (feed.format, feed.title, feed.link) == (
        "rdf",
        "RDF notes",
        "https://rdf.example/",
    )
    [item] = feed.items
    assert (item.id, item.title, item.authors, item.normalised) == (
        "https://rdf.example/1",
        "One",
        ("Lin",),
        {"published": "2025-06-03"},
    )


def test_a_json_feed_is_read_in_both_its_versions():
    feed = read_feed(json.dumps(JSON_FEED), url="https://json.example/feed.json")
    assert (feed.format, feed.title, feed.link, feed.language) == (
        "jsonfeed",
        "JSON notes",
        "https://json.example/",
        "en",
    )
    first, old = feed.items
    assert first.id == "1" and first.link == "https://json.example/posts/1"
    assert first.authors == ("Ada",) and first.categories == ("pads", "7")
    assert first.enclosures == (
        {"url": "https://json.example/a.mp3", "type": "audio/mpeg", "length": "9"},
    )
    assert first.content == "<p>Body</p>"
    assert old.authors == ("Bo",) and old.content == "plain"


@pytest.mark.parametrize(
    "data",
    [
        b"<html><head><title>A page</title></head></html>",
        b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>',
        b'{"version": "1.0", "items": []}',
        b"[1, 2]",
        b"not xml at all",
        b"<rss><channel><title>broken",
        b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY lol "lol">]><rss/>',
        b'<?xml version="1.0"?><!DOCTYPE rss SYSTEM "http://evil.example/x.dtd"><rss/>',
        b"",
        b'{"version": "https://jsonfeed.org/version/1.1"',
        b"<!DOCTYPE rss><rss><channel><title>T</title></channel></rss>",
    ],
)
def test_what_is_not_a_feed_is_none(data):
    assert read_feed(data) is None


def test_the_billion_laughs_are_refused_before_libxml2_reads_them():
    laughs = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        + b"".join(
            b'<!ENTITY lol%d "%s">'
            % (n, b"&lol%d;" % (n - 1) * 10 if n > 1 else b"&lol;" * 10)
            for n in range(1, 10)
        )
        + b"]><rss><channel><title>&lol9;</title></channel></rss>"
    )
    assert read_feed(laughs) is None


def test_a_feed_with_no_channel_or_items_is_an_empty_feed():
    assert read_feed(b"<rss/>") == Feed("rss")
    atom = read_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"/>')
    assert atom is not None and atom.items == ()


def test_text_already_decoded_is_read_though_it_declares_an_encoding():
    text = RSS.decode("utf-8").replace('encoding="utf-8"', 'encoding="windows-1251"')
    feed = read_feed(text, url=URL)
    assert feed is not None and feed.title == "Brake notes"


def test_bytes_in_their_declared_encoding_are_read_in_it():
    data = (
        '<?xml version="1.0" encoding="windows-1251"?><rss><channel>'
        "<title>Тормоза</title></channel></rss>"
    ).encode("windows-1251")
    assert read_feed(data).title == "Тормоза"


def test_a_hostile_feed_is_read_only_so_far():
    items = "".join(f"<item><title>{n}</title></item>" for n in range(10_050))
    feed = read_feed(f"<rss><channel>{items}</channel></rss>".encode())
    assert len(feed.items) == 10_000


# -- the command line ----------------------------------------------------------


def test_sluicer_feed_reads_a_file(tmp_path):
    path = tmp_path / "feed.xml"
    path.write_bytes(RSS)
    result = CliRunner().invoke(main, ["feed", str(path), "--url", URL])
    assert result.exit_code == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer["format"] == "rss" and len(answer["items"]) == 2
    assert answer["items"][0]["link"] == "https://blog.example/posts/pads"


def test_sluicer_feed_follows_the_feed_a_page_declares(monkeypatch):
    from sluicer.fetch.result import Fetched

    pages = {
        "https://blog.example/": '<html><head><link rel="alternate" '
        'type="application/rss+xml" href="/feed.xml"></head></html>',
        URL: RSS.decode(),
    }

    def fetch_url(url, **kwargs):
        return Fetched(url=url, html=pages[url], status=200, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fetch_url)
    result = CliRunner().invoke(main, ["feed", "https://blog.example/"])
    assert result.exit_code == 0, result.stderr
    assert "Reading the feed the page declares: https://blog.example/feed.xml" in (
        result.stderr
    )
    assert json.loads(result.stdout)["title"] == "Brake notes"


def test_sluicer_feed_says_what_is_not_a_feed_and_an_empty_one(tmp_path, monkeypatch):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><head><title>No feed</title></head></html>", encoding="utf-8"
    )
    refused = CliRunner().invoke(main, ["feed", str(page)])
    assert refused.exit_code == 2 and "is not RSS, Atom or JSON Feed" in refused.stderr
    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"<rss><channel><title>Quiet</title></channel></rss>")
    assert CliRunner().invoke(main, ["feed", str(empty)]).exit_code == 1

    from sluicer.fetch.result import Fetched

    def lying(url, **kwargs):
        html = (
            '<html><head><link rel="alternate" type="application/atom+xml" '
            'href="/x"></head></html>'
        )
        return Fetched(url=url, html=html, status=200, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", lying)
    wrong = CliRunner().invoke(main, ["feed", "https://blog.example/"])
    assert wrong.exit_code == 2 and "which the page declares as a feed, is not one" in (
        wrong.stderr
    )


# -- for an agent ---------------------------------------------------------------


def test_an_agent_reads_a_feed_and_is_told_how_many_it_holds(monkeypatch):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["read_feed"](RSS.decode(), limit=1)
    assert answer["ok"] is True and answer["format"] == "rss"
    assert len(answer["items"]) == 1 and answer["items_total"] == 2
    bad = registered["read_feed"]("<html></html>")
    assert bad["ok"] is False and bad["error"]["code"] == "bad_input"
    too_many = registered["read_feed"](RSS.decode(), limit=0)
    assert too_many["error"]["code"] == "bad_input"


def test_an_agent_is_led_from_a_page_to_its_feed(monkeypatch):
    from test_mcp_server import fake_fetch, fake_mcp

    registered = fake_mcp(monkeypatch)
    calls = []
    page = (
        '<html><head><link rel="alternate" type="application/rss+xml" href="/f">'
        "</head></html>"
    )
    fetch = fake_fetch(monkeypatch, landed_on="https://blog.example/", html=page)

    from sluicer.fetch.result import Fetched

    def fetch_either(url, **kwargs):
        calls.append(url)
        if url.endswith("/f"):
            return Fetched(url=url, html=RSS.decode(), status=200, rung="http")
        return fetch(url, **kwargs)

    monkeypatch.setattr("sluicer.fetch.fetch", fetch_either)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["read_feed"]("https://blog.example/")
    assert answer["ok"] is True and answer["url"] == "https://blog.example/f"
    assert calls == ["https://blog.example/", "https://blog.example/f"]
    assert answer["fetch"]["rung"] == "http"


def test_atom_content_that_is_text_or_empty_xhtml_is_its_text():
    entry = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        '<content type="html">&lt;p&gt;Hi&lt;/p&gt;</content></entry>'
        '<entry><content type="xhtml"></content></entry>'
        "<entry><title>No content</title></entry></feed>"
    )
    first, second, third = read_feed(entry.encode()).items
    assert first.content == "<p>Hi</p>"
    assert second.content is None and third.content is None


# Every encoding libxml2 tells from a document's first bytes and reads, a
# byte order mark or none: a declared entity must be found in each before it
# is parsed.
_WIDE = {
    "UTF-16 with its mark": lambda text: text.encode("utf-16"),
    "UTF-16LE": lambda text: text.encode("utf-16-le"),
    "UTF-16BE": lambda text: text.encode("utf-16-be"),
    "UTF-32 with its mark": lambda text: text.encode("utf-32"),
    "UTF-32LE": lambda text: text.encode("utf-32-le"),
    "UTF-32BE": lambda text: text.encode("utf-32-be"),
}


@pytest.mark.parametrize("encode", _WIDE.values(), ids=list(_WIDE))
def test_an_entity_is_found_in_every_encoding_libxml2_reads(encode, monkeypatch):
    """Suspected by security review, and so: the check before the parser
    decoded UTF-16 only by its byte order mark, and libxml2 reads UTF-16
    without one, and UTF-32, from the bytes of "<?" or "<". The parser left
    the entities unexpanded, but the check is there not to rely on it."""
    import lxml.etree

    from sluicer.safexml import as_text, declares_what_expands

    def must_not_parse(*args, **kwargs):
        raise AssertionError("the parser was handed a declared entity")

    text = (
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE rss [<!ENTITY a "a">'
        '<!ENTITY b "&a;&a;">]><rss><channel><title>&b;</title></channel></rss>'
    )
    assert declares_what_expands(as_text(encode(text)))
    monkeypatch.setattr(lxml.etree, "fromstring", must_not_parse)
    assert read_feed(encode(text)) is None


# The same, but for the big-endian ones without "<" as their first byte,
# which the reader does not take for XML and so never parses.
_READ = {name: encode for name, encode in _WIDE.items() if not name.endswith("BE")}


@pytest.mark.parametrize("encode", _READ.values(), ids=list(_READ))
def test_a_feed_in_every_encoding_libxml2_reads_is_read(encode):
    """What the check decodes it only searches: the feed is parsed as sent."""
    text = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        "<rss><channel><title>Brake notes é</title></channel></rss>"
    )
    feed = read_feed(encode(text))
    assert feed is not None and feed.title == "Brake notes é"


def test_read_feed_of_an_address_alone_warns_that_it_fetches_nothing():
    """Measured on 0.9.0: read_feed("https://peps.python.org/peps.rss")
    returned None, the answer for a document that is not a feed."""
    with pytest.warns(UserWarning, match="fetches nothing") as caught:
        assert read_feed("https://example.com/feed.xml") is None

    assert "from sluicer.fetch import fetch" in str(caught[0].message)
    assert caught[0].filename == __file__
