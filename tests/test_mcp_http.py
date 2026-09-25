"""MCP over streamable HTTP: ``/mcp`` on the app ``sluicer serve`` runs.

Through the SDK's own client, over httpx2's ASGI transport, so the app is
reached in process with no socket and every request goes through the door as
a real one would. The tests skip without the ``api`` extra. ``/mcp`` is the
MCP server's own streamable HTTP app over the very server the REST routes
answer from, so what a client lists and gets here is held to what the server
answers over stdio, not to a list written here. ``tests/live/mcp_http_check.py``
asks the same of ``sluicer serve`` over a real socket.
"""

import asyncio
import threading
import time

import pytest

from sluicer import http_api
from test_http_api import PAGE, TOKEN
from test_mcp_server import fake_fetch

BASE = "http://127.0.0.1:8000"
ASKS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
FETCH_CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "fetch_page", "arguments": {"url": "https://a.example/"}},
}
DEADLINE = 20
"""Seconds any one test's requests may take: a hang is a failure, not a stall."""


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

    def over(app, act, *, headers=None, mode="legacy", base_url=BASE, connect=True):
        async def go():
            http = httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url=base_url,
                headers=headers or {},
            )
            with anyio.fail_after(DEADLINE):
                async with app.router.lifespan_context(app), http:
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
        tool.model_dump(by_alias=True, exclude_none=True, mode="json") for tool in tools
    ]


def _innermost(failure):
    """The one exception an exception group, however nested, carries."""
    while getattr(failure, "exceptions", None):
        (failure,) = failure.exceptions
    return failure


def _refusal(answer, status, code):
    """A refusal of the door: a JSON-RPC error with no id, its code in data."""
    assert answer.status_code == status, answer.text
    body = answer.json()
    assert body["jsonrpc"] == "2.0" and body["id"] is None
    assert body["error"]["data"] == {"code": code}
    return body


def _slow_fetches(monkeypatch):
    """A fetch that hangs until released; each one counts in ``started``."""
    fetch = fake_fetch(monkeypatch, html=PAGE)
    released = threading.Event()
    started = threading.Semaphore(0)

    def slow(url, **options):
        started.release()
        released.wait(10)
        return fetch(url, **options)

    monkeypatch.setattr("sluicer.fetch.fetch", slow)
    return fetch, started, released


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
    assert len(listed) == 12
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


def test_a_tools_refusal_over_http_is_its_answer_over_stdio(mcp):
    """A bound of a tool's holds here as over stdio, in the same words."""
    server = _server()
    arguments = {"url": "https://example.com/", "limit": 5000}
    direct = asyncio.run(server.call_tool("map_site", arguments))

    async def act(client, http):
        return await client.call_tool("map_site", arguments)

    result = mcp(http_api.build_app(server), act)

    assert result.structured_content == direct.structured_content
    assert result.structured_content["error"]["code"] == "bad_input"


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


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT"])
def test_only_a_post_is_answered_and_no_stream_is_left_open(mcp, method):
    """A stateless server has nothing to send unasked, so it opens no stream.

    The SDK answered a GET with an event stream that never sent anything and
    stayed open until the client left, holding one of the connections uvicorn
    allows. The transport lets a server answer 405 instead.
    """

    async def act(client, http):
        return await http.request(method, http_api.MCP_PATH, headers=ASKS)

    answer = mcp(http_api.build_app(), act, connect=False)

    _refusal(answer, 405, "method_not_allowed")
    assert answer.headers["allow"] == "POST"


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
            await http.post(
                http_api.MCP_PATH,
                json=LIST_TOOLS,
                headers={**ASKS, "Authorization": f"Bearer {TOKEN}x"},
            ),
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


def test_without_the_token_the_client_is_told_why(mcp):
    from mcp.shared.exceptions import MCPError

    async def act(client, http):
        return await client.list_tools()

    with pytest.raises(BaseException) as raised:
        mcp(http_api.build_app(token=TOKEN), act)

    refused = _innermost(raised.value)
    assert isinstance(refused, MCPError), repr(refused)
    assert refused.error.data == {"code": "unauthorized"}


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

    async def act(client, http):
        return await http.post(
            http_api.MCP_PATH, json=FETCH_CALL, headers={**ASKS, "Origin": origin}
        )

    answer = mcp(http_api.build_app(), act, connect=False)

    _refusal(answer, 403, "cross_origin")
    assert fetch.calls == []


