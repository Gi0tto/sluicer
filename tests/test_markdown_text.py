"""Where a page's markdown came from, and the whole page as markdown
(sluicer.markdown's ``read_markdown`` and ``full``)."""

import sys
import types
from pathlib import Path

import lxml.html
import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "markdown"
NEWS = "https://news.example/2026/brakes"
TEASER = "Engineers tested the new ceramic pads on wet roads."


def fake_trafilatura(monkeypatch, output):
    """Stand in for trafilatura, its extraction ``output``."""
    calls = []

    def extract(html, **kwargs):
        calls.append(kwargs)
        return output

    module = types.ModuleType("trafilatura")
    module.extract = extract
    module.load_html = lxml.html.fromstring
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    return calls


def _page():
    return (FIXTURES / "declared_article.html").read_text(encoding="utf-8")


def test_the_main_content_is_said_to_be_trafilatura_s_extraction(monkeypatch):
    calls = fake_trafilatura(monkeypatch, TEASER)
    from sluicer.markdown import MainText, read_markdown, to_markdown

    found = read_markdown(_page(), url=NEWS)

    assert found == MainText(TEASER, "extracted", "trafilatura", None)
    assert to_markdown(_page(), url=NEWS) == TEASER
    # One extraction, asked for as 0.9.1 asked for it.
    assert [sorted(call) for call in calls] == [
        ["include_links", "include_tables", "output_format", "url"]
    ] * 2


def test_front_matter_says_where_the_text_came_from(monkeypatch):
    fake_trafilatura(monkeypatch, TEASER)
    from sluicer.markdown import to_markdown

    out = to_markdown(_page(), url=NEWS, front_matter=True)
    head, _, body = out.partition("\n---\n\n")

    assert '  text: "extracted trafilatura"' in head.splitlines()
    assert body == TEASER


def test_no_text_is_said_to_come_from_nowhere(monkeypatch):
    fake_trafilatura(monkeypatch, None)
    from sluicer.markdown import MainText, read_markdown, to_markdown

    page = "<html><body></body></html>"

    assert read_markdown(page) == read_markdown(page, full=True) == MainText("", "", "")
    assert to_markdown(page, front_matter=True) == ""


def test_the_whole_page_needs_no_extra(monkeypatch):
    class _NoTrafilatura:
        def find_spec(self, name, path=None, target=None):
            if name == "trafilatura" or name.startswith("trafilatura."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.delitem(sys.modules, "trafilatura", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoTrafilatura(), *sys.meta_path])
    import sluicer.markdown as markdown_module

    found = markdown_module.read_markdown(_page(), url=NEWS, full=True)

    assert (found.source, found.method, found.where) == ("page", "", None)
    assert found.markdown.startswith(
        "[Home](https://news.example/) [News](https://news.example/news)\n\n"
        "# New pads cut stopping distance"
    )
    assert "[Subscribe to read the rest](https://news.example/subscribe)" in (
        found.markdown
    )
    assert "@context" not in found.markdown
    with pytest.raises(markdown_module.MarkdownExtraMissing):
        markdown_module.read_markdown(_page(), url=NEWS)


def test_the_markdown_command_prints_the_whole_page_with_full(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "page.html"
    page.write_text(_page(), encoding="utf-8")

    result = CliRunner().invoke(
        main, ["--no-config", "markdown", str(page), "--url", NEWS, "--full"]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("[Home](https://news.example/)")


def test_page_markdown_says_where_its_text_came_from(monkeypatch):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    fake_trafilatura(monkeypatch, TEASER)
    from sluicer.mcp_server import build_server

    build_server()

    main = registered["page_markdown"](_page())
    whole = registered["page_markdown"](_page(), full=True)

    assert main["ok"] is True and main["markdown"] == TEASER
    assert main["text_from"] == {
        "source": "extracted",
        "method": "trafilatura",
        "where": None,
    }
    assert whole["text_from"] == {"source": "page", "method": "", "where": None}
    assert whole["markdown"].startswith("[Home](/)")
