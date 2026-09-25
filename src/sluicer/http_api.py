"""Sluicer over HTTP: the MCP server's tools, each at an address of its own,
and the MCP server itself at ``/mcp``.

``sluicer serve`` runs it; it needs the ``api`` extra. No tool is written here
a second time. The app is built from the server ``build_server`` returns,
through the SDK's own ``list_tools`` and ``call_tool``, so an HTTP call gets the
same argument validation, the same output-schema check and the same answer as
an MCP call, and a tool registered there is at ``POST /v1/tools/<name>`` with
nothing added here. ``/mcp`` is the SDK's own streamable HTTP transport over
that same server, for a client that speaks MCP and not stdio (n8n, Dify).

What this module adds is what a socket needs and stdio does not: a status for
every answer (``STATUS``), a bearer token, a refusal to listen beyond loopback
without one, a bound on the body, a time budget per request, workers that keep
a call which fetches nothing from waiting behind calls that fetch, and an
answer only to requests addressed to this machine when that is where it listens.

Importable in a base install, as the command line imports it: nothing optional
is imported until an app is built.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import importlib
import ipaddress
import json
import logging
import os
import sys
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Mapping,
    Sequence,
)
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

from sluicer import __version__, mcp_server
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch.result import MAX_RESPONSE_BYTES

logger = logging.getLogger(__name__)

TOKEN_ENV = "SLUICER_API_TOKEN"
"""The bearer token every request but ``GET /health`` must carry, when set."""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

TIME_BUDGET_SECONDS = 120.0
"""How long one request may take, reading its body included, before a 504.

One URL on the default ladder can cost twenty seconds of plain HTTP and thirty
of a browser, and ``compile_extractor`` fetches each page it is given, one after
another. A call that runs out keeps running to its end on its worker, and its
answer is dropped: a thread cannot be stopped from outside. ``MAX_CALLS`` is
what bounds how many such calls there can be.
"""

MAX_BODY_BYTES = MAX_RESPONSE_BYTES
"""The largest request body read, 16 MiB: the bound a fetched page is held to."""

MAX_CALLS = 4
"""Tool calls that may fetch running at once, a timed-out one included until it ends.

Each may hold a browser. A call beyond these waits for a worker, inside its own
time budget, and one that runs out while waiting is never started.
"""

MAX_READS = 4
"""Tool calls that fetch nothing running at once, on workers of their own.

A call whose every page is handed in (``may_fetch``) never waits behind the
calls that fetch: four slow sites held every worker, and ``extract_declared``
on HTML handed in waited about 65 s behind them, its budget before 0.7.1. It
only parses, so it waits at most for other calls that only parse.
"""

PAGE_ARGUMENTS = ("html_or_url", "url", "url_or_text", "pages")
"""The arguments the tools take a page through, a URL or the page itself.

A test holds every tool to naming its page with one of these.
"""

MCP_PATH = "/mcp"
"""Where ``serve`` answers MCP over streamable HTTP."""

MAX_CONNECTIONS = 64
"""Connections uvicorn holds at once before it answers 503 itself."""

TOOL_STATUS: dict[str, int] = {
    "bad_input": 400,
    "refused_by_robots": 403,
    "refused_by_site": 403,
    "payment_required": 402,
    "refused_address": 403,
    "too_large": 413,
    "missing_extra": 501,
    "fetch_failed": 502,
    # RFC 7725's Unavailable For Legal Reasons: the rights holder reserved it.
    "tdm_reserved": 451,
}
"""The status each of the tools' error codes is sent with.

One entry per member of ``sluicer.mcp_answers.ErrorCode``, and a test holds the
two to the same set, so a code a tool learns cannot reach a client as a 500.
"""

DOOR_STATUS: dict[str, int] = {
    "unauthorized": 401,
    "not_found": 404,
    "method_not_allowed": 405,
    "unsupported_media_type": 415,
    "misdirected": 421,
    "cross_origin": 403,
    "internal_error": 500,
    "timed_out": 504,
}
"""The codes only the HTTP door answers with, and their status.

