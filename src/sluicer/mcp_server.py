"""Sluicer as a tool an agent can call, over the Model Context Protocol.

Six tools -- ``extract_declared``, ``page_markdown``, ``fetch_page``, and
``compile_extractor``, ``run_extractor``, ``heal_extractor`` -- expose what the
library does and add no logic of their own. Run it with
``sluicer-mcp``; it needs the ``mcp`` extra.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from sluicer import __version__, extractor as extractor_module
from sluicer.api import extract
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch import AddressRefused, FetchFailed, RobotsRefused
from sluicer.markdown import to_markdown

MAX_HTML_CHARS = 200_000
"""How much of a page ``fetch_page`` hands an agent.

Measured on 2026-09-22, one product page was 3.95 MB of JSON, which is not a
tool result but the end of the agent's context. The page is cut here, and the
result says it was cut and how long it really was.
"""

ALLOW_PRIVATE_ENV = "SLUICER_ALLOW_PRIVATE"
"""Set to 1 to let the server fetch addresses off the public internet.

Off by default: an agent reading untrusted pages can be told to fetch
``http://localhost:8080/admin`` or a cloud metadata endpoint, and this server
runs on a machine that can reach both.
"""


class McpExtraMissing(MissingExtra):
    """The optional ``mcp`` extra is not installed, as opposed to broken."""


def _server_class() -> Any:
    """Return the SDK's ``MCPServer`` class, or say the extra is not installed.

    ``Any``, because ``mcp`` is never imported at module level and there is no
    class here to name. The extra pins ``mcp>=2``: 2.x renamed ``FastMCP`` to
    ``MCPServer`` and removed the old name.

    Only a missing top-level ``mcp`` counts as the extra being absent. mcp 2.x
    ships ``mcp/server/fastmcp.py`` solely to raise ``ModuleNotFoundError``
    with a migration guide; a wider match would report that as "install
    sluicer[mcp]" to someone who has it, and throw the guide away.
    """
    return import_extra(
        "mcp.server.mcpserver",
        "mcp",
        doing="Running the MCP server",
        package="the mcp package",
        error=McpExtraMissing,
    ).MCPServer


def _answers_instead_of_raising(tool: Callable[..., Any]) -> Callable[..., Any]:
    """Return the answerable failures as the tool's result, never as its content.

    Each is a mapping with ``error`` and a key saying which kind, because they
    call for different responses: ``missing_extra`` (install what the message
    says), ``refused_by_robots`` (do not work around it), ``refused_address``
    (a private address, refused by default), ``fetch_failed`` (worth trying
    later) and ``bad_input``. Raised instead, each reached the agent as the
    SDK's bare "Error executing tool".

    The shape is deliberately not the shape of any tool's content: returned as
    a ``str``, "Turning a page into markdown needs trafilatura" sat exactly
    where a page's words go, and an agent would summarise it as the page. So
    ``page_markdown`` returns ``str | dict``. A real bug inside a tool still
    raises.
    """

    @functools.wraps(tool)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except MissingExtra as missing:
            return {"error": str(missing), "missing_extra": missing.extra}
        except RobotsRefused as refused:
            return {"error": str(refused), "refused_by_robots": refused.url}
        except AddressRefused as refused:
            return {"error": str(refused), "refused_address": refused.url}
        except FetchFailed as failed:
            return {"error": str(failed), "fetch_failed": failed.url}
        except _BadInput as bad:
            return {"error": str(bad), "bad_input": True}

    return guarded


class _BadInput(ValueError):
    """A tool was handed something it cannot take."""


def _allow_private() -> bool:
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _html_of(html_or_url: str) -> tuple[str, str | None, dict[str, Any] | None]:
    """Return the page's HTML, the URL to attribute it to, and the fetch record.

    The URL is where the fetch landed, after redirects, since that is what the
    page's relative links resolve against; for literal HTML it is None.
    """
    if html_or_url.strip().lower().startswith(("http://", "https://")):
        from sluicer.fetch import fetch

        fetched = fetch(html_or_url, allow_private=_allow_private())
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
    """Build the server with its six tools registered.

    Returns the SDK's ``MCPServer``, typed ``Any`` because ``mcp`` is never
    imported at module level.
    """
    server = _server_class()(
        "sluicer",
        version=__version__,
        instructions=(
            "Deterministic extraction of the structured data a web page already "
            "declares, with no model in the loop. Every field names the vocabulary "
            "it came from. Fetching obeys robots.txt and refuses private addresses."
        ),
    )

    # The SDK instance is untyped here, so its decorator is too. The ignores
    # are narrow on purpose: ``warn_unused_ignores`` flags them the day the SDK
    # ships types, which a module-wide relaxation would not.
    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def extract_declared(html_or_url: str, induce: bool = False) -> dict[str, Any]:
        """Read the structured data a page declares, with where each value came from.

        html_or_url: an http(s) URL to fetch, or the HTML itself.
        induce: also read repeated rows (a listing, a feed) from a page that
        declares nothing about them; those fields say source "induced".

        Returns records of typed fields, each {"value", "source"}, where source
        is the vocabulary that declared it (jsonld, microdata, opengraph, html,
        ...). A nested value such as a price inside "offers" arrives whole.
        On failure returns {"error": ...} and never a record.
        """
        html, url, fetched = _html_of(html_or_url)
        result = asdict(extract(html, url=url, induce=induce))
        if fetched is not None:
            result["fetch"] = fetched
        return result

    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def page_markdown(html_or_url: str) -> str | dict[str, Any]:
        """Return a page's main content as markdown, without navigation or footer.

        html_or_url: an http(s) URL to fetch, or the HTML itself.

        Text is always the page's own content. A failure is never text: it
        comes back as {"error": ...}, so it cannot be mistaken for the page.
        """
        html, url, _fetched = _html_of(html_or_url)
        return to_markdown(html, url=url)

    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def fetch_page(url: str) -> dict[str, Any]:
        """Fetch a page's HTML, and say what it cost: plain HTTP or a browser.

        url: an http(s) URL. Literal HTML is refused, since nothing would be
        fetched.

        Returns {"html", "url", "fetch", "truncated", "length"}. The HTML is
        cut at 200,000 characters; prefer extract_declared or page_markdown,
        which return what is in the page rather than all of it.
        """
        if not url.strip().lower().startswith(("http://", "https://")):
            # Refused rather than echoed back: a caller handed the string it
            # sent, with no way to tell nothing was fetched, is worse off.
            raise _BadInput(f"fetch_page needs an http:// or https:// URL, got {url!r}")
        html, landed, fetched = _html_of(url)
        return {
            "html": html[:MAX_HTML_CHARS],
            "url": landed,
            "fetch": fetched,
            "truncated": len(html) > MAX_HTML_CHARS,
            "length": len(html),
        }

    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def compile_extractor(
        pages: list[str], listing: bool | None = None
    ) -> dict[str, Any]:
        """Learn an extractor from pages of one template, to replay later for free.

        pages: http(s) URLs, or the HTML itself, of pages built from one
        template -- two or three pages of one listing, or of one kind of
        product page.
        listing: learn the rows the pages repeat; by default only where they
        declare nothing about a thing.

        Returns {"extractor": {...}}: keep that object and hand it to
        run_extractor. It holds what the pages declared, the listing's place,
        its fields, and what every field looked like.
        """
        if not pages:
            raise _BadInput("compile_extractor needs at least one page")
        read = [_html_of(one)[:2] for one in pages]
        try:
            learnt = extractor_module.compile_extractor(read, listing=listing)
        except extractor_module.NothingToLearn as nothing:
            raise _BadInput(str(nothing)) from nothing
        return {"extractor": json.loads(learnt.to_json())}

    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def run_extractor(extractor: dict[str, Any], html_or_url: str) -> dict[str, Any]:
        """Replay an extractor on one page, and check the page still keeps to it.

        extractor: the object compile_extractor returned.
        html_or_url: an http(s) URL to fetch, or the HTML itself.

        Returns {"ok", "rows", "summary", "failed"}. ok is false when the page
        drifted -- the listing moved, rows or a field vanished, a price no
        longer looks like a price -- and "failed" says which expectation broke.
        Never read rows from a run whose ok is false as if nothing happened.
        """
        loaded = _extractor_from(extractor)
        html, url, _fetched = _html_of(html_or_url)
        run = extractor_module.run_extractor(loaded, html, url=url)
        return {
            "ok": run.ok,
            "rows": run.rows,
            "summary": run.summary,
            "failed": [asdict(check) for check in run.checks if not check.ok],
        }

    @server.tool()  # type: ignore[untyped-decorator]
    @_answers_instead_of_raising
    def heal_extractor(extractor: dict[str, Any], pages: list[str]) -> dict[str, Any]:
        """Learn pages again after a redesign, and say what moved where.

        extractor: the object compile_extractor returned.
        pages: http(s) URLs, or the HTML itself, of the redesigned pages.

        Returns {"extractor", "changes"}. A field that moved keeps its old
        name, so rows read with the healed extractor keep their columns;
        "vanished" or "summary-lost" in changes is data the page no longer has.
        """
        loaded = _extractor_from(extractor)
        if not pages:
            raise _BadInput("heal_extractor needs at least one page")
        read = [_html_of(one)[:2] for one in pages]
        try:
            healed, changes = extractor_module.heal(loaded, read)
        except extractor_module.NothingToLearn as nothing:
            raise _BadInput(str(nothing)) from nothing
        return {
            "extractor": json.loads(healed.to_json()),
            "changes": [asdict(change) for change in changes],
        }

    return server


def _extractor_from(given: dict[str, Any]) -> extractor_module.Extractor:
    try:
        return extractor_module.Extractor.from_json(json.dumps(given))
    except (ValueError, KeyError, TypeError) as invalid:
        raise _BadInput(
            f"not an extractor from compile_extractor: {invalid}"
        ) from invalid


def main() -> None:
    """Run the server over stdio, or explain a missing ``mcp`` extra in one line.

    A broken install, as opposed to a missing one, keeps its traceback.
    """
    try:
        server = build_server()
    except McpExtraMissing as missing:
        print(str(missing), file=sys.stderr)
        raise SystemExit(1) from missing
    # scrapling logs every request at INFO into the server's stderr, and sets
    # its level when first imported; a filter outlives that.
    logging.getLogger("scrapling").addFilter(
        lambda record: record.levelno >= logging.WARNING
    )
    server.run()
