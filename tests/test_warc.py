"""Reading the pages a WARC file holds, as they were served."""

from __future__ import annotations

import gzip
import io
import json
import zlib

import pytest
from click.testing import CliRunner

from sluicer.cli import main
from sluicer.warc import Skipped, WarcError, extract_warc, read_warc

PAGE = b"<html><head><title>Brake pads</title></head><body>ok</body></html>"


def record(
    kind: str, block: bytes, url: str = "https://shop.example/p", **fields: str
) -> bytes:
    """One WARC record, as archives write it."""
    named = {
        "WARC-Type": kind,
        "WARC-Record-ID": "<urn:uuid:1>",
        "WARC-Date": "2026-09-23T10:00:00Z",
        "WARC-Target-URI": url,
        "Content-Type": "application/http; msgtype=response",
        **{name.replace("_", "-"): value for name, value in fields.items()},
        "Content-Length": str(len(block)),
    }
    head = "WARC/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in named.items())
    return head.encode() + b"\r\n" + block + b"\r\n\r\n"


def http(body: bytes = PAGE, status: str = "200 OK", **headers: str) -> bytes:
    """An HTTP response as the wire had it."""
    named = {
        "Content-Type": "text/html",
        **{k.replace("_", "-"): v for k, v in headers.items()},
    }
    head = f"HTTP/1.1 {status}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in named.items())
    return head.encode() + b"\r\n" + body


def warc(*records: bytes, tmp_path, name: str = "pages.warc", zipped: bool = False):
    path = tmp_path / name
    if zipped:
        # One gzip member per record, as archives write them.
        path.write_bytes(b"".join(gzip.compress(r) for r in records))
    else:
        path.write_bytes(b"".join(records))
    return path


def pages(path, skipped=None):
    return list(read_warc(path, skipped))


# -- which records are pages ---------------------------------------------------


def test_a_response_record_is_a_page_with_its_status_headers_and_provenance(tmp_path):
    path = warc(
        record("response", http(Link="</c>; rel=canonical")),
        tmp_path=tmp_path,
    )
    [page] = pages(path)
    assert page.url == "https://shop.example/p"
    assert page.status == 200
    assert page.headers == {"content-type": "text/html", "link": "</c>; rel=canonical"}
    assert page.body == PAGE
    assert (page.record_id, page.date, page.truncated) == (
        "<urn:uuid:1>",
        "2026-09-23T10:00:00Z",
        None,
    )


def test_gzip_one_member_per_record_or_one_for_all_reads_the_same(tmp_path):
    records = [
        record("response", http()),
        record("response", http(), url="https://shop.example/q"),
    ]
    per_record = warc(*records, tmp_path=tmp_path, name="a.warc.gz", zipped=True)
    whole = tmp_path / "b.warc.gz"
    whole.write_bytes(gzip.compress(b"".join(records)))
    assert (
        [p.url for p in pages(per_record)]
        == [p.url for p in pages(whole)]
        == [
            "https://shop.example/p",
            "https://shop.example/q",
        ]
    )


def test_a_resource_record_is_a_body_alone(tmp_path):
    path = warc(
        record("resource", PAGE, Content_Type="text/html; charset=utf-8"),
        tmp_path=tmp_path,
    )
    [page] = pages(path)
    assert page.status is None
    assert page.headers == {"content-type": "text/html; charset=utf-8"}
    assert page.body == PAGE


def test_records_that_are_not_pages_are_passed_over_uncounted(tmp_path):
    skipped = Skipped()
    path = warc(
        record(
            "warcinfo", b"software: test\r\n", Content_Type="application/warc-fields"
        ),
        record(
            "request",
            b"GET / HTTP/1.1\r\n\r\n",
            Content_Type="application/http; msgtype=request",
        ),
        record("metadata", b"via: x\r\n", Content_Type="application/warc-fields"),
        record("response", http()),
        tmp_path=tmp_path,
    )
    assert len(pages(path, skipped)) == 1
    assert not skipped


