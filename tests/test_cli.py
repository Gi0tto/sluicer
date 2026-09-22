import json
from pathlib import Path

from click.testing import CliRunner

from sluicer.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_prints_json_records():
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "product_jsonld.html")])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["sources"] == ["jsonld"]
    assert payload["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_page_with_nothing_declared_exits_one():
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "plain.html")])

    assert result.exit_code == 1
    assert "declares no structured data" in result.stderr
    assert "declares no structured data" not in result.stdout


def test_an_empty_file_is_reported_not_crashed(tmp_path):
    empty_file = tmp_path / "empty.html"
    empty_file.write_text("   \n\n   ")

    result = CliRunner().invoke(main, ["extract", str(empty_file)])

    assert result.exit_code == 1
    assert "contains no HTML" in result.stderr
    assert (result.exception is None or isinstance(result.exception, SystemExit))


def test_a_url_is_fetched_and_the_ladder_is_reported(monkeypatch):
    import json

    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.fetch.result import Climb, Fetched

    def fake_fetch(url, rungs=None):
        return Fetched(
            url=url,
            html='<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>',
            status=200,
            rung="browser",
            climbs=[Climb(from_rung="http", to_rung="browser", reason="the server refused: status 403")],
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
    result = CliRunner().invoke(main, ["extract", str(fixtures / "product_jsonld.html")])

    assert result.exit_code == 0


def test_a_missing_file_is_reported_not_crashed(tmp_path):
    missing = tmp_path / "does-not-exist.html"

    result = CliRunner().invoke(main, ["extract", str(missing)])

    assert result.exit_code == 1
    assert "does not exist" in result.stderr
    assert (result.exception is None or isinstance(result.exception, SystemExit))
