"""Read the pages a WARC file holds, as they were served.

WARC (ISO 28500) is what web archives are written in: the Internet Archive's,
Common Crawl's, and what wget, Browsertrix and warcio write. A ``response``
record holds a page as its server sent it -- status, headers, body -- so it is
read as a fetched page is, its headers included: the charset, a canonical in
``Link``, ``X-Robots-Tag``. A ``resource`` record holds a body alone.

Nothing else is a page. ``request``, ``metadata``, ``warcinfo`` and
``conversion`` records are passed over; a page-like record that cannot be read
is counted in ``skipped`` under its reason -- ``revisit`` (the archive saying
"the same as before", with no body), ``not HTML``, ``status 4xx``, ``too
large``, ``compressed with br`` and the like -- so a run says what it left out.

A file may be plain or gzipped, whole or record by record, as archives write
it. Nothing is fetched: an archive is read as it is.
"""

from __future__ import annotations

import gzip
import io
import sys
import zlib
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from sluicer.api import Extraction, _extract as extract
from sluicer.fetch.result import MAX_RESPONSE_BYTES

# The longest header line read, and the most header lines a record may have:
# a file is data, and a broken or hostile one should not make a line endless.
_LINE = 65_536
_MOST_HEADERS = 512
# A record's block holds the HTTP head as well as the body.
_LARGEST_BLOCK = MAX_RESPONSE_BYTES + 1024 * 1024
_CHUNK = 1024 * 1024
_HTML = frozenset({"text/html", "application/xhtml+xml"})
_GZIP = b"\x1f\x8b"


