"""``sluicer map``, ``crawl`` and ``batch``: what they print, write and exit with.

The commands build the real web; each test hands them a ``FakeWeb`` instead,
by wrapping the library call the command makes, so nothing opens a socket.
"""

import csv
import io
import json

import pytest
from click.testing import CliRunner

from fake_site import FakeWeb, page
from sluicer.cli import main

ROOT = "https://example.com"


def shop():
    return {
        f"{ROOT}/": page("Home", "/a", "/b"),
        f"{ROOT}/a": page("A", "/b"),
        f"{ROOT}/b": page("B"),
        f"{ROOT}/plain": "<html><body><p>"
        + "Nothing declared. " * 20
        + "</p></body></html>",
    }


@pytest.fixture
def fake(monkeypatch):
    """The commands' library calls, pointed at a fake web of ``shop()``."""
    import sluicer.crawl as library

    web = FakeWeb(shop())
    paced = {"web": None, "clock": web.clock, "sleep": web.clock.sleep}

    def wrap(real):
        def call(*args, **kwargs):
            return real(*args, **{**kwargs, **paced, "web": web.web()})

        return call

    monkeypatch.setattr("sluicer.cli.sites.crawl_site", wrap(library.crawl))
    monkeypatch.setattr("sluicer.cli.sites.extract_many", wrap(library.extract_many))
    monkeypatch.setattr("sluicer.cli.sites.map_site", wrap(library.map_site))
    from sluicer.crawl import templates

    monkeypatch.setattr(
        "sluicer.cli.sites.sitemap_pages", wrap(templates.sitemap_pages)
    )
    monkeypatch.setattr(
        "sluicer.cli.sites.shopify_products", wrap(templates.shopify_products)
    )
    return web


def invoke(*args, stdin=None):
    return CliRunner().invoke(main, list(args), input=stdin)