def test_a_preflight_from_another_origin_is_refused(mcp):
    """What a browser asks before it sends JSON across origins: no."""

    async def act(client, http):
        return await http.options(
            http_api.MCP_PATH,
            headers={
                "Origin": "http://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    answer = mcp(http_api.build_app(), act, connect=False)

    _refusal(answer, 403, "cross_origin")
    assert not any(name.startswith("access-control-") for name in answer.headers)


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
        assert len(answer.json()["result"]["tools"]) == 12


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
    """DNS rebinding: a page's own name, pointed at 127.0.0.1, is its Host,
    and its Origin agrees with it; the Host is what gives it away."""

    async def act(client, http):
        return await http.post(
            http_api.MCP_PATH,
            json=LIST_TOOLS,
            headers={
                **ASKS,
                "Host": "rebound.example:8000",
                "Origin": "http://rebound.example:8000",
            },
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

    assert len(tools) == 12


def test_a_body_over_the_bound_is_refused_before_it_is_read(mcp, monkeypatch):
    """From its declared length, and as it arrives when sent in chunks."""
    fetch = fake_fetch(monkeypatch)
    big = b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "x": "' + b"x" * 200

    async def chunks():
        for start in range(0, len(big), 50):
            yield big[start : start + 50]

    async def act(client, http):
        headers = {**ASKS, "Content-Type": "application/json"}
        return [
            await http.post(http_api.MCP_PATH, content=big, headers=headers),
            await http.post(http_api.MCP_PATH, content=chunks(), headers=headers),
        ]

    declared, streamed = mcp(http_api.build_app(max_body=100), act, connect=False)

    assert "content-length" not in streamed.request.headers
    for answer in (declared, streamed):
        _refusal(answer, 413, "too_large")
    assert fetch.calls == []


def test_a_body_that_takes_longer_than_the_budget_is_answered_504(mcp):
    """A client that sends a byte now and then holds a connection no longer
    than any other request."""
    import anyio

    async def trickle():
        yield b'{"jsonrpc": "2.0",'
        await anyio.sleep(5)
        yield b' "id": 1, "method": "tools/list"}'

    async def act(client, http):
        began = time.monotonic()
        answer = await http.post(
            http_api.MCP_PATH,
            content=trickle(),
            headers={**ASKS, "Content-Type": "application/json"},
        )
        return answer, time.monotonic() - began

    answer, took = mcp(http_api.build_app(timeout=0.3), act, connect=False)

    body = _refusal(answer, 504, "timed_out")
    assert "0.3 seconds" in body["error"]["message"]
    assert took < 3


def test_a_call_past_its_budget_is_a_tool_error_that_says_so(mcp, monkeypatch):
    """``timed_out`` is no code of a tool's output schema, so it is MCP's own
    failed call, and the SDK's client does not check it against the schema."""
    _, _, released = _slow_fetches(monkeypatch)

    async def act(client, http):
        began = time.monotonic()
        try:
            result = await client.call_tool("fetch_page", {"url": "https://a.example/"})
        finally:
            released.set()
        return result, time.monotonic() - began

    result, took = mcp(http_api.build_app(timeout=0.5), act)

    assert result.is_error is True
    assert result.content[0].text.startswith("timed_out: ")
    assert "0.5 seconds" in result.content[0].text
    assert took < 3


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
    """The same workers as the REST routes, so the same separation: four
    slow sites hold every worker that fetches, and a page handed in is read
    at once."""
    import anyio

    fetch, started, released = _slow_fetches(monkeypatch)

    async def act(client, http):
        async with anyio.create_task_group() as calls:
            for n in range(http_api.MAX_CALLS):
                calls.start_soon(
                    client.call_tool, "fetch_page", {"url": f"https://s{n}.example/"}
                )
            try:
                for _ in range(http_api.MAX_CALLS):
                    assert await anyio.to_thread.run_sync(started.acquire, True, 10)
                began = time.monotonic()
                answer = await client.call_tool(
                    "extract_declared", {"html_or_url": PAGE}
                )
                took = time.monotonic() - began
            finally:
                released.set()
        return answer, took

    answer, took = mcp(http_api.build_app(timeout=5), act)

    assert answer.is_error is False
    assert answer.structured_content["summary"]["title"]["value"] == "Pad"
    assert took < 0.5
    assert len(fetch.calls) == http_api.MAX_CALLS