def test_what_is_left_out_is_counted_by_reason(tmp_path):
    skipped = Skipped()
    path = warc(
        record("revisit", http(b"")),
        record("response", http(b"\x89PNG", Content_Type="image/png")),
        record("response", http(b"gone", status="404 Not Found")),
        record("response", http(b"", status="301 Moved", Location="/x")),
        record("response", b"\x00dns", Content_Type="text/dns"),
        record("response", b"not http at all"),
        record("response", http(b"x", Content_Encoding="br")),
        record("revisit", http(b"")),
        tmp_path=tmp_path,
    )
    assert pages(path, skipped) == []
    assert skipped.reasons == {
        "revisit": 2,
        "not HTML": 1,
        "status 4xx": 1,
        "status 3xx": 1,
        "not HTTP": 1,
        "not an HTTP response": 1,
        "compressed with br": 1,
    }
    assert str(skipped).startswith("2 revisit, 1 not HTML")


def test_html_is_told_by_content_type_then_as_identified_then_by_its_start(tmp_path):
    bare = b"HTTP/1.1 200 OK\r\n\r\n"
    path = warc(
        record("response", http(Content_Type="application/xhtml+xml")),
        record(
            "response", bare + b"{}", WARC_Identified_Payload_Type="application/json"
        ),
        record("response", bare + b"x", WARC_Identified_Payload_Type="text/html"),
        record("response", bare + b"  <!DOCTYPE html><title>t</title>"),
        record("response", bare + b"plain words"),
        tmp_path=tmp_path,
    )
    skipped = Skipped()
    assert len(pages(path, skipped)) == 3
    assert skipped.reasons == {"not HTML": 2}


def test_a_target_uri_in_angle_brackets_is_read_without_them(tmp_path):
    path = warc(
        record("response", http(), url="<https://shop.example/p>"), tmp_path=tmp_path
    )
    assert pages(path)[0].url == "https://shop.example/p"


def test_folded_header_lines_are_joined(tmp_path):
    block = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
        b"Link: </a>;\r\n rel=canonical\r\nno colon here\r\n\r\n" + PAGE
    )
    folded = record("response", block).replace(
        b"WARC-Date: 2026-09-23T10:00:00Z\r\n",
        b"WARC-Date:\r\n 2026-09-23T10:00:00Z\r\nno colon here\r\n",
    )
    [page] = pages(warc(folded, tmp_path=tmp_path))
    assert page.headers["link"] == "</a>; rel=canonical"
    assert page.date == "2026-09-23T10:00:00Z"


def test_a_status_line_without_a_status_is_not_an_http_response(tmp_path):
    skipped = Skipped()
    path = warc(
        record("response", b"HTTP/1.1 OK\r\n\r\n" + PAGE),
        record("response", b"HTTP/1.1\r\n\r\n" + PAGE),
        tmp_path=tmp_path,
    )
    assert pages(path, skipped) == []
    assert skipped.reasons == {"not an HTTP response": 2}


def test_a_header_given_twice_is_joined_as_http_joins_it(tmp_path):
    block = (
        b"HTTP/1.1 200 OK\r\nLink: </a>; rel=canonical\r\nLink: </b>; rel=next\r\n\r\n"
        + PAGE
    )
    path = warc(record("response", block), tmp_path=tmp_path)
    assert pages(path)[0].headers["link"] == "</a>; rel=canonical, </b>; rel=next"


def test_a_head_with_bare_newlines_is_read(tmp_path):
    block = b"HTTP/1.0 200 OK\nContent-Type: text/html\n\n" + PAGE
    path = warc(record("response", block), tmp_path=tmp_path)
    assert pages(path)[0].body == PAGE


def test_a_truncated_record_says_so(tmp_path):
    path = warc(record("response", http(), WARC_Truncated="length"), tmp_path=tmp_path)
    assert pages(path)[0].truncated == "length"


