"""MCP over streamable HTTP: ``/mcp`` on the app ``sluicer serve`` runs.

Through the SDK's own client, over httpx2's ASGI transport, so the app is
reached in process with no socket and every request goes through the door as
a real one would. The tests skip without the ``api`` extra. ``/mcp`` is the
MCP server's own streamable HTTP app over the very server the REST routes
answer from, so what a client lists and gets here is held to what the server
answers over stdio, not to a list written here.
"""

import asyncio
import time

import pytest

from sluicer import http_api
from test_http_api import PAGE, TOKEN, _holding_every_fetch_worker
from test_mcp_server import fake_fetch

BASE = "http://127.0.0.1:8000"
ASKS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.fixture
def mcp():
    """Run ``act(client, http)`` against an app, inside the app's lifespan.

    ``client`` is the SDK's ``Client`` over streamable HTTP, ``http`` the
    httpx2 client under it, which carries ``headers`` on every request.
    ``connect=False`` gives no MCP client, for requests the door refuses
    before a handshake could happen.
    """
    pytest.importorskip("starlette")
    pytest.importorskip("mcp.server.mcpserver")
    httpx2 = pytest.importorskip("httpx2")
    import anyio
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    def over(
        app, act, *, headers=None, mode="legacy", base_url=BASE, connect=True
    ):
        async def go():
            async with app.router.lifespan_context(app):
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    base_url=base_url,
                    headers=headers or {},
                ) as http:
                    if not connect:
                        return await act(None, http)
                    transport = streamable_http_client(
                        f"{base_url}{http_api.MCP_PATH}", http_client=http
                    )
                    async with Client(transport, mode=mode) as client:
                        return await act(client, http)

        return anyio.run(go)

    return over


def _server():
    pytest.importorskip("mcp.server.mcpserver")
    from sluicer.mcp_server import build_server

    return build_server()


def _dumped(tools):
    return [
        tool.model_dump(by_alias=True, exclude_none=True, mode="json")
        for tool in tools
    ]


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_the_tools_listed_over_http_are_the_servers_own(mcp, mode):
    """Names, descriptions, annotations and both schemas, as stdio lists them.

    ``legacy`` is the initialize handshake n8n's and Dify's clients make;
    ``auto`` reaches the 2026-07-28 revision, which has none.
    """
    server = _server()
    over_stdio = _dumped(asyncio.run(server.list_tools()))

    async def act(client, http):
        return _dumped((await client.list_tools()).tools)

    listed = mcp(http_api.build_app(server), act, mode=mode)

    assert listed == over_stdio
    assert len(listed) == 10
    for tool in listed:
        assert tool["annotations"]["readOnlyHint"] is True, tool["name"]
        assert tool["outputSchema"]["required"] == ["ok"], tool["name"]


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_a_call_over_http_answers_what_the_server_answers(mcp, mode):
    server = _server()
    direct = asyncio.run(server.call_tool("extract_declared", {"html_or_url": PAGE}))

    async def act(client, http):
        return await client.call_tool("extract_declared", {"html_or_url": PAGE})

    result = mcp(http_api.build_app(server), act, mode=mode)

    assert result.is_error is False
    assert result.structured_content == direct.structured_content
    assert result.structured_content["summary"]["title"]["value"] == "Pad"


def test_no_session_is_kept_for_a_client(mcp):
    """Every tool only reads, so the transport runs stateless: an initialize
    is answered with no session to come back with."""

    async def act(client, http):
        return await http.post(
            http_api.MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "a test", "version": "1"},
                },
            },
            headers=ASKS,
        )

    answer = mcp(http_api.build_app(), act, connect=False)

    assert answer.status_code == 200
    assert answer.json()["result"]["serverInfo"]["name"] == "sluicer"
    assert "mcp-session-id" not in answer.headers


def _refusal(answer, status, code):
    assert answer.status_code == status, answer.text
    body = answer.json()
    assert body["jsonrpc"] == "2.0" and body["id"] is None
    assert body["error"]["data"] == {"code": code}
    return body


