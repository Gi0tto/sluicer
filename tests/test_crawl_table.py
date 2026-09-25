"""A crawl's pages and a map's addresses as rows: the flattening CSV writes."""

import csv
import io

from fake_site import FakeWeb, page
from sluicer.crawl import crawl
from sluicer.crawl.table import PAGE_COLUMNS, SITE_URL_COLUMNS, page_row, write_csv
from sluicer.summary import FIELDS

ROOT = "https://example.com"


def lines_of(pages):
    fake = FakeWeb(pages)
    return [
        p.to_json()
        for p in crawl(
            f"{ROOT}/", web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep
        )
    ]


def test_the_columns_are_the_page_s_then_every_summary_question_in_order():
    assert PAGE_COLUMNS[:4] == ("url", "ok", "depth", "found_on")
    assert PAGE_COLUMNS[-len(FIELDS) :] == tuple(f"summary.{name}" for name in FIELDS)
    assert len(set(PAGE_COLUMNS)) == len(PAGE_COLUMNS)
    assert SITE_URL_COLUMNS == ("url", "lastmod", "sitemap")


def test_a_page_s_row_is_its_line_flattened():
    [home, gone] = lines_of(
        {f"{ROOT}/": page("Home", "/gone"), f"{ROOT}/gone": ConnectionError("down")}
    )

    row = page_row(home)
    assert set(row) == set(PAGE_COLUMNS)
    assert row["url"] == f"{ROOT}/" and row["ok"] == "true" and row["depth"] == "0"
    assert row["found_on"] == "" and row["landed"] == f"{ROOT}/"
    assert row["status"] == "200" and row["rung"] == "http"
    assert row["climbs"] == "0" and row["retries"] == "0"
    assert row["error"] == row["message"] == ""
    assert row["sources"] == "jsonld" and row["types"] == "Product"
    assert row["records"] == "1" and row["links"] == "1"
    assert row["summary.title"] == "Home" and row["summary.price"] == ""

    failed = page_row(gone)
    assert failed["ok"] == "false" and failed["error"] == "fetch_failed"
    assert "down" in failed["message"] and failed["retries"] == "2"
    assert failed["status"] == failed["summary.title"] == failed["records"] == ""


def test_a_cell_a_spreadsheet_would_run_as_a_formula_is_written_as_text():
    """The pages are other people's: a title of =HYPERLINK(...) is theirs to
    write and not theirs to run in the reader's spreadsheet (OWASP's advice
    on CSV injection)."""
    [line] = lines_of({f"{ROOT}/": page('=HYPERLINK("https://evil.example")')})
    line["summary"]["price"] = {"value": "-3.50", "source": "jsonld", "key": "k"}
    line["summary"]["sku"] = {"value": "@sku", "source": "jsonld", "key": "k"}

    row = page_row(line)

    assert row["summary.title"] == '\'=HYPERLINK("https://evil.example")'
    assert row["summary.sku"] == "'@sku"
    assert row["summary.price"] == "-3.50"


def test_write_csv_writes_the_header_once_and_a_row_per_line():
    written = io.StringIO()
    lines = lines_of({f"{ROOT}/": page("Home", "/a"), f"{ROOT}/a": page("A, and B")})

    write = write_csv(written, PAGE_COLUMNS)
    for line in lines:
        write(page_row(line))

    rows = list(csv.DictReader(io.StringIO(written.getvalue())))
    assert [row["summary.title"] for row in rows] == ["Home", "A, and B"]
    assert written.getvalue().count("url,ok,depth") == 1