# -- codings undone ------------------------------------------------------------


def test_a_chunked_body_is_put_back_together(tmp_path):
    chunked = (
        b"a;ext=1\r\n<html><hea\r\n"
        + b"%x\r\n" % (len(PAGE) - 10)
        + PAGE[10:]
        + b"\r\n0\r\n\r\n"
    )
    path = warc(
        record("response", http(chunked, Transfer_Encoding="chunked")),
        tmp_path=tmp_path,
    )
    assert pages(path)[0].body == PAGE


def test_a_body_stored_dechunked_with_the_header_kept_is_used_as_it_is(tmp_path):
    path = warc(
        record("response", http(PAGE, Transfer_Encoding="chunked")), tmp_path=tmp_path
    )
    assert pages(path)[0].body == PAGE


def test_chunks_that_run_past_the_body_are_not_a_chunked_body(tmp_path):
    lying = b"ffff\r\n" + PAGE
    path = warc(
        record("response", http(lying, Transfer_Encoding="chunked")), tmp_path=tmp_path
    )
    assert pages(path)[0].body == lying


def test_an_empty_chunked_body_is_empty(tmp_path):
    path = warc(
        record("response", http(b"0\r\n\r\n", Transfer_Encoding="chunked")),
        tmp_path=tmp_path,
    )
    [page] = pages(path)
    assert page.body == b""


def test_gzip_and_both_deflates_are_undone(tmp_path):
    raw_deflate = zlib.compressobj(wbits=-15)
    raw = raw_deflate.compress(PAGE) + raw_deflate.flush()
    path = warc(
        record("response", http(gzip.compress(PAGE), Content_Encoding="gzip")),
        record("response", http(zlib.compress(PAGE), Content_Encoding="deflate")),
        record("response", http(raw, Content_Encoding="deflate")),
        record("response", http(PAGE, Content_Encoding="gzip")),
        tmp_path=tmp_path,
    )
    assert [page.body for page in pages(path)] == [PAGE] * 4


def test_a_body_too_large_is_left_out_before_or_after_inflating(tmp_path, monkeypatch):
    monkeypatch.setattr("sluicer.warc.MAX_RESPONSE_BYTES", 1000)
    monkeypatch.setattr("sluicer.warc._LARGEST_BLOCK", 5000)
    skipped = Skipped()
    bomb = gzip.compress(b"<html>" + b" " * 100_000)
    path = warc(
        record("response", http(bomb, Content_Encoding="gzip")),
        record("response", http(b"<html>" + b"x" * 2000)),
        record("response", http(b"<html>" + b"x" * 6000)),
        record("response", http(b"y" * 2000, Content_Encoding="gzip")),
        record("response", http(b"z" * 2000, Content_Encoding="deflate")),
        record("response", http()),
        tmp_path=tmp_path,
    )
    assert [page.body for page in pages(path, skipped)] == [PAGE]
    assert skipped.reasons == {"too large": 5}


def test_a_chunked_body_past_the_bound_is_not_put_together(tmp_path, monkeypatch):
    monkeypatch.setattr("sluicer.warc.MAX_RESPONSE_BYTES", 10)
    chunked = b"20\r\n" + b"x" * 32 + b"\r\n0\r\n\r\n"
    skipped = Skipped()
    path = warc(
        record("response", http(chunked, Transfer_Encoding="chunked")),
        tmp_path=tmp_path,
    )
    assert pages(path, skipped) == []
    assert skipped.reasons == {"too large": 1}


def test_malformed_chunk_sizes_are_not_a_chunked_body(tmp_path):
    for body in (b"zz\r\n", b"-1\r\nx", b"no newline"):
        path = warc(
            record("response", http(body, Transfer_Encoding="chunked")),
            tmp_path=tmp_path,
        )
        assert pages(path)[0].body == body


