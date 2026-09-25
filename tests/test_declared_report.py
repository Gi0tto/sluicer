"""The state of declared data counts what it says it counts, the same every time.

``bench/declared_report.py`` reads Common Crawl's WARC files; these build
small ones from the fixtures and pages written here, where every count is
known, and check the tally, the rule that picks the sample, the intervals and
the report written from the counts. The harness is not in the sdist: without
it, this skips.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench"
if not (BENCH / "declared_report.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("mf2py")
sys.path.insert(0, str(BENCH))

import declared_report as report  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def record(kind: str, block: bytes, url: str, **fields: str) -> bytes:
    """One WARC record, as Common Crawl writes it."""
    named = {
        "WARC-Type": kind,
        "WARC-Record-ID": "<urn:uuid:1>",
        "WARC-Date": "2026-09-10T10:00:00Z",
        "WARC-Target-URI": url,
        "Content-Type": "application/http; msgtype=response",
        **{name.replace("_", "-"): value for name, value in fields.items()},
        "Content-Length": str(len(block)),
    }
    head = "WARC/1.0\r\n" + "".join(f"{k}: {v}\r\n" for k, v in named.items())
    return head.encode() + b"\r\n" + block + b"\r\n\r\n"


def http(body: bytes, status: str = "200 OK", **headers: str) -> bytes:
    named = {
        "Content-Type": "text/html; charset=utf-8",
        **{k.replace("_", "-"): v for k, v in headers.items()},
    }
    head = f"HTTP/1.1 {status}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in named.items())
    return head.encode() + b"\r\n" + body


# A shop page that says a great deal, some of it twice and differently: a
# price of 41.90 in JSON-LD and 39.90 in OpenGraph, a GTIN whose check digit
# is wrong (4006381333931 is right), a JSON-LD block with a trailing comma, and
# every kind of link and right the report counts.
SHOP = b"""<!doctype html><html><head><title>Pads | Shop</title>
<link rel="canonical" href="https://shop.example/p">
<link rel="alternate" hreflang="de" href="https://shop.example/de/p">
<link rel="alternate" hreflang="x-default" href="https://shop.example/p">
<meta name="robots" content="noindex, NoFollow">
<meta name="googlebot" content="noarchive">
<meta name="tdm-reservation" content="1">
<meta property="og:title" content="Pads">
<meta property="og:price:amount" content="39.90">
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Pads",
 "gtin13": "4006381333932",
 "offers": {"@type": "Offer", "price": "41.90", "priceCurrency": "EUR"},}
</script>
</head><body></body></html>"""

# A story whose blocks are each broken another way: one valid, one with a raw
# newline inside a string, one that no reader recovers. Its date is written in
# numbers only, which is never read, since 03/04/2025 is two dates.
STORY = (
    b"""<!doctype html><html><head><title>Rain</title>
<link rel="canonical" href="https://news.example/elsewhere">
<meta property="og:title" content="Rain all week">
<script type="application/ld+json">{"@type": "NewsArticle", "headline": "Rain",
 "datePublished": "03/04/2025",
 "author": {"@type": "Person", "name": "Ann"}}</script>
<script type="application/ld+json">{"@type": "WebPage", "name": "Line"""
    + b"\n"
    + b"""break"}</script>
<script type="application/ld+json">{"@type": "Thing", "name": </script>
<script type="application/ld+json">   </script>
</head><body></body></html>"""
)

EMPTY = b"<!doctype html><html><head></head><body><p>Nothing.</p></body></html>"


def sample(tmp_path: Path, name: str = "sample.warc.gz") -> Path:
    """A WARC holding the pages above, the fixture in three vocabularies, and
    every kind of record the report leaves out."""
    records = [
        record("warcinfo", b"software: test\r\n", "",
               Content_Type="application/warc-fields"),
        record("request", b"GET / HTTP/1.1\r\n\r\n", "https://shop.example/p",
               Content_Type="application/http; msgtype=request"),
        record("response", http(SHOP, X_Robots_Tag="noai, noimageai"),
               "https://shop.example/p"),
        record("response", http(STORY), "https://news.example/rain",
               WARC_Truncated="length"),
        record("response", http((FIXTURES / "product_all_three.html").read_bytes()),
               "https://parts.example/pads"),
        record("response", http(EMPTY), "http://192.0.2.1/"),
        record("response", http(b"gone", status="404 Not Found"),
               "https://shop.example/gone"),
        record("response", http(b"\x89PNG", Content_Type="image/png"),
               "https://shop.example/a.png"),
        record("response", http(EMPTY, status="206 Partial Content"),
               "https://shop.example/part"),
        record("revisit", b"", "https://shop.example/p"),
    ]  # fmt: skip
    path = tmp_path / name
    path.write_bytes(b"".join(gzip.compress(r) for r in records))
    return path


