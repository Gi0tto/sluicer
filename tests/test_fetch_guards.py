"""The fetch layer's limits: the byte bound, the pinned connection, the guard.

Fakes throughout, so the suite opens no socket: the HTTP rung is the real
``http.client`` talking to ``tests/fake_wire.py``'s sockets, and the browser
rung drives ``tests/fake_browser.py``'s host. What a real server and a real
Chromium do with the same instructions is checked by ``tests/live/``, which CI
runs with a browser installed.
"""

import gzip
import time
import types
import zlib

import pytest

from fake_browser import FakeHost
from fake_wire import fake_http, render
from sluicer.fetch import wire
from sluicer.fetch.address import AddressRefused, public_addresses
from sluicer.fetch.browser_guard import Guard
from sluicer.fetch.ladder import fetch
from sluicer.fetch.result import Fetched, ResponseTooLarge

PUBLIC = "93.184.215.14"


def public(host):
    return [PUBLIC]


PAGE = (200, b"<html><body>ok</body></html>", {})


# -- the HTTP rung ------------------------------------------------------------


def test_the_http_rung_stops_reading_past_the_bound(monkeypatch):
    chunked = b"".join(b"3e8\r\n" + b"x" * 1000 + b"\r\n" for _ in range(5))
    reply = (200, chunked + b"0\r\n\r\n", {"Transfer-Encoding": "chunked"})
    fake_http(monkeypatch, [reply], chunk=1000)
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ResponseTooLarge):
        http_rung(max_bytes=2500)("https://example.com/p")


def test_a_chunked_body_is_read_to_its_end(monkeypatch):
    chunked = b"5\r\n<p>ok\r\n4\r\n</p>\r\n0\r\n\r\n"
    fake_http(monkeypatch, [(200, chunked, {"Transfer-Encoding": "chunked"})])
    from sluicer.fetch.http_rung import http_rung

    assert http_rung()("https://example.com/p").html == "<p>ok</p>"


def test_a_body_cut_short_of_its_length_is_not_a_page(monkeypatch):
    """The server announced 2000 bytes and closed after 11: what came is a
    fragment of the page, and handed back with 200 it was taken, and kept by
    a cache, as the page. curl called it error 18; so is it here."""
    cut = b"HTTP/1.1 200 OK\r\nContent-Length: 2000\r\n\r\n<html>half"
    seen = fake_http(monkeypatch, [cut])
    from sluicer.fetch.http_rung import ProtocolError, http_rung

    with pytest.raises(ProtocolError, match="cut short"):
        http_rung()("https://example.com/p")

    assert seen.sockets[0].closed, "a connection that ended mid-body is not kept"
    assert seen.pool._idle == []


def test_a_page_cut_short_fails_the_ladder_and_is_not_cached(monkeypatch, tmp_path):
    from sluicer.fetch.cache import Cache, fetch_cached
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.ladder import FetchFailed

    cut = b"HTTP/1.1 200 OK\r\nContent-Length: 2000\r\n\r\n<html>half"
    fake_http(monkeypatch, [cut])
    cache = Cache(tmp_path)

    with pytest.raises(FetchFailed, match="cut short"):
        fetch_cached(
            "https://example.com/p",
            cache,
            rungs=[("http", http_rung())],
            obey_robots=False,
        )

    assert list(tmp_path.iterdir()) == []


def _cut(body: bytes) -> bytes:
    return body[: len(body) // 2]


_WORDS = b"<html><body>" + b"words and more words " * 500 + b"</body></html>"


def _flushed(body: bytes, wbits: int) -> bytes:
    """``body`` compressed and sync-flushed, with no final block after it."""
    squeeze = zlib.compressobj(wbits=wbits)
    return squeeze.compress(body) + squeeze.flush(zlib.Z_SYNC_FLUSH)


def _chunked(body: bytes) -> bytes:
    pieces = [body[i : i + 700] for i in range(0, len(body), 700)]
    return b"".join(b"%x\r\n%s\r\n" % (len(p), p) for p in pieces) + b"0\r\n\r\n"


_CUT = [
    ("gzip", lambda body: _cut(gzip.compress(body))),
    ("deflate", lambda body: _cut(zlib.compress(body))),
    ("deflate", lambda body: _cut(zlib.compress(body)[2:-4])),
    ("gzip", lambda body: _cut(_flushed(body, 31))),
]


@pytest.mark.parametrize(("encoding", "encode"), _CUT)
@pytest.mark.parametrize("framing", ["length", "chunked"])
def test_a_whole_body_whose_stream_is_cut_is_not_a_page(
    monkeypatch, encoding, encode, framing
):
    """The framing was whole -- the length said, every byte came -- and the
    compressed stream inside it stops mid-way: half a page, which inflated
    to the words it held and was returned as the page. The server sent what
    it meant to, so asking again is told the same."""
    body = encode(_WORDS)
    headers = {"Content-Encoding": encoding}
    if framing == "chunked":
        body, headers["Transfer-Encoding"] = _chunked(body), "chunked"
    fake_http(monkeypatch, [(200, body, headers)])
    from sluicer.fetch.http_rung import BodyUnfinished, http_responses
    from sluicer.fetch.ladder import transient

    with pytest.raises(BodyUnfinished, match="ends before its end") as unfinished:
        http_responses()("https://example.com/p")
    assert not transient(unfinished.value)


_UNENDED = [
    ("gzip", lambda body: gzip.compress(body)[:-8]),
    ("gzip", lambda body: gzip.compress(body)[:-3]),
    ("gzip", lambda body: _flushed(body, 31)),
    ("deflate", lambda body: zlib.compress(body)[:-4]),
    ("deflate", lambda body: _flushed(body, 15)),
    ("deflate", lambda body: _flushed(body, -15)),
]


@pytest.mark.parametrize(("encoding", "encode"), _UNENDED)
@pytest.mark.parametrize("framing", ["length", "chunked"])
def test_a_whole_body_whose_stream_lacks_only_its_formal_end_is_the_page(
    monkeypatch, encoding, encode, framing
):
    """Every word came and the framing says the body is whole; only the
    stream's own end is missing -- gzip's trailer, zlib's checksum, the final
    block after a flush. curl and Chromium return the page, and so does the
    rung: the stream ends where a whole one could, checked by its checksum
    where it has one."""
    body = encode(_WORDS)
    headers = {"Content-Encoding": encoding}
    if framing == "chunked":
        body, headers["Transfer-Encoding"] = _chunked(body), "chunked"
    fake_http(monkeypatch, [(200, body, headers)], chunk=333)
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == _WORDS


@pytest.mark.parametrize(("encoding", "encode"), [*_CUT, *_UNENDED])
def test_a_stream_without_its_end_on_a_connection_that_closed_is_cut_short(
    monkeypatch, encoding, encode
):
    """Delimited by the close, a body has no framing to say it is whole: a
    stream without its end may be one the connection lost, and it is worth
    asking again."""
    head = f"HTTP/1.1 200 OK\r\nContent-Encoding: {encoding}\r\n"
    raw = (head + "Connection: close\r\n\r\n").encode() + encode(_WORDS)
    fake_http(monkeypatch, [raw])
    from sluicer.fetch.http_rung import BodyCutShort, http_responses
    from sluicer.fetch.ladder import transient

    with pytest.raises(BodyCutShort, match="cut short") as cut:
        http_responses()("https://example.com/p")
    assert transient(cut.value)


def test_a_whole_stream_on_a_connection_that_closed_is_the_page(monkeypatch):
    head = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nConnection: close\r\n\r\n"
    fake_http(monkeypatch, [head + gzip.compress(_WORDS)])
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == _WORDS


@pytest.mark.skipif(wire.ZSTD is None, reason="this Python has no zstd")
def test_a_zstd_body_cut_short_is_not_a_page(monkeypatch):
    cut = _cut(wire.ZSTD.compress(_WORDS))
    fake_http(monkeypatch, [(200, cut, {"Content-Encoding": "zstd"})])
    from sluicer.fetch.http_rung import BodyUnfinished, http_responses

    with pytest.raises(BodyUnfinished, match="ends before its end"):
        http_responses()("https://example.com/p")


def test_an_empty_body_announced_as_compressed_is_empty(monkeypatch):
    """No bytes at all is no stream to have cut short: a 204 or an empty 404
    sent with the site's usual Content-Encoding."""
    fake_http(monkeypatch, [(404, b"", {"Content-Encoding": "gzip"})])
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == b""


def test_raw_deflate_whose_first_read_is_one_byte_is_decoded():
    """Whether deflate is zlib's or raw was decided on the first read, and one
    byte is no zlib header yet: the second read then failed the check."""
    page = b"<html><body>" + b"hello world " * 200 + b"</body></html>"
    squeeze = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = squeeze.compress(page) + squeeze.flush()
    for first in (1, 2, 3):
        decoder = wire.Decoder("https://example.com/p", "deflate")
        out = decoder.feed(raw[:first], 1 << 20) + decoder.feed(raw[first:], 1 << 20)
        assert out + decoder.finish(1 << 20) == page


def test_zlib_deflate_read_a_byte_at_a_time_is_decoded(monkeypatch):
    page = b"<html><body>" + b"hello world " * 200 + b"</body></html>"
    fake_http(
        monkeypatch,
        [(200, zlib.compress(page), {"Content-Encoding": "deflate"})],
        chunk=1,
    )
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == page


@pytest.mark.skipif(wire.ZSTD is None, reason="this Python has no zstd")
@pytest.mark.parametrize("encoding", ["gzip", "zstd"])
def test_thousands_of_empty_members_are_read_without_recursion(encoding):
    """Each member after the first was read by a call inside the last one's:
    3,000 empty gzip members, 60 KB, raised RecursionError."""
    member = gzip.compress(b"") if encoding == "gzip" else wire.ZSTD.compress(b"")
    decoder = wire.Decoder("https://example.com/p", encoding)
    body = member * 3000 + (
        gzip.compress(b"<p>end</p>")
        if encoding == "gzip"
        else wire.ZSTD.compress(b"<p>end</p>")
    )

    out = decoder.feed(body, 1 << 20) + decoder.finish(1 << 20)

    assert out == b"<p>end</p>"


def test_a_length_announced_past_the_bound_is_refused_unread(monkeypatch):
    """What curl's own bound did: the length is read before the body is."""
    seen = fake_http(monkeypatch, [(200, b"x" * 5000, {})])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ResponseTooLarge):
        http_rung(max_bytes=2500)("https://example.com/p")

    assert seen.sockets[0].closed, "a connection left mid-body is not kept"
    assert seen.pool._idle == []


