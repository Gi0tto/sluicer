import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from sluicer import cli
from sluicer.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_prints_json_records():
    result = CliRunner().invoke(
        main, ["extract", str(FIXTURES / "product_jsonld.html")]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["sources"] == ["jsonld"]
    assert payload["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_page_that_gives_nothing_at_all_exits_one(tmp_path):
    page = tmp_path / "bare.html"
    page.write_text(
        "<html><body><p>Nothing declared here.</p></body></html>", encoding="utf-8"
    )

    result = CliRunner().invoke(main, ["extract", str(page)])

    assert result.exit_code == 1
    assert "gives nothing" in result.stderr
    assert result.stdout == ""


def test_a_page_that_gives_nothing_says_what_to_try_next(tmp_path):
    """ "This page gives nothing" ended there, and a listing, a page of fields
    a person can see, or a page whose byline is only on screen each has a
    way in that the message never named."""
    page = tmp_path / "bare.html"
    page.write_text("<html><body><p>Words.</p></body></html>", encoding="utf-8")

    said = CliRunner().invoke(main, ["extract", str(page)]).stderr
    assert "--induce" in said and "--visible" in said
    assert f"sluicer compile {page} --want" in said

    tried = CliRunner().invoke(main, ["extract", "--induce", "--visible", str(page)])
    assert tried.exit_code == 1
    assert "--induce" not in tried.stderr and "--visible" not in tried.stderr
    assert "sluicer compile" in tried.stderr

    inspected = CliRunner().invoke(main, ["inspect", str(page)])
    assert inspected.exit_code == 1 and "--induce" in inspected.stderr


def test_a_page_with_only_a_title_still_prints_its_summary():
    """The summary is an answer too: a <title> is on the page to be read."""
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "plain.html")])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["records"] == []
    assert payload["summary"]["title"]["value"] == "Plain page"


def test_the_readme_says_what_exits_one_as_extract_decides_it(tmp_path):
    """The README said 1 meant "nothing declared", and a page with only a
    <title> exits 0: the title is declared, read into the summary. The README
    now says a <title> alone is an answer."""
    import re

    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    said = re.search(r"Exit codes follow grep:(.*?)\n\n", readme, re.S)
    assert said is not None and "`<title>`" in said.group(1)
    title_only = CliRunner().invoke(main, ["extract", str(FIXTURES / "plain.html")])
    bare = tmp_path / "bare.html"
    bare.write_text("<html><body><p>Words.</p></body></html>", encoding="utf-8")
    assert title_only.exit_code == 0
    assert CliRunner().invoke(main, ["extract", str(bare)]).exit_code == 1