def lines(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# -- crawl -----------------------------------------------------------------------


def test_a_crawl_prints_one_line_per_page_and_says_how_it_went(fake):
    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 0, result.stderr
    assert [line["url"] for line in lines(result.stdout)] == [
        f"{ROOT}/",
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]
    assert f"    2  200 http  {ROOT}/a" in result.stderr
    assert "3 pages: 3 read." in result.stderr


def test_a_crawl_written_to_a_file_resumes_without_asking_again(fake, tmp_path):
    out = tmp_path / "pages.jsonl"

    first = invoke("crawl", f"{ROOT}/", "--max-pages", "2", "--out", str(out))
    asked = len(fake.requests)
    second = invoke("crawl", f"{ROOT}/", "--out", str(out), "--resume")

    assert first.exit_code == 0 and first.stdout == ""
    assert "the page budget left links unfollowed" in first.stderr
    assert second.exit_code == 0, second.stderr
    assert "Resuming after the 2 pages" in second.stderr
    assert "3 pages: 3 read." in second.stderr
    assert [r[0] for r in fake.requests[asked:]] == [f"{ROOT}/b"]
    assert [line["url"] for line in lines(out.read_text(encoding="utf-8"))] == [
        f"{ROOT}/",
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]


def test_a_file_that_holds_pages_is_not_written_over(fake, tmp_path):
    out = tmp_path / "pages.jsonl"
    out.write_text('{"url": "https://example.com/"}\n', encoding="utf-8")

    result = invoke("crawl", f"{ROOT}/", "--out", str(out))

    assert result.exit_code == 2
    assert "already holds pages" in result.stderr and "--resume" in result.stderr
    assert fake.requests == []


def test_resume_needs_a_file_to_resume(fake):
    result = invoke("crawl", f"{ROOT}/", "--resume")

    assert result.exit_code == 2
    assert "--resume needs --out" in result.stderr


def test_a_file_from_another_crawl_is_refused(fake, tmp_path):
    out = tmp_path / "pages.jsonl"
    invoke("crawl", f"{ROOT}/", "--max-pages", "1", "--out", str(out))

    result = invoke("crawl", f"{ROOT}/a", "--out", str(out), "--resume")

    assert result.exit_code == 2
    assert "cannot be resumed here" in result.stderr


def test_a_pattern_that_is_not_one_exits_two(fake):
    result = invoke("crawl", f"{ROOT}/", "--include", "(unclosed")

    assert result.exit_code == 2
    assert "not a regular expression" in result.stderr


def test_a_crawl_that_could_read_nothing_exits_two(fake):
    fake.pages[f"{ROOT}/robots.txt"] = "User-agent: *\nDisallow: /\n"

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 2
    assert "1 pages: 0 read, 1 failed (1 refused_by_robots)" in result.stderr
    assert lines(result.stdout)[0]["error"]["code"] == "refused_by_robots"


def test_a_crawl_whose_pages_declare_nothing_exits_one(fake):
    fake.pages[f"{ROOT}/plain"] = "<html><body></body></html>"

    result = invoke("crawl", f"{ROOT}/plain")

    assert result.exit_code == 1


def test_ctrl_c_keeps_what_was_written_and_says_how_to_go_on(fake, tmp_path):
    fake.pages[f"{ROOT}/a"] = KeyboardInterrupt()
    out = tmp_path / "pages.jsonl"

    result = invoke("crawl", f"{ROOT}/", "--out", str(out))

    assert result.exit_code == 130
    assert "--resume continues" in result.stderr
    assert [line["url"] for line in lines(out.read_text(encoding="utf-8"))] == [
        f"{ROOT}/"
    ]


def test_a_file_that_cannot_be_written_exits_two(fake, tmp_path):
    result = invoke("crawl", f"{ROOT}/", "--out", str(tmp_path / "no" / "such.jsonl"))

    assert result.exit_code == 2
    assert "Could not write" in result.stderr


def test_a_crawl_without_an_extra_it_needs_says_how_to_install_it(monkeypatch):
    from sluicer.fetch.rungs import FetchExtraMissing

    def missing(*args, **kwargs):
        raise FetchExtraMissing(
            "Loading a page in a browser needs playwright, which is not installed. "
            'Install it with: uv pip install "sluicer[browser]"'
        )

    monkeypatch.setattr("sluicer.cli.sites.crawl_site", missing)

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 2
    assert "sluicer[browser]" in result.stderr


def test_a_missing_extra_found_mid_crawl_says_so_too(monkeypatch):
    from sluicer.crawl.pages import Crawl
    from sluicer.fetch.rungs import FetchExtraMissing

    def pages(run):
        raise FetchExtraMissing("Loading a page in a browser needs playwright")
        yield

    monkeypatch.setattr("sluicer.cli.sites.crawl_site", lambda *a, **k: Crawl(pages))

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 2
    assert "needs playwright" in result.stderr


def test_a_page_asked_again_says_so_on_stderr(fake):
    fake.pages[f"{ROOT}/a"] = [ConnectionError("reset"), fake.pages[f"{ROOT}/a"]]

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 0, result.stderr
    assert f"    2  200 http, asked 2 times  {ROOT}/a" in result.stderr
    assert lines(result.stdout)[1]["retries"][0]["after"] == 2.0


def test_retries_zero_asks_every_page_once(fake):
    fake.pages[f"{ROOT}/a"] = ConnectionError("reset")

    result = invoke("crawl", f"{ROOT}/", "--retries", "0")

    assert f"    2  fetch_failed  {ROOT}/a" in result.stderr
    assert [r[0] for r in fake.requests].count(f"{ROOT}/a") == 1


@pytest.mark.parametrize("command", ["crawl", "batch"])
def test_jobs_is_how_many_sites_are_asked_at_once(monkeypatch, command):
    asked = []

    def record(*args, **kwargs):
        asked.append(kwargs)
        raise ValueError("stop here")

    name = "crawl_site" if command == "crawl" else "extract_many"
    monkeypatch.setattr(f"sluicer.cli.sites.{name}", record)
    source = f"{ROOT}/" if command == "crawl" else "-"

    invoke(command, source, "--jobs", "7", stdin=f"{ROOT}/a\n")
    invoke(command, source, stdin=f"{ROOT}/a\n")

    assert [one["concurrency"] for one in asked] == [7, 4]
    assert invoke(command, source, "--jobs", "0", stdin="x\n").exit_code == 2


# -- batch -----------------------------------------------------------------------


def test_a_batch_reads_its_list_in_order_and_answers_every_line(fake, tmp_path):
    listed = tmp_path / "urls.txt"
    listed.write_text(
        f"# products\n{ROOT}/b\n\n  {ROOT}/a  \nnot a url\n", encoding="utf-8"
    )

    result = invoke("batch", str(listed))

    assert result.exit_code == 0, result.stderr
    found = lines(result.stdout)
    assert [line["url"] for line in found] == [f"{ROOT}/b", f"{ROOT}/a", "not a url"]
    assert found[2]["error"]["code"] == "bad_input"
    assert "3 pages: 2 read, 1 failed (1 bad_input)" in result.stderr


def test_a_batch_reads_standard_input_and_resumes_from_its_file(fake, tmp_path):
    out = tmp_path / "pages.jsonl"

    invoke("batch", "-", "--out", str(out), stdin=f"{ROOT}/a\n")
    result = invoke(
        "batch", "-", "--out", str(out), "--resume", stdin=f"{ROOT}/a\n{ROOT}/b\n"
    )

    assert result.exit_code == 0, result.stderr
    assert [line["url"] for line in lines(out.read_text(encoding="utf-8"))] == [
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]


def test_a_batch_with_nothing_to_read_exits_two(fake, tmp_path):
    empty = tmp_path / "urls.txt"
    empty.write_text("# nothing yet\n\n", encoding="utf-8")

    assert invoke("batch", str(empty)).exit_code == 2
    assert invoke("batch", str(tmp_path / "missing.txt")).exit_code == 2


# -- map ---------------------------------------------------------------------------

SITEMAP = (
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://example.com/a</loc><lastmod>2026-09-01</lastmod></url>"
    "<url><loc>https://example.com/b</loc></url></urlset>"
)


def test_map_prints_the_sites_addresses_and_where_they_came_from(fake):
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("map", f"{ROOT}/")

    assert result.exit_code == 0, result.stderr
    mapped = json.loads(result.stdout)
    assert mapped["source"] == "sitemaps"
    assert mapped["urls"][0] == {
        "url": f"{ROOT}/a",
        "lastmod": "2026-09-01",
        "sitemap": f"{ROOT}/sitemap.xml",
    }
    assert f"sitemap {ROOT}/sitemap.xml: 2 entries (urlset)" in result.stderr
    assert "Found 2 addresses in its sitemaps." in result.stderr


def test_map_plain_is_one_address_a_line_for_batch(fake):
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("map", f"{ROOT}/", "--plain", "--limit", "1")

    assert result.stdout == f"{ROOT}/a\n"
    assert "cut short by a bound" in result.stderr


def test_map_stops_asking_for_sitemaps_once_its_time_budget_is_spent(fake):
    """A map read up to fifty sitemaps, each after the site's delay of up to a
    minute, with nothing on the command line to stop it sooner."""
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("map", f"{ROOT}/", "--time-budget", "0")

    assert result.exit_code == 0, result.stderr
    assert "cut short by a bound" in result.stderr
    assert f"{ROOT}/sitemap.xml" not in [url for url, _, _ in fake.requests]


def test_map_without_a_sitemap_falls_back_and_says_so(fake):
    result = invoke("map", f"{ROOT}/")

    assert result.exit_code == 0
    assert "in the start page's links" in result.stderr
    assert "it answered 404" in result.stderr


def test_map_cut_by_its_limit_in_the_start_pages_links_says_so(fake):
    result = invoke("map", f"{ROOT}/", "--limit", "1")

    assert result.exit_code == 0, result.stderr
    mapped = json.loads(result.stdout)
    assert mapped["source"] == "links" and len(mapped["urls"]) == 1
    assert mapped["truncated"] is True
    assert "cut short by a bound" in result.stderr


def test_map_of_a_site_that_lists_nothing_exits_one(fake):
    result = invoke("map", f"{ROOT}/b")

    assert result.exit_code == 1


def test_map_of_a_site_that_cannot_be_read_exits_two(fake):
    fake.pages[f"{ROOT}/robots.txt"] = (503, "busy", {})

    result = invoke("map", f"{ROOT}/")

    assert result.exit_code == 2
    assert "503" in result.stderr


def test_a_batch_without_an_extra_it_needs_says_how_to_install_it(monkeypatch):
    from sluicer.fetch.rungs import FetchExtraMissing

    def missing(*args, **kwargs):
        raise FetchExtraMissing('Install it with: uv pip install "sluicer[browser]"')

    monkeypatch.setattr("sluicer.cli.sites.extract_many", missing)

    result = invoke("batch", "-", stdin=f"{ROOT}/a\n")

    assert result.exit_code == 2
    assert "sluicer[browser]" in result.stderr


# -- a table, and a bar --------------------------------------------------------------


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.parametrize("command", ["crawl", "batch"])
def test_format_csv_is_a_row_per_page_with_its_summary_flattened(fake, command):
    source = f"{ROOT}/" if command == "crawl" else "-"

    result = invoke(command, source, "--format", "csv", stdin=f"{ROOT}/\n{ROOT}/a\n")

    assert result.exit_code == 0, result.stderr
    from sluicer.crawl.table import PAGE_COLUMNS

    assert result.stdout.splitlines()[0] == ",".join(PAGE_COLUMNS)
    got = rows(result.stdout)
    assert [row["url"] for row in got][:2] == [f"{ROOT}/", f"{ROOT}/a"]
    assert got[0]["summary.title"] == "Home" and got[0]["types"] == "Product"
    assert "pages:" in result.stderr


def test_format_csv_to_a_file_writes_the_table_there(fake, tmp_path):
    out = tmp_path / "pages.csv"

    result = invoke("crawl", f"{ROOT}/", "--format", "csv", "-o", str(out))

    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert [row["url"] for row in rows(out.read_text(encoding="utf-8"))] == [
        f"{ROOT}/",
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]
    assert "3 pages: 3 read." in result.stderr


def test_a_table_cannot_be_resumed(fake, tmp_path):
    out = tmp_path / "pages.csv"

    result = invoke("crawl", f"{ROOT}/", "--format", "csv", "-o", str(out), "--resume")

    assert result.exit_code == 2
    assert "--resume reads JSON Lines" in result.stderr
    assert fake.requests == []


def test_map_as_csv_is_a_row_per_address(fake):
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("map", f"{ROOT}/", "--format", "csv")

    assert result.exit_code == 0, result.stderr
    assert rows(result.stdout) == [
        {"url": f"{ROOT}/a", "lastmod": "2026-09-01", "sitemap": f"{ROOT}/sitemap.xml"},
        {"url": f"{ROOT}/b", "lastmod": "", "sitemap": f"{ROOT}/sitemap.xml"},
    ]
    assert invoke("map", f"{ROOT}/", "--format", "csv", "--plain").exit_code == 2


def test_a_terminal_sees_a_bar_and_not_a_line_per_page(fake, monkeypatch):
    monkeypatch.setattr("sluicer.cli.sites._stderr_is_a_terminal", lambda: True)

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 0, result.stderr
    assert "200 http" not in result.stderr
    assert "Crawling" in result.stderr
    assert "3 pages: 3 read." in result.stderr
    assert len(lines(result.stdout)) == 3


def test_what_is_not_a_terminal_sees_no_bar(fake):
    result = invoke("crawl", f"{ROOT}/")

    assert "Crawling" not in result.stderr
    assert "\r" not in result.stderr


# -- templates -------------------------------------------------------------------


def test_a_sitemap_template_reads_what_the_sitemaps_list(fake):
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("crawl", f"{ROOT}/", "--template", "sitemap")

    assert result.exit_code == 0, result.stderr
    assert [line["url"] for line in lines(result.stdout)] == [f"{ROOT}/a", f"{ROOT}/b"]


def test_a_sitemap_template_on_a_site_without_one_says_what_it_read_instead(fake):
    """It read the start page's links and said only "the page budget left
    links unfollowed", so the pages looked like the ones the site lists."""
    result = invoke("crawl", f"{ROOT}/", "--template", "sitemap")

    assert result.exit_code == 0, result.stderr
    assert [line["url"] for line in lines(result.stdout)] == [f"{ROOT}/a", f"{ROOT}/b"]
    said = result.stderr.splitlines()
    assert said[0] == (
        "Note: no sitemap listed an address on the site, so the start page's "
        "links are read instead."
    )
    assert said[-1].endswith(
        "; no sitemap listed an address on the site, so the start page's links "
        "are read instead."
    )


def test_a_sitemap_template_that_read_a_sitemap_has_no_such_note(fake):
    fake.pages[f"{ROOT}/sitemap.xml"] = SITEMAP

    result = invoke("crawl", f"{ROOT}/", "--template", "sitemap")

    assert "Note:" not in result.stderr
    assert "start page's links" not in result.stderr


def test_a_crawl_stopped_by_its_depth_says_so_in_its_last_line(fake):
    result = invoke("crawl", f"{ROOT}/", "--max-depth", "0")

    assert result.exit_code == 0, result.stderr
    assert result.stderr.splitlines()[-1] == (
        "1 pages: 1 read; 2 links deeper than max_depth 0 were not followed."
    )


def test_a_shopify_template_writes_a_product_a_line(fake):
    import json as j

    products = [
        {"title": "Pad", "handle": "pad", "variants": [{"price": "9.00"}]},
        {"title": "Disc", "handle": "disc", "variants": [{"price": "19.00"}]},
    ]
    fake.pages[f"{ROOT}/products.json?limit=250&page=1"] = j.dumps(
        {"products": products}
    )

    result = invoke("crawl", f"{ROOT}/", "--template", "shopify", "--format", "csv")

    assert result.exit_code == 0, result.stderr
    got = rows(result.stdout)
    assert [row["url"] for row in got] == [
        f"{ROOT}/products/pad",
        f"{ROOT}/products/disc",
    ]
    assert [row["summary.price"] for row in got] == ["9.00", "19.00"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--template", "sitemap", "--max-depth", "1"],
        ["--template", "sitemap", "--any-site"],
        ["--template", "shopify", "--include", "x"],
        ["--template", "shopify", "--induce"],
        ["--template", "shopify", "--respect", "tdm"],
    ],
)
def test_an_option_a_template_does_not_use_is_refused_not_ignored(fake, extra):
    result = invoke("crawl", f"{ROOT}/", *extra)

    assert result.exit_code == 2
    assert "--template" in result.stderr
    assert fake.requests == []