@pytest.fixture
def counts(tmp_path):
    return report.count_file(sample(tmp_path)).counts()


# -- the sample ------------------------------------------------------------------


def test_the_sample_is_the_middle_of_each_quarter_of_the_listing():
    lines = [f"f{n}" for n in range(100_000)]
    assert report.picked(lines) == ["f12500", "f37500", "f62500", "f87500"]
    assert report.picked([str(n) for n in range(8)]) == ["1", "3", "5", "7"]


# -- the intervals ---------------------------------------------------------------


def test_wilson_intervals_are_the_published_ones():
    low, high = report.wilson(5, 10)
    assert (round(low, 4), round(high, 4)) == (0.2366, 0.7634)
    low, high = report.wilson(0, 10)
    assert low == 0.0 and round(high, 4) == 0.2775
    low, high = report.wilson(10, 10)
    assert round(low, 4) == 0.7225 and high == 1.0
    assert report.wilson(0, 0) is None


# -- what a page is --------------------------------------------------------------


def test_only_html_answered_200_is_a_page_and_the_rest_is_counted_by_reason(counts):
    assert counts["pages"] == 4
    assert counts["left_out"] == {
        "status 4xx": 1,
        "not HTML": 1,
        "status 2xx but not 200": 1,
        "revisit": 1,
    }
    assert counts["truncated"] == 1
    assert counts["hosts"] == 4
    assert counts["top_level_domains"] == {"example": 3, "(an address)": 1}
    assert counts["failed"] == {}


# -- what the pages declare ------------------------------------------------------


def test_vocabularies_are_counted_by_page_and_by_host(counts):
    assert counts["vocabularies"]["pages"] == {
        "jsonld": 3,
        "microdata": 1,
        "opengraph": 3,
    }
    assert counts["vocabularies"]["hosts"] == {
        "jsonld": 3,
        "microdata": 1,
        "opengraph": 3,
    }
    assert counts["any"] == {"about_things": 3, "anything": 3, "nothing": 1}
    assert counts["combinations"] == {
        "jsonld + opengraph": 2,
        "jsonld + microdata + opengraph": 1,
        "(nothing)": 1,
    }


def test_types_are_counted_by_page_and_json_ld_nodes_one_by_one(counts):
    assert counts["types"]["pages"] == {
        "Product": 2,
        "NewsArticle": 1,
        "WebPage": 1,
    }
    # Nested nodes too, as written: the Offer and the Person; the lost block's
    # Thing is not read.
    assert counts["jsonld_nodes"] == {
        "typed": 6,
        "classes": {
            "Product": 2,
            "NewsArticle": 1,
            "Offer": 1,
            "Person": 1,
            "WebPage": 1,
        },
    }


def test_a_record_holding_fields_from_two_vocabularies_is_a_fold(counts):
    assert counts["merging"] == {
        "pages_with_things": 3,
        "several_vocabularies": 1,
        "folded": 1,
        "folded_by": {"jsonld + microdata": 1},
    }


def test_conflicts_are_counted_per_question_over_the_pages_it_is_answered_on(counts):
    conflicts = counts["conflicts"]
    assert conflicts["answered"]["price"] == 1
    assert conflicts["answered"]["title"] == 3
    assert conflicts["conflicting"] == {"price": 1}
    assert conflicts["between"] == {"price": {"jsonld / opengraph": 1}}
    assert conflicts["pages_with_any"] == 1


def test_titles_declared_twice_and_differently_are_counted_apart(counts):
    # The shop's "Pads | Shop" holds "Pads"; the story's "Rain all week" holds
    # "Rain"; the fixture's og:title holds its <title>. None differs beyond
    # one holding the other.
    assert counts["titles"] == {
        "declared_twice": 3,
        "differ": 3,
        "differ_beyond_containment": 0,
    }


def test_json_ld_blocks_are_counted_valid_mended_or_lost(counts):
    assert counts["jsonld_blocks"] == {
        "pages": 3,
        "blocks": 5,
        "valid": 2,
        "control_characters": 1,
        "recovered": 1,
        "lost": 1,
        "pages_with_invalid": 2,
        "pages_losing_one": 1,
    }