def test_an_empty_file_is_reported_not_crashed(tmp_path):
    empty_file = tmp_path / "empty.html"
    empty_file.write_text("   \n\n   ", encoding="utf-8")

    result = CliRunner().invoke(main, ["extract", str(empty_file)])

    assert result.exit_code == 2
    assert "contains no HTML" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_a_url_is_fetched_and_the_ladder_is_reported(monkeypatch):
    import json

    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.fetch.result import Climb, Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(
            url=url,
            html='<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"Brake pad set"}</script>'
            "</head><body></body></html>",
            status=200,
            rung="browser",
            climbs=[
                Climb(
                    from_rung="http",
                    to_rung="browser",
                    reason="the server refused: status 403",
                )
            ],
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["fetch"]["rung"] == "browser"
    assert payload["fetch"]["climbs"][0]["reason"] == "the server refused: status 403"
    assert payload["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_path_is_still_read_from_disk():
    from pathlib import Path

    from click.testing import CliRunner

    from sluicer.cli import main

    fixtures = Path(__file__).parent / "fixtures"
    result = CliRunner().invoke(
        main, ["extract", str(fixtures / "product_jsonld.html")]
    )

    assert result.exit_code == 0


def test_a_missing_file_is_reported_not_crashed(tmp_path):
    missing = tmp_path / "does-not-exist.html"

    result = CliRunner().invoke(main, ["extract", str(missing)])

    assert result.exit_code == 2
    assert "does not exist" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_a_url_whose_rung_needs_a_missing_extra_explains_itself(monkeypatch):
    from sluicer.fetch.rungs import FetchExtraMissing

    def fake_fetch(url, rungs=None, **kwargs):
        raise FetchExtraMissing(
            "The stealth rung needs scrapling, which is not installed. "
            'Install it with: uv pip install "sluicer[stealth]"'
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p", "--stealth"])

    assert result.exit_code == 2
    assert 'uv pip install "sluicer[stealth]"' in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_a_url_the_site_refuses_explains_itself_and_does_not_crash(monkeypatch):
    from sluicer.fetch import RobotsRefused

    def fake_fetch(url, rungs=None, **kwargs):
        raise RobotsRefused(url)

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/private/p"])

    assert result.exit_code == 2
    assert "https://example.com/private/p" in result.stderr
    assert "robots.txt" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_an_empty_url_result_still_reports_what_the_fetch_cost(monkeypatch):
    from sluicer.fetch.result import Climb, Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(
            url=url,
            html="<html><body>Nothing declared here.</body></html>",
            status=200,
            rung="stealth",
            climbs=[
                Climb(
                    from_rung="http",
                    to_rung="browser",
                    reason="the server refused: status 403",
                ),
                Climb(
                    from_rung="browser",
                    to_rung="stealth",
                    reason="the page looks like a challenge",
                ),
            ],
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 1
    assert "gives nothing" in result.stderr
    assert "stealth" in result.stderr
    assert "the server refused: status 403" in result.stderr
    assert "the page looks like a challenge" in result.stderr


def test_a_real_import_failure_is_not_reported_as_a_missing_extra(monkeypatch):
    def fake_fetch(url, rungs=None, **kwargs):
        raise ImportError("cannot import name 'Foo' from 'scrapling.engines'")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    # This is a real bug inside a working scrapling install, not a missing
    # extra: it must not be dressed up in the extra's install hint, and it
    # must not be quietly turned into our own tidy exit-1 message. "Not
    # swallowed" means concretely: the exception that reaches the test
    # runner is still the plain ImportError itself, not our SystemExit.
    assert "sluicer[fetch]" not in result.stderr
    assert "sluicer[fetch]" not in result.stdout
    assert type(result.exception) is ImportError
    assert not isinstance(result.exception, SystemExit)


def test_a_directory_is_not_a_file(tmp_path):
    result = CliRunner().invoke(main, ["extract", str(tmp_path)])

    assert result.exit_code == 2
    assert "is not a file" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_a_network_failure_is_a_message_not_a_traceback(monkeypatch):
    """The common failure: the site was down, or the name did not resolve."""

    def fake_fetch(url, rungs=None, **kwargs):
        raise ConnectionError("Connection refused")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 2
    assert (
        "Could not fetch https://example.com/p: ConnectionError: Connection refused"
        in result.stderr
    )
    assert isinstance(result.exception, SystemExit)


def test_a_rung_that_came_back_without_html_is_a_message_too(monkeypatch):
    """ValueError is what a rung raises when it brings back no HTML."""

    def fake_fetch(url, rungs=None, **kwargs):
        raise ValueError(
            "the stealth rung returned no HTML for 'https://example.com/p'"
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 2
    assert "Could not fetch https://example.com/p: ValueError: " in result.stderr
    assert "the stealth rung returned no HTML" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_an_unexpected_failure_is_not_dressed_up_as_a_fetch_failure(monkeypatch):
    """A bug keeps its traceback: only operational failures become messages."""

    def fake_fetch(url, rungs=None, **kwargs):
        raise RuntimeError("the ladder lost count of its rungs")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert "Could not fetch" not in result.stderr
    assert "Could not fetch" not in result.stdout
    assert type(result.exception) is RuntimeError


def test_markdown_prints_the_main_content(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr(
        "sluicer.cli.page.to_markdown", lambda html, url=None: "# Title\n\nBody."
    )
    page = tmp_path / "page.html"
    page.write_text("<html><body><h1>Title</h1></body></html>", encoding="utf-8")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 0
    assert result.stdout.strip() == "# Title\n\nBody."


def test_markdown_without_the_extra_explains_itself(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.markdown import MarkdownExtraMissing

    def refuse(html, url=None):
        raise MarkdownExtraMissing(
            "Turning a page into markdown needs trafilatura, which is not installed. "
            'Install it with: uv pip install "sluicer[markdown]"'
        )

    monkeypatch.setattr("sluicer.cli.page.to_markdown", refuse)
    page = tmp_path / "page.html"
    page.write_text("<html><body>hi</body></html>", encoding="utf-8")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 2
    assert "sluicer[markdown]" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_markdown_of_a_page_with_nothing_to_say_exits_one(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr("sluicer.cli.page.to_markdown", lambda html, url=None: "")
    page = tmp_path / "page.html"
    page.write_text("<html><body></body></html>", encoding="utf-8")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 1
    assert "no main content" in result.stderr


def test_a_windows_1252_file_keeps_its_characters(monkeypatch, tmp_path):
    """A file's own declared encoding must survive to the reader that needs it.

    Forcing UTF-8 (or replacing what does not fit) before ``to_markdown`` ever
    sees the page destroys a byte the page never lost: trafilatura and lxml
    each do their own encoding detection from a declared ``<meta charset>``,
    but only when they are handed the original bytes.
    """
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "cafe.html"
    html = (
        '<html><head><meta charset="windows-1252"></head>'
        "<body>Caf\xe9 au lait</body></html>"
    )
    page.write_bytes(html.encode("windows-1252"))

    received: dict[str, object] = {}

    def fake_to_markdown(html_or_bytes, url=None):
        received["value"] = html_or_bytes
        # Decode it ourselves so the test can also see what the command
        # would have printed, had the byte survived.
        return (
            html_or_bytes.decode("windows-1252")
            if isinstance(html_or_bytes, bytes)
            else html_or_bytes
        )

    monkeypatch.setattr("sluicer.cli.page.to_markdown", fake_to_markdown)

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 0
    assert isinstance(received["value"], bytes)
    assert "\xe9".encode("windows-1252") in received["value"]
    assert "�".encode() not in received["value"]
    assert "Caf\xe9 au lait" in result.stdout


def test_a_windows_1252_files_declared_data_keeps_its_characters(tmp_path):
    """The same defect, one layer down: extract() must see the real bytes too."""
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "product.html"
    html = (
        '<html><head><meta charset="windows-1252">'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Caf\xe9 filter"}'
        "</script></head><body></body></html>"
    )
    page.write_bytes(html.encode("windows-1252"))

    result = CliRunner().invoke(main, ["extract", str(page)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["records"][0]["fields"]["name"]["value"] == "Caf\xe9 filter"


def test_a_missing_protego_at_the_command_line_is_a_broken_install(monkeypatch, absent):
    """The rule ``sluicer.extras`` states, driven through the front door.

    Nothing here fakes the exception: the real ``fetch`` runs, with fake rungs
    and a robots.txt that has rules in it, so the real call site is the thing
    that raises. Until 0.8 protego came with the fetch extra, and a missing
    one was a sentence naming it. The base install brings it now, so without
    it the install is broken, as it would be without lxml: the import error
    keeps its traceback, and no install line sends the reader to install
    what they have.
    """
    from sluicer.fetch import fetch as real_fetch
    from sluicer.fetch.result import Fetched

    def rung(url):
        return Fetched(
            url=url, html="<html><body>hi</body></html>", status=200, rung="http"
        )

    monkeypatch.setattr(
        "sluicer.cli.source.fetch_url",
        lambda url, **kwargs: real_fetch(
            url,
            rungs=[("http", rung)],
            robots_reader=lambda _: "User-agent: *\nAllow: /\n",
        ),
    )
    absent("protego")

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert type(result.exception) is ModuleNotFoundError
    assert "uv pip install" not in result.stderr


def test_standard_input_is_a_source():
    from click.testing import CliRunner

    from sluicer.cli import main

    page = (
        '<script type="application/ld+json">{"@type":"Product","name":"Pad"}</script>'
    )

    result = CliRunner().invoke(main, ["extract", "-"], input=page)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["records"][0]["fields"]["name"]["value"] == "Pad"


def test_a_file_is_not_its_own_address_unless_one_is_given(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "page.html"
    page.write_text(
        '<div itemscope itemtype="https://schema.org/Product">'
        '<a itemprop="url" href="/p/1">x</a></div>',
        encoding="utf-8",
    )

    bare = CliRunner().invoke(main, ["extract", str(page)])
    based = CliRunner().invoke(
        main, ["extract", str(page), "--url", "https://shop.example/c/"]
    )

    assert json.loads(bare.stdout)["url"] is None
    assert json.loads(bare.stdout)["records"][0]["fields"]["url"]["value"] == "/p/1"
    fields = json.loads(based.stdout)["records"][0]["fields"]
    assert fields["url"]["value"] == "https://shop.example/p/1"


def test_induction_is_reachable_from_the_command_line(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "listing.html"
    page.write_text(
        "<ul>"
        + "".join(
            f"<li class='row'><a href='/p{n}'>Product {n}</a>"
            f"<span class='price'>{n}.99</span></li>"
            for n in range(5)
        )
        + "</ul>",
        encoding="utf-8",
    )

    plain = CliRunner().invoke(main, ["extract", str(page)])
    induced = CliRunner().invoke(main, ["extract", str(page), "--induce"])

    assert plain.exit_code == 1
    assert induced.exit_code == 0
    assert "induced" in json.loads(induced.stdout)["sources"]


def test_a_fetch_that_failed_on_every_rung_exits_two_with_what_each_said(monkeypatch):
    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.fetch import FetchFailed

    def fake_fetch(url, **kwargs):
        raise FetchFailed(url, [], "the rung raised TimeoutError: Timeout 30000ms")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://slow.example/p"])

    assert result.exit_code == 2
    assert "Timeout 30000ms" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_the_fetch_flags_reach_the_ladder(monkeypatch):
    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.fetch.result import Fetched

    seen = {}

    def fake_fetch(url, **kwargs):
        seen.update(kwargs)
        return Fetched(url=url, html="<html></html>", status=200, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    CliRunner().invoke(
        main, ["extract", "https://example.com/p", "--stealth", "--no-robots"]
    )

    assert seen == {
        "stealth": True,
        "obey_robots": False,
        "headers": {},
        "cookies": {},
    }


def test_inspect_shows_each_field_and_answer_with_where_it_came_from():
    result = CliRunner().invoke(
        main, ["inspect", str(FIXTURES / "drift" / "product.html")]
    )

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].endswith("product.html")
    assert any(
        line.startswith("readers   jsonld (1 record, 3 fields)") for line in lines
    )
    assert any("Product  (jsonld)" in line for line in lines)
    assert any(
        line.split() == ["price", "41.90", "[jsonld", "Product.offers.price]"]
        for line in lines
    )
    assert any("not read: microformats" in line for line in lines)


def test_inspect_does_not_call_a_reader_silent_that_answered_the_summary():
    """plain.html's title comes from html's <title>, which is no record field:
    the readers line said "none said anything / silent: ..., html" right above
    "title  Plain page  [html <title>]"."""
    result = CliRunner().invoke(main, ["inspect", str(FIXTURES / "plain.html")])

    lines = result.stdout.splitlines()
    readers = next(line for line in lines if line.startswith("readers"))
    silent = next(line for line in lines if "silent:" in line)
    assert readers == "readers   html (1 summary answer)"
    assert "html" not in silent.split(":", 1)[1].replace(",", " ").split()
    assert any(line.split()[:3] == ["title", "Plain", "page"] for line in lines)


def test_inspect_is_the_same_report_every_time():
    page = str(FIXTURES / "drift" / "product.html")

    first = CliRunner().invoke(main, ["inspect", page]).stdout
    second = CliRunner().invoke(main, ["inspect", page]).stdout

    assert first == second


def test_inspect_says_what_the_fetch_cost(monkeypatch):
    from sluicer.fetch.result import Climb, Fetched

    page = (FIXTURES / "drift" / "product.html").read_text(encoding="utf-8")

    def fetched(url, **options):
        return Fetched(
            url=url,
            html=page,
            status=200,
            rung="browser",
            climbs=[Climb("http", "browser", "the server refused: status 403", 0.25)],
            seconds=1.5,
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fetched)
    result = CliRunner().invoke(main, ["inspect", "https://shop.example/p"])

    assert result.exit_code == 0, result.output
    assert "fetch     browser rung, status 200, 1.50 s" in result.stdout
    assert "http -> browser after 0.25 s: the server refused: status 403" in (
        result.stdout
    )
    assert "robots    allowed by the site's robots.txt" in result.stdout


def test_inspect_of_a_page_that_gives_nothing_exits_one(tmp_path):
    page = tmp_path / "bare.html"
    page.write_text(
        "<html><body><p>Nothing declared here.</p></body></html>", encoding="utf-8"
    )

    result = CliRunner().invoke(main, ["inspect", str(page)])

    assert result.exit_code == 1
    assert "records   0, nothing declared" in result.stdout


def test_a_page_too_heavy_to_fetch_exits_two_with_a_message(monkeypatch):
    from sluicer.fetch.result import ResponseTooLarge

    def heavy(url, **options):
        raise ResponseTooLarge(url, 16)

    monkeypatch.setattr("sluicer.cli.source.fetch_url", heavy)
    result = CliRunner().invoke(main, ["extract", "https://shop.example/huge"])

    assert result.exit_code == 2
    assert "larger than 16 bytes" in result.stderr


def test_inspect_shows_what_a_date_means_beside_what_the_page_wrote(tmp_path):
    page = tmp_path / "dated.html"
    page.write_text(
        '<html><head><meta property="article:published_time" content="Jun 16, 2025">'
        "<title>A post</title></head></html>",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["inspect", str(page)])

    assert "Jun 16, 2025 = 2025-06-16" in result.stdout


def test_inspect_shows_the_link_relations(tmp_path):
    page = tmp_path / "linked.html"
    page.write_text(
        '<html><head><link rel="canonical" href="https://s.example/p">'
        '<link rel="alternate" hreflang="de" href="https://s.example/de/p">'
        "<title>P</title></head></html>",
        encoding="utf-8",
    )

    out = CliRunner().invoke(main, ["inspect", str(page)]).stdout

    assert "links     canonical https://s.example/p" in out
    assert "1 alternates: de" in out


def test_inspect_says_whether_the_page_declares_how_it_may_be_used(tmp_path):
    page = tmp_path / "reserved.html"
    page.write_text(
        '<html><head><meta name="robots" content="noai">'
        '<meta name="tdm-reservation" content="1"><title>T</title></head></html>',
        encoding="utf-8",
    )
    bare = tmp_path / "bare.html"
    bare.write_text("<html><head><title>T</title></head></html>", encoding="utf-8")

    reserved = CliRunner().invoke(main, ["inspect", str(page)]).stdout
    silent = CliRunner().invoke(main, ["inspect", str(bare)]).stdout

    assert "rights    robots noai" in reserved
    assert "tdm-reservation 1" in reserved
    assert "rights    none declared in the page" in silent


def test_extract_reads_the_fetched_pages_headers(monkeypatch):
    from sluicer.fetch.result import Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(
            url="https://example.com/p",
            html="<html><head><title>T</title>"
            '<link rel="license" href="/licence"></head></html>',
            status=200,
            rung="http",
            headers={
                "link": "</c>; rel=canonical",
                "x-robots-tag": "noindex",
                "content-usage": "train-ai=n",
            },
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    extracted = CliRunner().invoke(main, ["extract", "https://example.com/p"])
    inspected = CliRunner().invoke(main, ["inspect", "https://example.com/p"])

    payload = json.loads(extracted.stdout)
    assert payload["links"]["canonical"] == "https://example.com/c"
    assert payload["rights"]["http"] == {
        "robots": ["noindex"],
        "content_usage": {"train-ai": "disallow"},
    }
    assert "rights    license https://example.com/licence" in inspected.stdout
    assert "robots noindex  [http header]" in inspected.stdout
    assert "content-usage train-ai=disallow  [http header]" in inspected.stdout


# -- audit --------------------------------------------------------------------

AUDITED_WELL = (
    "<html><head><title>Example</title>"
    '<meta name="description" content="An example site.">'
    '<link rel="canonical" href="https://example.com/">'
    '<meta property="og:title" content="Example"><meta property="og:type" '
    'content="website"><meta property="og:image" content="https://example.com/i.png">'
    '<meta property="og:url" content="https://example.com/">'
    '<script type="application/ld+json">{"@type":"WebSite","name":"Example",'
    '"alternateName":"EX","url":"https://example.com/"}</script>'
    "</head><body></body></html>"
)


def test_audit_of_a_page_that_keeps_to_the_rules_exits_zero(tmp_path):
    page = tmp_path / "home.html"
    page.write_text(AUDITED_WELL, encoding="utf-8")

    result = CliRunner().invoke(main, ["audit", str(page)])

    assert result.exit_code == 0, result.output
    assert "WebSite  (jsonld record 0)" in result.stdout
    assert "Site name  requirements met" in result.stdout
    assert "page      0 findings" in result.stdout
    assert "the site is read only for a URL" in result.stdout
    assert result.stdout.rstrip().endswith("summary   0 errors, 0 warnings, 0 notes")


def test_audit_of_a_page_that_breaks_a_documented_rule_exits_three():
    result = CliRunner().invoke(
        main, ["audit", str(FIXTURES / "product_all_three.html")]
    )

    assert result.exit_code == 3
    assert "Product  (jsonld record 0)" in result.stdout
    assert "Product  (microdata record 0)" in result.stdout
    assert "Merchant listing  2 required missing: image, offers" in result.stdout
    assert "review|aggregateRating|offers" in result.stdout
    assert "og:type is absent" in result.stdout


def test_audit_names_each_refused_value_with_its_rule(tmp_path):
    page = tmp_path / "p.html"
    page.write_text(
        '<script type="application/ld+json">{"@type":"Product","name":"Pad",'
        '"offers":{"price":"41,90","priceCurrency":"EUR"}}</script>',
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["audit", str(page)])

    assert result.exit_code == 3
    line = next(
        line for line in result.stdout.splitlines() if "offers.price is" in line
    )
    assert line.split()[0] == "error"
    assert "[https://schema.org/price]" in line


def test_audit_of_a_page_that_declares_nothing_exits_one(tmp_path):
    page = tmp_path / "bare.html"
    page.write_text(
        AUDITED_WELL.split("<script")[0] + "</head></html>", encoding="utf-8"
    )

    result = CliRunner().invoke(main, ["audit", str(page)])

    assert result.exit_code == 1
    assert "records   0 audited, none declared" in result.stdout


def test_audit_json_is_the_audit_itself(tmp_path):
    page = tmp_path / "home.html"
    page.write_text(AUDITED_WELL, encoding="utf-8")

    result = CliRunner().invoke(main, ["audit", str(page), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["records"][0]["features"][0]["name"] == "Site name"
    assert payload["errors"] == 0
    assert "fetch" not in payload


def test_audit_of_a_file_that_cannot_be_read_exits_two(tmp_path):
    result = CliRunner().invoke(main, ["audit", str(tmp_path / "nope.html")])

    assert result.exit_code == 2
    assert "does not exist" in result.stderr


def _fetched_well(monkeypatch):
    from sluicer.fetch.result import Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(
            url="https://example.com/", html=AUDITED_WELL, status=200, rung="http"
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)


def test_audit_of_a_url_reads_the_site_beside_it(monkeypatch):
    from sluicer.audit import Site, SiteFile

    _fetched_well(monkeypatch)
    asked = {}

    def read_site(url, **kwargs):
        asked.update(url=url, **kwargs)
        return Site(
            SiteFile(
                "https://example.com/robots.txt",
                200,
                "User-agent: GPTBot\nDisallow: /\n\nUser-agent: anthropic-ai\n"
                "Disallow: /\n",
            ),
            SiteFile("https://example.com/llms.txt", 200, "No heading here\n"),
            SiteFile("https://example.com/llms-full.txt", 200, "x" * 1500),
        )

    monkeypatch.setattr("sluicer.fetch.site.read_site", read_site)

    result = CliRunner().invoke(main, ["audit", "https://example.com/", "--no-robots"])

    assert asked == {"url": "https://example.com/", "obey_robots": False}
    assert result.exit_code == 3, "an llms.txt with no name is an error"
    out = result.stdout
    assert "agents    robots.txt https://example.com/robots.txt, status 200" in out
    gpt = next(line for line in out.splitlines() if line.strip().startswith("GPTBot"))
    assert "disallowed" in gpt and "User-agent: gptbot" in gpt
    user = next(line for line in out.splitlines() if "ChatGPT-User" in line)
    assert "(may ignore robots.txt)" in user
    assert "also named, by no agent documented here: anthropic-ai" in out
    assert "llms.txt  https://example.com/llms.txt: no name, 0 sections" in out
    assert "llms-full https://example.com/llms-full.txt: 1,500 characters" in out
    assert "robots    not asked (--no-robots)" in out


def test_audit_of_a_url_can_leave_the_site_alone(monkeypatch):
    _fetched_well(monkeypatch)

    def read_site(url, **kwargs):
        raise AssertionError("the site was read")

    monkeypatch.setattr("sluicer.fetch.site.read_site", read_site)

    result = CliRunner().invoke(main, ["audit", "https://example.com/", "--no-site"])

    assert result.exit_code == 0
    assert "not asked (--no-site)" in result.stdout


def test_audit_of_a_site_whose_robots_txt_could_not_be_read_says_so(monkeypatch):
    from sluicer.audit import Site, SiteFile

    _fetched_well(monkeypatch)

    def read_site(url, **kwargs):
        return Site(
            SiteFile("https://example.com/robots.txt", error="OSError: timed out"),
            SiteFile("https://example.com/llms.txt", error="not fetched"),
            SiteFile("https://example.com/llms-full.txt", 404),
        )

    monkeypatch.setattr("sluicer.fetch.site.read_site", read_site)

    result = CliRunner().invoke(main, ["audit", "https://example.com/"])

    out = result.stdout
    assert "not read: OSError: timed out" in out
    assert "unknown" in next(line for line in out.splitlines() if "GPTBot" in line)
    assert "llms.txt  https://example.com/llms.txt: not served (no answer)" in out
    assert "not served (status 404)" in out


def test_audit_of_a_site_without_robots_txt_says_everything_is_allowed(monkeypatch):
    from sluicer.audit import Site, SiteFile

    _fetched_well(monkeypatch)
    monkeypatch.setattr(
        "sluicer.fetch.site.read_site",
        lambda url, **kwargs: Site(
            SiteFile("https://example.com/robots.txt", 404),
            SiteFile("https://example.com/llms.txt", 404),
            SiteFile("https://example.com/llms-full.txt", 404),
        ),
    )

    result = CliRunner().invoke(main, ["audit", "https://example.com/", "--json"])

    payload = json.loads(result.stdout)
    assert payload["fetch"]["rung"] == "http"
    assert {v["allowed"] for v in payload["crawlers"]} == {True}
    human = CliRunner().invoke(main, ["audit", "https://example.com/"]).stdout
    assert "status 404, none published: everything is allowed" in human


def test_audit_reports_retired_limited_unchecked_and_featureless_records(tmp_path):
    nodes = [
        {"@type": "WebPage", "name": "Home"},
        {"@type": "FAQPage", "mainEntity": []},
        {"@type": "Dataset", "name": "D", "description": "d" * 60},
        {"@type": "Movie", "name": "Up"},
        {
            "@type": "Product",
            "name": "P",
            "image": "https://e.com/p.jpg",
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        },
    ]
    page = tmp_path / "many.html"
    page.write_text(
        "".join(
            f'<script type="application/ld+json">{json.dumps(node)}</script>'
            for node in nodes
        ),
        encoding="utf-8",
    )

    out = CliRunner().invoke(main, ["audit", str(page)]).stdout

    assert "no rich-result feature is documented for this type" in out
    assert "FAQ  retired: Not shown in Google Search since 2026-05-07" in out
    assert "(limited: see the note in --json)" in out
    assert "not checked here: Movie carousel" in out
    assert "Merchant listing  a value this feature refuses" in out


def test_audit_of_a_page_the_site_refused_says_what_it_audited(monkeypatch):
    from sluicer.fetch.result import Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(url=url, html="<html>Forbidden</html>", status=403, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["audit", "https://example.com/p", "--no-site"])

    assert result.exit_code == 1
    notes = result.stdout.split("not checked\n", 1)[1].splitlines()
    assert notes[0] == (
        "  The page asked for: the site answered status 403, and what is audited "
        "is that answer."
    )


def test_audit_folds_what_every_item_of_a_list_lacks_into_one_entry(tmp_path):
    reviews = [
        {"@type": "Review", "author": {"@type": "Person", "name": f"R{n}"}}
        for n in range(3)
    ]
    node = {
        "@type": "Product",
        "name": "Pad",
        "image": "https://e.com/p.jpg",
        "offers": {"@type": "Offer", "price": "1", "priceCurrency": "EUR"},
        "review": reviews,
    }
    page = tmp_path / "p.html"
    page.write_text(
        f'<script type="application/ld+json">{json.dumps(node)}</script>',
        encoding="utf-8",
    )

    out = CliRunner().invoke(main, ["audit", str(page)]).stdout

    assert "optional parts unusable, missing: review[].reviewRating (3)" in out
    assert "review[0].reviewRating" not in out


def test_sluicer_mcp_runs_the_mcp_server_as_sluicer_mcp_does(monkeypatch):
    """The MCP Registry starts a package's own command: uvx --with
    "sluicer[mcp]" sluicer mcp."""
    ran = []
    monkeypatch.setattr("sluicer.mcp_server.main", lambda tools=None: ran.append(tools))
    result = CliRunner().invoke(main, ["mcp"])
    assert result.exit_code == 0, result.output
    result = CliRunner().invoke(main, ["mcp", "--tools", "extract_declared,map_site"])
    assert result.exit_code == 0, result.output
    assert ran == [None, ["extract_declared", "map_site"]]


def test_sluicer_mcp_with_a_tool_that_does_not_exist_is_an_error_not_a_traceback(
    monkeypatch,
):
    """`sluicer mcp --tools bogus` printed thirty lines of traceback."""
    from test_mcp_server import fake_mcp

    fake_mcp(monkeypatch)
    result = CliRunner().invoke(main, ["mcp", "--tools", "extract_declared,bogus"])
    assert result.exit_code == 2
    assert "no such tool: 'bogus'" in result.stderr
    assert "crawl_site" in result.stderr
    assert "Traceback" not in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_sluicer_mcp_without_the_extra_says_so_in_one_line(monkeypatch):
    import sys

    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])
    result = CliRunner().invoke(main, ["mcp"])
    assert result.exit_code == 1
    assert "sluicer[mcp]" in result.stderr and "Traceback" not in result.stderr


def test_the_output_is_utf8_where_the_system_would_give_another_code_page(tmp_path):
    """Windows gives a pipe cp1252, and a Chinese title printed to one raised.

    Run as a user runs it, a process of its own, with its streams set to the
    code page a Windows pipe gets.
    """
    page = tmp_path / "page.html"
    page.write_text(
        "<html><head><title>2023年5月10日 新闻</title></head></html>", encoding="utf-8"
    )
    done = subprocess.run(
        [sys.executable, "-c", "from sluicer.cli import main; main()", "extract", page],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    title = json.loads(done.stdout.decode("utf-8"))["summary"]["title"]["value"]
    assert title == "2023年5月10日 新闻"


def test_text_piped_in_is_read_as_utf8_whatever_the_code_page():
    piped = io.TextIOWrapper(
        io.BytesIO("https://例え.jp/\n".encode()), encoding="cp1252"
    )
    shown = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")

    cli._speak_utf8(piped, shown)

    assert piped.read() == "https://例え.jp/\n"
    assert shown.encoding == "utf-8"


def test_the_help_groups_the_commands_by_what_they_are_for():
    """Sixteen commands in one alphabetical list put audit first and extract
    among the servers; each section is a thing a person comes to do."""
    said = CliRunner().invoke(main, ["--help"]).stdout
    sections = {
        "Read a page": [
            "fetch",
            "extract",
            "select",
            "inspect",
            "markdown",
            "diff",
            "audit",
        ],
        "Whole sites": ["map", "crawl", "batch", "feed", "warc"],
        "Extractors": ["compile", "run", "heal"],
        "Servers": ["mcp", "serve"],
    }
    starts = [said.index(f"{title}:\n") for title in sections]
    assert starts == sorted(starts) and "Commands:" not in said
    for (title, names), start in zip(sections.items(), starts, strict=True):
        block = said[start:].split("\n\n")[0].splitlines()[1:]
        # A description too long for its line goes on under itself, indented.
        named = [line for line in block if not line.startswith("   ")]
        assert [line.split()[0] for line in named] == names, title
    placed = [name for names in sections.values() for name in names]
    assert sorted(placed) == sorted(main.commands)


def test_the_help_gives_each_command_its_whole_first_sentence():
    """Cut to fit one line, the list stopped where commands differ: "map  List
    a site's addresses, from its sitemaps or its start..." hid "page's links",
    the words that tell map from crawl."""
    import inspect as source

    said = CliRunner().invoke(main, ["--help"], terminal_width=80).stdout
    listed = said[said.index("Read a page:") :]

    assert "..." not in listed and "\u2026" not in listed
    flowing = " ".join(said.split())
    for name, command in main.commands.items():
        if command.hidden:
            continue
        first = source.cleandoc(command.help or "").split("\n\n")[0]
        sentence = " ".join(first.split()).split(". ")[0].rstrip(".") + "."
        assert f"{name} {sentence}" in flowing, name
    assert "its start page's links." in flowing


# -- the caller's headers and cookies --------------------------------------------


def _recording_fetch(monkeypatch):
    from sluicer.fetch.result import Fetched

    seen = {}

    def fake_fetch(url, **kwargs):
        seen.update(kwargs)
        return Fetched(
            url=url,
            html="<html><head><title>T</title></head></html>",
            status=200,
            rung="http",
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)
    return seen


def test_headers_and_cookies_given_at_the_command_line_are_sent(monkeypatch):
    seen = _recording_fetch(monkeypatch)

    result = CliRunner().invoke(
        main,
        [
            "extract",
            "https://example.com/account",
            "--header",
            "Authorization: Bearer t",
            "-H",
            "X-Team:  readers ",
            "--cookie",
            "session=abc",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert seen["headers"] == {"Authorization": "Bearer t", "X-Team": "readers"}
    assert seen["cookies"] == {"session": "abc"}


def test_without_them_nothing_extra_is_sent(monkeypatch):
    seen = _recording_fetch(monkeypatch)

    CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert not seen.get("headers") and not seen.get("cookies")


@pytest.mark.parametrize(
    ("option", "said"),
    [
        (["--header", "User-Agent: Mozilla/5.0"], "User-Agent is not replaced"),
        (["--header", "no colon here"], "NAME: VALUE"),
        (["--cookie", "no-equals"], "NAME=VALUE"),
        (["--header", "Host: elsewhere.example"], "written by the transport"),
    ],
)
def test_a_header_or_cookie_that_cannot_be_sent_stops_the_command(
    monkeypatch, option, said
):
    seen = _recording_fetch(monkeypatch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p", *option])

    assert result.exit_code == 2
    assert said in result.stderr
    assert seen == {}, "nothing was asked"


def test_the_archive_is_never_sent_a_login(monkeypatch):
    _recording_fetch(monkeypatch)

    result = CliRunner().invoke(
        main, ["extract", "https://example.com/p", "--at", "2020", "--cookie", "s=1"]
    )

    assert result.exit_code == 2
    assert "--at" in result.stderr and "archive" in result.stderr


def test_a_crawl_and_a_batch_send_them_with_every_request(monkeypatch):
    from sluicer.crawl.pages import Crawl

    seen = {}

    def recording(*args, **kwargs):
        seen.update(kwargs)
        return Crawl(lambda run: iter(()))

    monkeypatch.setattr("sluicer.cli.sites.crawl_site", recording)
    monkeypatch.setattr("sluicer.cli.sites.extract_many", recording)

    for command in (["crawl", "https://example.com/"], ["batch", "-"]):
        seen.clear()
        CliRunner().invoke(
            main,
            [*command, "--cookie", "session=abc", "--header", "X-Team: a"],
            input="https://example.com/a\n",
        )
        assert seen["cookies"] == {"session": "abc"}, command
        assert seen["headers"] == {"X-Team": "a"}, command


# -- a page that answered an error --------------------------------------------


def _answered(monkeypatch, status, html=""):
    from sluicer.fetch.result import Fetched

    def fake_fetch(url, rungs=None, **kwargs):
        return Fetched(url=url, html=html, status=status, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)


def _shop_extractor(tmp_path):
    from pathlib import Path

    from sluicer.extractor import compile_extractor

    drift = Path(__file__).parent / "fixtures" / "drift"
    pages = [
        ((drift / name).read_bytes(), f"https://shop.example/{name}")
        for name in ("shop_v1.html", "shop_v1_page2.html")
    ]
    out = tmp_path / "shop.json"
    out.write_text(compile_extractor(pages).to_json(), encoding="utf-8")
    return out


@pytest.mark.parametrize("command", ["run", "heal"])
@pytest.mark.parametrize(
    ("status", "html"), [(503, ""), (404, "<p>Not found</p>")], ids=["503", "404"]
)
def test_run_and_heal_do_not_read_an_error_page_as_the_page(
    monkeypatch, tmp_path, command, status, html
):
    """An empty 503 was replayed as the page: run exited 3 blaming the
    extractor's contract, heal 3 for fields lost, and neither named the
    status. The page was never read, which is exit 2."""
    from click.testing import CliRunner

    from sluicer.cli import main

    extractor = _shop_extractor(tmp_path)
    _answered(monkeypatch, status, html)

    result = CliRunner().invoke(
        main, [command, str(extractor), "https://shop.example/p"]
    )

    assert result.exit_code == 2, result.output
    assert f"answered status {status}" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("status", [404, 503])
def test_extract_of_an_empty_error_page_names_the_status(monkeypatch, status):
    """An empty 404 was "This page gives nothing", with compile --want to try
    on a page that is the site's error."""
    from click.testing import CliRunner

    from sluicer.cli import main

    _answered(monkeypatch, status)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 1
    assert f"the site answered status {status}" in result.stderr
    assert "compile" not in result.stderr


def test_select_of_an_attribute_of_the_page_that_gives_nothing_says_where_it_read(
    tmp_path,
):
    """'@href' is read from the <html> element and gave nothing without a word
    of why; //@href is what reads every href."""
    page = tmp_path / "p.html"
    page.write_text(
        '<html lang="en"><body><a href="/x">x</a></body></html>', encoding="utf-8"
    )

    nothing = CliRunner().invoke(main, ["select", str(page), "@href"])
    lang = CliRunner().invoke(main, ["select", str(page), "@lang"])

    assert nothing.exit_code == 1
    assert "reads the <html> element's attribute; //@href reads it" in (nothing.stderr)
    assert lang.exit_code == 0 and lang.stdout.startswith("en\t/html")