# -- what a page's headers say, read -------------------------------------------


def test_each_page_is_read_with_the_headers_it_was_served_with(tmp_path):
    body = '<html><head><meta charset="utf-8"><title>Цена</title></head></html>'
    path = warc(
        record(
            "response",
            http(
                body.encode("windows-1251"),
                Content_Type="text/html; charset=windows-1251",
                Link="</p/canonical>; rel=canonical",
                X_Robots_Tag="noai",
            ),
        ),
        tmp_path=tmp_path,
    )
    [(_page, read)] = list(extract_warc(path))
    assert read.url == "https://shop.example/p"
    assert read.summary["title"].value == "Цена"
    assert read.links["canonical"] == "https://shop.example/p/canonical"
    assert read.rights["http"] == {"robots": ["noai"]}


def test_a_page_that_declares_nothing_is_still_given(tmp_path):
    path = warc(
        record("response", http(b"<html><body>hi</body></html>")), tmp_path=tmp_path
    )
    [(_page, read)] = list(extract_warc(path))
    assert read.records == []


def test_a_file_object_is_read_too():
    data = gzip.compress(record("response", http()))
    assert [p.url for p in read_warc(io.BytesIO(data))] == ["https://shop.example/p"]


# -- files that are not WARCs, or break off -------------------------------------


@pytest.mark.parametrize(
    ("data", "said"),
    [
        (b"<html>not an archive</html>", "it opens with"),
        (b"WARC/1.1\r\nWARC-Type: response\r\n\r\n", "no Content-Length"),
        (b"WARC/1.1\r\nContent-Length: -5\r\n\r\n", "negative"),
        (b"WARC/1.1\r\nContent-Length: 50\r\n\r\nshort", "breaks off inside a record"),
        (b"WARC/1.1\r\nWARC-Type: response\r\n", "breaks off inside a record's header"),
        (b"WARC/1.1\r\n" + b"X: y\r\n" * 600, "runs past"),
    ],
)
def test_a_file_that_is_not_a_warc_says_why(tmp_path, data, said):
    path = tmp_path / "bad.warc"
    path.write_bytes(data)
    with pytest.raises(WarcError, match=said):
        pages(path)


def test_a_corrupt_gzip_member_is_a_file_that_breaks_off(tmp_path):
    good = gzip.compress(record("response", http()))
    path = tmp_path / "cut.warc.gz"
    path.write_bytes(good + gzip.compress(record("response", http()))[:30])
    read = read_warc(path)
    assert next(read).status == 200
    with pytest.raises(WarcError):
        next(read)


