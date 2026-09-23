"""Reading a page as the Wayback Machine captured it."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import sluicer
from sluicer.cli import main
from sluicer.fetch.archive import (
    NotArchived,
    _within_archive,
    fetch_archived,
    timestamp,
)
from sluicer.fetch.ladder import FetchFailed
from sluicer.fetch.result import Capture, Fetched

PAGE = (
    "<html><head><title>Brake pads</title></head><body>"
    '<a rel="next" href="/p/2">next</a></body></html>'
)
CAPTURE = "https://web.archive.org/web/20200629104713id_/http://shop.example/p/1"


def archive(landed=CAPTURE, status=200, html=PAGE, headers=None):
    """A rung standing in for the archive: robots.txt absent, one capture."""
    asked: list[str] = []

    def rung(url: str) -> Fetched:
        asked.append(url)
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="not found", status=404, rung="http")
        return Fetched(
            url=landed,
            html=html,
            status=status,
            rung="http",
            headers=headers
            if headers is not None
            else {
                "content-type": "text/html; charset=utf-8",
                "x-archive-orig-link": "</p/1>; rel=canonical",
                "x-archive-orig-x-robots-tag": "noai",
                "x-archive-src": "crawl.warc.gz",
            },
        )

    rung.asked = asked  # type: ignore[attr-defined]
    return rung


@pytest.mark.parametrize(
    ("written", "stamp"),
    [
        ("2025", "2025"),
        ("2025-06", "202506"),
        ("2025-06-01", "20250601"),
        (" 2025-06-01T10:30:00Z ", "20250601103000"),
        ("20250601", "20250601"),
    ],
)
def test_a_date_is_read_as_the_archive_writes_it(written, stamp):
    assert timestamp(written) == stamp


@pytest.mark.parametrize(
    "written", ["June 2025", "2025-13", "2025-06-32", "20250601246000", "25", ""]
)
def test_what_is_not_a_date_is_refused(written):
    with pytest.raises(ValueError, match="is not a date"):
        timestamp(written)


def test_a_capture_is_read_as_the_page_its_site_served():
    rung = archive()
    fetched = fetch_archived("http://shop.example/p/1", "2020-06", rung=rung)

    assert rung.asked[-1] == (
        "https://web.archive.org/web/202006id_/http://shop.example/p/1"
    )
    assert fetched.url == "http://shop.example/p/1"
    assert fetched.rung == "archive"
    assert fetched.archived == Capture(
        "web.archive.org", "202006", "20200629104713", "http://shop.example/p/1"
    )
    assert fetched.headers == {
        "link": "</p/1>; rel=canonical",
        "x-robots-tag": "noai",
        "content-type": "text/html; charset=utf-8",
    }
    read = sluicer.extract(fetched.html, url=fetched.url, headers=fetched.headers)
    assert read.links["canonical"] == "http://shop.example/p/1"
    assert read.links["next"] == "http://shop.example/p/2", "the site's links"
    assert read.rights["http"] == {"robots": ["noai"]}


def test_the_capture_the_site_redirected_to_is_the_one_reported():
    moved = "https://web.archive.org/web/20190101000000id_/https://shop.example/new"
    fetched = fetch_archived("http://shop.example/p/1", "2019", rung=archive(moved))
    assert fetched.archived.captured == "20190101000000"
    assert fetched.url == "https://shop.example/new"


def test_a_page_never_captured_is_said_to_be():
    with pytest.raises(
        NotArchived, match=r"holds no capture of http://shop\.example/x"
    ):
        fetch_archived("http://shop.example/x", "2020", rung=archive(status=404))


def test_an_answer_from_off_the_archive_or_an_error_is_a_failed_fetch():
    with pytest.raises(FetchFailed, match=r"answered from https://elsewhere\.example/"):
        fetch_archived(
            "http://shop.example/p/1",
            "2020",
            rung=archive("https://elsewhere.example/"),
        )
    with pytest.raises(FetchFailed, match="answered status 503"):
        fetch_archived("http://shop.example/p/1", "2020", rung=archive(status=503))


def test_only_an_http_address_is_asked_for():
    with pytest.raises(ValueError, match="not an http"):
        fetch_archived("ftp://shop.example/p", "2020", rung=archive())


def test_a_redirect_is_followed_only_within_the_archive():
    assert _within_archive(CAPTURE, "https://web.archive.org/web/2020id_/x") is None
    assert "leads off web.archive.org" in _within_archive(
        CAPTURE, "https://evil.example/"
    )
    assert _within_archive(CAPTURE, "http://web.archive.org/web/2020id_/x")


def test_the_archive_is_read_over_the_http_rung_kept_within_it(monkeypatch):
    built = {}

    def http_rung(allow_private, resolve, max_bytes, error, redirects):
        built.update(allow_private=allow_private, redirects=redirects)
        return archive()

    monkeypatch.setattr("sluicer.fetch.http_rung.http_rung", http_rung)
    fetched = fetch_archived(
        "http://shop.example/p/1",
        "2020",
        allow_private=False,
        # A public address, answered here: the suite never asks a real resolver.
        resolve=lambda host: ["93.184.216.34"],
    )
    assert fetched.archived is not None
    assert built == {"allow_private": False, "redirects": _within_archive}


def test_a_capture_without_headers_of_its_site_is_read_without_them():
    fetched = fetch_archived(
        "http://shop.example/p/1", "2020", rung=archive(headers={})
    )
    assert fetched.headers == {}


# -- the command line ----------------------------------------------------------


@pytest.fixture
def archived(monkeypatch):
    """fetch_archived answering from the fake archive, every call recorded."""
    calls: list[tuple[str, str]] = []

    def fake(url, at, obey_robots=True, **kwargs):
        calls.append((url, at))
        return fetch_archived(url, at, obey_robots=obey_robots, rung=archive())

    monkeypatch.setattr("sluicer.fetch.archive.fetch_archived", fake)
    return calls


def test_extract_at_a_date_says_which_capture_it_read(archived):
    result = CliRunner().invoke(
        main, ["extract", "http://shop.example/p/1", "--at", "2020-06"]
    )
    assert result.exit_code == 0, result.stderr
    fetch = json.loads(result.stdout)["fetch"]
    assert fetch["rung"] == "archive"
    assert fetch["archived"] == {
        "archive": "web.archive.org",
        "asked": "202006",
        "captured": "20200629104713",
        "url": "http://shop.example/p/1",
    }


def test_inspect_says_when_the_capture_was_made(archived):
    result = CliRunner().invoke(
        main, ["inspect", "http://shop.example/p/1", "--at", "2020-06"]
    )
    assert (
        "archived  web.archive.org capture of http://shop.example/p/1 at "
        "2020-06-29 10:47:13, asked for 2020-06"
    ) in result.stdout
    assert "robots    allowed by web.archive.org's robots.txt" in result.stdout


def test_diff_at_a_date_reads_before_from_the_archive_and_after_live(
    archived, monkeypatch
):
    live: list[str] = []

    def fetch_live(url, **kwargs):
        live.append(url)
        return Fetched(
            url=url, html=PAGE.replace("Brake pads", "Disc"), status=200, rung="http"
        )

    monkeypatch.setattr("sluicer.cli.fetch_url", fetch_live)
    result = CliRunner().invoke(
        main,
        ["diff", "http://shop.example/p/1", "http://shop.example/p/1", "--at", "2020"],
    )
    assert archived == [("http://shop.example/p/1", "2020")]
    assert live == ["http://shop.example/p/1"]
    assert result.exit_code == 1
    assert "title: Brake pads -> Disc" in result.stdout


def test_an_archived_page_is_audited_without_todays_site(archived):
    result = CliRunner().invoke(
        main, ["audit", "http://shop.example/p/1", "--at", "2020", "--json"]
    )
    audited = json.loads(result.stdout)
    assert audited["robots_txt"] is None
    assert audited["not_checked"][0].startswith(
        "The site's robots.txt and llms.txt: the page is a capture of 20200629104713"
    )


def test_the_audit_report_says_which_capture_it_audited(archived):
    result = CliRunner().invoke(
        main, ["audit", "http://shop.example/p/1", "--at", "2020"]
    )
    assert "archived  web.archive.org capture of http://shop.example/p/1 at " in (
        result.stdout
    )
    assert "web.archive.org's robots.txt" in result.stdout


def test_at_needs_an_address_and_no_stealth(tmp_path):
    page = tmp_path / "p.html"
    page.write_text(PAGE)
    on_a_file = CliRunner().invoke(main, ["extract", str(page), "--at", "2020"])
    assert on_a_file.exit_code == 2
    assert "is not one" in on_a_file.stderr
    stealthy = CliRunner().invoke(
        main, ["extract", "http://shop.example/p", "--at", "2020", "--stealth"]
    )
    assert stealthy.exit_code == 2
    assert "--stealth has no rung there" in stealthy.stderr


def test_a_date_that_is_not_one_or_a_page_never_captured_exits_two(monkeypatch):
    def never(url, at, **kwargs):
        raise NotArchived(url, at)

    monkeypatch.setattr("sluicer.fetch.archive.fetch_archived", never)
    missing = CliRunner().invoke(
        main, ["extract", "http://shop.example/x", "--at", "2020"]
    )
    assert missing.exit_code == 2
    assert "holds no capture" in missing.stderr
    monkeypatch.undo()
    bad = CliRunner().invoke(main, ["extract", "http://shop.example/x", "--at", "June"])
    assert bad.exit_code == 2
    assert "is not a date" in bad.stderr


# -- for an agent --------------------------------------------------------------


def test_an_agent_reads_a_page_as_it_was(monkeypatch, archived):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    read = registered["extract_declared"]("http://shop.example/p/1", at="2020-06")
    assert read["ok"] is True
    assert read["fetch"]["archived"]["captured"] == "20200629104713"
    assert read["links"]["canonical"] == "http://shop.example/p/1"
    from test_markdown import fake_trafilatura

    fake_trafilatura(monkeypatch)
    text = registered["page_markdown"]("http://shop.example/p/1", at="2020")
    assert text["ok"] is True and text["fetch"]["rung"] == "archive"


def test_an_agent_is_told_why_there_is_no_capture(monkeypatch):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    def never(url, at, **kwargs):
        raise NotArchived(url, at)

    monkeypatch.setattr("sluicer.fetch.archive.fetch_archived", never)
    build_server()
    missing = registered["extract_declared"]("http://shop.example/x", at="2020")
    assert missing["ok"] is False
    assert missing["error"]["code"] == "fetch_failed"
    assert missing["error"]["retryable"] is False, "asking again will not help"
    literal = registered["extract_declared"]("<html></html>", at="2020")
    assert literal["error"]["code"] == "bad_input"
    monkeypatch.undo()
    registered = fake_mcp(monkeypatch)
    build_server()
    bad = registered["extract_declared"]("http://shop.example/x", at="June")
    assert bad["error"]["code"] == "bad_input"
    assert "is not a date" in bad["error"]["message"]
