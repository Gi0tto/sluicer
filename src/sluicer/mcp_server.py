"""Sluicer as a tool an agent can call.

Nine percent of the live projects in this field now ship an MCP server, which
makes it table stakes rather than an edge: a tool an agent cannot install is a
tool an agent will not use. The server adds no logic. It exposes what the
library already does and gets out of the way.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from sluicer.api import extract
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch import RobotsRefused
from sluicer.markdown import to_markdown


class McpExtraMissing(MissingExtra):
    """The optional ``mcp`` extra is not installed, as opposed to broken."""


def _server_class():
    """Return the SDK's ``MCPServer`` class, or say the extra is not installed.

    Named for what it returns. This built ``mcp.server.fastmcp.FastMCP`` until
    the class was renamed in mcp 2.x, which the extra's pin now follows: the v1
    name is gone from the package, and supporting both spellings would double
    this surface for a project at 0.0.1 with no users to keep working.

    The match here is on the top-level ``mcp`` only, the same rule the other
    two extras use, and the rename is the proof that it is the right one.
    mcp 2.x ships ``mcp/server/fastmcp.py`` as a module that exists solely to
    raise ``ModuleNotFoundError(name="mcp.server.fastmcp")`` carrying its
    migration guide. Under the wider ``mcp.*`` match this file used to have,
    that would have been swallowed and reported as "the mcp package is not
    installed. Install it with: uv pip install 'sluicer[mcp]'" -- sending a
    reader to install what they already had, and throwing away the one
    sentence that says what to do. The narrow rule lets it through untouched.
    """
    return import_extra(
        "mcp.server.mcpserver",
        "mcp",
        doing="Running the MCP server",
        package="the mcp package",
        error=McpExtraMissing,
    ).MCPServer


def _answers_instead_of_raising(tool: Callable) -> Callable:
    """Turn the two answerable events into the tool's own result, hint intact.

    Every tool here can meet an absent extra: two fetch, two read markdown or
    structured data. Every tool here can also be aimed at a URL whose site
    refuses us, since ``fetch`` asks robots.txt before any rung runs and raises
    ``RobotsRefused`` when the answer is no. Without this, either one leaves
    the tool body as an exception, and what the agent on the other end sees is
    whatever the SDK decides to do with one -- which is not this project's to
    promise, is not tested here, and is not written down anywhere. "Explain
    what happened" is a duty this package discharges at every entry point; the
    CLI does it in ``cli.py``, and this is the server's one place to do it.

    Both answers share one shape -- a mapping with ``error`` -- and carry a
    different second key, because they call for opposite responses: a missing
    extra is fixed by the one install command in its own message, and a
    refusal is not to be worked around at all. ``missing_extra`` names the
    extra; ``refused_by_robots`` names the URL the site refused. A reader that
    saw only ``error`` would have to parse English to tell them apart.

    That shape is deliberately not the shape of any tool's content. This first
    followed each tool's declared return type, so ``page_markdown`` -- which
    returns a page's markdown as a ``str`` -- got the explanation as a ``str``
    too. Measured, an agent then received "Turning a page into markdown needs
    trafilatura..." in the exact place a page's own words go, with nothing to
    tell it apart: it would summarise it, quote it, or act on it. A failure
    wearing the shape of a success is the defect this project keeps finding,
    and it is worse here than at the command line, because a person reading a
    terminal notices and an agent does not. A return type that differs between
    success and failure is mildly awkward; this is the trade, and
    ``page_markdown`` is annotated ``str | dict`` because that is what it
    returns. Measured against mcp 2.2.0, a tool returning text gets no
    generated output schema, so the annotation costs nothing there either.

    Only those two are caught. A connection that never opened is not an answer
    from anyone, and a real bug inside a tool is still a bug: both still raise.
    """

    @functools.wraps(tool)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except MissingExtra as missing:
            return {"error": str(missing), "missing_extra": missing.extra}
        except RobotsRefused as refused:
            return {"error": str(refused), "refused_by_robots": refused.url}

    return guarded


def _html_of(html_or_url: str) -> tuple[str, str | None, dict[str, Any] | None]:
    """Return the page's HTML, the URL to attribute it to, and the fetch record.

    The URL is the *response's* own ``fetched.url``, not the string the caller
    passed: a fetch that followed a redirect landed somewhere else, and every
    relative link on the page resolves against where it landed. For literal
    HTML there is no URL at all -- ``None`` says "this came from nowhere I can
    name", which is the truth, and is what the library already means by it.
    """
    if html_or_url.startswith(("http://", "https://")):
        from sluicer.fetch import fetch

        fetched = fetch(html_or_url)
        return (
            fetched.html,
            fetched.url,
            {
                "rung": fetched.rung,
                "status": fetched.status,
                "climbs": [asdict(climb) for climb in fetched.climbs],
            },
        )
    return html_or_url, None, None


def build_server() -> Any:
    """Build the server with its three tools registered.

    Returns the mcp SDK's ``MCPServer`` instance. That type cannot be named in
    this signature: ``mcp`` is an optional extra, and this module's whole
    point is to not import it at module level, so there is no ``MCPServer``
    name here for even a string annotation to resolve to. ``Any`` says that
    honestly rather than writing a forward reference to a name nothing in
    this file ever defines.
    """
    server = _server_class()("sluicer")

    @server.tool()
    @_answers_instead_of_raising
    def extract_declared(html_or_url: str) -> dict:
        """Read the structured data a page declares, with per-field provenance."""
        html, url, fetched = _html_of(html_or_url)
        result = asdict(extract(html, url=url))
        if fetched is not None:
            result["fetch"] = fetched
        return result

    @server.tool()
    @_answers_instead_of_raising
    def page_markdown(html_or_url: str) -> str | dict:
        """Return the page's main content as markdown, with boilerplate removed.

        A ``str`` is the page's markdown. A ``dict`` is never content: it is
        the ``error`` report the three tools share when an optional extra is
        absent (``missing_extra``) or the site's own robots.txt refuses the
        URL (``refused_by_robots``). The two cannot be confused with a page,
        which is the whole reason neither failure is a ``str``.
        """
        html, url, _fetched = _html_of(html_or_url)
        return to_markdown(html, url=url)

    @server.tool()
    @_answers_instead_of_raising
    def fetch_page(url: str) -> dict:
        """Fetch a page and report which rung it took and every climb.

        Unlike ``extract_declared`` and ``page_markdown``, literal HTML is
        not a legitimate input here: this tool's whole job is to fetch, so a
        caller handed back the string it sent -- with no way to tell that
        nothing was fetched -- is worse than an error.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"fetch_page needs an http:// or https:// URL, got {url!r}"
            )
        html, _url, fetched = _html_of(url)
        return {"html": html, "fetch": fetched}

    return server


def main() -> None:
    """Run the server over stdio, or explain a missing extra in one line.

    Only ``McpExtraMissing`` is caught here, the same as ``FetchExtraMissing``
    and ``MarkdownExtraMissing`` are caught at their own entry points: a
    genuinely absent extra becomes a one-line message, while a real import
    failure from inside a broken install keeps its traceback.
    """
    try:
        server = build_server()
    except McpExtraMissing as missing:
        print(str(missing), file=sys.stderr)
        raise SystemExit(1) from missing
    server.run()