It also answers ``bad_input`` (a body that is not a JSON object, or arguments
that do not fit the tool's input schema) and ``too_large`` (a body over
``MAX_BODY_BYTES``) with the tools' own statuses. ``timed_out`` is the only
retryable one here. Only ``/mcp`` answers ``cross_origin``.
"""

STATUS: dict[str, int] = {**TOOL_STATUS, **DOOR_STATUS}


class ApiExtraMissing(MissingExtra):
    """The optional ``api`` extra is not installed, as opposed to broken."""


class Unprotected(ValueError):
    """Asked to listen beyond loopback with no token, and not told to anyway."""


def status_of(answer: Mapping[str, Any]) -> int:
    """The HTTP status an answer is sent with.

    200 whenever the request did what it asked for, which is not the same as
    ``ok``. A replayed page that broke its extractor (``run_extractor``, with
    ``failed``) and a heal that lost data (``heal_extractor``, with ``lost``)
    are ``ok`` false with no ``error``: the tool ran, read the pages, and its
    answer is that they drifted. That is the finding the call was made for, and
    a 4xx would tell an HTTP client to fix a request that was right. Only an
    ``error`` means there is no answer, and its code picks the status; a code
    this table does not know is a 500.
    """
    error = answer.get("error")
    if answer.get("ok") is True or not isinstance(error, Mapping):
        return 200
    return STATUS.get(str(error.get("code")), 500)


def refusal(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    """An answer in the tools' error shape, for what the door itself refuses."""
    return {
        "ok": False,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


def is_loopback(host: str) -> bool:
    """Whether ``host`` names this machine and nothing else.

    ``localhost`` or a loopback address; ``0.0.0.0`` and ``::`` are every
    interface, so they are not.
    """
    name = host.strip().lower()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _addressed_locally(host_header: str | None) -> bool:
    """Whether a request's ``Host`` names this machine.

    A page in the user's own browser can reach a server on loopback: it points
    a name it owns at 127.0.0.1 and asks it (DNS rebinding). The browser still
    sends that name as ``Host``, so a server that listens only on loopback
    answers only requests addressed to a loopback name.
    """
    header = (host_header or "").strip()
    if header.startswith("["):
        name, _, port = header[1:].partition("]")
        port = port.removeprefix(":")
    else:
        name, _, port = header.partition(":")
    return bool(name) and (not port or port.isdigit()) and is_loopback(name)


def _from_here(origin: str | None, host: str | None) -> bool:
    """Whether a request's ``Origin``, when it sends one, is this server's own.

    MCP's streamable HTTP transport must refuse an ``Origin`` that is not valid
    with a 403 (spec 2026-07-28, "Security Warning"). A browser sends one with
    every POST; a client that is not a browser, as n8n's and Dify's are not,
    sends none. This server serves no page, so the only origin a browser could
    rightly name is its own: the scheme and the very ``Host`` it was asked by.
    ``null``, a sandboxed or local file's origin, is not.
    """
    if origin is None:
        return True
    scheme, _, place = origin.strip().lower().partition("://")
    return (
        scheme in ("http", "https")
        and bool(place)
        and place == (host or "").strip().lower()
    )


def _bearer_matches(header: str | None, token: str) -> bool:
    scheme, _, given = (header or "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(
        given.strip().encode(), token.encode()
    )


def _unfit(name: str, refused: Exception) -> str:
    """The sentence for arguments the SDK refused, one clause per field.

    The SDK's own message is pydantic's: several lines, a clipped copy of each
    rejected value and a documentation link per field. The field and what was
    wrong with it are what a caller acts on.
    """
    errors = getattr(refused.__cause__, "errors", None)
    if not callable(errors):
        return str(refused)
    found = [
        f"{'.'.join(str(part) for part in error['loc']) or 'the arguments'}: "
        f"{error['msg']}"
        for error in errors(include_url=False, include_input=False)
    ]
    return f"the arguments do not fit {name}'s input schema: " + "; ".join(found)


def _modules() -> SimpleNamespace:
    """Starlette and the SDK's parts, or say the ``api`` extra is missing.

    Only an absent top-level package counts as the extra missing; a broken
    install keeps its traceback, as everywhere else (``sluicer.extras``).
    """
    doing = "Serving the HTTP API"
    applications = import_extra(
        "starlette.applications", "api", doing=doing, error=ApiExtraMissing
    )
    tool_errors = import_extra(
        "mcp.server.mcpserver.exceptions",
        "api",
        doing=doing,
        package="the mcp package",
        error=ApiExtraMissing,
    )
    return SimpleNamespace(
        applications=applications,
        tool_errors=tool_errors,
        types=importlib.import_module("mcp.types"),
        transport_security=importlib.import_module("mcp.server.transport_security"),
        datastructures=importlib.import_module("starlette.datastructures"),
        exceptions=importlib.import_module("starlette.exceptions"),
        requests=importlib.import_module("starlette.requests"),
        responses=importlib.import_module("starlette.responses"),
        routing=importlib.import_module("starlette.routing"),
    )


def may_fetch(arguments: Mapping[str, Any]) -> bool:
    """Whether a call with these arguments may reach the network.

    Read as the tools read a page (``sluicer.mcp_server``): a string that
    starts with ``http://`` or ``https://`` is fetched, and anything else in
    ``PAGE_ARGUMENTS`` is the page itself. A call that names no page there,
    or names one that is not a string, is taken to fetch: that is the side
    on which a wrong guess only makes the call wait.
    """
    pages: list[Any] = []
    for name in PAGE_ARGUMENTS:
        given = arguments.get(name)
        if isinstance(given, list):
            pages.extend(given)
        elif given is not None:
            pages.append(given)
    return not pages or any(
        not isinstance(page, str)
        or page.strip().lower().startswith(("http://", "https://"))
        for page in pages
    )


def _run_tool(
    call_tool: Callable[..., Coroutine[Any, Any, Any]],
    name: str,
    arguments: dict[str, Any],
) -> Any:
    """One tool call through the SDK, on a worker thread with a loop of its own.

    The SDK runs a tool on an anyio worker of the calling loop, and anyio holds
    a cancel from its own scopes until that worker returns: measured on
    2026-09-23 with mcp 2.2.0, a call whose page took two seconds was stopped
    at 2.01 s by a 0.3 s ``anyio.move_on_after``, and at 0.30 s by
    ``asyncio.wait_for`` only because asyncio's own cancel is not held. On a
    pool of this module's, the budget does not rest on that difference, and
    ``MAX_CALLS`` and ``MAX_READS`` bound the calls still running after their
    answer was sent. ``call_tool`` is the server's own, the SDK's.
    """
    return asyncio.run(call_tool(name, arguments))


async def _body(request: Any, limit: int) -> bytes | None:
    """The request's body, or None once it is over ``limit`` bytes.

    A declared length over the bound is refused before a byte is read; a body
    sent in chunks is counted as it arrives.
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def build_app(
    server: Any = None,
    *,
    token: str | None = None,
    local_only: bool = True,
    timeout: float = TIME_BUDGET_SECONDS,
    max_body: int = MAX_BODY_BYTES,
    max_calls: int = MAX_CALLS,
    max_reads: int = MAX_READS,
) -> Any:
    """Build the HTTP app over ``server``'s tools, the MCP server's by default.

    ``token``: when given, every request but ``GET /health`` must carry
    ``Authorization: Bearer <token>``. ``local_only``: answer only requests
    whose ``Host`` is a loopback name; on by default, and turned off by
    ``serve`` only when it listens beyond loopback. ``max_calls`` calls that
    may fetch and ``max_reads`` that fetch nothing run at once, each kind on
    workers of its own. Returns a Starlette app, typed ``Any`` because
    starlette is never imported at module level.

    ``/mcp`` is ``server``'s own streamable HTTP app, stateless, behind the
    same checks and an ``Origin`` check of its own. So that an MCP call runs on
    the same workers within the same budget, ``server.call_tool`` is replaced
    by one that does, the SDK's own kept as its ``__wrapped__``: the server
    handed in is changed, and stays so.
    """
    web = _modules()
    if server is None:
        server = mcp_server.build_server()
    fetching = ThreadPoolExecutor(
        max_workers=max_calls, thread_name_prefix="sluicer-fetch"
    )
    reading = ThreadPoolExecutor(
        max_workers=max_reads, thread_name_prefix="sluicer-read"
    )
    # A second app over the same server must not run its calls through the
    # first app's workers, which it would reach through the first's stand-in.
    direct = getattr(server.call_tool, "__wrapped__", server.call_tool)

    async def run(name: str, arguments: dict[str, Any]) -> Any:
        """One call on a worker of the pool its arguments choose."""
        pool = fetching if may_fetch(arguments) else reading
        return await asyncio.wrap_future(
            pool.submit(_run_tool, direct, name, arguments)
        )

    async def call_over_mcp(
        name: str, arguments: dict[str, Any], context: Any = None
    ) -> Any:
        """The SDK's ``call_tool`` for ``/mcp``: on the workers, within the budget.

        The SDK maps what this raises -- arguments that do not fit, a bug --
        as it does over stdio. A call that runs out of time is a tool error,
        MCP's own way to say a call failed: ``timed_out`` is no code of a
        tool's output schema, which a client checks structured content by.
        """
        try:
            return await asyncio.wait_for(run(name, arguments), timeout)
        except asyncio.TimeoutError:
            said = web.types.TextContent(
                type="text",
                text=f"timed_out: the call took longer than its {timeout:g} "
                "seconds; the same call may finish in time later",
            )
            return web.types.CallToolResult(content=[said], is_error=True)

    call_over_mcp.__wrapped__ = direct  # type: ignore[attr-defined]
    server.call_tool = call_over_mcp
    # The checks are this module's (``barred``), so the SDK's are turned off:
    # its list of hosts would refuse a Host of "localhost" with no port, and
    # every Host at all when listening beyond loopback.
    streamable = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        max_request_body_size=max_body,
        transport_security=web.transport_security.TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )

    def send(
        answer: Mapping[str, Any],
        status: int | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return web.responses.JSONResponse(
            dict(answer),
            status_code=status_of(answer) if status is None else status,
            headers=headers,
        )

    def refuse(
        code: str,
        message: str,
        *,
        retryable: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return send(refusal(code, message, retryable=retryable), STATUS[code], headers)

    def barred(
        headers: Mapping[str, str], *, open_to_all: bool = False, origin: bool = False
    ) -> tuple[str, str, dict[str, str] | None] | None:
        """What the door refuses a request for before reading it, if anything:
        its code, its sentence and the headers it is sent with."""
        if local_only and not _addressed_locally(headers.get("host")):
            return (
                "misdirected",
                "this server answers only requests addressed to this machine "
                "(localhost, 127.0.0.1 or [::1])",
                None,
            )
        if origin and not _from_here(headers.get("origin"), headers.get("host")):
            return (
                "cross_origin",
                "this server answers no page from another origin; a client that "
                "is not a browser sends no Origin",
                None,
            )
        if (
            token is not None
            and not open_to_all
            and not _bearer_matches(headers.get("authorization"), token)
        ):
            return (
                "unauthorized",
                "this server needs the header Authorization: Bearer <token>",
                {"WWW-Authenticate": 'Bearer realm="sluicer"'},
            )
        return None

    def guarded(
        handler: Callable[[Any], Awaitable[Any]], *, open_to_all: bool = False
    ) -> Callable[[Any], Awaitable[Any]]:
        async def endpoint(request: Any) -> Any:
            refused = barred(request.headers, open_to_all=open_to_all)
            if refused is not None:
                code, message, headers = refused
                return refuse(code, message, headers=headers)
            try:
                return await asyncio.wait_for(handler(request), timeout)
            except asyncio.TimeoutError:
                return refuse(
                    "timed_out",
                    f"the request took longer than its {timeout:g} seconds; "
                    "the same call may finish in time later",
                    retryable=True,
                )

        return endpoint

    async def health(request: Any) -> Any:
        return send({"ok": True, "version": __version__})

    async def listing(request: Any) -> Any:
        return send({"ok": True, "tools": await _described(server)})

    async def openapi(request: Any) -> Any:
        tools = await _described(server)
        return send(
            openapi_document(tools, secured=token is not None, local_only=local_only)
        )

    async def call(request: Any) -> Any:
        name = request.path_params["name"]
        if name not in {tool.name for tool in await server.list_tools()}:
            return refuse(
                "not_found",
                f"there is no tool named {name!r}; GET /v1/tools lists them",
            )
        media = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media != "application/json":
            return refuse(
                "unsupported_media_type",
                "the body must be the tool's arguments as application/json",
            )
        body = await _body(request, max_body)
        if body is None:
            return refuse("too_large", f"the request body is over {max_body} bytes")
        try:
            arguments = json.loads(body)
        except (ValueError, RecursionError) as bad:
            return refuse("bad_input", f"the body is not JSON: {bad}")
        if not isinstance(arguments, dict):
            return refuse(
                "bad_input",
                "the body must be a JSON object, the tool's arguments by name",
            )
        try:
            result = await run(name, arguments)
        except web.tool_errors.UnexpectedToolError:
            logger.exception("the tool %s raised", name)
            return refuse(
                "internal_error", f"{name} failed; the server's log has the traceback"
            )
        except web.tool_errors.ToolError as refused:
            # Anticipated: arguments that do not fit the tool's input schema,
            # which the SDK refuses before the tool runs, or a tool refusing on
            # purpose. Ours never do the second; they answer ok false instead.
            return refuse("bad_input", _unfit(name, refused))
        answer = getattr(result, "structured_content", None)
        if not isinstance(answer, dict):
            logger.error("the tool %s answered without structured content", name)
            return refuse("internal_error", f"{name} answered without an output schema")
        return send(answer)

    async def unrouted(request: Any, failure: Any) -> Any:
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            failure.status_code, "bad_input"
        )
        return send(
            refusal(code, str(failure.detail)), failure.status_code, failure.headers
        )

    async def crashed(request: Any, failure: Exception) -> Any:
        return refuse("internal_error", "the server failed; its log has the traceback")

    async def mcp(scope: Any, receive: Any, send: Any) -> None:
        """``/mcp``, once the door lets the request through.

        Only a POST. The transport's GET opens a stream for what a server
        sends unasked, and a stateless one has nothing to send: the SDK kept
        that stream open, empty, until the client left, one of uvicorn's
        connections held for each, and the transport lets a server answer 405
        instead. The body is read here, within the budget and the bound, and
        handed to the SDK whole, so a client that sends a byte now and then
        is a 504 like any request past its time.

        A refusal is a JSON-RPC error with no ``id``, as the transport's own
        are, with the door's code in its ``data``.
        """
        refused = barred(web.datastructures.Headers(scope=scope), origin=True)
        if refused is None and scope["method"] != "POST":
            refused = (
                "method_not_allowed",
                "this server answers MCP with a POST only; it keeps no session "
                "and sends nothing unasked",
                {"Allow": "POST"},
            )
        if refused is None:
            try:
                body = await asyncio.wait_for(
                    _body(web.requests.Request(scope, receive), max_body), timeout
                )
            except asyncio.TimeoutError:
                refused = (
                    "timed_out",
                    f"the request body took longer than its {timeout:g} seconds "
                    "to arrive",
                    None,
                )
            else:
                if body is None:
                    refused = (
                        "too_large",
                        f"the request body is over {max_body} bytes",
                        None,
                    )
                else:
                    await streamable(scope, _replaying(body, receive), send)
                    return
        code, message, headers = refused
        error = {"code": -32600, "message": message, "data": {"code": code}}
        answer = web.responses.JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": error},
            status_code=STATUS[code],
            headers=headers,
        )
        await answer(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        try:
            # The SDK's own lifespan for its app: the task group every
            # request to /mcp runs in.
            async with streamable.router.lifespan_context(streamable):
                yield
        finally:
            for pool in (fetching, reading):
                pool.shutdown(wait=False, cancel_futures=True)

    route = web.routing.Route
    return web.applications.Starlette(
        routes=[
            route("/health", guarded(health, open_to_all=True), methods=["GET"]),
            route("/v1/tools", guarded(listing), methods=["GET"]),
            route("/v1/tools/{name}", guarded(call), methods=["POST"]),
            route("/openapi.json", guarded(openapi), methods=["GET"]),
            # An ASGI app, not a function, so every method reaches the SDK,
            # which answers each as the transport says.
            route(MCP_PATH, _Asgi(mcp)),
        ],
        exception_handlers={
            web.exceptions.HTTPException: unrouted,
            Exception: crashed,
        },
        lifespan=lifespan,
    )


def _replaying(
    body: bytes, receive: Callable[[], Awaitable[Any]]
) -> Callable[[], Awaitable[Any]]:
    """An ASGI ``receive`` that gives ``body`` whole, then what ``receive`` gives.

    What follows the body is the client leaving, which the SDK still has to
    hear about.
    """
    pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def replay() -> Any:
        return pending.pop() if pending else await receive()

    return replay


class _Asgi:
    """An ASGI callable Starlette routes to as it is, every method included.

    A plain function would be taken for an endpoint that answers a request.
    """

    def __init__(self, app: Callable[[Any, Any, Any], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)


async def _described(server: Any) -> list[dict[str, Any]]:
    """Every tool as the SDK lists it over MCP: name, description, both schemas."""
    return [
        tool.model_dump(by_alias=True, exclude_none=True, mode="json")
        for tool in await server.list_tools()
    ]


_ERROR_ANSWER: dict[str, Any] = {
    "type": "object",
    "required": ["ok", "error"],
    "properties": {
        "ok": {"const": False},
        "error": {
            "type": "object",
            "required": ["code", "message", "retryable"],
            "properties": {
                "code": {"enum": sorted(STATUS)},
                "message": {"type": "string"},
                "retryable": {"type": "boolean"},
                "url": {"type": "string"},
                "extra": {"type": "string"},
            },
        },
    },
}

_HEALTH: dict[str, Any] = {
    "type": "object",
    "required": ["ok", "version"],
    "properties": {"ok": {"const": True}, "version": {"type": "string"}},
}

_TOOL_LIST: dict[str, Any] = {
    "type": "object",
    "required": ["ok", "tools"],
    "properties": {
        "ok": {"const": True},
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "inputSchema"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            },
        },
    },
}

_DEFS = "#/$defs/"
_COMPONENTS = "#/components/schemas/"


def openapi_document(
    tools: Sequence[Mapping[str, Any]], *, secured: bool, local_only: bool
) -> dict[str, Any]:
    """The OpenAPI 3.1 description of this server, from the tools' own schemas.

    ``tools`` is the listing ``GET /v1/tools`` serves. Each tool's input schema
    is its request body and its output schema its 200. A schema's ``$defs``
    move to ``components`` with their references rewritten, since ``#/$defs``
    inside an OpenAPI document resolves against the document, not the schema.
    """
    schemas: dict[str, Any] = {
        "ErrorAnswer": _ERROR_ANSWER,
        "Health": _HEALTH,
        "ToolList": _TOOL_LIST,
    }
    learnt = dict(schemas)
    errors = _error_responses(secured=secured, local_only=local_only)
    paths: dict[str, Any] = {
        "/health": {
            "get": {
                "operationId": "health",
                "summary": "Whether the server is up, and its version.",
                "security": [],
                "responses": {"200": _json("The server is up.", "Health")},
            }
        },
        "/v1/tools": {
            "get": {
                "operationId": "list_tools",
                "summary": "Every tool, with its input and output schemas.",
                "responses": {"200": _json("The tools.", "ToolList"), **errors},
            }
        },
    }
    for tool in sorted(tools, key=lambda described: str(described["name"])):
        name = str(tool["name"])
        description = str(tool.get("description") or name)
        answer = tool.get("outputSchema") or {"type": "object"}
        paths[f"/v1/tools/{name}"] = {
            "post": {
                "operationId": name,
                "summary": description.strip().splitlines()[0],
                "description": description,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _hoisted(
                                tool["inputSchema"], schemas, learnt, name
                            )
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": (
                            "The tool's answer. ok false without an error is still "
                            "an answer: a page that drifted, or a heal that lost data."
                        ),
                        "content": {
                            "application/json": {
                                "schema": _hoisted(answer, schemas, learnt, name)
                            }
                        },
                    },
                    **errors,
                },
            }
        }
    document: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Sluicer",
            "version": __version__,
            "description": (
                "The MCP server's tools over HTTP. Deterministic extraction of the "
                "structured data a web page declares, with no model in the loop."
            ),
        },
        "paths": paths,
        "components": {"schemas": schemas},
    }
    if secured:
        document["components"]["securitySchemes"] = {
            "bearer": {"type": "http", "scheme": "bearer"}
        }
        document["security"] = [{"bearer": []}]
    return document


def _json(description: str, schema: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": _COMPONENTS + schema}}},
    }


def _error_responses(*, secured: bool, local_only: bool) -> dict[str, Any]:
    """One response per status a request that reached a tool's address can get."""
    unreachable = {"not_found", "method_not_allowed", "cross_origin"}
    if not secured:
        unreachable.add("unauthorized")
    if not local_only:
        unreachable.add("misdirected")
    codes_of: dict[int, list[str]] = {}
    for code, status in sorted(STATUS.items()):
        if code not in unreachable:
            codes_of.setdefault(status, []).append(code)
    return {
        str(status): _json(", ".join(codes), "ErrorAnswer")
        for status, codes in sorted(codes_of.items())
    }


def _hoisted(
    schema: Mapping[str, Any],
    schemas: dict[str, Any],
    learnt: dict[str, Any],
    owner: str,
) -> Any:
    """``schema`` with its ``$defs`` moved into ``schemas`` and pointed at there.

    A definition already there under the same name is shared, when it is the
    same. If any one differs, every definition of this schema is filed under
    ``owner.<name>`` instead, so no reference can reach the other tool's.
    ``learnt`` keeps each definition as it arrived, before its references were
    rewritten, which is what "the same" is judged on.
    """
    definitions: Mapping[str, Any] = schema.get("$defs") or {}
    clash = any(
        name in learnt and learnt[name] != definition
        for name, definition in definitions.items()
    )
    filed = {name: f"{owner}.{name}" if clash else name for name in definitions}

    def moved(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {
                key: _COMPONENTS + filed.get(value[len(_DEFS) :], value[len(_DEFS) :])
                if key == "$ref" and isinstance(value, str) and value.startswith(_DEFS)
                else moved(value)
                for key, value in node.items()
                if key != "$defs"
            }
        if isinstance(node, list):
            return [moved(item) for item in node]
        return node

    for name, definition in definitions.items():
        learnt.setdefault(filed[name], definition)
        schemas.setdefault(filed[name], moved(definition))
    return moved(schema)


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    timeout: float = TIME_BUDGET_SECONDS,
    allow_unauthenticated: bool = False,
) -> None:
    """Serve the app with uvicorn until interrupted, token from ``SLUICER_API_TOKEN``.

    Raises ``Unprotected`` rather than listen beyond loopback with no token,
    unless ``allow_unauthenticated``: anyone who can reach the port could make
    this machine fetch any URL. Raises ``ApiExtraMissing`` without the extra.
    """
    token = os.environ.get(TOKEN_ENV, "").strip() or None
    local = is_loopback(host)
    if not (local or token or allow_unauthenticated):
        raise Unprotected(
            f"Refusing to listen on {host} with no token: anyone who can reach port "
            f"{port} could make this machine fetch any URL. Set {TOKEN_ENV}, or pass "
            "--allow-unauthenticated if something in front of this server already "
            "decides who may call it."
        )
    uvicorn = import_extra(
        "uvicorn", "api", doing="Serving the HTTP API", error=ApiExtraMissing
    )
    app = build_app(token=token, local_only=local, timeout=timeout)
    guard = "a token" if token else "no token"
    if local:
        guard += ", answering only requests addressed to this machine"
    print(f"sluicer {__version__}: serving the tools with {guard}.", file=sys.stderr)
    uvicorn.run(
        app,
        host=host,
        port=port,
        limit_concurrency=MAX_CONNECTIONS,
        server_header=False,
        log_level="info",
    )
