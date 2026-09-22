import sys
import types

import pytest


def fake_trafilatura(monkeypatch, output="# Brake pad set\n\nReal content."):
    """Stand in for trafilatura so no test needs it installed."""
    seen = {}

    def extract(html, **kwargs):
        seen["called_with"] = (html, kwargs)
        return output

    module = types.ModuleType("trafilatura")
    module.extract = extract
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

    to_markdown("<html><body>hi</body></html>".encode())

    assert isinstance(seen["called_with"][0], bytes)


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    import importlib

    class _NoTrafilatura:
        def find_module(self, name, path=None):
            return None

        def find_spec(self, name, path=None, target=None):
            if name == "trafilatura" or name.startswith("trafilatura."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    monkeypatch.delitem(sys.modules, "trafilatura", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoTrafilatura(), *sys.meta_path])

    import sluicer.markdown as markdown_module

    importlib.reload(markdown_module)
    with pytest.raises(markdown_module.MarkdownExtraMissing) as raised:
        markdown_module.to_markdown("<html><body>hi</body></html>")

    assert "sluicer[markdown]" in str(raised.value)
