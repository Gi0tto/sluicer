import sys
import types

import pytest


def fake_mcp(monkeypatch):
    """Stand in for the mcp SDK, recording every tool the server registers."""
    registered = {}

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self, *args, **kwargs):
            def decorate(function):
                registered[function.__name__] = function
                return function

            return decorate

        def run(self):
            registered["__ran__"] = True

    server_module = types.ModuleType("mcp.server.fastmcp")
    server_module.FastMCP = FastMCP
    package = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    monkeypatch.setitem(sys.modules, "mcp", package)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", server_module)
    return registered


def test_the_server_registers_the_three_tools(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert set(registered) == {"extract_declared", "page_markdown", "fetch_page"}


def test_extract_declared_reads_html_given_directly(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"](
        '<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>'
    )

    assert result["sources"] == ["jsonld"]
    assert result["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    import importlib

    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])

    import sluicer.mcp_server as server_module

    importlib.reload(server_module)
    with pytest.raises(server_module.McpExtraMissing) as raised:
        server_module.build_server()

    assert "sluicer[mcp]" in str(raised.value)


def test_fetch_page_refuses_something_that_is_not_a_url(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    literal_html = "<html><body>hi</body></html>"
    with pytest.raises(ValueError) as raised:
        registered["fetch_page"](literal_html)

    assert literal_html in str(raised.value)


def test_fetch_page_still_accepts_a_url(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.fetch.result import Fetched
    from sluicer.mcp_server import build_server

    def fake_fetch(url):
        return Fetched(url=url, html="<html>fetched</html>", status=200, rung="http")

    monkeypatch.setattr("sluicer.fetch.fetch", fake_fetch)

    build_server()
    result = registered["fetch_page"]("https://example.com/p")

    assert result["html"] == "<html>fetched</html>"
    assert result["fetch"]["rung"] == "http"


def test_running_without_the_extra_is_a_message_not_a_traceback(monkeypatch, capsys):
    import importlib

    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])

    import sluicer.mcp_server as server_module

    importlib.reload(server_module)

    with pytest.raises(SystemExit) as raised:
        server_module.main()

    assert raised.value.code == 1
    captured = capsys.readouterr()
    assert "sluicer[mcp]" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def fake_fetch(monkeypatch, landed_on="https://example.com/final", html="<html></html>"):
    """Stand in for the ladder, landing on a URL that is not the one asked for.

    A redirect is the ordinary case, so the fake models it: the tool must
    report where the fetch landed, which is what ``Fetched.url`` carries,
    not the string the caller happened to type.
    """
    from sluicer.fetch.result import Fetched

    def fetch(url):
        return Fetched(url=landed_on, html=html, status=200, rung="http")

    monkeypatch.setattr("sluicer.fetch.fetch", fetch)


def test_extract_declared_reports_the_url_it_landed_on(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(
        monkeypatch,
        html='<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>',
    )
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"]("https://example.com/p")

    assert result["url"] == "https://example.com/final"
    assert result["fetch"]["rung"] == "http"


def test_extract_declared_reports_no_url_for_literal_html(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"]("<html><body>hi</body></html>")

    assert result["url"] is None
    assert "fetch" not in result


def test_page_markdown_hands_trafilatura_the_url_it_landed_on(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch)
    from test_markdown import fake_trafilatura

    seen = fake_trafilatura(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    registered["page_markdown"]("https://example.com/p")

    assert seen["called_with"][1]["url"] == "https://example.com/final"


def test_page_markdown_hands_trafilatura_no_url_for_literal_html(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from test_markdown import fake_trafilatura

    seen = fake_trafilatura(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["page_markdown"]("<html><body>hi</body></html>")

    assert seen["called_with"][1]["url"] is None
    assert result == "# Brake pad set\n\nReal content."


def test_an_mcp_that_is_installed_but_too_old_keeps_its_traceback(monkeypatch):
    """The wider ``mcp.*`` match is gone, and this is what it used to hide.

    ``mcp`` is pinned ``>=1.2``, the first release carrying
    ``mcp.server.fastmcp``, so installing ``sluicer[mcp]`` cannot leave the
    submodule absent. If it is absent anyway the package is there and is too
    old or broken, and "install it with uv pip install" is advice that cannot
    help someone who already installed it. Same rule as a missing
    ``scrapling.fetchers``: it is a bug, so it is a traceback.
    """

    class _NoFastMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp.server.fastmcp":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setattr(sys, "meta_path", [_NoFastMcp(), *sys.meta_path])

    from sluicer.mcp_server import McpExtraMissing, _fastmcp

    with pytest.raises(ModuleNotFoundError) as raised:
        _fastmcp()

    assert not isinstance(raised.value, McpExtraMissing)
