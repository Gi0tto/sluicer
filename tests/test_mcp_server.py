import sys
import types

import pytest


def fake_mcp(monkeypatch):
    """Stand in for the mcp SDK, recording every tool the server registers.

    The module and class names here are the ones mcp 2.x actually ships:
    ``mcp.server.mcpserver.MCPServer``. That matters more than it looks. This
    fake presented ``mcp.server.fastmcp.FastMCP`` for a whole branch, and 128
    tests passed against a class the installed package no longer has -- a fake
    can only ever confirm the shape you already believe in. The suite is not
    what catches that; installing the real package is.
    """
    registered = {}

    class MCPServer:
        def __init__(self, name):
            self.name = name

        def tool(self, *args, **kwargs):
            def decorate(function):
                registered[function.__name__] = function
                return function

            return decorate

        def run(self, transport="stdio", **kwargs):
            registered["__ran__"] = True

    server_module = types.ModuleType("mcp.server.mcpserver")
    server_module.MCPServer = MCPServer
    package = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    monkeypatch.setitem(sys.modules, "mcp", package)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", server_module)
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
    from sluicer.mcp_server import build_server

    fake_fetch(monkeypatch, html="<html>fetched</html>")

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


def fake_fetch(
    monkeypatch,
    landed_on="https://example.com/final",
    html="<html></html>",
    raises=None,
):
    """Stand in for the ladder, with the real ``fetch``'s signature and failures.

    Two things this fake has to be, both learned the hard way on this branch.

    It has the signature the real function has. Every fake here used to be
    ``def fetch(url)``, which is narrower than
    ``fetch(url, rungs=None, obey_robots=True, stealth=False,
    robots_reader=None)``: a caller that passed any of those would have blown
    up in production while the suite stayed green, and a parameter added to
    the real function would never be noticed here.
    ``test_the_fetch_fake_matches_the_real_fetch_signature`` pins that down.

    It can fail. A fake that can only succeed encodes the belief that fetching
    always succeeds, and that belief is what let ``RobotsRefused`` escape all
    three tools: the ladder raises it, and nothing here could even express the
    event. ``raises`` is the exception this fetch raises instead of returning,
    so a test can say what the tool does when the site says no.

    A redirect stays the default success, since it is the ordinary case: the
    tool must report where the fetch landed, which is what ``Fetched.url``
    carries, not the string the caller happened to type.
    """
    from sluicer.fetch.result import Fetched

    def fetch(url, rungs=None, obey_robots=True, stealth=False, robots_reader=None):
        if raises is not None:
            raise raises
        return Fetched(url=landed_on, html=html, status=200, rung="http")

    monkeypatch.setattr("sluicer.fetch.fetch", fetch)
    return fetch


