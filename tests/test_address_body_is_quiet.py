"""A page whose body is an address alone, fetched or read from a file, is read
without the warning that tells a caller of ``sluicer.extract()`` to fetch it
first: it was fetched, or read, already.

Found by the hostile review of 0.9.1: ``fetch()`` of such a page raised under
``-W error::UserWarning`` (0.9.0 answered status 200), and ``sluicer extract``
of a file holding a URL printed a Python warning pointing at cli/page.py.
"""

import warnings

import pytest
from click.testing import CliRunner

from sluicer.fetch.result import Fetched

BODY = "https://example.com/landing\n"


def _rung(name, html):
    def go(url):
        return Fetched(url=url, html=html, status=200, rung=name)

    return go


@pytest.fixture
def no_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


def test_fetch_of_a_page_whose_body_is_an_address_does_not_warn(no_warning):
    from sluicer.fetch.ladder import fetch

    page = fetch(
        "https://example.com/url.html",
        rungs=[("http", _rung("http", BODY)), ("browser", _rung("browser", BODY))],
        obey_robots=False,
    )

    assert page.status == 200
    assert page.html == BODY


def test_the_public_extract_still_warns():
    import sluicer

    with pytest.warns(UserWarning, match="fetches nothing"):
        sluicer.extract(BODY)


def test_the_extract_command_on_a_file_holding_an_address_does_not_warn(
    tmp_path, no_warning
):
    from sluicer.cli import main

    page = tmp_path / "url.html"
    page.write_text(BODY)

    result = CliRunner().invoke(main, ["extract", str(page)])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "UserWarning" not in result.output
    assert result.exit_code == 1  # read, and gave nothing


def test_the_markdown_and_feed_commands_on_such_a_file_do_not_warn(
    tmp_path, no_warning
):
    from sluicer.cli import main

    page = tmp_path / "url.html"
    page.write_text(BODY)

    for command in (["markdown", "--front-matter"], ["feed"]):
        result = CliRunner().invoke(main, [*command, str(page)])
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            command,
            result.exception,
        )


def test_the_mcp_tools_on_a_fetched_address_body_do_not_warn(monkeypatch, no_warning):
    from test_mcp_server import fake_fetch, fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    fake_fetch(monkeypatch, html=BODY)

    answer = registered["extract_declared"]("https://example.com/url.html")
    assert answer["ok"] is True
    feed = registered["read_feed"]("https://example.com/url.html")
    assert feed["ok"] is False