def test_a_record_too_large_that_breaks_off_is_a_file_that_breaks_off(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("sluicer.warc._LARGEST_BLOCK", 10)
    path = tmp_path / "cut.warc"
    path.write_bytes(
        b"WARC/1.1\r\nWARC-Type: response\r\nContent-Length: 100\r\n\r\nshort"
    )
    with pytest.raises(WarcError, match="breaks off"):
        pages(path)


def test_stray_bytes_after_a_record_are_passed_over_to_the_next(tmp_path):
    """As in warcio's damaged sample: a Content-Length two bytes short."""
    skipped = Skipped()
    path = warc(
        record("response", http())[:-4] + b"\x00\x00\r\n\r\n",
        record("response", http(), url="https://shop.example/q"),
        tmp_path=tmp_path,
    )
    path.write_bytes(
        path.read_bytes().replace(b"\r\n\r\nWARC/1.1", b"\r\njunk\r\nWARC/1.1", 1)
    )
    assert [p.url for p in pages(path, skipped)] == [
        "https://shop.example/p",
        "https://shop.example/q",
    ]
    assert skipped.reasons == {"stray bytes between records": 1}


def test_stray_bytes_to_the_end_of_the_file_end_it(tmp_path):
    path = warc(record("response", http()), tmp_path=tmp_path)
    path.write_bytes(path.read_bytes() + b"trailing junk\r\n")
    assert len(pages(path)) == 1


def test_stray_bytes_that_never_end_are_a_broken_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sluicer.warc._LARGEST_BLOCK", 100)
    path = warc(record("response", http()), tmp_path=tmp_path)
    path.write_bytes(path.read_bytes() + b"junk\r\n" * 100)
    with pytest.raises(WarcError, match="no record follows"):
        pages(path)


def test_a_missing_file_is_an_os_error(tmp_path):
    with pytest.raises(OSError):
        pages(tmp_path / "absent.warc")


# -- sluicer warc --------------------------------------------------------------


def test_sluicer_warc_writes_one_line_per_page_and_counts_what_it_left_out(tmp_path):
    path = warc(
        record("response", http(Link="</c>; rel=canonical")),
        record("revisit", http(b"")),
        record("response", http(WARC_Truncated="length"), WARC_Truncated="length"),
        tmp_path=tmp_path,
        zipped=True,
        name="crawl.warc.gz",
    )
    result = CliRunner().invoke(main, ["warc", str(path)])
    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 2
    first = lines[0]
    assert list(first)[:3] == ["url", "warc", "summary"]
    assert first["warc"] == {
        "file": str(path),
        "record_id": "<urn:uuid:1>",
        "date": "2026-09-23T10:00:00Z",
        "digest": None,
        "status": 200,
    }
    assert first["links"]["canonical"] == "https://shop.example/c"
    assert first["summary"]["title"]["value"] == "Brake pads"
    assert lines[1]["warc"]["truncated"] == "length"
    assert "crawl.warc.gz: 2 pages; skipped 1 revisit." in result.stderr


def test_sluicer_warc_reads_several_files_and_stdin(tmp_path):
    one = warc(record("response", http()), tmp_path=tmp_path, name="one.warc")
    data = gzip.compress(record("response", http(), url="https://shop.example/q"))
    result = CliRunner().invoke(main, ["warc", str(one), "-"], input=data)
    assert result.exit_code == 0
    assert [json.loads(line)["url"] for line in result.stdout.splitlines()] == [
        "https://shop.example/p",
        "https://shop.example/q",
    ]
    assert json.loads(result.stdout.splitlines()[1])["warc"]["file"] == "-"
    assert "-: 1 pages." in result.stderr


def test_sluicer_warc_with_no_page_exits_as_nothing_found(tmp_path):
    path = warc(record("revisit", http(b"")), tmp_path=tmp_path)
    result = CliRunner().invoke(main, ["warc", str(path)])
    assert result.exit_code == 1
    assert "0 pages; skipped 1 revisit." in result.stderr


def test_sluicer_warc_says_where_a_broken_file_broke(tmp_path):
    path = tmp_path / "bad.warc"
    path.write_bytes(
        record("response", http()) + b"WARC/1.1\r\nContent-Length: 99\r\n\r\nx"
    )
    result = CliRunner().invoke(main, ["warc", str(path)])
    assert result.exit_code == 2
    assert "1 pages were read before it" in result.stderr
    assert len(result.stdout.splitlines()) == 1


def test_sluicer_warc_says_when_a_file_cannot_be_opened(tmp_path):
    result = CliRunner().invoke(main, ["warc", str(tmp_path / "absent.warc")])
    assert result.exit_code == 2


def test_sluicer_warc_needs_the_microformats_extra_to_read_them(tmp_path, monkeypatch):
    from sluicer.declared.microformats import MicroformatsExtraMissing

    def missing(*args, **kwargs):
        raise MicroformatsExtraMissing()

    monkeypatch.setattr("sluicer.warc.extract", missing)
    path = warc(record("response", http()), tmp_path=tmp_path)
    result = CliRunner().invoke(main, ["warc", str(path), "--microformats"])
    assert result.exit_code == 2
