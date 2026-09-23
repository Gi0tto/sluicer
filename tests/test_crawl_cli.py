"""``sluicer map``, ``crawl`` and ``batch``: what they print, write and exit with.

The commands build the real web; each test hands them a ``FakeWeb`` instead,
by wrapping the library call the command makes, so nothing opens a socket.
"""

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

    monkeypatch.setattr("sluicer.cli.crawl_site", wrap(library.crawl))
    monkeypatch.setattr("sluicer.cli.extract_many", wrap(library.extract_many))
    monkeypatch.setattr("sluicer.cli.map_site", wrap(library.map_site))
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
    assert [line["url"] for line in lines(out.read_text())] == [
        f"{ROOT}/",
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]


def test_a_file_that_holds_pages_is_not_written_over(fake, tmp_path):
    out = tmp_path / "pages.jsonl"
    out.write_text('{"url": "https://example.com/"}\n')

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
    assert [line["url"] for line in lines(out.read_text())] == [f"{ROOT}/"]


def test_a_file_that_cannot_be_written_exits_two(fake, tmp_path):
    result = invoke("crawl", f"{ROOT}/", "--out", str(tmp_path / "no" / "such.jsonl"))

    assert result.exit_code == 2
    assert "Could not write" in result.stderr


def test_a_crawl_without_the_fetch_extra_says_how_to_install_it(monkeypatch):
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    def missing(*args, **kwargs):
        raise FetchExtraMissing(
            "Fetching a URL needs scrapling, which is not installed. "
            "Install it with: uv pip install 'sluicer[fetch]'"
        )

    monkeypatch.setattr("sluicer.cli.crawl_site", missing)

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 2
    assert "sluicer[fetch]" in result.stderr


def test_a_missing_extra_found_mid_crawl_says_so_too(monkeypatch):
    from sluicer.crawl.pages import Crawl
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    def pages(run):
        raise FetchExtraMissing("Reading a site's robots.txt needs protego")
        yield

    monkeypatch.setattr("sluicer.cli.crawl_site", lambda *a, **k: Crawl(pages))

    result = invoke("crawl", f"{ROOT}/")

    assert result.exit_code == 2
    assert "needs protego" in result.stderr


# -- batch -----------------------------------------------------------------------


def test_a_batch_reads_its_list_in_order_and_answers_every_line(fake, tmp_path):
    listed = tmp_path / "urls.txt"
    listed.write_text(f"# products\n{ROOT}/b\n\n  {ROOT}/a  \nnot a url\n")

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
    assert [line["url"] for line in lines(out.read_text())] == [
        f"{ROOT}/a",
        f"{ROOT}/b",
    ]


def test_a_batch_with_nothing_to_read_exits_two(fake, tmp_path):
    empty = tmp_path / "urls.txt"
    empty.write_text("# nothing yet\n\n")

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


def test_map_without_a_sitemap_falls_back_and_says_so(fake):
    result = invoke("map", f"{ROOT}/")

    assert result.exit_code == 0
    assert "in the start page's links" in result.stderr
    assert "it answered 404" in result.stderr


def test_map_of_a_site_that_lists_nothing_exits_one(fake):
    result = invoke("map", f"{ROOT}/b")

    assert result.exit_code == 1


def test_map_of_a_site_that_cannot_be_read_exits_two(fake):
    fake.pages[f"{ROOT}/robots.txt"] = (503, "busy", {})

    result = invoke("map", f"{ROOT}/")

    assert result.exit_code == 2
    assert "503" in result.stderr


def test_a_batch_without_the_fetch_extra_says_how_to_install_it(monkeypatch):
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    def missing(*args, **kwargs):
        raise FetchExtraMissing("Install it with: uv pip install 'sluicer[fetch]'")

    monkeypatch.setattr("sluicer.cli.extract_many", missing)

    result = invoke("batch", "-", stdin=f"{ROOT}/a\n")

    assert result.exit_code == 2
    assert "sluicer[fetch]" in result.stderr
