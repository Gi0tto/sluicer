"""A WARC file, however damaged, is read or refused -- never a traceback.

Valid records are drawn -- responses and resources, plain, chunked, gzip- or
deflate-coded, one gzip member each or none -- then damaged: bytes flipped,
cut short, spliced with junk. Reading one gives the pages before the damage
and then a ``WarcError``; it never raises anything else and never loops.
"""

from __future__ import annotations

import contextlib
import gzip
import io
import zlib

from hypothesis import given, strategies as st

from sluicer.warc import Skipped, WarcError, read_warc

_BODY = st.sampled_from(
    [b"<html><head><title>T</title></head></html>", b"", b"\x89PNG", b"<html>" * 50]
)


@st.composite
def _record(draw) -> bytes:
    body = draw(_BODY)
    headers = {"Content-Type": draw(st.sampled_from(["text/html", "image/png", ""]))}
    coding = draw(st.sampled_from(["", "gzip", "deflate", "br"]))
    if coding == "gzip":
        body = gzip.compress(body)
    elif coding == "deflate":
        body = zlib.compress(body)
    if coding:
        headers["Content-Encoding"] = coding
    if draw(st.booleans()):
        body = b"%x\r\n" % len(body) + body + b"\r\n0\r\n\r\n"
        headers["Transfer-Encoding"] = "chunked"
    status = draw(st.sampled_from(["200 OK", "404 Not Found", "301 Moved", "OK"]))
    head = f"HTTP/1.1 {status}\r\n" + "".join(
        f"{k}: {v}\r\n" for k, v in headers.items()
    )
    kind = draw(st.sampled_from(["response", "resource", "revisit", "request"]))
    block = head.encode() + b"\r\n" + body if kind != "resource" else body
    named = (
        f"WARC/1.1\r\nWARC-Type: {kind}\r\nWARC-Target-URI: https://s.example/p\r\n"
        f"Content-Type: application/http; msgtype=response\r\n"
        f"Content-Length: {len(block)}\r\n\r\n"
    )
    return named.encode() + block + b"\r\n\r\n"


@st.composite
def damaged(draw) -> bytes:
    records = draw(st.lists(_record(), min_size=1, max_size=4))
    zipped = draw(st.booleans())
    data = b"".join(gzip.compress(r) for r in records) if zipped else b"".join(records)
    for _ in range(draw(st.integers(0, 3))):
        if not data:
            break
        where = draw(st.integers(0, len(data) - 1))
        what = draw(st.sampled_from(["flip", "cut", "splice"]))
        if what == "flip":
            data = data[:where] + bytes([data[where] ^ 0xFF]) + data[where + 1 :]
        elif what == "cut":
            data = data[:where]
        else:
            data = data[:where] + draw(st.binary(max_size=20)) + data[where:]
    return data


@given(damaged())
def test_a_damaged_warc_is_read_or_refused(data):
    skipped = Skipped()
    try:
        for page in read_warc(io.BytesIO(data), skipped):
            assert isinstance(page.body, bytes)
            assert page.status is None or 200 <= page.status < 300
    except WarcError:
        pass
    assert all(count > 0 for count in skipped.reasons.values())


@given(st.binary(max_size=300))
def test_bytes_that_are_no_warc_at_all_are_refused(data):
    with contextlib.suppress(WarcError):
        list(read_warc(io.BytesIO(data)))