def test_extract_declared_reports_the_url_it_landed_on(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(
        monkeypatch,
        html='<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script>'
        "</head><body></body></html>",
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


def test_an_mcp_that_is_installed_but_wrong_keeps_its_traceback(monkeypatch):
    """The wider ``mcp.*`` match is gone, and this is what it used to hide.

    Not hypothetical: mcp 2.x ships ``mcp/server/fastmcp.py`` as a module whose
    only job is to raise ``ModuleNotFoundError(name="mcp.server.fastmcp")``
    with its migration guide in the message. A wide match would report that as
    "the mcp package is not installed", sending a reader to install what they
    already have and discarding the only sentence that says what to do. So a
    missing submodule of a present package keeps its traceback, exactly as a
    missing ``scrapling.fetchers`` does.
    """

    class _NoServerModule:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp.server.mcpserver":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setattr(sys, "meta_path", [_NoServerModule(), *sys.meta_path])

    from sluicer.mcp_server import McpExtraMissing, _server_class

    with pytest.raises(ModuleNotFoundError) as raised:
        _server_class()

    assert not isinstance(raised.value, McpExtraMissing)


def absent(monkeypatch, *names):
    """Make ``names`` genuinely unimportable, submodules and all."""

    class Finder:
        def find_spec(self, name, path=None, target=None):
            for gone in names:
                if name == gone or name.startswith(gone + "."):
                    raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    for name in [
        n
        for n in list(sys.modules)
        if any(n == g or n.startswith(g + ".") for g in names)
    ]:
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


def test_the_fetch_fake_matches_the_real_fetch_signature(monkeypatch):
    """The fake crosses the seam, so the seam is where it has to be honest.

    Three times on this project a hand-written fake with a narrower signature
    than the real function kept a defect invisible. This is the cheap guard:
    if ``fetch`` grows, loses or renames a parameter, the fake stops matching
    and says so here rather than in production.
    """
    import inspect

    from sluicer.fetch import fetch as real_fetch

    fake = fake_fetch(monkeypatch)

    assert list(inspect.signature(fake).parameters) == list(
        inspect.signature(real_fetch).parameters
    )


def test_a_refusal_reaches_every_tool_as_an_answer_it_can_read(monkeypatch):
    """A site saying no must arrive as a result, not as an escaped exception.

    ``fetch`` raises ``RobotsRefused``, and an exception that leaves a tool
    body becomes whatever the SDK decides to do with it -- which is not this
    project's to promise, is not tested anywhere, and is not written down. The
    MCP server is the front door most likely to be aimed at an arbitrary URL,
    so this is where a refusal fires most often. The CLI already turns it into
    a message; this is the server's version of the same duty.
    """
    from collections.abc import Mapping

    from sluicer.fetch import RobotsRefused

    registered = fake_mcp(monkeypatch)
    url = "https://example.com/private/p"
    fake_fetch(monkeypatch, raises=RobotsRefused(url))
    from sluicer.mcp_server import build_server

    build_server()

    results = {
        "extract_declared": registered["extract_declared"](url),
        "page_markdown": registered["page_markdown"](url),
        "fetch_page": registered["fetch_page"](url),
    }

    for name, result in results.items():
        assert isinstance(result, Mapping), f"{name} returned {type(result).__name__}"
        assert "robots.txt" in result["error"], f"{name}: {result!r}"
        assert result["refused_by_robots"] == url, f"{name}: {result!r}"


def test_a_refusal_and_a_missing_extra_can_be_told_apart(monkeypatch):
    """Same shape, different discriminator: the reader must not have to guess.

    "The site refused us" and "you did not install an extra" call for opposite
    responses -- stop, versus run one install command -- so a reader that can
    only see ``error`` cannot act on either. The key beside it is what says
    which happened.
    """
    from sluicer.fetch import RobotsRefused

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    # The missing-extra case first: it needs the real ``fetch`` to run far
    # enough to look for scrapling. Patching the fake in afterwards is what
    # makes the second call a refusal instead.
    absent(monkeypatch, "scrapling")
    missing = registered["fetch_page"]("https://example.com/p")

    fake_fetch(monkeypatch, raises=RobotsRefused("https://example.com/private/p"))
    refused = registered["fetch_page"]("https://example.com/private/p")

    assert "refused_by_robots" in refused and "missing_extra" not in refused
    assert "missing_extra" in missing and "refused_by_robots" not in missing


def test_a_refusal_is_never_mistakable_for_a_page_s_own_words(monkeypatch):
    """``page_markdown`` returns a ``str`` when it works, so a refusal must not.

    The same reasoning as for a missing extra, and the same trap: a sentence
    handed back where a page's markdown goes is a sentence an agent will
    summarise, quote or act on.
    """
    from sluicer.fetch import RobotsRefused

    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, raises=RobotsRefused("https://example.com/private/p"))
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["page_markdown"]("https://example.com/private/p")

    assert not isinstance(result, str), f"a refusal came back as content: {result!r}"


def test_a_real_fetch_failure_is_still_not_swallowed(monkeypatch):
    """Only the two answers are turned into results; an operational failure raises.

    A connection that never opened is not an answer from the site, and giving
    it the shape of one would be the same defect this file keeps removing in
    the other direction.
    """
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, raises=ConnectionError("connection refused"))
    from sluicer.mcp_server import build_server

    build_server()

    with pytest.raises(ConnectionError):
        registered["fetch_page"]("https://example.com/p")
