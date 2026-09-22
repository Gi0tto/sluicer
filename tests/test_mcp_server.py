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
