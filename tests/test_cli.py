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
    assert "declares no structured data" in result.output
