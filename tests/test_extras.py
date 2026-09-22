"""One rule for "the extra is missing", owned in one place.

The three lazy-import helpers each re-decided what "missing" means, and the
third decided differently. These tests pin the single rule down so the next
entry point cannot drift from it.
"""

import sys
import types

import pytest


def _absent(*names):
    """A meta_path finder that makes ``names`` and their submodules unimportable."""

    class Finder:
        def find_spec(self, name, path=None, target=None):
            for absent in names:
                if name == absent or name.startswith(absent + "."):
                    raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    return Finder()


def test_import_extra_returns_the_module_it_imported(monkeypatch):
    from sluicer.extras import import_extra

    module = types.ModuleType("pretend_package")
    monkeypatch.setitem(sys.modules, "pretend_package", module)

    assert import_extra("pretend_package", "fetch", doing="Doing the thing") is module


def test_an_absent_package_becomes_a_missing_extra_naming_the_extra(monkeypatch):
    from sluicer.extras import MissingExtra, import_extra

    monkeypatch.delitem(sys.modules, "pretend_package", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_absent("pretend_package"), *sys.meta_path])

    with pytest.raises(MissingExtra) as raised:
        import_extra("pretend_package.inner", "fetch", doing="Doing the thing")

    assert raised.value.extra == "fetch"
    assert "uv pip install 'sluicer[fetch]'" in str(raised.value)
    assert "Doing the thing needs pretend_package" in str(raised.value)


def test_a_missing_submodule_of_a_present_package_keeps_its_traceback(monkeypatch):
    """A broken install must not be told to install what is already there."""
    from sluicer.extras import MissingExtra, import_extra

    monkeypatch.setitem(sys.modules, "pretend_package", types.ModuleType("pretend_package"))
    monkeypatch.setattr(sys, "meta_path", [_absent("pretend_package.inner"), *sys.meta_path])

    with pytest.raises(ModuleNotFoundError) as raised:
        import_extra("pretend_package.inner", "fetch", doing="Doing the thing")

    assert not isinstance(raised.value, MissingExtra)


def test_a_plain_import_error_from_inside_a_working_install_is_re_raised(monkeypatch):
    from sluicer.extras import MissingExtra, import_extra

    class Broken:
        def find_spec(self, name, path=None, target=None):
            if name == "pretend_package":
                raise ImportError("something inside the package is broken")
            return None

    monkeypatch.delitem(sys.modules, "pretend_package", raising=False)
    monkeypatch.setattr(sys, "meta_path", [Broken(), *sys.meta_path])

    with pytest.raises(ImportError) as raised:
        import_extra("pretend_package", "fetch", doing="Doing the thing")

    assert not isinstance(raised.value, MissingExtra)


def test_the_package_shown_in_the_message_can_be_spelled_for_a_human(monkeypatch):
    """"the mcp package" reads better than "mcp"; the sentence is not the module."""
    from sluicer.extras import MissingExtra, import_extra

    monkeypatch.delitem(sys.modules, "mcp", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_absent("mcp"), *sys.meta_path])

    with pytest.raises(MissingExtra) as raised:
        import_extra(
            "mcp.server.mcpserver",
            "mcp",
            doing="Running the MCP server",
            package="the mcp package",
        )

    assert str(raised.value) == (
        "Running the MCP server needs the mcp package, which is not installed. "
        "Install it with: uv pip install 'sluicer[mcp]'"
    )


def test_the_three_named_extras_are_all_one_kind(monkeypatch):
    """The names stay -- the CLI catches them -- but the rule is one rule."""
    from sluicer.extras import MissingExtra
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing
    from sluicer.markdown import MarkdownExtraMissing
    from sluicer.mcp_server import McpExtraMissing

    for named in (FetchExtraMissing, MarkdownExtraMissing, McpExtraMissing):
        assert issubclass(named, MissingExtra)
        assert issubclass(named, ImportError)


def test_the_named_subclass_is_what_gets_raised(monkeypatch):
    """The rule is shared; the label is not.

    ``sluicer.cli`` catches ``FetchExtraMissing`` and ``MarkdownExtraMissing``
    by name and prints their message instead of a traceback, so the helper has
    to raise the caller's own class rather than the base one.
    """
    from sluicer.extras import MissingExtra, import_extra

    class PretendMissing(MissingExtra):
        pass

    monkeypatch.delitem(sys.modules, "pretend_package", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_absent("pretend_package"), *sys.meta_path])

    with pytest.raises(PretendMissing) as raised:
        import_extra("pretend_package", "fetch", doing="Doing the thing", error=PretendMissing)

    assert raised.value.extra == "fetch"