def test_a_small_gzip_that_inflates_past_the_bound_costs_the_bound(monkeypatch):
    bomb = gzip.compress(b"c" * 10_000_000)
    fake_http(monkeypatch, [(200, bomb, {"Content-Encoding": "gzip"})])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ResponseTooLarge):
        http_rung(max_bytes=100_000)("https://example.com/p")


@pytest.mark.parametrize(
    ("encoding", "encode"),
    [
        ("gzip", gzip.compress),
        ("deflate", zlib.compress),
        ("deflate", lambda body: zlib.compress(body)[2:-4]),  # raw, as some send it
        ("gzip, gzip", lambda body: gzip.compress(gzip.compress(body))),
        ("identity", lambda body: body),
    ],
)
def test_a_compressed_body_is_decoded(monkeypatch, encoding, encode):
    page = b"<html><body>" + b"words " * 1000 + b"</body></html>"
    fake_http(monkeypatch, [(200, encode(page), {"Content-Encoding": encoding})])
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == page


def test_two_gzip_members_are_read_as_gzip_reads_them(monkeypatch):
    body = gzip.compress(b"<p>one</p>") + gzip.compress(b"<p>two</p>")
    fake_http(monkeypatch, [(200, body, {"Content-Encoding": "gzip"})])
    from sluicer.fetch.http_rung import http_responses

    assert http_responses()("https://example.com/p").body == b"<p>one</p><p>two</p>"


@pytest.mark.skipif(wire.ZSTD is None, reason="this Python has no zstd")
def test_a_zstd_body_is_decoded_and_bounded(monkeypatch):
    page = b"<html><body>" + b"words " * 1000 + b"</body></html>"
    fake_http(
        monkeypatch,
        [
            (200, wire.ZSTD.compress(page), {"Content-Encoding": "zstd"}),
            (200, wire.ZSTD.compress(b"z" * 10_000_000), {"Content-Encoding": "zstd"}),
        ],
    )
    from sluicer.fetch.http_rung import http_responses

    get = http_responses(max_bytes=100_000)
    assert get("https://example.com/p").body == page
    with pytest.raises(ResponseTooLarge):
        get("https://example.com/bomb")


def test_an_encoding_it_cannot_decode_fails_the_rung(monkeypatch):
    """Brotli is never asked for, having no decoder in the standard library; a
    server that sends it anyway has sent bytes this rung cannot read, and a
    browser can: a failed rung, so the ladder climbs."""
    fake_http(monkeypatch, [(200, b"\x8b\x02\x80", {"Content-Encoding": "br"})])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(wire.UnreadableEncoding, match="'br'"):
        http_rung()("https://example.com/p")


def test_the_request_says_who_it_is_and_what_it_takes(monkeypatch):
    """Measured on the wire in tests/live/http_check.py as well."""
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.identity import USER_AGENT

    http_rung()("https://example.com:8443/a%20b/caf\u00e9?q=a b")

    request = seen.requests[0]
    assert request.line == "GET /a%20b/caf%C3%A9?q=a%20b HTTP/1.1"
    assert request.names == ["Host", "User-Agent", "Accept", "Accept-Encoding"]
    assert request.headers["host"] == "example.com:8443"
    assert request.headers["user-agent"] == USER_AGENT
    assert request.headers["accept"].startswith("text/html")
    encodings = request.headers["accept-encoding"].split(", ")
    assert encodings[:2] == ["gzip", "deflate"]
    assert ("zstd" in encodings) == (wire.ZSTD is not None)
    assert "br" not in encodings


def test_the_http_rung_keeps_the_responses_headers(monkeypatch):
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Link", "</a>; rel=canonical"),
        ("link", "</b>; rel=next"),
    ]
    fake_http(monkeypatch, [(200, b"<html><body>ok</body></html>", headers)])
    from sluicer.fetch.http_rung import http_rung

    fetched = http_rung()("https://example.com/p")

    assert fetched.headers["content-type"] == "text/html; charset=utf-8"
    assert fetched.headers["link"] == "</a>; rel=canonical, </b>; rel=next"


def test_a_guarded_connection_is_made_to_the_addresses_that_were_checked(
    monkeypatch,
):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(allow_private=False, resolve=public)("https://example.com:8443/p")

    target = seen.targets[0]
    assert (target.host, target.port, target.addresses) == (
        "example.com",
        8443,
        (PUBLIC,),
    )


def test_the_dial_connects_only_to_the_addresses_it_is_given(monkeypatch):
    """No name lookup when there are addresses: the second lookup is the one
    DNS rebinding answers."""
    asked = []

    def connect(address, timeout):
        asked.append(address)
        raise ConnectionRefusedError("nothing listens")

    monkeypatch.setattr(wire.socket, "create_connection", connect)
    monkeypatch.setattr(
        wire.socket,
        "getaddrinfo",
        lambda *a, **k: pytest.fail("the name was looked up again"),
    )
    target = wire.Target("http", "example.com", 80, ("203.0.113.9", "2001:db8::9"))

    with pytest.raises(ConnectionRefusedError):
        wire.dial(target, time.monotonic() + 5)

    assert asked == [("203.0.113.9", 80), ("2001:db8::9", 80)]