class WarcError(ValueError):
    """The file is not a WARC, or breaks off inside a record. ``source`` is it."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"{source} is not a readable WARC: {reason}")
        self.source = source


@dataclass(frozen=True)
class WarcPage:
    """One page a WARC holds: where it was, what its server said, and its body.

    ``status`` is None for a ``resource`` record, which has no HTTP answer;
    its ``headers`` then hold only the record's ``content-type``. ``body`` is
    as the page was sent, transfer and content codings undone. ``record_id``,
    ``date`` and ``digest`` are the record's own ``WARC-Record-ID``,
    ``WARC-Date`` and ``WARC-Payload-Digest``; ``truncated`` is its
    ``WARC-Truncated``, the reason the archive cut the body short.
    """

    url: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    record_id: str | None = None
    date: str | None = None
    digest: str | None = None
    truncated: str | None = None


@dataclass
class Skipped:
    """What a run left out, by reason, in the order first met.

    ``reasons`` holds the page-like records left out, and is what a run
    reports; ``passed_over`` counts the records that are no page by kind --
    ``request``, ``metadata`` and the like -- for a caller that accounts for
    every record of a file.
    """

    reasons: Counter[str] = field(default_factory=Counter)
    passed_over: Counter[str] = field(default_factory=Counter)

    def add(self, reason: str) -> None:
        self.reasons[reason] += 1

    def __bool__(self) -> bool:
        return bool(self.reasons)

    def __str__(self) -> str:
        return ", ".join(f"{count} {reason}" for reason, count in self.reasons.items())


def read_warc(
    source: str | Path | BinaryIO, skipped: Skipped | None = None
) -> Iterator[WarcPage]:
    """Every page ``source`` holds, in file order.

    ``source`` is a path, ``-`` for standard input, or a binary file object.
    ``skipped`` counts the page-like records left out, by reason.

    Raises:
        WarcError: the file is not a WARC or breaks off inside a record; the
            pages before the break have been given.
        OSError: the file cannot be opened.
    """
    skipped = skipped if skipped is not None else Skipped()
    name = "standard input" if source == "-" else getattr(source, "name", str(source))
    with _opened(source) as stream:
        for fields, block in _records(stream, str(name), skipped):
            page = _page(fields, block, skipped)
            if page is not None:
                yield page


def extract_warc(
    source: str | Path | BinaryIO,
    *,
    induce: bool = False,
    microformats: bool = False,
    skipped: Skipped | None = None,
    visible: bool = True,
) -> Iterator[tuple[WarcPage, Extraction]]:
    """``sluicer.extract`` over every page ``source`` holds, with its headers.

    The arguments are ``extract``'s and ``read_warc``'s. A page that declares
    nothing is still given, with an empty extraction: that it said nothing is
    a finding too.
    """
    for page in read_warc(source, skipped):
        yield (
            page,
            extract(
                page.body,
                url=page.url or None,
                induce=induce,
                microformats=microformats,
                headers=page.headers,
                visible=visible,
            ),
        )


@contextmanager
def _opened(source: str | Path | BinaryIO) -> Iterator[io.BufferedIOBase]:
    """``source`` as one stream of WARC bytes, gzip undone when it is gzipped."""
    if isinstance(source, (str, Path)):
        raw: BinaryIO = sys.stdin.buffer if source == "-" else open(source, "rb")  # noqa: SIM115
        close = source != "-"
    else:
        raw, close = source, False
    try:
        buffered: Any = (
            raw if isinstance(raw, io.BufferedReader) else io.BufferedReader(raw)
        )
        if buffered.peek(2)[:2] == _GZIP:
            # One member or one per record: GzipFile reads on across members.
            # Not wrapped in a buffer of its own, which would read ahead into
            # a broken member and lose the good record before it.
            yield gzip.GzipFile(fileobj=buffered)
        else:
            yield buffered
    finally:
        if close:
            raw.close()


def _records(
    stream: io.BufferedIOBase, name: str, skipped: Skipped
) -> Iterator[tuple[dict[str, str], bytes | None]]:
    """Each record's named fields, lowercased, and its block; None when too large.

    A file must open with a record. Bytes out of place after one -- a
    ``Content-Length`` a few bytes short, as a damaged archive has -- are
    passed over to the next line that opens a record, counted in ``skipped``,
    as warcio does; the record before them was read as its length said.
    """
    started = False
    try:
        while True:
            line = stream.readline(_LINE)
            if not line:
                return
            if not line.strip():
                continue
            if not line.startswith(b"WARC/"):
                if not started:
                    raise WarcError(name, f"it opens with {line[:40]!r}, not WARC/")
                line = _next_record(stream, name)
                skipped.add("stray bytes between records")
                if not line:
                    return
            started = True
            fields = _fields(stream, name)
            try:
                length = int(fields.get("content-length", ""))
            except ValueError:
                raise WarcError(name, "a record has no Content-Length") from None
            if length < 0:
                raise WarcError(name, "a record's Content-Length is negative")
            if length > _LARGEST_BLOCK:
                _discard(stream, length, name)
                yield fields, None
                continue
            block = stream.read(length)
            if len(block) < length:
                raise WarcError(name, "it breaks off inside a record")
            yield fields, block
    except (OSError, EOFError, zlib.error) as broken:
        # A gzip member cut short or corrupt is a file that breaks off.
        raise WarcError(name, str(broken) or type(broken).__name__) from broken


def _next_record(stream: io.BufferedIOBase, name: str) -> bytes:
    """The next line that opens a record, or b"" at the end of the file."""
    passed = 0
    while passed <= _LARGEST_BLOCK:
        line = stream.readline(_LINE)
        if not line or line.startswith(b"WARC/"):
            return line
        passed += len(line)
    raise WarcError(name, f"no record follows for {passed} bytes")


def _fields(stream: io.BufferedIOBase, name: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    last = ""
    for _ in range(_MOST_HEADERS):
        line = stream.readline(_LINE)
        if not line:
            raise WarcError(name, "it breaks off inside a record's header")
        if line in (b"\r\n", b"\n"):
            return fields
        text = line.decode("utf-8", "replace").rstrip("\r\n")
        if text[:1] in (" ", "\t") and last:
            fields[last] = f"{fields[last]} {text.strip()}".strip()
            continue
        key, colon, value = text.partition(":")
        if colon:
            last = key.strip().lower()
            fields[last] = value.strip()
    raise WarcError(name, f"a record's header runs past {_MOST_HEADERS} lines")


def _discard(stream: io.BufferedIOBase, length: int, name: str) -> None:
    left = length
    while left:
        read = len(stream.read(min(left, _CHUNK)))
        if not read:
            raise WarcError(name, "it breaks off inside a record")
        left -= read


def _page(
    fields: dict[str, str], block: bytes | None, skipped: Skipped
) -> WarcPage | None:
    """The page a record holds, or None -- counted in ``skipped`` when page-like."""
    kind = fields.get("warc-type", "").lower()
    if kind == "revisit":
        skipped.add("revisit")
        return None
    if kind not in ("response", "resource"):
        skipped.passed_over[kind or "(no WARC-Type)"] += 1
        return None
    if block is None:
        skipped.add("too large")
        return None
    url = fields.get("warc-target-uri", "").strip().strip("<>").strip()
    if kind == "response":
        if not fields.get("content-type", "").lower().startswith("application/http"):
            # Heritrix writes DNS lookups as response records, for one.
            skipped.add("not HTTP")
            return None
        answer = _http(block)
        if answer is None:
            skipped.add("not an HTTP response")
            return None
        status, headers, body = answer
        if not 200 <= status < 300:
            skipped.add(f"status {status // 100}xx")
            return None
    else:
        status, headers, body = (
            None,
            {"content-type": fields.get("content-type", "")},
            block,
        )
    decoded = _decoded(body, headers)
    if isinstance(decoded, str):
        skipped.add(decoded)
        return None
    if not _is_html(headers, fields, decoded):
        skipped.add("not HTML")
        return None
    return WarcPage(
        url=url,
        status=status,
        headers=headers,
        body=decoded,
        record_id=fields.get("warc-record-id"),
        date=fields.get("warc-date"),
        digest=fields.get("warc-payload-digest"),
        truncated=fields.get("warc-truncated"),
    )


def _http(block: bytes) -> tuple[int, dict[str, str], bytes] | None:
    """The status, headers and body of an HTTP response as the wire had it."""
    end, gap = block.find(b"\r\n\r\n"), 4
    if end == -1:
        end, gap = block.find(b"\n\n"), 2
    head, body = (block, b"") if end == -1 else (block[:end], block[end + gap :])
    lines = head.split(b"\n")
    status_line = lines[0].strip().split()
    if len(status_line) < 2 or not status_line[0].startswith(b"HTTP/"):
        return None
    if not status_line[1].isdigit():
        return None
    headers: dict[str, str] = {}
    last = ""
    for raw in lines[1 : _MOST_HEADERS + 1]:
        # HTTP's headers are Latin-1 as the wire has them.
        text = raw.decode("latin-1").rstrip("\r")
        if text[:1] in (" ", "\t") and last:
            headers[last] = f"{headers[last]} {text.strip()}".strip()
            continue
        key, colon, value = text.partition(":")
        key = key.strip().lower()
        if colon and key:
            headers[key] = (
                f"{headers[key]}, {value.strip()}" if key in headers else value.strip()
            )
            last = key
    return int(status_line[1]), headers, body


def _decoded(body: bytes, headers: dict[str, str]) -> bytes | str:
    """``body`` with its transfer and content codings undone, or why it cannot be.

    A body an archive stored decoded while keeping the header that said it was
    coded is used as it is: a chunked reading that fails, or a gzip one, means
    the coding was already undone.
    """
    codings = [
        c.strip() for c in headers.get("transfer-encoding", "").lower().split(",")
    ]
    if "chunked" in codings:
        dechunked = _dechunked(body)
        body = body if dechunked is None else dechunked
    coding = headers.get("content-encoding", "").strip().lower()
    if coding in ("", "identity"):
        return body if len(body) <= MAX_RESPONSE_BYTES else "too large"
    if coding in ("gzip", "x-gzip", "deflate"):
        return _inflated(body, deflate=coding == "deflate")
    return f"compressed with {coding}"


def _dechunked(body: bytes) -> bytes | None:
    """A chunked body put back together, or None when it is not one."""
    out = bytearray()
    at = 0
    while True:
        line_end = body.find(b"\n", at)
        if line_end == -1:
            return None
        size_text = body[at:line_end].split(b";")[0].strip()
        try:
            size = int(size_text, 16)
        except ValueError:
            return None
        if size < 0:
            return None
        at = line_end + 1
        if size == 0:
            return bytes(out)
        if at + size > len(body) or len(out) + size > MAX_RESPONSE_BYTES:
            return None
        out += body[at : at + size]
        at += size
        at += (
            2
            if body[at : at + 2] == b"\r\n"
            else 1
            if body[at : at + 1] == b"\n"
            else 0
        )


def _inflated(body: bytes, deflate: bool) -> bytes | str:
    """A gzip or deflate body undone, held to the bound a fetched page is."""
    # gzip or zlib by its header, for "deflate" also raw deflate, as servers send.
    for wbits in (15, -15) if deflate else (47,):
        inflater = zlib.decompressobj(wbits)
        try:
            out = inflater.decompress(body, MAX_RESPONSE_BYTES + 1)
        except zlib.error:
            continue
        if len(out) > MAX_RESPONSE_BYTES:
            return "too large"
        return out
    # Stored decoded, with the header kept: the body is what it is.
    return body if len(body) <= MAX_RESPONSE_BYTES else "too large"


def _is_html(headers: dict[str, str], fields: dict[str, str], body: bytes) -> bool:
    """Whether the page is HTML: by its ``Content-Type``, else as the archive
    identified it, else by how it starts."""
    media = headers.get("content-type", "").split(";")[0].strip().lower()
    if media:
        return media in _HTML
    identified = (
        fields.get("warc-identified-payload-type", "").split(";")[0].strip().lower()
    )
    if identified:
        return identified in _HTML
    start = body[:1024].lstrip().lower()
    return start.startswith((b"<!doctype html", b"<html"))