def test_a_token_is_asked_of_every_request_to_mcp(mcp):
    app = http_api.build_app(token=TOKEN)

    async def refused(client, http):
        return [
            await http.post(http_api.MCP_PATH, json=LIST_TOOLS, headers=ASKS),
            await http.post(
                http_api.MCP_PATH,
                json=LIST_TOOLS,
                headers={**ASKS, "Authorization": "Bearer not-it"},
            ),
            await http.post(
                http_api.MCP_PATH,
                json=LIST_TOOLS,
                headers={**ASKS, "Authorization": f"Basic {TOKEN}"},
            ),
            await http.get(http_api.MCP_PATH),
        ]

    async def listed(client, http):
        return [tool.name for tool in (await client.list_tools()).tools]

    for answer in mcp(app, refused, connect=False):
        _refusal(answer, 401, "unauthorized")
        assert answer.headers["www-authenticate"] == 'Bearer realm="sluicer"'
    names = mcp(
        http_api.build_app(token=TOKEN),
        listed,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert "extract_declared" in names


def test_without_a_token_the_client_cannot_connect(mcp):
    import httpx2
    from mcp.shared.exceptions import MCPError

    async def act(client, http):
        return await client.list_tools()

    with pytest.raises((MCPError, httpx2.HTTPError, ExceptionGroup)):
        mcp(http_api.build_app(token=TOKEN), act)


@pytest.mark.parametrize(
    "origin",
    [
        "http://attacker.example",
        "http://attacker.example:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "https://127.0.0.1:8000.attacker.example",
        "null",
        "",
    ],
)
def test_a_page_from_another_origin_is_refused_before_any_tool_runs(
    mcp, monkeypatch, origin
):
    """MCP's streamable HTTP must refuse an Origin that is not valid with a
    403. This server serves no page, so only its own origin is one; a
    loopback page on another port is another origin, and so is ``null``."""
    fetch = fake_fetch(monkeypatch)
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "fetch_page", "arguments": {"url": "https://a.example/"}},
    }

    async def act(client, http):
        return await http.post(
            http_api.MCP_PATH, json=call, headers={**ASKS, "Origin": origin}
        )

    answer = mcp(http_api.build_app(), act, connect=False)

    _refusal(answer, 403, "cross_origin")
    assert fetch.calls == []


def test_the_servers_own_origin_and_none_at_all_are_answered(mcp):
    async def act(client, http):
        return [
            await http.post(
                http_api.MCP_PATH,
                json=LIST_TOOLS,
                headers={**ASKS, "Origin": "http://127.0.0.1:8000"},
            ),
            await http.post(http_api.MCP_PATH, json=LIST_TOOLS, headers=ASKS),
        ]

    for answer in mcp(http_api.build_app(), act, connect=False):
        assert answer.status_code == 200, answer.text
        assert len(answer.json()["result"]["tools"]) == 10


@pytest.mark.parametrize(
    ("origin", "host", "here"),
    [
        (None, "127.0.0.1:8000", True),
        ("http://127.0.0.1:8000", "127.0.0.1:8000", True),
        ("HTTPS://Sluicer.Example", "sluicer.example", True),
        ("http://[::1]:8000", "[::1]:8000", True),
        ("http://127.0.0.1:8000", "localhost:8000", False),
        ("http://127.0.0.1", "127.0.0.1:8000", False),
        ("file://", "127.0.0.1:8000", False),
        ("ws://127.0.0.1:8000", "127.0.0.1:8000", False),
        ("null", "127.0.0.1:8000", False),
        ("http://127.0.0.1:8000", None, False),
    ],
)
def test_an_origin_is_this_servers_own_only_with_the_host_it_was_asked_by(
    origin, host, here
):
    assert http_api._from_here(origin, host) is here


def test_on_loopback_mcp_answers_only_requests_addressed_to_this_machine(mcp):
    async def act(client, http):
        return await http.post(
            http_api.MCP_PATH,
            json=LIST_TOOLS,
            headers={**ASKS, "Host": "attacker.example:8000"},
        )

    _refusal(mcp(http_api.build_app(), act, connect=False), 421, "misdirected")


def test_beyond_loopback_any_host_is_answered_with_the_token(mcp):
    async def act(client, http):
        return (await client.list_tools()).tools

    tools = mcp(
        http_api.build_app(token=TOKEN, local_only=False),
        act,
        headers={"Authorization": f"Bearer {TOKEN}"},
        base_url="http://sluicer.example",
    )

    assert len(tools) == 10


def test_private_addresses_are_refused_over_mcp_unless_the_server_is_told(
    mcp, monkeypatch
):
    fetch = fake_fetch(monkeypatch)

    async def act(client, http):
        monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
        await client.call_tool("fetch_page", {"url": "https://example.com/p"})
        monkeypatch.setenv("SLUICER_ALLOW_PRIVATE", "1")
        await client.call_tool("fetch_page", {"url": "https://example.com/p"})

    mcp(http_api.build_app(), act)

    assert [call["allow_private"] for call in fetch.calls] == [False, True]


def test_a_call_that_fetches_nothing_never_waits_behind_fetches_over_mcp(
    mcp, monkeypatch
):
    """The same workers as the REST routes, so the same separation."""
    import anyio

    async def act(client, http):
        def fetching(url):
            anyio.from_thread.run(client.call_tool, "fetch_page", {"url": url})

        async with anyio.create_task_group() as calls:
            held = await anyio.to_thread.run_sync(
                lambda: _holding_every_fetch_worker(
                    monkeypatch, fetching, many=0
                )
            )
            released = held[0]
            for n in range(http_api.MAX_CALLS):
                calls.start_soon(
                    client.call_tool,
                    "fetch_page",
                    {"url": f"https://s{n}.example/slow"},
                )
            await _started(http_api.MAX_CALLS)
            began = time.monotonic()
            answer = await client.call_tool("extract_declared", {"html_or_url": PAGE})
            took = time.monotonic() - began
            released.set()
        return answer, took

    answer, took = mcp(http_api.build_app(timeout=3), act)

    assert answer.is_error is False
    assert answer.structured_content["summary"]["title"]["value"] == "Pad"
    assert took < 0.5
