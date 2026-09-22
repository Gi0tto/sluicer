"""Sluicer as a tool an agent can call.

Nine percent of the live projects in this field now ship an MCP server, which
makes it table stakes rather than an edge: a tool an agent cannot install is a
tool an agent will not use. The server adds no logic. It exposes what the
library already does and gets out of the way.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from typing import Any

from sluicer.api import extract
from sluicer.extras import MissingExtra, import_extra
from sluicer.markdown import to_markdown


class McpExtraMissing(MissingExtra):
    """The optional ``mcp`` extra is not installed, as opposed to broken."""


def _fastmcp():
    """Return the SDK's ``FastMCP`` class, or say the extra is not installed.

    This once matched ``"mcp"`` *or* anything under ``mcp.``, unlike the other
    two extras, which match the top-level name only. The wider match is not
    needed and is now gone: ``mcp`` is pinned ``>=1.2``, the first release with
    ``mcp.server.fastmcp``, so installing ``sluicer[mcp]`` cannot leave the
    submodule absent. If it is absent anyway, ``mcp`` is installed and too old
    or broken -- and "install it with uv pip install" is the wrong advice for
    someone who already has it. That keeps its traceback, exactly as a missing
    ``scrapling.fetchers`` does.
    """
    return import_extra(
        "mcp.server.fastmcp",
        "mcp",
        doing="Running the MCP server",
        package="the mcp package",
        error=McpExtraMissing,
    ).FastMCP


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

    Returns the mcp SDK's ``FastMCP`` instance. That type cannot be named in
    this signature: ``mcp`` is an optional extra, and this module's whole
    point is to not import it at module level, so there is no ``FastMCP``
    name here for even a string annotation to resolve to. ``Any`` says that
    honestly rather than writing a forward reference to a name nothing in
    this file ever defines.
    """
    server = _fastmcp()("sluicer")

    @server.tool()
    def extract_declared(html_or_url: str) -> dict:
        """Read the structured data a page declares, with per-field provenance."""
        html, url, fetched = _html_of(html_or_url)
        result = asdict(extract(html, url=url))
        if fetched is not None:
            result["fetch"] = fetched
        return result

    @server.tool()
    def page_markdown(html_or_url: str) -> str:
        """Return the page's main content as markdown, with boilerplate removed."""
        html, url, _fetched = _html_of(html_or_url)
        return to_markdown(html, url=url)

    @server.tool()
    def fetch_page(url: str) -> dict:
        """Fetch a page and report which rung it took and every climb.

        Unlike ``extract_declared`` and ``page_markdown``, literal HTML is
        not a legitimate input here: this tool's whole job is to fetch, so a
        caller handed back the string it sent -- with no way to tell that
        nothing was fetched -- is worse than an error.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"fetch_page needs an http:// or https:// URL, got {url!r}")
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
