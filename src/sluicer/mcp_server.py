"""Sluicer as a tool an agent can call.

Nine percent of the live projects in this field now ship an MCP server, which
makes it table stakes rather than an edge: a tool an agent cannot install is a
tool an agent will not use. The server adds no logic. It exposes what the
library already does and gets out of the way.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sluicer.api import extract
from sluicer.markdown import to_markdown

_MISSING = (
    "Running the MCP server needs the mcp package, which is not installed. "
    "Install it with: uv pip install 'sluicer[mcp]'"
)


class McpExtraMissing(ImportError):
    """The optional mcp extra is not installed, as opposed to broken."""


def _fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as missing:
        if missing.name == "mcp" or (missing.name or "").startswith("mcp."):
            raise McpExtraMissing(_MISSING) from missing
        raise
    return FastMCP


def _html_of(html_or_url: str) -> tuple[str, dict[str, Any] | None]:
    """Return the page's HTML, fetching it when given a URL."""
    if html_or_url.startswith(("http://", "https://")):
        from sluicer.fetch import fetch

        fetched = fetch(html_or_url)
        return fetched.html, {
            "rung": fetched.rung,
            "status": fetched.status,
            "climbs": [asdict(climb) for climb in fetched.climbs],
        }
    return html_or_url, None


def build_server():
    """Build the server with its three tools registered."""
    server = _fastmcp()("sluicer")

    @server.tool()
    def extract_declared(html_or_url: str) -> dict:
        """Read the structured data a page declares, with per-field provenance."""
        html, fetched = _html_of(html_or_url)
        result = asdict(extract(html))
        if fetched is not None:
            result["fetch"] = fetched
        return result

    @server.tool()
    def page_markdown(html_or_url: str) -> str:
        """Return the page's main content as markdown, with boilerplate removed."""
        html, _ = _html_of(html_or_url)
        return to_markdown(html)

    @server.tool()
    def fetch_page(url: str) -> dict:
        """Fetch a page and report which rung it took and every climb."""
        html, fetched = _html_of(url)
        return {"html": html, "fetch": fetched}

    return server


def main() -> None:
    """Run the server over stdio."""
    build_server().run()
