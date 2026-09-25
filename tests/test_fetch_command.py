"""``sluicer fetch URL``: the page as the ladder brought it, and what it cost."""

import json

import pytest
from click.testing import CliRunner

from sluicer.cli import main
from sluicer.fetch.result import CacheHit, Climb, Fetched

PAGE = "<html><head><title>Café</title></head><body>ok</body></html>"


def _fetched(monkeypatch, **options):
    seen = {}

    def fake_fetch(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return Fetched(
            url="https://example.com/final",
            html=PAGE,
            status=200,
            rung="browser",
            climbs=[Climb("http", "browser", "the body is skeletal", seconds=0.12)],
            seconds=0.5,
            headers={"content-type": "text/html; charset=utf-8"},
            **options,
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fake_fetch)
    return seen


def test_the_page_goes_to_stdout_and_what_it_cost_to_stderr(monkeypatch):
    _fetched(monkeypatch)

    result = CliRunner().invoke(main, ["fetch", "https://example.com/p"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == PAGE + "\n"
    assert "http -> browser after 0.12 s: the body is skeletal" in result.stderr
    assert "https://example.com/final: 200, from the browser rung" in result.stderr


def test_with_json_everything_is_one_object_and_stderr_says_nothing(monkeypatch):
    _fetched(monkeypatch, cached=CacheHit(age=12.0, revalidated=True))

    result = CliRunner().invoke(main, ["fetch", "https://example.com/p", "--json"])

    assert result.exit_code == 0
    assert result.stderr == ""
    answer = json.loads(result.stdout)
    assert answer == {
        "url": "https://example.com/final",
        "status": 200,
        "rung": "browser",
        "seconds": 0.5,
        "climbs": [
            {
                "from_rung": "http",
                "to_rung": "browser",
                "reason": "the body is skeletal",
                "seconds": 0.12,
            }
        ],
        "headers": {"content-type": "text/html; charset=utf-8"},
        "cached": {"age": 12.0, "revalidated": True},
        "html": PAGE,
    }


def test_the_page_can_be_written_to_a_file(monkeypatch, tmp_path):
    _fetched(monkeypatch)
    out = tmp_path / "page.html"

    result = CliRunner().invoke(main, ["fetch", "https://example.com/p", "-o", out])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.read_text(encoding="utf-8") == PAGE
    assert str(out) in result.stderr


@pytest.mark.parametrize("source", ["-", "page.html"])
def test_only_an_address_is_fetched(monkeypatch, source):
    seen = _fetched(monkeypatch)

    result = CliRunner().invoke(main, ["fetch", source])

    assert result.exit_code == 2
    assert "an http(s) address" in result.stderr
    assert seen == {}


def test_the_fetch_options_reach_the_ladder(monkeypatch):
    seen = _fetched(monkeypatch)

    CliRunner().invoke(
        main,
        [
            "fetch",
            "https://example.com/p",
            "--no-robots",
            "--header",
            "Authorization: Bearer t",
            "--cookie",
            "session=abc",
        ],
    )

    assert seen["obey_robots"] is False
    assert seen["headers"] == {"Authorization": "Bearer t"}
    assert seen["cookies"] == {"session": "abc"}


def test_a_fetch_that_failed_exits_2_with_its_reason(monkeypatch):
    from sluicer.fetch import RobotsRefused

    def refused(url, **kwargs):
        raise RobotsRefused(url)

    monkeypatch.setattr("sluicer.cli.source.fetch_url", refused)

    result = CliRunner().invoke(main, ["fetch", "https://example.com/private"])

    assert result.exit_code == 2
    assert "robots.txt" in result.stderr


def test_fetch_is_listed_with_the_commands_that_read_a_page():
    from sluicer.cli import SECTIONS

    assert SECTIONS["Read a page"][0] == "fetch"


def test_fetch_never_repeats_a_password_it_was_handed():
    """Every message the command line fails with goes through one door, and
    no password in an address passes it."""
    ran = CliRunner().invoke(main, ["fetch", "ftp://me:secret@files.example/p"])

    assert ran.exit_code == 2
    assert "secret" not in ran.output and "me:***@" in ran.output
