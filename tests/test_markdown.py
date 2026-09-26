import json
import sys
import types
from pathlib import Path

import lxml.html
import pytest


def fake_trafilatura(monkeypatch, output="# Brake pad set\n\nReal content."):
    """Stand in for trafilatura so no test needs it installed."""
    seen = {}

    def extract(html, **kwargs):
        seen["called_with"] = (html, kwargs)
        return output

    module = types.ModuleType("trafilatura")
    module.extract = extract
    # trafilatura's own loader, which to_markdown uses to resolve the links.
    module.load_html = lxml.html.fromstring
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    return seen


def test_a_page_becomes_markdown(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    result = to_markdown("<html><body><h1>Brake pad set</h1></body></html>")

    assert result == "# Brake pad set\n\nReal content."
    assert seen["called_with"][1]["output_format"] == "markdown"


def test_every_option_trafilatura_is_given_is_the_one_asked_for(monkeypatch):
    """Assert all four kwargs, not just the format.

    ``output_format`` alone was asserted, so the three that carry the rest of
    the meaning went unwatched -- and ``url`` going in as ``None`` from a
    caller that had one was invisible for exactly that reason. Links and
    tables are what distinguish this from a plain text dump, and ``url`` is
    what lets trafilatura turn a relative link into one that can be followed.
    """
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    to_markdown("<html><body>hi</body></html>", url="https://example.com/p")

    passed = seen["called_with"][1]
    assert passed["output_format"] == "markdown"
    assert passed["include_links"] is True
    assert passed["include_tables"] is True
    assert passed["url"] == "https://example.com/p"


def test_a_page_with_no_url_gives_trafilatura_none(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    to_markdown("<html><body>hi</body></html>")

    assert seen["called_with"][1]["url"] is None


def test_a_page_with_no_main_content_gives_an_empty_string(monkeypatch):
    fake_trafilatura(monkeypatch, output=None)
    from sluicer.markdown import to_markdown

    assert to_markdown("<html><body></body></html>") == ""


def test_bytes_reach_trafilatura_undecoded(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    to_markdown(b"<html><body>hi</body></html>")

    assert isinstance(seen["called_with"][0], bytes)


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    class _NoTrafilatura:
        def find_module(self, name, path=None):
            return None

        def find_spec(self, name, path=None, target=None):
            if name == "trafilatura" or name.startswith("trafilatura."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.delitem(sys.modules, "trafilatura", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoTrafilatura(), *sys.meta_path])

    import sluicer.markdown as markdown_module

    with pytest.raises(markdown_module.MarkdownExtraMissing) as raised:
        markdown_module.to_markdown("<html><body>hi</body></html>")

    assert "sluicer[markdown]" in str(raised.value)


def test_front_matter_opens_the_markdown_with_what_the_page_declares(monkeypatch):
    fake_trafilatura(monkeypatch, output="The article.")
    from sluicer.markdown import to_markdown

    page = (
        '<html lang="en"><head>'
        '<meta property="og:title" content="A: title, &quot;quoted&quot;">'
        '<meta property="article:published_time" content="Jun 16, 2025"></head></html>'
    )

    out = to_markdown(page, front_matter=True)

    head, _, body = out.partition("\n---\n\n")
    lines = head.splitlines()
    assert lines[0] == "---"
    fields = dict(
        line.split(": ", 1)
        for line in lines[1:]
        if not line.startswith(" ") and ": " in line
    )
    # Every value is a JSON string, so a colon or a quote cannot break the YAML.
    assert json.loads(fields["title"]) == 'A: title, "quoted"'
    assert json.loads(fields["published"]) == "2025-06-16"
    assert '  title: "opengraph og:title"' in lines
    assert body == "The article."


def test_no_front_matter_unless_asked(monkeypatch):
    fake_trafilatura(monkeypatch, output="The article.")
    from sluicer.markdown import to_markdown

    page = '<meta property="og:title" content="T">'

    assert to_markdown(page) == "The article."


def test_a_page_that_declares_nothing_gets_no_front_matter(monkeypatch):
    fake_trafilatura(monkeypatch, output="The article.")
    from sluicer.markdown import to_markdown

    assert to_markdown("<p>plain</p>", front_matter=True) == "The article."


FIXTURES = Path(__file__).parent / "fixtures"


def _hrefs(given):
    return [a.get("href") for a in given.iter("a")]


def test_relative_links_go_to_trafilatura_resolved_against_the_page(monkeypatch):
    """trafilatura resolves against the site's root, so the page does it first.

    ``c.html`` on ``/a/b/page.html`` became ``https://example.com/c.html`` and
    ``#frag`` ``https://example.com#frag``: every relative link was broken.
    """
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    page = (
        '<html><body><a href="c.html">c</a><a href="#frag">f</a>'
        '<a href="../up.html">u</a><a href="/root.html">r</a>'
        '<a href="https://other.example/x">o</a><a href="{slot}">t</a>'
        "</body></html>"
    )
    to_markdown(page, url="https://example.com/a/b/page.html")

    given, passed = seen["called_with"]
    assert _hrefs(given) == [
        "https://example.com/a/b/c.html",
        "https://example.com/a/b/page.html#frag",
        "https://example.com/a/up.html",
        "https://example.com/root.html",
        "https://other.example/x",
        "{slot}",
    ]
    assert passed["url"] == "https://example.com/a/b/page.html"


def test_a_base_href_is_what_links_resolve_against(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    page = (
        '<html><head><base href="https://cdn.example/docs/"></head>'
        '<body><a href="c.html">c</a></body></html>'
    )
    to_markdown(page)

    assert _hrefs(seen["called_with"][0]) == ["https://cdn.example/docs/c.html"]


def test_markdown_links_lead_where_the_page_links(monkeypatch):
    """The real trafilatura, on a page whose address has a path."""
    pytest.importorskip("trafilatura")
    monkeypatch.delitem(sys.modules, "trafilatura", raising=False)
    from sluicer.markdown import to_markdown

    page = (FIXTURES / "article_relative_links.html").read_bytes()
    out = to_markdown(page, url="https://example.com/guide/brakes/fitting.html")

    assert "(https://example.com/guide/brakes/next.html)" in out
    assert "(https://example.com/guide/brakes/fitting.html#intro)" in out
    assert "(https://example.com/guide/overview.html)" in out
    assert "(https://example.com/index.html)" in out
    assert "(https://other.example/x)" in out


def test_the_markdown_command_resolves_links_against_the_page():
    pytest.importorskip("trafilatura")
    from click.testing import CliRunner

    from sluicer.cli import main

    result = CliRunner().invoke(
        main,
        [
            "--no-config",
            "markdown",
            str(FIXTURES / "article_relative_links.html"),
            "--url",
            "https://example.com/guide/brakes/fitting.html",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "(https://example.com/guide/brakes/next.html)" in result.output
    assert "(https://example.com/guide/brakes/fitting.html#intro)" in result.output
