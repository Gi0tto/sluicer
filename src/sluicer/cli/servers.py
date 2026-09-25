"""``sluicer serve`` and ``sluicer mcp``: the MCP server's tools, over HTTP or stdio.

Each is a door to a server defined elsewhere, ``sluicer.http_api`` and
``sluicer.mcp_server``; what is here is their options and how they refuse.
"""

from __future__ import annotations

import click

from sluicer.cli.exits import _fail
from sluicer.http_api import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    TIME_BUDGET_SECONDS,
    TOKEN_ENV,
    ApiExtraMissing,
    Unprotected,
    serve as serve_http,
)


@click.command()
@click.option(
    "--host",
    default=DEFAULT_HOST,
    show_default=True,
    help=f"Where to listen. Anything but loopback needs {TOKEN_ENV}.",
)
@click.option(
    "--port", default=DEFAULT_PORT, show_default=True, type=click.IntRange(0, 65535)
)
@click.option(
    "--timeout",
    default=TIME_BUDGET_SECONDS,
    show_default=True,
    type=click.FloatRange(min=0, min_open=True),
    help="Seconds a request may take before it is answered 504.",
)
@click.option(
    "--allow-unauthenticated",
    is_flag=True,
    help="Listen beyond loopback with no token, behind something that already "
    "decides who may call.",
)
def serve(host: str, port: int, timeout: float, allow_unauthenticated: bool) -> None:
    """Serve the MCP server's tools over HTTP (needs sluicer[api]).

    POST /v1/tools/<name> with the tool's arguments as a JSON object answers
    what the tool answers; GET /v1/tools and /openapi.json describe them. /mcp
    is the MCP server itself over streamable HTTP, stateless, for a client
    that does not start servers over stdio, as n8n's and Dify's do not. The
    token, when SLUICER_API_TOKEN is set, goes in "Authorization: Bearer".
    Private addresses are refused unless SLUICER_ALLOW_PRIVATE=1, as for the
    MCP server. Exits 2 without listening when it cannot serve safely.
    """
    try:
        serve_http(
            host, port, timeout=timeout, allow_unauthenticated=allow_unauthenticated
        )
    except (ApiExtraMissing, Unprotected) as refused:
        _fail(str(refused), refused)


@click.command("mcp")
@click.option(
    "--tools",
    help="Register only these tools, comma-separated: "
    "--tools extract_declared,page_markdown. All twelve by default.",
)
def mcp_command(tools: str | None) -> None:
    """Run the MCP server over stdio (needs sluicer[mcp]), as sluicer-mcp does.

    For a client that starts a package's own command, as the MCP Registry's
    entry does: uvx --with "sluicer[mcp]" sluicer mcp. Each tool registered
    costs an agent context whether it is called or not; --tools, or the
    SLUICER_MCP_TOOLS variable, keeps only those named.
    """
    from sluicer.mcp_server import main as run

    if tools is None:
        run()
    else:
        run(tools=[name.strip() for name in tools.split(",") if name.strip()])
