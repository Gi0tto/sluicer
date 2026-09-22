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


def absent(monkeypatch, *names):
    """Make ``names`` genuinely unimportable, submodules and all."""

    class Finder:
        def find_spec(self, name, path=None, target=None):
            for gone in names:
                if name == gone or name.startswith(gone + "."):
                    raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    for name in [n for n in list(sys.modules) if any(n == g or n.startswith(g + ".") for g in names)]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])


def test_extract_declared_without_the_fetch_extra_returns_the_sentence(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "scrapling")

    result = registered["extract_declared"]("https://example.com/p")

    assert "uv pip install 'sluicer[fetch]'" in result["error"]
    assert result["missing_extra"] == "fetch"


def test_fetch_page_without_the_fetch_extra_returns_the_sentence(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "scrapling")

    result = registered["fetch_page"]("https://example.com/p")

    assert "uv pip install 'sluicer[fetch]'" in result["error"]
    assert result["missing_extra"] == "fetch"


def test_page_markdown_without_the_markdown_extra_reports_it_as_an_error(monkeypatch):
    """Replaces a test that asserted the defect.

    Its first version asserted ``isinstance(result, str)`` and called that
    right, reasoning from the tool's declared return type instead of from what
    the reader of the result can tell apart. That is what let a failure keep
    the shape of a page's content all the way through a round of review.
    """
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "trafilatura")

    result = registered["page_markdown"]("<html><body>hi</body></html>")

    assert "uv pip install 'sluicer[markdown]'" in result["error"]
    assert result["missing_extra"] == "markdown"


def test_a_tool_that_works_is_left_alone_by_the_guard(monkeypatch):
    """The decorator must not change what a tool returns when nothing is missing."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"](
        '<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>'
    )

    assert "error" not in result
    assert result["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_real_bug_inside_a_tool_is_not_swallowed(monkeypatch):
    """Only a missing extra is turned into a result; everything else raises."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    with pytest.raises(ValueError):
        registered["fetch_page"]("not a url at all")


def test_page_markdown_returns_the_markdown_of_a_page_it_fetched(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<html><body><h1>Brake pad set</h1></body></html>")
    from test_markdown import fake_trafilatura

    fake_trafilatura(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert registered["page_markdown"]("https://example.com/p") == (
        "# Brake pad set\n\nReal content."
    )


def test_main_starts_the_server(monkeypatch):
    """The fake has recorded ``__ran__`` all along and nothing ever read it."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import main

    main()

    assert registered["__ran__"] is True


def test_a_missing_extra_is_never_mistakable_for_content(monkeypatch):
    """A failure must not wear the shape of a success, for any of the three.

    page_markdown returns a str when it works, so returning the explanation as
    a str handed an agent a sentence it could not tell apart from the page's
    own words -- it would summarise it, quote it, or act on it. A person at a
    terminal notices; an agent does not. So all three report a missing extra
    in one shape, and that shape is not the shape of any tool's content.
    """
    from collections.abc import Mapping

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "scrapling", "trafilatura")

    results = {
        "extract_declared": registered["extract_declared"]("https://example.com/p"),
        "page_markdown": registered["page_markdown"]("<html><body>hi</body></html>"),
        "fetch_page": registered["fetch_page"]("https://example.com/p"),
    }

    assert not isinstance(results["page_markdown"], str), (
        "page_markdown returned the explanation in the same shape as a page's "
        f"content: {results['page_markdown']!r}"
    )
    for name, result in results.items():
        assert isinstance(result, Mapping), f"{name} returned {type(result).__name__}"
        assert "error" in result, f"{name} carries no error key: {result!r}"
        assert "uv pip install 'sluicer[" in result["error"], name
