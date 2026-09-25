"""MCP over streamable HTTP against a real ``sluicer serve``, over a real socket.

Run by CI's with-extras job, with every extra installed; not part of the unit
suite, which opens no sockets and reaches ``/mcp`` through httpx2's ASGI
transport. This starts ``sluicer serve`` in its own process, twice, and asks
it what n8n's or Dify's MCP client would, through the ``mcp`` package's own
client over its own streamable HTTP transport:

    python tests/live/mcp_http_check.py

- **A**, as a user would run it: a token, private addresses refused. It lists
  its tools, in both of the SDK's modes, the initialize handshake and the
  2026-07-28 revision, and they are held to what the MCP server lists over
  stdio, schemas and all. ``extract_declared`` on a fixture page handed in
  answers what the server answers without a socket; on the same page's local
  URL it answers ``refused_address``. Then one request for each refusal of the
  door: no token, a wrong one, another origin, a rebound name, a body over the
  bound, a GET.
- **B**, told to fetch private addresses (``SLUICER_ALLOW_PRIVATE=1``), so a
  local server can stand in for the web: ``extract_declared`` fetches the
  fixture page over plain HTTP and reads it.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.client
import http.server
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

TOKEN = "live-mcp-check-token"
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "product_jsonld.html"
PAGE = FIXTURE.read_text(encoding="utf-8")
ASKS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


class Web(http.server.BaseHTTPRequestHandler):
    """The web, as far as server B can tell: the fixture page, and no robots.txt."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        body, status = (PAGE.encode(), 200) if self.path == "/product" else (b"", 404)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)


class _Quiet(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    """``sluicer serve`` on ``port``, in a process of its own, once it answers.

    Its environment is this one's without the two variables the server reads,
    and then ``env``: nothing leaks from the shell that ran the check.
    """
    inherited = {
        name: value
        for name, value in os.environ.items()
        if name not in ("SLUICER_ALLOW_PRIVATE", "SLUICER_API_TOKEN")
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "sluicer", "serve", "--port", str(port)],
        env={**inherited, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            said = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"the server on {port} exited: {said}")
        with contextlib.suppress(OSError):
            if request(port, "GET", "/health")[0] == 200:
                return process
        time.sleep(0.2)
    process.kill()
    raise RuntimeError(f"the server on {port} never answered")


def stop(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(30)
    except subprocess.TimeoutExpired:
        process.kill()


def request(
    port: int,
    method: str,
    path: str,
    body: Any = None,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    """One request over a real connection, as no MCP client would send it."""
    sent = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        sent.setdefault("Content-Type", "application/json")
        sent.setdefault("Content-Length", str(len(data)))
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in sent.items():
            connection.putheader(name, value)
        connection.endheaders(data)
        response = connection.getresponse()
        text = response.read()
        return response.status, dict(response.getheaders()), json.loads(text)
    finally:
        connection.close()


async def over_mcp(port: int, act: Any, *, mode: str, token: str | None) -> Any:
    """``act(client)`` with the SDK's client over streamable HTTP to ``port``."""
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx2.AsyncClient(headers=headers, timeout=60) as http:
        transport = streamable_http_client(
            f"http://127.0.0.1:{port}/mcp", http_client=http
        )
        async with Client(transport, mode=mode) as client:
            return await act(client)


def _dumped(tools: Any) -> list[dict[str, Any]]:
    return [
        tool.model_dump(by_alias=True, exclude_none=True, mode="json") for tool in tools
    ]


def main() -> int:
    from sluicer.mcp_server import build_server

    failures: list[str] = []
    stdio = build_server()
    listed_over_stdio = _dumped(asyncio.run(stdio.list_tools()))
    direct = asyncio.run(stdio.call_tool("extract_declared", {"html_or_url": PAGE}))
    web = _Quiet(("127.0.0.1", 0), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{web.server_address[1]}"
    a, b = free_port(), free_port()
    servers = []
    try:
        servers.append(start(a, {"SLUICER_API_TOKEN": TOKEN}))
        servers.append(
            start(b, {"SLUICER_API_TOKEN": TOKEN, "SLUICER_ALLOW_PRIVATE": "1"})
        )

        async def listed(client: Any) -> Any:
            return _dumped((await client.list_tools()).tools)

        async def handed_in(client: Any) -> Any:
            return await client.call_tool("extract_declared", {"html_or_url": PAGE})

        async def local_url(client: Any) -> Any:
            return await client.call_tool(
                "extract_declared", {"html_or_url": f"{site}/product"}
            )

        for mode in ("legacy", "auto"):
            tools = asyncio.run(over_mcp(a, listed, mode=mode, token=TOKEN))
            if tools != listed_over_stdio:
                failures.append(f"{mode}: the tools listed over HTTP are not stdio's")
            answer = asyncio.run(over_mcp(a, handed_in, mode=mode, token=TOKEN))
            if (
                answer.is_error
                or answer.structured_content != direct.structured_content
            ):
                failures.append(
                    f"{mode}: extract_declared over HTTP is not what the server "
                    f"answers: {str(answer)[:300]}"
                )
            refused = asyncio.run(over_mcp(a, local_url, mode=mode, token=TOKEN))
            code = (refused.structured_content or {}).get("error", {}).get("code")
            if code != "refused_address":
                failures.append(f"{mode}: a private address was not refused: {refused}")
            fetched = asyncio.run(over_mcp(b, local_url, mode=mode, token=TOKEN))
            content = fetched.structured_content or {}
            if (
                fetched.is_error
                or content.get("summary", {}).get("title", {}).get("value")
                != "Brake pad set"
                or content.get("fetch", {}).get("rung") != "http"
            ):
                failures.append(
                    f"{mode}: extract_declared did not fetch the local page: "
                    f"{str(fetched)[:300]}"
                )
        print(
            f"mcp over http: {len(listed_over_stdio)} tools listed as over stdio, "
            "extract_declared answered in both modes, a private address refused"
        )

        auth = {"Authorization": f"Bearer {TOKEN}", **ASKS}
        refusals = [
            ("no token", "POST", LIST_TOOLS, ASKS, 401, "unauthorized"),
            (
                "a wrong token",
                "POST",
                LIST_TOOLS,
                {**ASKS, "Authorization": "Bearer not-it"},
                401,
                "unauthorized",
            ),
            (
                "another origin",
                "POST",
                LIST_TOOLS,
                {**auth, "Origin": "http://attacker.example"},
                403,
                "cross_origin",
            ),
            (
                "a rebound name",
                "POST",
                LIST_TOOLS,
                {**auth, "Host": "rebound.example", "Origin": "http://rebound.example"},
                421,
                "misdirected",
            ),
            (
                "a body over the bound",
                "POST",
                None,
                {
                    **auth,
                    "Content-Type": "application/json",
                    "Content-Length": str(16 * 1024 * 1024 + 1),
                },
                413,
                "too_large",
            ),
            ("a GET", "GET", None, auth, 405, "method_not_allowed"),
        ]
        for what, method, body, headers, status, code in refusals:
            got, _, answer = request(a, method, "/mcp", body, headers=headers)
            data = (answer.get("error") or {}).get("data") if answer else None
            if got != status or data != {"code": code}:
                failures.append(
                    f"{what}: {got} {str(answer)[:300]}, not {status} {code}"
                )
        print(f"mcp over http: {len(refusals)} refusals of the door, each its status")
    finally:
        for process in servers:
            stop(process)
        web.shutdown()

    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
