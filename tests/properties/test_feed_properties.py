"""A feed, however damaged, is read or is not one -- never a traceback."""

from __future__ import annotations

from hypothesis import given, strategies as st

from sluicer.feeds import Feed, read_feed

_SEEDS = [
    b'<?xml version="1.0"?><rss><channel><title>T</title><item><title>A</title>'
    b"<link>/a</link><pubDate>Tue, 03 Jun 2025 10:00:00 GMT</pubDate></item>"
    b"</channel></rss>",
    b'<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://e.example/">'
    b'<entry><link href="a"/><content type="xhtml"><div>x</div></content>'
    b"<updated>2025-06-03T10:00:00Z</updated></entry></feed>",
    b'{"version": "https://jsonfeed.org/version/1.1", "items": [{"url": "/a", '
    b'"authors": [{"name": "A"}], "attachments": [{"url": "/b"}]}]}',
]


@st.composite
def damaged(draw) -> bytes:
    data = draw(st.sampled_from(_SEEDS))
    for _ in range(draw(st.integers(0, 4))):
        where = draw(st.integers(0, len(data)))
        what = draw(st.sampled_from(["flip", "cut", "splice"]))
        if what == "flip" and where < len(data):
            data = data[:where] + bytes([data[where] ^ 0x20]) + data[where + 1 :]
        elif what == "cut":
            data = data[:where]
        else:
            data = data[:where] + draw(st.binary(max_size=12)) + data[where:]
    return data


@given(damaged(), st.sampled_from([None, "https://e.example/f", "https://[x]/f"]))
def test_a_damaged_feed_is_read_or_is_none(data, url):
    found = read_feed(data, url=url)
    assert found is None or isinstance(found, Feed)
    text = data.decode("utf-8", errors="replace")
    again = read_feed(text, url=url)
    assert again is None or isinstance(again, Feed)


@given(st.binary(max_size=200))
def test_bytes_that_are_no_feed_are_none_or_a_feed(data):
    found = read_feed(data)
    assert found is None or isinstance(found, Feed)
