import json
from pathlib import Path

from click.testing import CliRunner

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
    page.write_text("<html><body><p>Nothing declared here.</p></body></html>")

    result = CliRunner().invoke(main, ["extract", str(page)])

    assert result.exit_code == 1
    assert "gives nothing" in result.stderr
    assert result.stdout == ""


def test_a_page_with_only_a_title_still_prints_its_summary():
    """The summary is an answer too: a <title> is on the page to be read."""
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "plain.html")])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["records"] == []
    assert payload["summary"]["title"]["value"] == "Plain page"


def test_an_empty_file_is_reported_not_crashed(tmp_path):
    empty_file = tmp_path / "empty.html"
    empty_file.write_text("   \n\n   ")

    result = CliRunner().invoke(main, ["extract", str(empty_file)])

    assert result.exit_code == 2
    assert "contains no HTML" in result.stderr
    assert (result.exception is None or isinstance(result.exception, SystemExit))


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

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

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
    assert (result.exception is None or isinstance(result.exception, SystemExit))


def test_a_url_without_the_fetch_extra_explains_itself(monkeypatch):
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    def fake_fetch(url, rungs=None, **kwargs):
        raise FetchExtraMissing(
            "Fetching a URL needs scrapling, which is not installed. "
            "Install it with: uv pip install 'sluicer[fetch]'"
        )

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 2
    assert "uv pip install 'sluicer[fetch]'" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_a_url_the_site_refuses_explains_itself_and_does_not_crash(monkeypatch):
    from sluicer.fetch import RobotsRefused

    def fake_fetch(url, rungs=None, **kwargs):
        raise RobotsRefused(url)

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

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

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 1
    assert "gives nothing" in result.stderr
    assert "stealth" in result.stderr
    assert "the server refused: status 403" in result.stderr
    assert "the page looks like a challenge" in result.stderr


def test_a_real_import_failure_is_not_reported_as_a_missing_extra(monkeypatch):
    def fake_fetch(url, rungs=None, **kwargs):
        raise ImportError("cannot import name 'Foo' from 'scrapling.engines'")

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

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
    assert (result.exception is None or isinstance(result.exception, SystemExit))


def test_a_network_failure_is_a_message_not_a_traceback(monkeypatch):
    """The common failure: the site was down, or the name did not resolve."""

    def fake_fetch(url, rungs=None, **kwargs):
        raise ConnectionError("Connection refused")

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

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
        raise ValueError("the stealth rung returned no HTML for 'https://example.com/p'")

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 2
    assert "Could not fetch https://example.com/p: ValueError: " in result.stderr
    assert "the stealth rung returned no HTML" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_an_unexpected_failure_is_not_dressed_up_as_a_fetch_failure(monkeypatch):
    """A bug keeps its traceback: only operational failures become messages."""

    def fake_fetch(url, rungs=None, **kwargs):
        raise RuntimeError("the ladder lost count of its rungs")

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert "Could not fetch" not in result.stderr
    assert "Could not fetch" not in result.stdout
    assert type(result.exception) is RuntimeError


def test_markdown_prints_the_main_content(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr(
        "sluicer.cli.to_markdown", lambda html, url=None: "# Title\n\nBody."
    )
    page = tmp_path / "page.html"
    page.write_text("<html><body><h1>Title</h1></body></html>")

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
            "Install it with: uv pip install 'sluicer[markdown]'"
        )

    monkeypatch.setattr("sluicer.cli.to_markdown", refuse)
    page = tmp_path / "page.html"
    page.write_text("<html><body>hi</body></html>")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 2
    assert "sluicer[markdown]" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_markdown_of_a_page_with_nothing_to_say_exits_one(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr("sluicer.cli.to_markdown", lambda html, url=None: "")
    page = tmp_path / "page.html"
    page.write_text("<html><body></body></html>")

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

    monkeypatch.setattr("sluicer.cli.to_markdown", fake_to_markdown)

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


def test_a_missing_protego_at_the_command_line_is_a_message_not_a_traceback(
    monkeypatch, absent
):
    """The rule ``sluicer.extras`` states, driven through the front door.

    Nothing here fakes the exception: the real ``fetch`` runs, with fake rungs
    and a robots.txt that has rules in it, so the real call site is the thing
    that raises. With protego absent and the call site raising the base
    ``MissingExtra``, this walked straight past ``cli.py``'s
    ``except FetchExtraMissing`` and reached the user as a traceback.
    """
    from sluicer.fetch import fetch as real_fetch
    from sluicer.fetch.result import Fetched

    def rung(url):
        return Fetched(
            url=url, html="<html><body>hi</body></html>", status=200, rung="http"
        )

    monkeypatch.setattr(
        "sluicer.cli.fetch_url",
        lambda url, **kwargs: real_fetch(
            url,
            rungs=[("http", rung)],
            robots_reader=lambda _: "User-agent: *\nAllow: /\n",
        ),
    )
    absent("protego")

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 2
    assert "uv pip install 'sluicer[fetch]'" in result.stderr
    assert isinstance(
        result.exception, SystemExit
    ), f"reached the user as {result.exception!r}"


def test_standard_input_is_a_source():
    from click.testing import CliRunner

    from sluicer.cli import main

    page = (
        '<script type="application/ld+json">{"@type":"Product","name":"Pad"}'
        "</script>"
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
        '<a itemprop="url" href="/p/1">x</a></div>'
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
        + "</ul>"
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

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

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

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    CliRunner().invoke(
        main, ["extract", "https://example.com/p", "--stealth", "--no-robots"]
    )

    assert seen == {"stealth": True, "obey_robots": False}