def test_an_ipv6_address_is_pinned_and_written_in_brackets(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE, PAGE])
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung(allow_private=False, resolve=lambda host: ["2606:2800:21f::1"])
    rung("https://example.com/p")
    http_rung()("http://[2606:2800:21f::1]:8080/p")

    assert seen.targets[0].addresses == ("2606:2800:21f::1",)
    assert seen.requests[1].headers["host"] == "[2606:2800:21f::1]:8080"


def test_an_unguarded_connection_is_not_pinned(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://example.com/p")

    assert seen.targets[0].addresses is None


def test_a_redirect_into_a_private_address_is_refused_before_it_is_asked(
    monkeypatch,
):
    seen = fake_http(monkeypatch, [(302, b"", {"location": "http://10.0.0.1/admin"})])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused) as refused:
        http_rung(allow_private=False, resolve=public)("https://example.com/p")

    assert refused.value.url == "http://10.0.0.1/admin"
    assert seen.urls == ["/p"]
    assert len(seen.targets) == 1


@pytest.mark.parametrize(
    "target",
    [
        "gopher://127.0.0.1:6379/_SET%20pwned%201%0D%0A",
        "dict://127.0.0.1:11211/stats",
        "file:///etc/hosts",
        "ftp://example.com/file",
    ],
)
def test_a_redirect_off_the_web_is_refused_before_it_is_asked(monkeypatch, target):
    """Measured with curl before this was refused: a 302 to gopher:// sent
    ``SET pwned 1`` to whatever listened on that port, and a 302 to
    file:///etc/hosts returned the file as the page. The standard library
    speaks neither, and the hop is refused before anything is dialled."""
    seen = fake_http(monkeypatch, [(302, b"", {"location": target}), PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused, match="only http and https") as refused:
        http_rung()("https://example.com/p")

    assert refused.value.url == target
    assert seen.urls == ["/p"]
    assert len(seen.targets) == 1


def test_an_address_off_the_web_is_never_asked_by_the_rung(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(AddressRefused, match="not file"):
        http_rung()("file:///etc/hosts")

    assert seen.targets == []


def test_the_ladder_refuses_an_address_off_the_web_whatever_it_allows():
    browser = _rung("browser")

    with pytest.raises(AddressRefused, match="not file"):
        fetch("file:///etc/hosts", rungs=[("browser", browser)], allow_private=True)

    assert browser.calls == []


def test_a_page_that_landed_off_the_web_is_refused():
    """A rung that follows redirects itself is judged where it landed."""

    def landed_elsewhere(url):
        return Fetched(url="file:///etc/hosts", html="<p>ok</p>", status=200, rung="x")

    with pytest.raises(AddressRefused, match="not file"):
        fetch(
            "https://example.com/p",
            rungs=[("x", landed_elsewhere)],
            robots_reader=lambda url: None,
        )


def test_every_wait_is_given_what_is_left_of_one_deadline(monkeypatch):
    """A timeout per read is a floor on speed, not a deadline: a body dripped
    eight bytes a second held curl_cffi's stream for as long as it dripped."""
    seen = fake_http(monkeypatch, [(302, b"", {"location": "/q"}), PAGE], chunk=4)
    from sluicer.fetch.http_rung import http_rung

    http_rung(timeout=7)("https://example.com/p")

    assert seen.timeouts, "no wait was bounded"
    assert all(0 < t <= 7 for t in seen.timeouts)
    assert seen.timeouts == sorted(seen.timeouts, reverse=True), (
        "each wait gets what is left, never a fresh allowance"
    )


def test_a_dripped_body_is_cut_at_the_deadline(monkeypatch):
    fake_http(monkeypatch, [PAGE], chunk=4, drip=0.2)
    from sluicer.fetch.http_rung import http_rung

    started = time.monotonic()
    with pytest.raises(TimeoutError, match=r"longer than 0\.5 seconds") as raised:
        http_rung(timeout=0.5)("https://example.com/p")

    assert time.monotonic() - started < 1.5
    assert isinstance(raised.value, OSError), "callers catch OSError"


def test_a_fetch_past_its_deadline_asks_nothing_more(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(TimeoutError, match="longer than 0 seconds"):
        http_rung(timeout=0)("https://example.com/p")

    assert seen.targets == []


def test_a_name_lookup_that_never_answers_ends_at_the_deadline():
    def hangs():
        time.sleep(5)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        wire.within(time.monotonic() + 0.2, hangs)
    assert time.monotonic() - started < 1


def test_no_proxy_is_used_unless_one_is_asked_for(monkeypatch):
    """libcurl read HTTPS_PROXY itself: measured, a CONNECT reached a local
    proxy nobody had named to Sluicer. Nothing here reads it."""
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:3128")
    monkeypatch.delenv("SLUICER_PROXY", raising=False)
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://example.com/p")

    assert seen.targets[0].proxy is None


@pytest.mark.parametrize("by", ["argument", "environment"])
def test_a_proxy_asked_for_is_the_one_used(monkeypatch, by):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    kwargs = {}
    if by == "argument":
        kwargs["proxy"] = "socks5h://proxy.example:1080"
    else:
        monkeypatch.setenv("SLUICER_PROXY", "socks5h://proxy.example:1080")
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(**kwargs)("https://example.com/p")

    assert seen.targets[0].proxy == wire.Proxy("socks5h", "proxy.example", 1080)


def test_an_empty_proxy_is_none(monkeypatch):
    monkeypatch.setenv("SLUICER_PROXY", "socks5h://proxy.example:1080")
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(proxy="")("https://example.com/p")

    assert seen.targets[0].proxy is None


def test_a_proxy_of_a_kind_it_does_not_speak_is_refused_when_built():
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ValueError, match="not a proxy Sluicer speaks to"):
        http_rung(proxy="ftp://proxy.example:21")


@pytest.mark.parametrize(
    "address",
    [
        "https://alice:HUNTER2@proxy.example:3128",
        "http://alice:HUNTER2@proxy.example:notaport",
        "socks5://alice:HUNTER2@",
    ],
)
def test_a_proxy_refused_is_not_repeated_with_its_password(address):
    """Measured on 0.8.0: the whole address, password and all, was in the
    message, and so in the MCP server's log."""
    with pytest.raises(ValueError) as refused:
        wire.Proxy.parse(address)

    assert "HUNTER2" not in str(refused.value)
    assert "alice" in str(refused.value) or "proxy" in str(refused.value)


def test_plain_http_through_an_http_proxy_names_the_whole_address(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(proxy="http://me:secret@proxy.example:3128")("http://example.com/p?q=1")

    request = seen.requests[0]
    assert request.line == "GET http://example.com/p?q=1 HTTP/1.1"
    assert request.headers["proxy-authorization"] == "Basic bWU6c2VjcmV0"


def test_a_redirect_loop_ends(monkeypatch):
    loop = [(302, b"", {"location": "/p"}) for _ in range(20)]
    fake_http(monkeypatch, loop)
    from sluicer.fetch.http_rung import TooManyRedirects, http_rung

    with pytest.raises(TooManyRedirects):
        http_rung()("https://example.com/p")


def test_the_charset_the_response_was_sent_with_decodes_it(monkeypatch):
    body = "<html><body>Café</body></html>".encode("windows-1252")
    fake_http(
        monkeypatch, [(200, body, {"content-type": "text/html; charset=windows-1252"})]
    )
    from sluicer.fetch.http_rung import http_rung

    assert "Café" in http_rung()("https://example.com/p").html


def test_a_name_that_resolves_to_nothing_is_not_left_for_curl_to_look_up():
    """Left to the client, the second lookup is the one DNS rebinding answers."""
    with pytest.raises(OSError):
        public_addresses("https://example.com/p", resolve=lambda host: [])


def test_a_host_written_as_an_address_is_its_own_pin(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(allow_private=False)(f"https://{PUBLIC}/p")

    assert seen.targets[0].addresses == (PUBLIC,)


def test_an_answer_that_is_not_http_is_a_connection_error(monkeypatch):
    fake_http(monkeypatch, [b"SSH-2.0-OpenSSH_9.9\r\n\r\n"])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ConnectionError):
        http_rung()("https://example.com/p")


# -- one connection per site ----------------------------------------------------


def test_twenty_pages_of_a_site_are_asked_on_one_connection(monkeypatch):
    """A new session for every request was twenty handshakes for twenty
    pages: measured, twenty client ports where one would do."""
    seen = fake_http(monkeypatch, [PAGE] * 21)
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    for page in range(20):
        rung(f"https://example.com/p/{page}")
    http_rung()("https://example.com/again")

    assert seen.connections == 1
    assert {request.connection for request in seen.requests} == {0}


def test_two_sites_are_two_connections_and_so_are_two_schemes(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE] * 4)
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    for url in ("https://a.example/", "https://b.example/", "http://a.example/"):
        rung(url)
    rung("https://a.example/2")

    assert [t.host for t in seen.targets] == ["a.example", "b.example", "a.example"]
    assert [r.connection for r in seen.requests] == [0, 1, 2, 0]


def test_a_connection_the_server_said_it_would_close_is_not_kept(monkeypatch):
    closing = (200, b"<p>ok</p>", {"Connection": "close"})
    seen = fake_http(monkeypatch, [closing, PAGE])
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    rung("https://example.com/1")
    rung("https://example.com/2")

    assert seen.connections == 2
    assert seen.sockets[0].closed


def test_a_kept_connection_the_server_closed_is_found_out_before_it_is_used(
    monkeypatch,
):
    seen = fake_http(monkeypatch, [PAGE, PAGE])
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    rung("https://example.com/1")
    seen.sockets[0].hung_up = True
    rung("https://example.com/2")

    assert seen.connections == 2
    assert [r.connection for r in seen.requests] == [0, 1]


def test_a_request_that_meets_a_close_on_a_kept_connection_is_sent_again(
    monkeypatch,
):
    seen = fake_http(monkeypatch, [PAGE, ConnectionResetError("reset"), PAGE])
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    rung("https://example.com/1")
    assert rung("https://example.com/2").html == "<html><body>ok</body></html>"

    assert seen.connections == 2
    assert [r.target for r in seen.requests] == ["/1", "/2", "/2"]


def test_a_new_connection_that_fails_is_not_tried_again(monkeypatch):
    seen = fake_http(monkeypatch, [ConnectionResetError("reset"), PAGE])
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ConnectionResetError):
        http_rung()("https://example.com/1")

    assert seen.connections == 1


# One byte a read, so that what a server sent after an answer's headers is
# still on the connection when they were read: the next segment, not yet come.
_HINTS = b"HTTP/1.1 103 Early Hints\r\nLink: </style.css>; rel=preload\r\n\r\n"


def test_early_hints_are_read_past_to_the_answer_they_precede(monkeypatch):
    """http.client skips a 100 and no other 1xx: a 103 came back as the
    answer, empty, the connection was kept with the real answer unread on it,
    and the next page of the site was handed that answer as its own. Measured
    in a crawl: /p/p3 recorded Product p2."""
    first = _HINTS + render((200, b"<p>first</p>", {}))
    seen = fake_http(monkeypatch, [first, (200, b"<p>second</p>", {})], chunk=1)
    from sluicer.fetch.http_rung import http_rung

    rung = http_rung()
    got = rung("https://example.com/1")
    assert (got.status, got.html) == (200, "<p>first</p>")
    assert rung("https://example.com/2").html == "<p>second</p>"
    assert seen.connections == 1


@pytest.mark.parametrize("chunk", [1, None])
def test_every_interim_answer_is_read_past(monkeypatch, chunk):
    """Read whole, as one segment, the page after the hints was in the reader
    the 103 was parsed from, and went with it."""
    interim = (
        b"HTTP/1.1 102 Processing\r\n\r\n"
        + _HINTS
        + b"HTTP/1.1 100 Continue\r\n\r\n"
        + _HINTS
    )
    fake_http(monkeypatch, [interim + render((200, b"<p>ok</p>", {}))], chunk=chunk)
    from sluicer.fetch.http_rung import http_rung

    got = http_rung()("https://example.com/p")
    assert (got.status, got.html) == (200, "<p>ok</p>")


def test_a_switch_of_protocols_nobody_asked_for_is_not_an_answer(monkeypatch):
    switching = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: h2c\r\n\r\n"
    seen = fake_http(monkeypatch, [switching, PAGE])
    from sluicer.fetch.http_rung import ProtocolError, http_responses

    with pytest.raises(ProtocolError, match="101"):
        http_responses()("https://example.com/p")

    assert seen.sockets[0].closed
    assert seen.pool._idle == []


def test_a_no_content_answer_that_announces_content_is_not_kept(monkeypatch):
    """A 204 may carry no body and must not say it has one: one that sends
    a Content-Length and its bytes after the headers left them on the kept
    connection, where the next request read them as the start of its answer."""
    no_content = b"HTTP/1.1 204 No Content\r\nContent-Length: 5\r\n\r\nhello"
    seen = fake_http(monkeypatch, [no_content, PAGE], chunk=1)
    from sluicer.fetch.http_rung import http_responses

    get = http_responses()
    assert (get("https://example.com/1").status, seen.connections) == (204, 1)
    assert get("https://example.com/2").body == PAGE[1]
    assert seen.connections == 2


def test_a_not_modified_answer_with_its_length_keeps_the_connection(monkeypatch):
    """A 304 may name the length the page would have had (RFC 9110, 8.6),
    and sends no body: its connection is kept, as the cache's revalidations
    count on."""
    not_modified = b"HTTP/1.1 304 Not Modified\r\nContent-Length: 1234\r\n\r\n"
    seen = fake_http(monkeypatch, [not_modified, PAGE], chunk=1)
    from sluicer.fetch.http_rung import http_responses

    get = http_responses()
    assert get("https://example.com/1").status == 304
    assert get("https://example.com/2").body == PAGE[1]
    assert seen.connections == 1


def test_a_kept_connection_is_not_used_once_its_address_is_no_longer_checked(
    monkeypatch,
):
    """The pin holds for a kept connection too: the name now resolves
    elsewhere, so the connection to where it used to is not the site's."""
    seen = fake_http(monkeypatch, [PAGE, PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung(allow_private=False, resolve=public)("https://example.com/1")
    moved = http_rung(allow_private=False, resolve=lambda host: ["93.184.215.15"])
    moved("https://example.com/2")

    assert seen.connections == 2
    assert seen.targets[1].addresses == ("93.184.215.15",)


def test_a_connection_left_idle_too_long_is_closed_not_used():
    clock = [0.0]
    dialled = []

    class Sock:
        closed = False

        def close(self):
            self.closed = True

    def dial(target, deadline):
        dialled.append(Sock())
        return wire.Timed(dialled[-1], deadline, None)

    pool = wire.Connections(dial=dial, idle_seconds=60, clock=lambda: clock[0])
    target = wire.Target("https", "example.com", 443)
    first, _ = pool.take(target, time.monotonic() + 5)
    pool.give(target, first)
    clock[0] = 61
    second, kept = pool.take(target, time.monotonic() + 5)

    assert not kept and second is not first
    assert dialled[0].closed


def test_the_pool_keeps_no_more_than_its_bound():
    def dial(target, deadline):
        return wire.Timed(types.SimpleNamespace(close=lambda: None), deadline, None)

    pool = wire.Connections(dial=dial, max_idle=2)
    for host in ("a", "b", "c"):
        target = wire.Target("https", f"{host}.example", 443)
        pool.give(target, pool.take(target, time.monotonic() + 5)[0])

    assert [key[1] for key, _, _ in pool._idle] == ["b.example", "c.example"]


# -- the caller's headers --------------------------------------------------------


def test_the_callers_headers_go_to_the_origin_asked_and_nowhere_else(monkeypatch):
    seen = fake_http(
        monkeypatch,
        [
            (302, b"", {"location": "/login/done"}),
            (302, b"", {"location": "https://cdn.example/p"}),
            PAGE,
        ],
    )
    from sluicer.fetch.http_rung import http_rung

    send = {"Authorization": "Bearer t", "Cookie": "session=1"}
    http_rung(send=send)("https://example.com/p")

    first, second, elsewhere = (r.headers for r in seen.requests)
    assert first["authorization"] == second["authorization"] == "Bearer t"
    assert first["cookie"] == second["cookie"] == "session=1"
    assert "authorization" not in elsewhere and "cookie" not in elsewhere


@pytest.mark.parametrize(
    "name", ["User-Agent", "user-agent", "Host", "Accept-Encoding", "Connection"]
)
def test_the_caller_cannot_replace_what_the_transport_writes(name):
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(ValueError, match=r"User-Agent|written by the transport"):
        http_rung(send={name: "x"})


def test_an_address_with_a_user_and_password_sends_them_as_basic(monkeypatch):
    seen = fake_http(monkeypatch, [PAGE])
    from sluicer.fetch.http_rung import http_rung

    http_rung()("https://me:p%40ss@example.com/p")

    assert seen.requests[0].headers["authorization"] == "Basic bWU6cEBzcw=="


def test_a_password_in_the_address_is_sent_and_never_repeated(
    monkeypatch, plain_ladder
):
    """Measured on 0.8.0 (the second security review's userinfo.py): the
    page fetched from ``http://alice:PW123@...`` came back with that address
    as its ``url``, password and all, for every answer and file to repeat."""
    seen = fake_http(monkeypatch, [NOTHING, PAGE])

    landed = fetch("https://me:secret@example.com/p", resolve=public)

    assert seen.requests[1].headers["authorization"] == "Basic bWU6c2VjcmV0"
    assert landed.url == "https://me:***@example.com/p"


@pytest.mark.parametrize(
    ("address", "options", "raised"),
    [
        # Not an address at all: its port is not a number.
        ("https://me:secret@example.com:99999/p", {}, "FetchFailed"),
        # A private address, refused before it is asked.
        ("http://me:secret@127.0.0.1/p", {"allow_private": False}, "AddressRefused"),
        # A connection refused, on every rung.
        ("http://me:secret@127.0.0.1:9/p", {}, "FetchFailed"),
    ],
)
def test_a_password_in_the_address_is_never_repeated_by_a_failure(
    monkeypatch, plain_ladder, address, options, raised
):
    """Measured on 0.8.0: ``Could not fetch http://alice:PW123@127.0.0.1:9/page:
    could not read the robots.txt for http://alice:PW123@...``, which the MCP
    server and the HTTP API hand on as the answer's message and ``url``."""
    with pytest.raises(Exception) as failed:
        fetch(address, **options)

    assert type(failed.value).__name__ == raised
    assert "secret" not in str(failed.value)
    assert "me:***@" in str(failed.value)
    assert "secret" not in failed.value.url


def test_a_robots_refusal_never_repeats_the_password(monkeypatch, plain_ladder):
    from sluicer.fetch.ladder import RobotsRefused

    fake_http(monkeypatch, [(200, b"User-agent: *\nDisallow: /\n", {})])

    with pytest.raises(RobotsRefused) as refused:
        fetch("https://me:secret@example.com/p", resolve=public)

    assert "secret" not in str(refused.value) and "secret" not in refused.value.url


def test_a_message_names_an_address_with_its_password_hidden():
    from sluicer.fetch.result import shown

    assert shown("Could not fetch http://me:p%40ss@h.example:8/p?q=a@b: no") == (
        "Could not fetch http://me:***@h.example:8/p?q=a@b: no"
    )
    assert shown("'https://me:a:b@c@[::1]:8443/'") == "'https://me:***@[::1]:8443/'"
    # A user alone is no secret, and an address without one is left as it is.
    assert shown("socks5://me@proxy.example") == "socks5://me@proxy.example"
    assert shown("http://h.example:8080/@me:x") == "http://h.example:8080/@me:x"
    assert shown("http://a:1@x.example and https://b:2@y.example") == (
        "http://a:***@x.example and https://b:***@y.example"
    )


LOGIN = {"headers": {"Authorization": "Bearer t"}, "cookies": {"session": "1"}}
NOTHING = (404, b"", {})


def _sent_a_login(request):
    return "authorization" in request.headers or "cookie" in request.headers


@pytest.fixture
def plain_ladder(monkeypatch):
    """The default ladder without a browser, the gate not waiting."""
    from sluicer.fetch.gate import GATE

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    monkeypatch.setattr(GATE, "min_delay", 0.0)


def test_the_robots_txt_a_redirect_lands_on_is_not_sent_the_login(
    monkeypatch, plain_ladder
):
    """Measured on 0.8.0: the other origin's robots.txt was read through the
    ladder's own rung, which took the robots.txt address for the one asked
    and sent it the caller's Authorization and cookies."""
    seen = fake_http(
        monkeypatch,
        [NOTHING, (302, b"", {"location": "https://other.example/q"}), PAGE, NOTHING],
    )

    landed = fetch("https://example.com/p", **LOGIN)

    assert landed.url == "https://other.example/q"
    assert [(seen.targets[r.connection].host, r.target) for r in seen.requests] == [
        ("example.com", "/robots.txt"),
        ("example.com", "/p"),
        ("other.example", "/q"),
        ("other.example", "/robots.txt"),
    ]
    assert [_sent_a_login(r) for r in seen.requests] == [False, True, False, False]


def test_robots_txt_is_read_as_anyone_reads_it(monkeypatch, plain_ladder):
    """One answer per site, whoever asks: read with a login, the answer was
    kept for the site and given to every caller for a day, with that login
    or without it."""
    from sluicer.fetch.identity import _CACHE

    seen = fake_http(monkeypatch, [(200, b"User-agent: *\nAllow: /\n", {}), PAGE])

    fetch("https://example.com/p", **LOGIN)

    assert [r.target for r in seen.requests] == ["/robots.txt", "/p"]
    assert [_sent_a_login(r) for r in seen.requests] == [False, True]
    assert list(_CACHE) == ["https://example.com"]


def test_a_redirect_to_another_port_reads_that_ports_robots_txt(
    monkeypatch, plain_ladder
):
    """An origin is its scheme, host and port: a redirect from :443 to :8443
    lands on a server whose robots.txt had not been read."""
    seen = fake_http(
        monkeypatch,
        [
            NOTHING,
            (302, b"", {"location": "https://example.com:8443/q"}),
            PAGE,
            (200, b"User-agent: *\nDisallow: /q\n", {}),
        ],
    )
    from sluicer.fetch.ladder import RobotsRefused

    with pytest.raises(RobotsRefused):
        fetch("https://example.com/p")

    assert [r.target for r in seen.requests] == [
        "/robots.txt",
        "/p",
        "/q",
        "/robots.txt",
    ]
    assert seen.targets[-1].port == 8443


def test_the_login_is_not_sent_back_over_plain_http(monkeypatch):
    """The origin a login goes to is the one the caller named: an https page
    that redirects to its own host over http is asked there without it."""
    seen = fake_http(
        monkeypatch, [(302, b"", {"location": "http://example.com/q"}), PAGE]
    )
    from sluicer.fetch.http_rung import http_rung

    send = {"Authorization": "Bearer t", "Cookie": "session=1"}
    http_rung(send=send, send_to=["https://example.com/"])("https://example.com/p")

    assert [_sent_a_login(r) for r in seen.requests] == [True, False]


def test_a_transport_given_its_origins_sends_the_login_to_them_alone(monkeypatch):
    """Built for the addresses a caller named, it is handed others -- a link,
    a sitemap another host serves -- and sends those nothing of the login."""
    seen = fake_http(monkeypatch, [PAGE] * 4)
    from sluicer.fetch.http_rung import http_responses

    get = http_responses(
        send={"Authorization": "Bearer t"},
        send_to=["https://example.com/start", "https://shop.example:8443/"],
    )
    for url in (
        "https://example.com/other",
        "https://shop.example:8443/p",
        "https://www.example.com/",
        "https://cdn.example/sitemap.xml",
    ):
        get(url)

    assert [_sent_a_login(r) for r in seen.requests] == [True, True, False, False]


# -- proxies, on the wire --------------------------------------------------------


class Scripted:
    """A socket to a proxy: what the proxy answers is scripted."""

    def __init__(self, answer: bytes) -> None:
        self.answer = answer
        self.sent = b""

    def settimeout(self, value):
        pass

    def sendall(self, data):
        self.sent += data

    def recv(self, size):
        data, self.answer = self.answer[:size], self.answer[size:]
        return data

    def close(self):
        pass


def test_an_http_proxy_is_asked_for_a_tunnel_and_nothing_past_its_answer_is_read():
    sock = Scripted(b"HTTP/1.1 200 Connection established\r\n\r\nTLS BYTES")
    target = wire.Target(
        "https", "example.com", 443, proxy=wire.Proxy.parse("http://u:p@proxy:3128")
    )

    wire._tunnel(sock, target, target.proxy, time.monotonic() + 5)

    assert sock.sent == (
        b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n"
        b"Proxy-Authorization: Basic dTpw\r\n\r\n"
    )
    assert sock.answer == b"TLS BYTES"


def test_an_http_proxy_that_refuses_the_tunnel_says_so():
    sock = Scripted(b"HTTP/1.1 403 Forbidden\r\n\r\n")
    target = wire.Target(
        "https", "example.com", 443, proxy=wire.Proxy.parse("http://p")
    )

    with pytest.raises(wire.ProxyRefused, match="403"):
        wire._tunnel(sock, target, target.proxy, time.monotonic() + 5)


def test_socks5h_hands_the_name_to_the_proxy():
    sock = Scripted(b"\x05\x00" + b"\x05\x00\x00\x01" + b"\x00" * 6)
    target = wire.Target(
        "https", "example.com", 443, proxy=wire.Proxy.parse("socks5h://p:1080")
    )

    wire._socks5(sock, target, target.proxy, time.monotonic() + 5)

    assert sock.sent == (b"\x05\x01\x00" + b"\x05\x01\x00\x03\x0bexample.com\x01\xbb")


def test_socks5_sends_a_checked_address_and_logs_in_when_given_a_user():
    sock = Scripted(b"\x05\x02" + b"\x01\x00" + b"\x05\x00\x00\x01" + b"\x00" * 6)
    target = wire.Target(
        "http",
        "example.com",
        80,
        addresses=("203.0.113.9",),
        proxy=wire.Proxy.parse("socks5://me:pw@p:1080"),
    )

    wire._socks5(sock, target, target.proxy, time.monotonic() + 5)

    assert sock.sent == (
        b"\x05\x02\x00\x02"
        + b"\x01\x02me\x02pw"
        + b"\x05\x01\x00\x01"
        + bytes([203, 0, 113, 9])
        + b"\x00\x50"
    )


def test_a_socks_proxy_that_cannot_connect_says_why():
    sock = Scripted(b"\x05\x00" + b"\x05\x05\x00\x01" + b"\x00" * 6)
    target = wire.Target(
        "https", "x.example", 443, proxy=wire.Proxy.parse("socks5h://p")
    )

    with pytest.raises(wire.ProxyRefused, match="connection refused"):
        wire._socks5(sock, target, target.proxy, time.monotonic() + 5)


# -- the browser guard --------------------------------------------------------


class FakeRequest:
    def __init__(self, url, document=False):
        self.url = url
        self._document = document
        self.frame = types.SimpleNamespace(parent_frame=None if document else object())

    def is_navigation_request(self):
        return self._document


class FakeRoute:
    """A route whose ``fetch`` answers from ``answers``, keyed by URL."""

    def __init__(self, url, answers, document=False):
        self.request = FakeRequest(url, document)
        self.answers = answers
        self.fetched = []
        self.outcome = None

    def fetch(self, url, max_redirects):
        assert max_redirects == 0
        self.fetched.append(url)
        status, location = self.answers[url]
        headers = {"location": location} if location else {}
        return types.SimpleNamespace(status=status, headers=headers)

    def fulfill(self, response):
        self.outcome = ("fulfilled", response.status)

    def abort(self, reason):
        self.outcome = ("aborted", reason)

    def continue_(self):
        self.outcome = ("continued", None)


def resolve_by_name(host):
    return ["10.0.0.5"] if host.startswith("internal") else [PUBLIC]


def test_the_guard_turns_away_a_request_for_a_private_address():
    guard = Guard(resolve_by_name)
    route = FakeRoute("http://internal.example/img", {})

    guard._route(route)

    assert route.outcome == ("aborted", "blockedbyclient")
    assert route.fetched == []
    assert guard.refused[0][0] == "http://internal.example/img"


def test_the_guard_walks_a_subresource_redirect_chain_itself():
    """Chromium follows a fulfilled redirect without asking the route: measured.

    So the chain is walked here, and the private hop at its end never asked.
    """
    guard = Guard(resolve_by_name)
    answers = {
        "https://cdn.example/a": (302, "/b"),
        "https://cdn.example/b": (302, "http://internal.example/secret"),
    }
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.fetched == ["https://cdn.example/a", "https://cdn.example/b"]
    assert route.outcome == ("aborted", "blockedbyclient")
    assert guard.refused == [
        (
            "http://internal.example/secret",
            guard.why_refused("http://internal.example/x"),
        )
    ]


def test_the_guard_hands_over_the_last_answer_of_a_public_chain():
    guard = Guard(resolve_by_name)
    answers = {
        "https://cdn.example/a": (301, "/b"),
        "https://cdn.example/b": (200, None),
    }
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.outcome == ("fulfilled", 200)


def test_the_documents_own_redirect_is_left_for_the_rung_to_ask_again():
    guard = Guard(resolve_by_name)
    answers = {"https://example.com/old": (301, "https://example.com/new")}
    route = FakeRoute("https://example.com/old", answers, document=True)

    guard._route(route)

    assert guard.redirect == "https://example.com/new"
    assert route.outcome == ("aborted", "blockedbyclient")


def test_the_guard_lets_non_web_schemes_through_untouched():
    guard = Guard(resolve_by_name)
    route = FakeRoute("data:image/png;base64,AAAA", {})

    guard._route(route)

    assert route.outcome == ("continued", None)


def test_the_guard_looks_each_host_up_once():
    asked = []

    def resolve(host):
        asked.append(host)
        return [PUBLIC]

    guard = Guard(resolve)
    for path in ("a", "b", "c"):
        guard.why_refused(f"https://cdn.example/{path}")

    assert asked == ["cdn.example"]


def test_a_websocket_to_a_private_address_is_never_connected():
    guard = Guard(resolve_by_name)
    connected = []
    socket = types.SimpleNamespace(
        url="ws://internal.example/live", connect_to_server=lambda: connected.append(1)
    )

    guard._socket(socket)

    assert connected == []
    assert guard.refused[0][0] == "ws://internal.example/live"


def test_a_websocket_to_a_public_address_is_connected():
    guard = Guard(resolve_by_name)
    connected = []
    socket = types.SimpleNamespace(
        url="wss://live.example/feed", connect_to_server=lambda: connected.append(1)
    )

    guard._socket(socket)

    assert connected == [1]


def test_a_route_that_nothing_answers_is_aborted_not_left_hanging():
    guard = Guard(resolve_by_name)
    route = FakeRoute("https://down.example/a", {})  # fetch raises KeyError

    guard._route(route)

    assert route.outcome == ("aborted", "failed")


# -- the browser rung, guarded --------------------------------------------------


def _browser(pages, **options):
    from sluicer.fetch.browser import browser_rung

    host = FakeHost(pages)
    return browser_rung(host=host, **options), host


def test_the_guarded_browser_asks_for_the_documents_redirect_as_a_new_fetch():
    browser, host = _browser(
        {
            "https://example.com/old": "->https://example.com/new",
            "https://example.com/new": "<p>new</p>",
        },
        allow_private=False,
        resolve=public,
    )
    result = browser("https://example.com/old")

    assert result.url == "https://example.com/new"
    assert host.loads == ["https://example.com/old", "https://example.com/new"]
    assert all(context.closed for context in host.contexts)


def test_the_guarded_browser_refuses_a_document_redirected_somewhere_private():
    browser, host = _browser(
        {"https://example.com/old": "->http://10.0.0.1/"},
        allow_private=False,
        resolve=public,
    )
    with pytest.raises(AddressRefused):
        browser("https://example.com/old")

    assert host.loads == ["https://example.com/old"]


def test_the_guard_is_installed_on_every_pages_context_before_it_loads():
    """A context per page, the guard on each: a route installed once on a
    shared page could be dropped by whoever used the page next."""
    browser, host = _browser(
        {"https://example.com/a": "<p>a</p>", "https://example.com/b": "<p>b</p>"},
        allow_private=False,
        resolve=public,
    )
    browser("https://example.com/a")
    browser("https://example.com/b")

    assert len(host.contexts) == 2
    for context in host.contexts:
        assert [pattern for pattern, _ in context.routes] == ["**/*"]
        assert isinstance(context.routes[0][1].__self__, Guard)
        assert [pattern for pattern, _ in context.sockets] == ["**/*"]


def test_a_guard_that_could_not_install_fails_the_rung():
    from sluicer.fetch.browser import browser_rung

    host = FakeHost({"https://example.com/p": "<p>hi</p>"})

    def broken(pattern, handler):
        raise RuntimeError("route is not supported by this browser")

    original = host.run

    def run(job, wait=0.0):
        def with_broken_routes(browser):
            made = browser.new_context

            def new_context(**options):
                context = made(**options)
                context.route = broken
                return context

            browser.new_context = new_context
            return job(browser)

        return original(with_broken_routes)

    host.run = run
    rung = browser_rung(allow_private=False, resolve=public, host=host)
    with pytest.raises(RuntimeError, match="not supported"):
        rung("https://example.com/p")
    assert host.loads == []


def test_the_browsers_page_is_held_to_the_same_bound():
    browser, _ = _browser(
        {"https://example.com/p": "<p>" + "x" * 5000 + "</p>"}, max_bytes=1000
    )
    with pytest.raises(ResponseTooLarge):
        browser("https://example.com/p")


# -- the ladder ----------------------------------------------------------------


def _rung(name, html="<html><body>ok</body></html>", raises=None, status=200):
    calls = []

    def rung(url):
        calls.append(url)
        if raises is not None:
            raise raises
        return Fetched(url=url, html=html, status=status, rung=name)

    rung.calls = calls
    return rung


def test_a_page_too_heavy_is_never_a_reason_to_climb():
    heavy = _rung("http", raises=ResponseTooLarge("https://example.com/p", 10))
    browser = _rung("browser")

    with pytest.raises(ResponseTooLarge):
        fetch(
            "https://example.com/p",
            rungs=[("http", heavy), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []


_HALF = b"HTTP/1.1 200 OK\r\nContent-Length: 2000\r\n\r\n<html>half"
_HALF_CHUNKED = (
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n7d0\r\n<html>half"
)
_HALF_GZIP = render((200, _cut(gzip.compress(_WORDS)), {"Content-Encoding": "gzip"}))


@pytest.mark.parametrize(
    ("reply", "again"),
    [(_HALF, True), (_HALF_CHUNKED, True), (_HALF_GZIP, False)],
    ids=["length", "chunked", "gzip"],
)
def test_a_body_cut_short_is_never_a_reason_to_climb(monkeypatch, reply, again):
    """With the browser installed, a page the HTTP rung refused as cut short
    was asked of the browser, which was sent the same cut and returned half
    the page with 200: the refusal undone one rung up."""
    fake_http(monkeypatch, [reply])
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.ladder import FetchFailed

    browser = _rung("browser")
    with pytest.raises(FetchFailed, match=r"cut short|ends before its end") as failed:
        fetch(
            "https://example.com/p",
            rungs=[("http", http_rung()), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []
    assert failed.value.transient is again


def test_the_ladder_holds_an_injected_rung_to_the_bound():
    big = _rung("http", html="<p>" + "x" * 5000 + "</p>")

    with pytest.raises(ResponseTooLarge):
        fetch(
            "https://example.com/p",
            rungs=[("http", big)],
            robots_reader=lambda url: None,
            max_bytes=1000,
        )


def test_a_redirect_refused_inside_a_rung_is_a_refusal_not_a_climb():
    refusing = _rung("http", raises=AddressRefused("http://10.0.0.1/", "private"))
    browser = _rung("browser")

    with pytest.raises(AddressRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", refusing), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []


def test_the_ladder_says_how_long_each_rung_took():
    refused = _rung("http", status=403, html="<html><body>Forbidden</body></html>")
    browser = _rung(
        "browser", html="<html><body>" + "Real text. " * 40 + "</body></html>"
    )

    result = fetch(
        "https://example.com/p",
        rungs=[("http", refused), ("browser", browser)],
        robots_reader=lambda url: None,
    )

    assert result.rung == "browser"
    assert result.seconds >= 0
    assert [climb.seconds >= 0 for climb in result.climbs] == [True]


def test_the_guard_installs_its_routes_and_no_service_workers_nor_webrtc():
    """WebRTC connects past every route: measured on 0.8.0, a page reached a
    STUN and a TURN server on a private address with the guard installed."""
    calls = []
    page = types.SimpleNamespace(
        add_init_script=lambda script: calls.append(
            ("script", "serviceWorker" in script or "RTCPeerConnection" in script)
        ),
        route=lambda pattern, handler: calls.append(("route", pattern)),
        route_web_socket=lambda pattern, handler: calls.append(("socket", pattern)),
    )
    guard = Guard(resolve_by_name)

    guard.setup(page)

    assert guard.installed
    assert calls == [
        ("script", True),
        ("script", True),
        ("route", "**/*"),
        ("socket", "**/*"),
    ]


# -- the guard proxy ----------------------------------------------------------------


def test_the_guard_proxy_reads_a_tunnel_and_a_plain_request():
    from sluicer.fetch.browser_proxy import asked_of

    tunnel = asked_of(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443")
    six = asked_of(b"CONNECT [2001:db8::1]:8443 HTTP/1.1")
    plain = asked_of(
        b"GET http://example.com:8080/a?b=1 HTTP/1.1\r\nHost: example.com:8080\r\n"
        b"Proxy-Connection: keep-alive\r\nAccept: */*"
    )

    assert (tunnel.tunnel, tunnel.host, tunnel.port) == (True, "example.com", 443)
    assert (six.host, six.port, six.url) == (
        "2001:db8::1",
        8443,
        "http://[2001:db8::1]:8443/",
    )
    assert (plain.host, plain.port, plain.path) == ("example.com", 8080, "/a?b=1")
    assert plain.head(absolute=False) == (
        b"GET /a?b=1 HTTP/1.1\r\nHost: example.com:8080\r\nAccept: */*\r\n"
        b"Connection: close\r\n\r\n"
    )
    assert plain.head(absolute=True, authorization="Basic dTpw").startswith(
        b"GET http://example.com:8080/a?b=1 HTTP/1.1\r\n"
    )
    assert b"Proxy-Authorization: Basic dTpw" in plain.head(True, "Basic dTpw")


@pytest.mark.parametrize(
    "head",
    [
        b"GET /relative HTTP/1.1",
        b"GET https://example.com/ HTTP/1.1",
        b"CONNECT example.com HTTP/1.1",
        b"CONNECT example.com:99999 HTTP/1.1",
        b"CONNECT example.com:\xb2 HTTP/1.1",
        b"GET ftp://example.com/ HTTP/1.1",
        b"BREW coffee HTCPCP/1.0",
    ],
)
def test_the_guard_proxy_serves_nothing_else(head):
    from sluicer.fetch.browser_proxy import asked_of

    assert asked_of(head) is None


def test_a_guarded_pages_context_goes_through_the_guard_proxy(monkeypatch):
    """Every connection the browser makes for the page, loopback included:
    Chromium passes loopback by a proxy unless told ``<-loopback>``."""
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.setattr(
        "sluicer.fetch.browser_proxy.guard_proxy",
        lambda resolve, upstream: types.SimpleNamespace(
            address=f"http://127.0.0.1:1/ via {upstream}",
            username="sluicer",
            password="secret",
        ),
    )
    host = FakeHost({"https://example.com/p": "<p>hi</p>"})
    from sluicer.fetch.browser import browser_rung

    browser_rung(allow_private=False, resolve=public, host=host, proxy="socks5://p:1")(
        "https://example.com/p"
    )

    assert host.contexts[0].options["proxy"] == {
        "server": "http://127.0.0.1:1/ via socks5://p:1",
        "username": "sluicer",
        "password": "secret",
        "bypass": "<-loopback>",
    }


def test_a_browser_elsewhere_is_given_no_guard_proxy_it_cannot_reach(monkeypatch):
    monkeypatch.setenv("SLUICER_CDP_URL", "ws://browser.example:9222/")
    host = FakeHost({"https://example.com/p": "<p>hi</p>"})
    from sluicer.fetch.browser import browser_rung

    browser_rung(allow_private=False, resolve=public, host=host)(
        "https://example.com/p"
    )

    assert "proxy" not in host.contexts[0].options


def test_the_guard_ends_a_subresource_redirect_loop():
    guard = Guard(resolve_by_name)
    answers = {"https://cdn.example/a": (302, "/a")}
    route = FakeRoute("https://cdn.example/a", answers)

    guard._route(route)

    assert route.outcome == ("aborted", "blockedbyclient")
    assert "redirects" in guard.refused[-1][1]


def test_an_address_the_guard_cannot_parse_is_refused():
    assert Guard(resolve_by_name).why_refused("http://[::1") is not None


def test_the_guarded_browser_ends_a_document_redirect_loop():
    browser, _ = _browser(
        {"https://example.com/a": "->https://example.com/a"},
        allow_private=False,
        resolve=public,
    )
    with pytest.raises(RuntimeError, match="redirected more than"):
        browser("https://example.com/a")


def test_a_browser_failure_that_is_not_a_redirect_is_the_rungs_failure():
    browser, host = _browser({}, allow_private=False, resolve=public)
    with pytest.raises(KeyError):
        browser("https://example.com/p")
    assert all(context.closed for context in host.contexts)


@pytest.mark.parametrize(
    ("status", "fetched"), [(200, True), (404, True), (503, False)]
)
def test_an_empty_robots_txt_is_judged_by_its_status(monkeypatch, status, fetched):
    """An empty robots.txt has no rules and allows everything (RFC 9309).

    The HTTP rung refuses an empty body, since an empty page is no page, and
    the robots reader built from it took that refusal for an unreachable
    robots.txt: a site whose robots.txt was an empty file could not be fetched
    at all. A 5xx with an empty body is still unreachable.
    """
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.ladder import FetchFailed

    fake_http(monkeypatch, [(status, b"", {}), PAGE])
    ladder = [("http", http_rung())]

    if fetched:
        assert fetch("https://example.com/p", rungs=ladder).html.startswith("<html>")
    else:
        with pytest.raises(FetchFailed, match="status 503"):
            fetch("https://example.com/p", rungs=ladder)


@pytest.mark.parametrize("status", [404, 410, 403, 500, 503])
def test_an_empty_error_page_is_that_statuses_answer(monkeypatch, status):
    """An empty 404 is a 404: the site's answer about the address, which the
    rung reported as a rung that failed, so the ladder climbed and a crawl
    asked again."""
    fake_http(monkeypatch, [(status, b"", {})])
    from sluicer.fetch.http_rung import http_rung

    page = http_rung()("https://example.com/p")

    assert (page.status, page.html) == (status, "")


def test_an_empty_page_is_still_a_rung_that_failed(monkeypatch):
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.result import EmptyBody

    fake_http(monkeypatch, [(200, b"", {})])

    with pytest.raises(EmptyBody, match="returned no HTML") as raised:
        http_rung()("https://example.com/p")

    assert raised.value.status == 200
    assert isinstance(raised.value, ValueError), "callers catch ValueError"


# -- a caller's rule for redirects ----------------------------------------------


def _same_host(current, target):
    from urllib.parse import urlsplit

    if urlsplit(target).hostname != urlsplit(current).hostname:
        return "it leaves the site"
    return None


def test_a_redirect_the_callers_rule_refuses_is_never_asked(monkeypatch):
    from sluicer.fetch.result import RedirectRefused

    seen = fake_http(
        monkeypatch, [(301, b"", {"location": "https://elsewhere.example/p"}), PAGE]
    )
    from sluicer.fetch.http_rung import http_rung

    with pytest.raises(RedirectRefused) as refused:
        http_rung(redirects=_same_host)("https://example.com/p")

    assert refused.value.url == "https://example.com/p"
    assert refused.value.target == "https://elsewhere.example/p"
    assert refused.value.reason == "it leaves the site"
    assert seen.urls == ["/p"]


def test_a_redirect_the_callers_rule_allows_is_followed(monkeypatch):
    seen = fake_http(monkeypatch, [(302, b"", {"location": "/q"}), PAGE])
    from sluicer.fetch.http_rung import http_rung

    result = http_rung(redirects=_same_host)("https://example.com/p")

    assert result.url == "https://example.com/q"
    assert seen.urls == ["/p", "/q"]


def test_the_transport_hands_back_the_bytes_as_they_came(monkeypatch):
    """A sitemap may be gzip nobody announced; decoding it as a page destroys it."""
    body = gzip.compress(b"<urlset/>")
    fake_http(monkeypatch, [(200, body, {"content-type": "application/x-gzip"})])
    from sluicer.fetch.http_rung import http_responses

    response = http_responses()("https://example.com/sitemap.xml.gz")

    assert response.body == body
    assert response.status == 200
    assert response.content_type == "application/x-gzip"
    assert response.url == "https://example.com/sitemap.xml.gz"


def test_the_guarded_browser_asks_the_callers_rule_about_its_document():
    from sluicer.fetch.result import RedirectRefused

    browser, host = _browser(
        {"https://example.com/old": "->https://elsewhere.example/new"},
        allow_private=False,
        resolve=public,
        redirects=_same_host,
    )
    with pytest.raises(RedirectRefused):
        browser("https://example.com/old")

    assert host.loads == ["https://example.com/old"]


def test_a_redirect_the_callers_rule_refused_is_not_a_reason_to_climb():
    from sluicer.fetch.result import RedirectRefused

    refusing = _rung(
        "http",
        raises=RedirectRefused("https://example.com/p", "https://b.example/", "no"),
    )
    browser = _rung("browser")

    with pytest.raises(RedirectRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", refusing), ("browser", browser)],
            robots_reader=lambda url: None,
        )

    assert browser.calls == []