def test_a_site_the_sitemap_template_cannot_map_exits_two(fake):
    fake.pages[f"{ROOT}/robots.txt"] = (503, "busy", {})

    result = invoke("crawl", f"{ROOT}/", "--template", "sitemap", "--retries", "0")

    assert result.exit_code == 2
    assert "503" in result.stderr


# -- a page the site answered with its error -----------------------------------


@pytest.mark.parametrize("status", [404, 503])
@pytest.mark.parametrize("command", ["crawl", "batch"])
def test_an_error_page_is_a_failed_line_and_exits_two(fake, command, status):
    """Measured on 0.9.0: a crawl of a 404 said "ok": true, "1 pages: 1
    read." and exit 0, with "404 Not Found" as the page's title; a batch of a
    503 the same after its retries."""
    fake.pages[f"{ROOT}/gone"] = (status, page(f"{status} Not Found"), {})
    args = [f"{ROOT}/gone"] if command == "crawl" else ["-"]
    stdin = None if command == "crawl" else f"{ROOT}/gone\n"

    result = invoke(command, *args, "--retries", "0", stdin=stdin)

    assert result.exit_code == 2, result.stderr
    [line] = lines(result.stdout)
    assert line["ok"] is False
    assert line["error"]["code"] == "fetch_failed"
    assert f"answered status {status}" in line["error"]["message"]
    assert line["error"]["retryable"] is (status == 503)
    assert "summary" not in line
