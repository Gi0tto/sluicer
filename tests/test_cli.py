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