def test_normalisation_is_counted_per_question_with_the_shapes_it_could_not_read(
    counts,
):
    normalised = counts["normalised"]
    assert normalised["answered"]["published"] == 1
    assert normalised["read"].get("published", 0) == 0
    assert normalised["answered"]["price"] == normalised["read"]["price"] == 1
    assert normalised["answered"]["currency"] == normalised["read"]["currency"] == 1
    assert normalised["unread_shapes"]["date"] == {"99/99/9999": 1}
    assert counts["gtin"] == {
        "answered": 1,
        "not_a_gtin_shape": 0,
        "wrong_check_digit": 1,
        "valid": 0,
    }


def test_canonicals_and_alternates_are_counted(counts):
    assert counts["links"] == {
        "canonical": 2,
        "canonical_self": 1,
        "canonical_elsewhere": 1,
        "canonical_conflict": 0,
        "hreflang": 1,
        "x_default": 1,
    }


def test_rights_are_counted_from_the_page_and_its_headers(counts):
    rights = counts["rights"]
    assert rights["robots_meta"] == 1
    assert rights["robots_directives"] == {"noindex": 1, "nofollow": 1}
    assert rights["crawler_named"] == {"googlebot": 1}
    assert rights["x_robots_tag"] == 1
    assert rights["x_robots_directives"] == {"noai": 1, "noimageai": 1}
    assert rights["tdm_reservation"] == {"1": 1}
    assert rights["tdm_policy"] == 0
    assert rights["http_tdm_reservation"] == {}
    assert rights["license"] == 0


# -- the same every time ---------------------------------------------------------


def test_counts_are_the_same_on_every_run_and_in_any_order_of_files(tmp_path):
    one = report.count_file(sample(tmp_path, "a.warc.gz"))
    two = report.count_file(sample(tmp_path, "b.warc.gz"))
    both = report.Tally.combined([one, two]).counts()
    again = report.Tally.combined([two, one]).counts()
    assert json.dumps(both, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert both["pages"] == 8
    # A host met in both files is one host.
    assert both["hosts"] == 4
    assert both["vocabularies"]["hosts"]["jsonld"] == 3


def test_ties_are_broken_by_name_not_by_the_order_pages_came_in():
    assert report.top({"b": 2, "a": 2, "c": 5}, 2) == {"c": 5, "a": 2}


def test_a_page_that_breaks_the_reader_is_counted_not_dropped(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RecursionError("too deep")

    monkeypatch.setattr(report, "_extract_document", broken)
    counts = report.count_file(sample(tmp_path)).counts()
    assert counts["failed"] == {"RecursionError": 4}
    assert counts["pages"] == 0


# -- the report ------------------------------------------------------------------


def test_the_report_is_written_from_the_counts_alone(counts):
    manifest = {
        "crawl": "CC-MAIN-2026-39",
        "listing": {"path": "x/warc.paths.gz", "lines": 8, "sha256": "0" * 64},
        "rule": "r",
        "files": [{"index": 1, "path": "x/a.warc.gz", "bytes": 10, "sha256": "1" * 64}],
    }
    counts["sluicer"] = {"src": "abc1234", "version": "0.7.1", "lxml": "6.1.3",
                         "libxml2": "2.14.6", "mf2py": "2.0.2"}  # fmt: skip
    written = report.render(counts, manifest)
    assert written == report.render(counts, manifest)
    assert "CC-MAIN-2026-39" in written and "abc1234" in written
    # 3 of 4 pages declare JSON-LD: 75.0%, with its interval.
    low, high = report.wilson(3, 4)
    assert f"75.0% ({100 * low:.1f}-{100 * high:.1f})" in row(written, "JSON-LD")
    counts["vocabularies"]["pages"]["jsonld"] = 1
    assert "25.0%" in row(report.render(counts, manifest), "JSON-LD")


def row(markdown: str, name: str) -> str:
    """The first table row of ``markdown`` that opens with ``name``."""
    return next(
        line for line in markdown.splitlines() if line.startswith(f"| {name} |")
    )


def test_the_published_report_is_the_one_the_committed_counts_write():
    if not (report.COUNTS.exists() and report.REPORT.exists()):
        pytest.skip("no counts committed yet")
    counts = json.loads(report.COUNTS.read_text(encoding="utf-8"))
    manifest = json.loads(report.MANIFEST.read_text(encoding="utf-8"))
    assert report.REPORT.read_text(encoding="utf-8") == report.render(counts, manifest)
