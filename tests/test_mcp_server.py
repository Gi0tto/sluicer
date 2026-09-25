import json
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
        def __init__(self, name, **kwargs):
            self.name = name
            registered["__options__"] = kwargs

        def tool(self, *args, **kwargs):
            def decorate(function):
                registered[function.__name__] = function
                registered.setdefault("__tool_options__", {})[function.__name__] = (
                    kwargs
                )
                return function

            return decorate

        def run(self, transport="stdio", **kwargs):
            registered["__ran__"] = True

    class ToolAnnotations(dict):
        """What the SDK's ToolAnnotations was given."""

        def __init__(self, **hints):
            super().__init__(hints)

    server_module = types.ModuleType("mcp.server.mcpserver")
    server_module.MCPServer = MCPServer
    package = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    types_module = types.ModuleType("mcp.types")
    types_module.ToolAnnotations = ToolAnnotations
    monkeypatch.setitem(sys.modules, "mcp", package)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", server_module)
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)
    return registered


TOOLS = {
    "extract_declared",
    "page_markdown",
    "fetch_page",
    "compile_extractor",
    "run_extractor",
    "heal_extractor",
    "audit_page",
    "read_feed",
    "map_site",
    "crawl_site",
    "extract_many",
    "select_values",
}


def test_the_server_registers_its_twelve_tools(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert {name for name in registered if not name.startswith("__")} == TOOLS


def test_every_tool_says_it_only_reads_and_has_a_title(monkeypatch):
    """Codex's writes mode and Claude Code run a tool without asking when it
    says it is read-only; without the hint, every call to a tool that only
    reads waited for a person to approve it, and codex exec cancelled it."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    options = registered["__tool_options__"]
    assert set(options) == TOOLS
    for name, given in options.items():
        hints = given["annotations"]
        assert given["title"] and hints["title"] == given["title"], name
        assert hints["read_only_hint"] is True, name
        assert hints["destructive_hint"] is False, name
        assert hints["idempotent_hint"] is True, name
        assert hints["open_world_hint"] is True, name
    assert len({given["title"] for given in options.values()}) == len(TOOLS)


def test_the_module_names_every_tool_it_registers_and_counts_them():
    """A review found the docstring still saying "Nine tools" after the tenth."""
    import re

    import sluicer.mcp_server as module

    doc = module.__doc__ or ""
    listed = doc.split(" tools -- ", 1)[1].split(" -- ", 1)[0]
    assert set(re.findall(r"``([a-z_]+)``", listed)) == TOOLS
    count = {10: "ten", 11: "eleven", 12: "twelve"}[len(TOOLS)]
    assert f"{count.capitalize()} tools -- " in doc
    assert f"with its {count} tools registered" in (module.build_server.__doc__ or "")


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


def test_extract_declared_guesses_the_visible_page_only_when_asked(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    page = "<html><body><h1>Brake pads</h1><p>By Ada Lovelace</p></body></html>"

    assert "visible" not in registered["extract_declared"](page)
    shown = registered["extract_declared"](page, visible=True)["visible"]
    assert shown["author"] == {
        "value": "Ada Lovelace",
        "where": "/html/body/p",
        "rule": "by-line",
    }


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])

    import sluicer.mcp_server as server_module

    with pytest.raises(server_module.McpExtraMissing) as raised:
        server_module.build_server()

    assert "sluicer[mcp]" in str(raised.value)


def test_fetch_page_refuses_something_that_is_not_a_url(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    literal_html = "<html><body>hi</body></html>"
    result = registered["fetch_page"](literal_html)

    assert result["error"]["code"] == "bad_input"
    assert literal_html in result["error"]["message"]


def test_fetch_page_still_accepts_a_url(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    fake_fetch(monkeypatch, html="<html>fetched</html>")

    build_server()
    result = registered["fetch_page"]("https://example.com/p")

    assert result["html"] == "<html>fetched</html>"
    assert result["fetch"]["rung"] == "http"


def test_running_without_the_extra_is_a_message_not_a_traceback(monkeypatch, capsys):
    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])

    import sluicer.mcp_server as server_module

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
    headers=None,
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

    def fetch(
        url,
        rungs=None,
        obey_robots=True,
        stealth=False,
        robots_reader=None,
        allow_private=True,
        resolve=None,
        max_bytes=None,
        proxy=None,
        headers=None,
        cookies=None,
        memory=None,
    ):
        fetch.calls.append({"url": url, "allow_private": allow_private})
        if raises is not None:
            raise raises
        return Fetched(
            url=landed_on, html=html, status=200, rung="http", headers=answered
        )

    # Named apart: the real signature's own ``headers`` is what a caller sends.
    answered = headers or {}
    fetch.calls = []

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


def test_extract_declared_reads_the_response_headers_and_never_returns_them(
    monkeypatch,
):
    registered = fake_mcp(monkeypatch)
    fake_fetch(
        monkeypatch,
        html="<html><head><title>T</title></head></html>",
        headers={
            "link": "</canonical>; rel=canonical",
            "x-robots-tag": "noai",
            "set-cookie": "session=secret",
        },
    )
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"]("https://example.com/p")

    assert result["links"]["canonical"] == "https://example.com/canonical"
    assert result["rights"]["http"] == {"robots": ["noai"]}
    assert "secret" not in json.dumps(result)


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
    assert result["markdown"] == "# Brake pad set\n\nReal content."


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


def _web_of_one_page(monkeypatch, html):
    """The real ladder, over the fake wire, a name that resolves publicly, and
    no browser: what an MCP server installed with no fetching extra has."""
    import socket

    from fake_wire import fake_http

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, 0))],
    )
    return fake_http(
        monkeypatch,
        [(404, b"", {}), (200, html.encode(), {"Content-Type": "text/html"})],
    )


PUBLIC = "93.184.215.14"


def test_extract_declared_reads_a_url_with_no_fetching_extra(monkeypatch):
    """Until 0.8 a URL needed scrapling even for plain HTTP, and the tool
    answered missing_extra; the base install fetches now."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "scrapling", "playwright")
    page = (
        '<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script></head>'
        "<body>" + "Real content. " * 40 + "</body></html>"
    )
    seen = _web_of_one_page(monkeypatch, page)

    result = registered["extract_declared"]("https://example.com/p")

    assert result["ok"] is True, result
    assert result["fetch"]["rung"] == "http"
    assert [r.target for r in seen.requests] == ["/robots.txt", "/p"]
    assert seen.targets[0].addresses == (PUBLIC,), "the server's fetches are pinned"


def test_fetch_page_reads_a_url_with_no_fetching_extra(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "scrapling", "playwright")
    _web_of_one_page(monkeypatch, "<html><body>" + "Words. " * 60 + "</body></html>")

    result = registered["fetch_page"]("https://example.com/p")

    assert result["ok"] is True, result
    assert "Words." in result["html"]


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

    assert 'uv pip install "sluicer[markdown]"' in result["error"]["message"]
    assert result["error"] | {"message": ""} == {
        "code": "missing_extra",
        "message": "",
        "retryable": False,
        "extra": "markdown",
    }


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
    """Only the named answers become results; anything else raises."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    monkeypatch.setattr(
        "sluicer.mcp_server.extract", lambda *a, **k: (_ for _ in ()).throw(ValueError)
    )
    build_server()

    with pytest.raises(ValueError):
        registered["extract_declared"]("<html></html>")


def test_page_markdown_returns_the_markdown_of_a_page_it_fetched(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<html><body><h1>Brake pad set</h1></body></html>")
    from test_markdown import fake_trafilatura

    fake_trafilatura(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert registered["page_markdown"]("https://example.com/p")["markdown"] == (
        "# Brake pad set\n\nReal content."
    )


def test_main_starts_the_server(monkeypatch):
    """The fake has recorded ``__ran__`` all along and nothing ever read it."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import main

    main()

    assert registered["__ran__"] is True


def test_a_missing_extra_is_never_mistakable_for_content(monkeypatch):
    """A failure must not wear the shape of a success.

    page_markdown returns a str when it works, so returning the explanation as
    a str handed an agent a sentence it could not tell apart from the page's
    own words -- it would summarise it, quote it, or act on it. A person at a
    terminal notices; an agent does not. So a missing extra is reported in one
    shape, and that shape is not the shape of any tool's content. Until 0.8
    extract_declared and fetch_page could lack theirs too; fetching needs no
    extra now, and page_markdown is the one left.
    """
    from collections.abc import Mapping

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    absent(monkeypatch, "trafilatura")

    results = {
        "page_markdown": registered["page_markdown"]("<html><body>hi</body></html>"),
    }

    assert not isinstance(results["page_markdown"], str), (
        "page_markdown returned the explanation in the same shape as a page's "
        f"content: {results['page_markdown']!r}"
    )
    for name, result in results.items():
        assert isinstance(result, Mapping), f"{name} returned {type(result).__name__}"
        assert "error" in result, f"{name} carries no error key: {result!r}"
        assert 'uv pip install "sluicer[' in result["error"]["message"], name


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
        assert "robots.txt" in result["error"]["message"], f"{name}: {result!r}"
        assert (
            result["error"]["url"] == url
            and result["error"]["code"] == "refused_by_robots"
        ), f"{name}: {result!r}"


def test_a_challenge_page_is_answered_as_the_site_refusing(monkeypatch):
    """The last rung's challenge page came back ok: true, a waiting room's
    words read as the page's."""
    from sluicer.fetch import SiteRefused

    registered = fake_mcp(monkeypatch)
    url = "https://example.com/p"
    reason = "the response is a challenge page, not the content: 'just a moment'"
    fake_fetch(monkeypatch, raises=SiteRefused(url, [], reason))
    from sluicer.mcp_server import build_server

    build_server()

    for name in ("extract_declared", "page_markdown", "fetch_page"):
        answer = registered[name](url)
        assert answer["ok"] is False, name
        assert answer["error"]["code"] == "refused_by_site", name
        assert answer["error"]["retryable"] is False, name
        assert answer["error"]["url"] == url, name
        assert "just a moment" in answer["error"]["message"], name


def test_a_site_that_asks_to_be_paid_is_answered_so(monkeypatch):
    from sluicer.fetch import PaymentRequired

    registered = fake_mcp(monkeypatch)
    url = "https://example.com/p"
    fake_fetch(monkeypatch, raises=PaymentRequired(url, []))
    from sluicer.mcp_server import build_server

    build_server()

    answer = registered["extract_declared"](url)
    assert answer["ok"] is False
    assert answer["error"]["code"] == "payment_required"
    assert answer["error"]["retryable"] is False
    assert "402" in answer["error"]["message"]


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

    # The missing-extra case: page_markdown is the one tool whose extra an
    # install can lack, now that fetching needs none.
    absent(monkeypatch, "trafilatura")
    missing = registered["page_markdown"]("<html><body>hi</body></html>")

    fake_fetch(monkeypatch, raises=RobotsRefused("https://example.com/private/p"))
    refused = registered["fetch_page"]("https://example.com/private/p")

    assert refused["error"]["code"] == "refused_by_robots"
    assert missing["error"]["code"] == "missing_extra"


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


def test_a_fetch_that_failed_says_what_failed_rather_than_raising(monkeypatch):
    """Raised, it reached the agent as a bare "Error executing tool fetch_page"."""
    from sluicer.fetch import FetchFailed

    registered = fake_mcp(monkeypatch)
    fake_fetch(
        monkeypatch,
        raises=FetchFailed("https://example.com/p", [], "connection refused"),
    )
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["fetch_page"]("https://example.com/p")

    assert result["error"]["url"] == "https://example.com/p"
    assert result["error"]["code"] == "fetch_failed"
    assert result["error"]["retryable"] is True
    assert "connection refused" in result["error"]["message"]


def test_a_real_bug_below_the_fetch_is_still_not_swallowed(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, raises=KeyError("a bug"))
    from sluicer.mcp_server import build_server

    build_server()

    with pytest.raises(KeyError):
        registered["fetch_page"]("https://example.com/p")


def test_the_server_refuses_private_addresses_unless_told_otherwise(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fetch = fake_fetch(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
    registered["fetch_page"]("https://example.com/p")
    monkeypatch.setenv("SLUICER_ALLOW_PRIVATE", "1")
    registered["fetch_page"]("https://example.com/p")

    assert [call["allow_private"] for call in fetch.calls] == [False, True]


def test_a_large_page_is_read_in_slices_that_join_back_to_the_whole(monkeypatch):
    """Claude Code keeps a tool answer to 25,000 tokens and puts a larger one
    in a file: the 200,000 characters fetch_page used to return were over that
    on most real pages. A slice says where the next one starts."""
    from sluicer.mcp_server import MOST_CHARS

    page = "".join(f"<p>{n}</p>" for n in range(20_000))
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html=page)
    from sluicer.mcp_server import build_server

    build_server()
    first = registered["fetch_page"]("https://example.com/p")
    assert first["truncated"] is True and first["length"] == len(page)
    assert len(first["html"]) <= MOST_CHARS and first["next_offset"] == len(
        first["html"]
    )
    slices, offset = [], 0
    while offset is not None:
        got = registered["fetch_page"]("https://example.com/p", offset=offset)
        slices.append(got["html"])
        offset = got["next_offset"]
    assert "".join(slices) == page
    assert got["truncated"] is False


def test_a_slice_larger_than_an_answer_may_be_is_refused(monkeypatch):
    from sluicer.mcp_server import MOST_CHARS

    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<p>x</p>")
    from sluicer.mcp_server import build_server

    build_server()
    big = registered["fetch_page"]("https://example.com/p", max_chars=MOST_CHARS + 1)
    assert big["ok"] is False and big["error"]["code"] == "bad_input"
    past = registered["fetch_page"]("https://example.com/p", offset=10_000)
    assert past["ok"] is False and past["error"]["code"] == "bad_input"


def test_markdown_is_read_in_slices_too(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<html></html>")
    import sluicer.mcp_server as server_module

    text = "".join(f"line {n}\n" for n in range(10_000))
    monkeypatch.setattr(server_module, "to_markdown", lambda *a, **k: text)
    server_module.build_server()
    slices, offset = [], 0
    while offset is not None:
        got = registered["page_markdown"]("https://example.com/p", offset=offset)
        assert got["ok"] is True and got["length"] == len(text)
        slices.append(got["markdown"])
        offset = got["next_offset"]
    assert "".join(slices) == text and len(slices) > 1


def test_extract_declared_answers_without_records_when_asked(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    page = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "Product", "name": "Pads", "offers": {"price": "41.90"}}'
        "</script></head></html>"
    )
    whole = registered["extract_declared"](page)
    brief = registered["extract_declared"](page, records=False)
    assert whole["records"] and "records" not in brief
    assert brief["summary"] == whole["summary"]


def test_records_too_large_for_an_answer_are_left_out_and_counted(monkeypatch):
    registered = fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    monkeypatch.setattr(server_module, "MOST_ANSWER_BYTES", 2_000)
    server_module.build_server()
    items = ",".join(
        f'{{"@type": "Product", "name": "Item {n}", "description": "{"word " * 20}"}}'
        for n in range(40)
    )
    page = f'<script type="application/ld+json">[{items}]</script>'
    got = registered["extract_declared"](page)
    assert got["ok"] is True and "records" not in got
    assert got["records_left_out"] == 40
    assert got["sources"] == ["jsonld"]
    whole = server_module._bytes_of(got)
    assert whole < server_module.MOST_ANSWER_BYTES


def test_the_server_reports_its_own_version(monkeypatch):
    import sluicer

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert registered["__options__"]["version"] == sluicer.__version__


def _drift(name):
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "drift" / name).read_text(
        encoding="utf-8"
    )


def test_an_agent_compiles_an_extractor_and_replays_it(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"](
        [_drift("shop_v1.html"), _drift("shop_v1_page2.html")]
    )
    good = registered["run_extractor"](learnt["extractor"], _drift("shop_v1.html"))
    bad = registered["run_extractor"](
        learnt["extractor"], _drift("shop_prices_gone.html")
    )

    assert learnt["extractor"]["listing"]["member"] == "li.product"
    assert good["ok"] is True and len(good["rows"]) == 6
    assert bad["ok"] is False
    assert bad["failed"][0]["name"] == "field"


def test_an_agent_names_the_columns_it_wants_by_example(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"](
        [_drift("shop_v1.html")], want={"title": "Sapiens", "price": "54.23"}
    )
    run = registered["run_extractor"](learnt["extractor"], _drift("shop_v1_page2.html"))
    missing = registered["compile_extractor"](
        [_drift("shop_v1.html")], want={"price": "1.00"}
    )
    own = registered["compile_extractor"](
        [_drift("shop_v1.html")], listing=False, want={"price": "54.23"}
    )
    replayed = registered["run_extractor"](own["extractor"], _drift("shop_v1.html"))

    assert run["ok"] is True
    assert set(run["rows"][0]) == {"title", "price"}
    assert missing["ok"] is False and missing["error"]["code"] == "bad_input"
    assert "price='1.00'" in missing["error"]["message"]
    assert replayed["ok"] is True and replayed["fields"] == {"price": "£54.23"}
    assert run["fields"] == {}


def test_an_agent_heals_an_extractor_after_a_redesign(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"]([_drift("shop_v1.html")])
    healed = registered["heal_extractor"](
        learnt["extractor"], [_drift("shop_redesigned.html")]
    )
    run = registered["run_extractor"](
        healed["extractor"], _drift("shop_redesigned.html")
    )

    moved = {c["before"]: c["after"] for c in healed["changes"] if c["kind"] == "moved"}
    assert moved["span.price"] == "div.cost"
    assert run["ok"] is True
    assert set(run["rows"][0]) == {
        "a.title",
        "a.title@href",
        "span.price",
        "span.stock",
    }


def test_an_agent_selects_values_and_sees_where_each_is(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    prices = registered["select_values"](_drift("shop_v1.html"), "span.price::text")
    links = registered["select_values"](_drift("shop_v1.html"), "//li[1]/a/@href")
    nothing = registered["select_values"](_drift("shop_v1.html"), "table")
    broken = registered["select_values"](_drift("shop_v1.html"), "td[")

    assert prices["ok"] is True and prices["count"] == 6
    assert prices["values"][0] == {
        "value": "£51.77",
        "where": "/html/body/div[1]/ol[1]/li[1]/span[1]",
    }
    assert links["values"] == [
        {"value": "/book/1", "where": "/html/body/div[1]/ol[1]/li[1]/a[1]"}
    ]
    assert nothing["ok"] is True and nothing["values"] == [] and nothing["count"] == 0
    assert broken["ok"] is False and broken["error"]["code"] == "bad_input"
    assert "'td['" in broken["error"]["message"]


def test_values_past_the_bound_are_left_out_and_counted(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    rows = "".join(f"<li>{'word ' * 40}{n}</li>" for n in range(2_000))

    got = registered["select_values"](f"<ul>{rows}</ul>", "li")

    assert got["ok"] is True and got["count"] == 2_000
    assert got["values_left_out"] == 2_000 - len(got["values"]) > 0
    assert len(json.dumps(got).encode()) <= 75_000


def test_an_agent_writes_an_extractor_by_selectors(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    written = registered["compile_extractor"](
        [_drift("shop_v1.html")],
        select={"title": "a.title", "price": "span.price"},
        rows="li.product",
    )
    good = registered["run_extractor"](written["extractor"], _drift("shop_v1.html"))
    bad = registered["run_extractor"](
        written["extractor"], _drift("shop_redesigned.html")
    )
    healed = registered["heal_extractor"](
        written["extractor"], [_drift("shop_redesigned.html")]
    )
    bare = registered["compile_extractor"]([], select={"name": "h1"})
    unread = registered["compile_extractor"]([], select={"name": "h1["})

    assert written["extractor"]["format"] == 3
    assert good["ok"] is True and good["rows"][0]["price"] == "£51.77"
    assert bad["ok"] is False and bad["failed"][0]["name"] == "listing"
    assert healed["ok"] is False and healed["lost"] is True
    assert [c["kind"] for c in healed["changes"]] == ["broken"]
    assert bare["ok"] is True
    assert unread["error"]["code"] == "bad_input"


def test_a_bad_extractor_or_no_page_is_a_bad_input(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert (
        registered["run_extractor"]({"format": 99}, "<p>x</p>")["error"]["code"]
        == "bad_input"
    )
    assert registered["compile_extractor"]([])["error"]["code"] == "bad_input"
    assert registered["compile_extractor"](["<p>x</p>"])["error"]["code"] == "bad_input"
    learnt = registered["compile_extractor"]([_drift("shop_v1.html")])
    assert (
        registered["heal_extractor"](learnt["extractor"], [])["error"]["code"]
        == "bad_input"
    )
    assert (
        registered["heal_extractor"](learnt["extractor"], ["<p>x</p>"])["error"]["code"]
        == "bad_input"
    )


def test_every_answer_can_be_checked_on_ok_alone(monkeypatch):
    """``ok`` is true exactly when the answer can be used as it is."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    page = (
        '<script type="application/ld+json">{"@type":"Product","name":"Pad"}</script>'
    )
    learnt = registered["compile_extractor"]([_drift("shop_v1.html")])

    assert registered["extract_declared"](page)["ok"] is True
    assert learnt["ok"] is True
    assert registered["compile_extractor"]([])["ok"] is False


def test_a_heal_that_lost_data_is_not_ok(monkeypatch):
    """The CLI exits 3 and writes nothing; the tool says ok false and why."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"]([_drift("shop_v1.html")])
    healed = registered["heal_extractor"](
        learnt["extractor"], [_drift("shop_prices_gone.html")]
    )

    assert healed["lost"] is True
    assert healed["ok"] is False
    assert "error" not in healed
    assert any(change["kind"] == "vanished" for change in healed["changes"])


def test_html_handed_in_is_held_to_the_bound_a_fetched_page_is(monkeypatch):
    registered = fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    monkeypatch.setattr(server_module, "MAX_RESPONSE_BYTES", 100)
    server_module.build_server()

    answer = registered["extract_declared"]("<p>" + "x" * 200 + "</p>")

    assert answer["ok"] is False
    assert answer["error"]["code"] == "too_large"
    assert answer["error"]["retryable"] is False
    assert "url" not in answer["error"]


def test_only_a_failed_fetch_is_worth_retrying(monkeypatch):
    from sluicer.fetch import FetchFailed, RobotsRefused
    from sluicer.mcp_server import _answers_instead_of_raising

    def failing(error):
        return _answers_instead_of_raising(lambda: (_ for _ in ()).throw(error))()

    failed = failing(FetchFailed("https://example.com/p", [], "timed out"))
    refused = failing(RobotsRefused("https://example.com/p"))

    assert failed["error"]["retryable"] is True
    assert refused["error"]["retryable"] is False


def test_every_answer_type_requires_ok_and_nothing_else():
    """The output schemas say what an agent may rely on: ``ok``, always."""
    pytest.importorskip("typing_extensions")
    from sluicer import mcp_answers

    answers = [
        mcp_answers.ExtractAnswer,
        mcp_answers.MarkdownAnswer,
        mcp_answers.PageAnswer,
        mcp_answers.CompileAnswer,
        mcp_answers.RunAnswer,
        mcp_answers.HealAnswer,
        mcp_answers.AuditAnswer,
        mcp_answers.MapAnswer,
        mcp_answers.CrawlAnswer,
        mcp_answers.CrawledPage,
    ]
    for answer in answers:
        assert answer.__required_keys__ == {"ok"}, answer.__name__
        assert "error" in answer.__optional_keys__, answer.__name__
    assert mcp_answers.ErrorDetail.__required_keys__ == {"code", "message", "retryable"}


def test_audit_page_audits_html_handed_in_without_reading_any_site(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["audit_page"](
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Pad","offers":{"price":"41,90"}}</script>'
    )

    assert answer["ok"] is True
    assert answer["url"] is None
    assert "fetch" not in answer
    record = answer["records"][0]
    assert (record["source"], record["types"]) == ("jsonld", ["Product"])
    bad = [f for f in record["findings"] if f["path"] == "offers.price"]
    assert bad[0]["severity"] == "error"
    assert answer["errors"] >= 1
    assert answer["crawlers"] == []
    assert any("site was not read" in note for note in answer["not_checked"])


def test_audit_page_reads_the_site_of_a_url_under_the_servers_address_rule(
    monkeypatch,
):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<html><head><title>T</title></head></html>")
    from sluicer.audit import Site, SiteFile
    from sluicer.mcp_server import build_server

    asked = {}

    def read_site(url, **kwargs):
        asked.update(url=url, **kwargs)
        return Site(
            SiteFile(
                "https://example.com/robots.txt",
                200,
                "User-agent: GPTBot\nDisallow: /\n",
            ),
            SiteFile("https://example.com/llms.txt", 200, "# Example\n> Summary\n"),
            SiteFile("https://example.com/llms-full.txt", 404),
        )

    monkeypatch.setattr("sluicer.fetch.site.read_site", read_site)
    build_server()
    answer = registered["audit_page"]("https://example.com/p")

    assert asked == {"url": "https://example.com/final", "allow_private": False}
    assert answer["ok"] is True
    assert answer["fetch"]["rung"] == "http"
    verdicts = {v["agent"]: v["allowed"] for v in answer["crawlers"]}
    assert verdicts["GPTBot"] is False
    assert verdicts["ClaudeBot"] is True
    assert answer["llms_txt"]["name"] == "Example"
    assert answer["robots_txt"]["text"] is None


def test_audit_page_can_leave_the_site_alone(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch)
    from sluicer.mcp_server import build_server

    def read_site(url, **kwargs):
        raise AssertionError("the site was read")

    monkeypatch.setattr("sluicer.fetch.site.read_site", read_site)
    build_server()

    answer = registered["audit_page"]("https://example.com/p", site=False)

    assert answer["ok"] is True
    assert answer["llms_txt"] is None


def test_audit_page_reports_a_refusal_as_an_answer(monkeypatch):
    from sluicer.fetch import RobotsRefused

    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, raises=RobotsRefused("https://example.com/p"))
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["audit_page"]("https://example.com/p")

    assert answer["ok"] is False
    assert answer["error"]["code"] == "refused_by_robots"


def test_audit_page_says_when_it_audited_an_error_page(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.fetch.result import Fetched
    from sluicer.mcp_server import build_server

    def fetch(url, **kwargs):
        return Fetched(url=url, html="<html>Not found</html>", status=404, rung="http")

    monkeypatch.setattr("sluicer.fetch.fetch", fetch)
    build_server()

    answer = registered["audit_page"]("https://example.com/gone", site=False)

    assert answer["ok"] is True
    assert answer["not_checked"][0].startswith(
        "The page asked for: the site answered status 404"
    )


# -- map_site and crawl_site -------------------------------------------------------


def _shop():
    from fake_site import page

    return {
        "https://example.com/": page("Home", "/a", "/b?page=2", "/private/x"),
        "https://example.com/a": page("A", "/b?page=2"),
        "https://example.com/b?page=2": page("B"),
        "https://example.com/private/x": page("X"),
        "https://example.com/sitemap.xml": (
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/a</loc><lastmod>2026-09-01</lastmod></url>"
            "</urlset>"
        ),
    }


def _fake_site_library(monkeypatch, pages=None):
    """The library's map and crawl, pointed at a fake web, recording each call.

    Names resolve to one public address without asking a resolver, since the
    server judges every address and the suite may not look one up.
    """
    import sluicer.crawl as library
    from fake_site import FakeWeb

    fake = FakeWeb(pages if pages is not None else _shop())
    calls = []

    def wrap(real):
        def call(*args, **kwargs):
            calls.append(kwargs)
            paced = {
                "web": fake.web(),
                "clock": fake.clock,
                "sleep": fake.clock.sleep,
                "resolve": lambda host: ["93.184.215.14"],
            }
            return real(*args, **{**kwargs, **paced})

        return call

    monkeypatch.setattr("sluicer.crawl.map_site", wrap(library.map_site))
    monkeypatch.setattr("sluicer.crawl.crawl", wrap(library.crawl))
    monkeypatch.setattr("sluicer.crawl.extract_many", wrap(library.extract_many))
    return fake, calls


def test_map_site_lists_the_sites_addresses_within_its_bounds(monkeypatch):
    registered = fake_mcp(monkeypatch)
    _, calls = _fake_site_library(monkeypatch)
    from sluicer.mcp_server import (
        CRAWL_MAX_DELAY_SECONDS,
        MAP_SITEMAPS,
        TIME_BUDGET_SECONDS,
        build_server,
    )

    monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
    build_server()
    answer = registered["map_site"]("https://example.com/")

    assert answer["ok"] is True and answer["source"] == "sitemaps"
    assert answer["urls"] == [
        {
            "url": "https://example.com/a",
            "lastmod": "2026-09-01",
            "sitemap": "https://example.com/sitemap.xml",
        }
    ]
    assert answer["sitemaps"][0]["kind"] == "urlset"
    assert calls[0]["max_sitemaps"] == MAP_SITEMAPS
    assert calls[0]["time_budget"] == TIME_BUDGET_SECONDS
    assert calls[0]["max_delay"] == CRAWL_MAX_DELAY_SECONDS
    assert calls[0]["allow_private"] is False


def test_a_map_or_a_crawl_asked_past_its_bounds_is_a_bad_input(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake, _ = _fake_site_library(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    for answer in (
        registered["map_site"]("https://example.com/", limit=0),
        registered["map_site"]("https://example.com/", limit=5000),
        registered["crawl_site"]("https://example.com/", max_pages=26),
        registered["crawl_site"]("https://example.com/", max_depth=9),
        registered["crawl_site"]("mailto:x@example.com"),
    ):
        assert answer["ok"] is False and answer["error"]["code"] == "bad_input"
    assert fake.requests == []


def test_crawl_site_summarises_each_page_and_leaves_the_records_out(monkeypatch):
    registered = fake_mcp(monkeypatch)
    _, calls = _fake_site_library(monkeypatch)
    from sluicer.mcp_server import (
        CRAWL_MAX_DELAY_SECONDS,
        TIME_BUDGET_SECONDS,
        build_server,
    )

    build_server()
    answer = registered["crawl_site"]("https://example.com/", max_pages=3)

    assert answer["ok"] is True and answer["stopped"] == "max_pages"
    assert [page["url"] for page in answer["pages"]] == [
        "https://example.com/",
        "https://example.com/a",
        "https://example.com/b?page=2",
    ]
    first = answer["pages"][0]
    assert first["summary"]["title"]["value"] == "Home"
    assert first["types"] == ["Product"] and first["links"] == 3
    assert "records" not in first
    assert calls[0]["max_delay"] == CRAWL_MAX_DELAY_SECONDS
    assert calls[0]["time_budget"] == TIME_BUDGET_SECONDS


def test_crawl_site_reads_include_and_exclude_as_plain_text(monkeypatch):
    """An agent writes "?page=", which as a pattern would mean something else."""
    registered = fake_mcp(monkeypatch)
    _fake_site_library(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    only = registered["crawl_site"]("https://example.com/", include=["?page="])
    without = registered["crawl_site"]("https://example.com/", exclude=["/private/"])

    assert [p["url"] for p in only["pages"]] == [
        "https://example.com/",
        "https://example.com/b?page=2",
    ]
    assert "https://example.com/private/x" not in [p["url"] for p in without["pages"]]


def test_a_crawl_that_read_nothing_is_not_ok_and_says_why(monkeypatch):
    registered = fake_mcp(monkeypatch)
    pages = _shop()
    pages["https://example.com/robots.txt"] = "User-agent: *\nDisallow: /\n"
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["crawl_site"]("https://example.com/")

    assert answer["ok"] is False
    assert answer["error"]["code"] == "refused_by_robots"
    assert answer["error"]["url"] == "https://example.com/"
    assert answer["pages"][0] == {
        "ok": False,
        "url": "https://example.com/",
        "depth": 0,
        "error": answer["error"],
    }


def test_a_crawled_page_asked_again_says_so_failed_or_not(monkeypatch):
    registered = fake_mcp(monkeypatch)
    pages = _shop()
    pages["https://example.com/a"] = [(503, "busy", {}), pages["https://example.com/a"]]
    pages["https://example.com/private/x"] = ConnectionError("down")
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["crawl_site"]("https://example.com/", max_depth=1)

    got = {page["url"]: page for page in answer["pages"]}
    assert got["https://example.com/a"]["retries"] == [
        {"reason": "it answered 503", "after": 2.0}
    ]
    failed = got["https://example.com/private/x"]
    assert failed["error"]["code"] == "fetch_failed"
    assert len(failed["retries"]) == 2
    assert "retries" not in got["https://example.com/"]


def test_extract_many_reads_the_pages_given_in_their_order_within_its_bounds(
    monkeypatch,
):
    registered = fake_mcp(monkeypatch)
    fake, calls = _fake_site_library(monkeypatch)
    from sluicer.mcp_server import (
        CRAWL_MAX_DELAY_SECONDS,
        TIME_BUDGET_SECONDS,
        build_server,
    )

    monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
    build_server()
    given = ["https://example.com/a", "https://example.com/", "https://example.com/a"]
    answer = registered["extract_many"](given)

    assert answer["ok"] is True and answer["stopped"] == "done"
    assert [p["url"] for p in answer["pages"]] == given[:2]
    first = answer["pages"][0]
    assert first["summary"]["title"]["value"] == "A" and first["types"] == ["Product"]
    assert "records" not in first
    assert calls[0]["max_delay"] == CRAWL_MAX_DELAY_SECONDS
    assert calls[0]["time_budget"] == TIME_BUDGET_SECONDS
    assert calls[0]["allow_private"] is False
    assert fake.gaps("example.com") == [1.0, 1.0]


def test_extract_many_gives_the_records_when_asked(monkeypatch):
    registered = fake_mcp(monkeypatch)
    _fake_site_library(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["extract_many"](["https://example.com/a"], records=True)

    [page] = answer["pages"]
    assert page["records"][0]["fields"]["name"]["value"] == "A"
    assert page["types"] == ["Product"]


def test_extract_many_asked_past_its_bounds_is_a_bad_input(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake, _ = _fake_site_library(monkeypatch)
    from sluicer.mcp_server import MANY_URLS, build_server

    build_server()
    too_many = [f"https://example.com/{n}" for n in range(MANY_URLS + 1)]

    for answer in (
        registered["extract_many"]([]),
        registered["extract_many"](too_many),
    ):
        assert answer["ok"] is False and answer["error"]["code"] == "bad_input"
    assert fake.requests == []


def test_extract_many_leaves_the_heaviest_pages_records_out_first(monkeypatch):
    from fake_site import page

    registered = fake_mcp(monkeypatch)
    heavy = '<script type="application/ld+json">{"@type":"Thing","name":"%s"}</script>'
    pages = {
        "https://example.com/big": page("Big", extra=heavy % ("x" * 80_000)),
        "https://example.com/small": page("Small"),
    }
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import MOST_ANSWER_BYTES, _bytes_of, build_server

    build_server()
    answer = registered["extract_many"](
        ["https://example.com/big", "https://example.com/small"], records=True
    )

    big, small = answer["pages"]
    assert "records" not in big and big["records_left_out"] == 2
    assert small["records"][0]["fields"]["name"]["value"] == "Small"
    assert _bytes_of(answer) <= MOST_ANSWER_BYTES


def test_extract_many_that_read_nothing_is_not_ok_and_says_why(monkeypatch):
    registered = fake_mcp(monkeypatch)
    pages = _shop()
    pages["https://example.com/robots.txt"] = "User-agent: *\nDisallow: /\n"
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import build_server

    build_server()
    answer = registered["extract_many"](["https://example.com/a"])

    assert answer["ok"] is False
    assert answer["error"]["code"] == "refused_by_robots"


def test_the_crawl_tools_refuse_private_addresses_unless_told(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake, _ = _fake_site_library(monkeypatch, {})
    from sluicer.mcp_server import build_server

    build_server()
    monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
    crawled = registered["crawl_site"]("http://127.0.0.1:8080/")
    mapped = registered["map_site"]("http://127.0.0.1:8080/")

    assert crawled["error"]["code"] == "refused_address"
    assert crawled["error"]["retryable"] is False
    assert mapped["error"]["code"] == "refused_address"
    assert fake.requests == []


def test_every_parameter_says_what_it_is_in_the_schema_an_agent_reads():
    """A client reads what a parameter means from its schema, not from the
    tool's prose: all 28 had nothing there, and Glama's directory scores tools
    on it. Each is its docstring's ``name: text`` paragraph, word for word."""
    pytest.importorskip("mcp.server.mcpserver")
    import asyncio

    from sluicer.mcp_server import build_server

    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    assert set(tools) == TOOLS
    for tool in tools.values():
        for name, spec in tool.input_schema["properties"].items():
            assert spec.get("description"), (tool.name, name)
    said = tools["extract_declared"].input_schema["properties"]
    assert said["html_or_url"]["description"] == (
        "an http(s) URL to fetch, or the HTML itself."
    )
    assert said["induce"]["description"].endswith('those fields say source "induced".')


def test_a_tool_that_leaves_a_parameter_unexplained_is_not_registered():
    from sluicer.mcp_server import _parameter_notes

    doc = """Do a thing.

    url: where to go,
    and how.
    limit: how many.

    Returns {"ok"}. url: is not a parameter here.
    """
    assert _parameter_notes(doc, ["url", "limit"]) == {
        "url": "where to go, and how.",
        "limit": "how many.",
    }
    assert _parameter_notes(doc, ["depth"]) == {}


def test_only_the_tools_asked_for_are_registered(monkeypatch):
    """Every tool registered costs an agent context whether it is called or
    not; a client that wants two of the twelve can have only those."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server(tools=["extract_declared", "page_markdown"])

    assert set(registered["__tool_options__"]) == {"extract_declared", "page_markdown"}


def test_a_tool_asked_for_that_does_not_exist_is_named_with_the_twelve_that_do(
    monkeypatch,
):
    fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    with pytest.raises(ValueError) as raised:
        build_server(tools=["extract", "page_markdown"])
    said = str(raised.value)
    assert "'extract'" in said
    assert all(name in said for name in TOOLS)


def test_the_server_reads_the_tools_asked_for_from_its_environment(monkeypatch):
    """sluicer-mcp takes no arguments; a client that can set a variable and
    not a command line still chooses."""
    fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    asked = []

    class _Server:
        def run(self):
            pass

    def build(tools=None):
        asked.append(tools)
        return _Server()

    monkeypatch.setattr(server_module, "build_server", build)
    monkeypatch.setenv("SLUICER_MCP_TOOLS", " extract_declared, map_site ,")
    server_module.main()
    monkeypatch.delenv("SLUICER_MCP_TOOLS")
    server_module.main()
    server_module.main(tools=["read_feed"])
    assert asked == [["extract_declared", "map_site"], None, ["read_feed"]]


def test_a_tool_that_does_not_exist_stops_the_server_in_one_line(monkeypatch, capsys):
    """The documented message, and exit 2 as for any wrong option: a
    traceback put the list of the tools under thirty lines of click's frames."""
    fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    for asked in (["bogus"], None):
        if asked is None:
            monkeypatch.setenv("SLUICER_MCP_TOOLS", "bogus")
        with pytest.raises(SystemExit) as raised:
            server_module.main(tools=asked)
        assert raised.value.code == 2
        said = capsys.readouterr().err
        assert "no such tool: 'bogus'" in said
        assert all(name in said for name in TOOLS)
        assert "Traceback" not in said


# -- every answer within MOST_ANSWER_BYTES -------------------------------------------


def _within_the_bound(answer):
    from sluicer.mcp_server import MOST_ANSWER_BYTES, _bytes_of

    weight = _bytes_of(answer)
    assert weight <= MOST_ANSWER_BYTES, f"{weight:,} bytes"
    return answer


def test_a_huge_title_is_left_out_of_the_summary_and_named(monkeypatch):
    """A 200,000-character <title> made extract_declared answer 200 KB even
    with records=False: only the records were ever bounded."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    page = (
        f"<html><head><title>{'Brake pads ' * 20_000}</title>"
        '<meta name="description" content="Pads for the front axle.">'
        "</head></html>"
    )
    for records in (True, False):
        got = _within_the_bound(registered["extract_declared"](page, records=records))
        assert got["ok"] is True
        assert got["summary_left_out"] == ["title"]
        assert got["summary"]["description"]["value"] == "Pads for the front axle."
    assert got.get("records_left_out") is None


def test_the_heaviest_answers_go_first_and_each_is_named(monkeypatch):
    registered = fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    monkeypatch.setattr(server_module, "MOST_ANSWER_BYTES", 3_000)
    server_module.build_server()
    page = (
        f"<html><head><title>{'t' * 2_000}</title>"
        f'<meta name="description" content="{"d" * 1_500}">'
        '<meta name="author" content="Ann Lee"></head></html>'
    )
    got = _within_the_bound(registered["extract_declared"](page, records=False))
    assert got["summary_left_out"] == ["title"]
    assert set(got["summary"]) == {"description", "author"}


def test_a_slice_of_chinese_is_held_to_the_bound_in_bytes_not_characters(
    monkeypatch,
):
    """60,000 characters of Chinese are 180,000 bytes: fetch_page answered
    180 KB. The slice is shortened, and the slices still join to the page."""
    page = "<html><body><p>" + "漢字" * 50_000 + "</p></body></html>"
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html=page)
    from sluicer.mcp_server import MOST_CHARS, build_server

    build_server()
    slices, offset = [], 0
    while offset is not None:
        got = _within_the_bound(
            registered["fetch_page"](
                "https://example.com/p", offset=offset, max_chars=MOST_CHARS
            )
        )
        assert got["truncated"] is (got["next_offset"] is not None)
        slices.append(got["html"])
        offset = got["next_offset"]
    assert "".join(slices) == page
    assert 20_000 < len(slices[0]) < MOST_CHARS


def test_a_slice_of_markdown_is_held_to_the_bound_in_bytes_too(monkeypatch):
    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, html="<html></html>")
    import sluicer.mcp_server as server_module

    text = '"quoted"\n' * 20_000
    monkeypatch.setattr(server_module, "to_markdown", lambda *a, **k: text)
    server_module.build_server()
    slices, offset = [], 0
    while offset is not None:
        got = _within_the_bound(
            registered["page_markdown"](
                "https://example.com/p", offset=offset, max_chars=60_000
            )
        )
        slices.append(got["markdown"])
        offset = got["next_offset"]
    assert "".join(slices) == text


def _rss(items, words):
    body = "".join(
        f"<item><title>Item {n}</title><link>https://example.com/{n}</link>"
        f"<description>{'word ' * words}</description></item>"
        for n in range(items)
    )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>'
        f"<link>https://example.com/</link>{body}</channel></rss>"
    )


def test_feed_items_past_the_bound_are_left_out_and_counted(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    got = _within_the_bound(registered["read_feed"](_rss(60, 2_000), limit=60))
    assert got["ok"] is True and got["items_total"] == 60
    assert got["items_left_out"] == 60 - len(got["items"]) > 0
    assert [item["title"] for item in got["items"]] == [
        f"Item {n}" for n in range(len(got["items"]))
    ]


def test_a_map_past_the_bound_is_cut_counted_and_called_truncated(monkeypatch):
    long = "/" + "section/" * 25
    entries = "".join(
        f"<url><loc>https://example.com{long}{n}</loc></url>" for n in range(1_000)
    )
    pages = {
        "https://example.com/": "<html><body>Home</body></html>",
        "https://example.com/sitemap.xml": (
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>"
        ),
    }
    registered = fake_mcp(monkeypatch)
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import build_server

    build_server()
    got = _within_the_bound(registered["map_site"]("https://example.com/", limit=1000))
    assert got["ok"] is True and got["truncated"] is True
    assert got["urls_left_out"] == 1_000 - len(got["urls"]) > 0


def test_a_crawl_leaves_out_the_heaviest_summary_answers_and_keeps_every_page(
    monkeypatch,
):
    """One page with a 200,000-character title costs that title, not the
    pages after it."""
    from fake_site import page

    pages = _shop()
    pages["https://example.com/a"] = page("A" * 200_000, "/b?page=2")
    registered = fake_mcp(monkeypatch)
    _fake_site_library(monkeypatch, pages)
    from sluicer.mcp_server import build_server

    build_server()
    got = _within_the_bound(registered["crawl_site"]("https://example.com/"))
    urls = [one["url"] for one in got["pages"]]
    assert "https://example.com/b?page=2" in urls and "pages_left_out" not in got
    heavy = got["pages"][urls.index("https://example.com/a")]
    assert heavy["summary_left_out"] == ["title"]
    assert got["pages"][0]["summary"]["title"]["value"] == "Home"
    assert "summary_left_out" not in got["pages"][0]


def test_an_audit_past_the_bound_keeps_the_records_that_fit(monkeypatch):
    """Sixty products made a 570 KB audit, 3,000 a 28 MB one; the rest are counted."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    products = [
        '<script type="application/ld+json">'
        f'{{"@type": "Product", "name": "Pad {n}"}}</script>'
        for n in range(60)
    ]
    got = _within_the_bound(registered["audit_page"]("".join(products)))
    assert got["ok"] is True and got["records"]
    assert got["records_left_out"] == 60 - len(got["records"]) > 0
    assert got["errors"] == 3 * 60
    few = registered["audit_page"]("".join(products[:3]))
    assert len(few["records"]) == 3 and "records_left_out" not in few


def test_rows_past_the_bound_are_left_out_and_counted(monkeypatch):
    registered = fake_mcp(monkeypatch)
    import sluicer.extractor as extractor_module
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"](
        [_drift("shop_v1.html"), _drift("shop_v1_page2.html")]
    )
    rows = [{"title": f"Book {n} " + "x" * 400} for n in range(1_000)]
    monkeypatch.setattr(
        extractor_module,
        "run_extractor",
        lambda *a, **k: extractor_module.Run(url=None, ok=True, rows=rows),
    )
    got = _within_the_bound(
        registered["run_extractor"](learnt["extractor"], _drift("shop_v1.html"))
    )
    assert got["ok"] is True
    assert got["rows"] == rows[: len(got["rows"])]
    assert got["rows_left_out"] == 1_000 - len(got["rows"]) > 0


def test_an_answer_nothing_can_be_left_out_of_is_too_large(monkeypatch):
    """An extractor is used whole or not at all: one learnt from pages whose
    template repeats a 100,000-character value cannot be cut, and is refused
    rather than handed to a client that cannot hold it."""
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import MOST_ANSWER_BYTES, build_server

    build_server()
    heavy = "Sapiens " * 12_500
    pages = [_drift("shop_v1.html").replace("Sapiens", heavy)]
    got = registered["compile_extractor"](pages)
    assert got["ok"] is False and got["error"]["code"] == "too_large"
    assert f"{MOST_ANSWER_BYTES:,}" in got["error"]["message"]
    _within_the_bound(got)


def test_conflicts_go_before_the_summary_and_are_counted(monkeypatch):
    registered = fake_mcp(monkeypatch)
    import sluicer.mcp_server as server_module

    server_module.build_server()
    page = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "Product", "name": "Pads", "offers": {"price": "41.90"}}'
        '</script><meta property="og:price:amount" content="39.90"></head></html>'
    )
    whole = registered["extract_declared"](page, records=False)
    assert len(whole["conflicts"]) == 1
    monkeypatch.setattr(
        server_module, "MOST_ANSWER_BYTES", server_module._bytes_of(whole) - 10
    )
    got = _within_the_bound(registered["extract_declared"](page, records=False))
    assert got["conflicts"] == [] and got["conflicts_left_out"] == 1
    assert got["summary"] == whole["summary"] and "summary_left_out" not in got


def test_a_healed_extractor_too_large_for_an_answer_is_refused(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    learnt = registered["compile_extractor"](
        [_drift("shop_v1.html"), _drift("shop_v1_page2.html")]
    )
    heavy = _drift("shop_v1.html").replace("Sapiens", "Sapiens " * 12_500)
    got = registered["heal_extractor"](learnt["extractor"], [heavy])
    assert got["ok"] is False and got["error"]["code"] == "too_large"
    _within_the_bound(got)
