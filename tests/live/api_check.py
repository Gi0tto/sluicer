"""The HTTP door against a real server, over a real socket.

Run by CI with the api extra installed; not part of the unit suite, which opens
no sockets and reaches the app through starlette's TestClient. This starts
``sluicer serve`` in its own process, three times, and asks it over HTTP what a
client would: every tool the server lists, and one error of every kind a
request can provoke.

    python tests/live/api_check.py

Three servers, because what they are asked needs three configurations:

- **A**, as a user would run it: a token, and private addresses refused. Every
  tool on HTML handed in, every refusal of the door itself, and a local URL
  refused as private.
- **B**, told to fetch private addresses (``SLUICER_ALLOW_PRIVATE=1``) with a
  three-second budget, so a local server can stand in for the web: a real
  fetch, a robots.txt that says no, a page too heavy, an address nothing
  listens on, and a page that answers too late.
- **C**, with trafilatura made unimportable in its process, for the one error
  that needs an extra missing.

Every answer is checked against the schema the server itself publishes: a
tool's answer against its output schema, every error against ``ErrorAnswer``.
``internal_error`` is not provoked: only a bug in the server can.

A tool the server lists that this check does not call is a failure: a tool
added to the MCP server is served at once, and it should be asked something
here over a real socket before anyone relies on it.
"""

from __future__ import annotations

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

import jsonschema

TOKEN = "live-check-token"
DRIFT = Path(__file__).resolve().parent.parent / "fixtures" / "drift"
PAGE = (
    "<html><head><title>Brake pad set</title>"
    '<script type="application/ld+json">'
    '{"@type":"Product","name":"Brake pad set","sku":"BP-2210"}</script>'
    "</head><body><article><h1>Brake pad set</h1>"
    + "<p>Four pads for the front axle, with the wear sensor fitted.</p>" * 20
    + "</article></body></html>"
)
HUGE = 17 * 1024 * 1024
released = threading.Event()


class Web(http.server.BaseHTTPRequestHandler):
    """The web, as far as server B can tell."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:
        pass

    def _send(self, status: int, body: bytes, kind: str = "text/html") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/robots.txt":
            self._send(200, b"User-agent: *\nDisallow: /private/\n", "text/plain")
        elif self.path == "/page":
            self._send(200, PAGE.encode())
        elif self.path == "/huge":
            self._send(200, b"<p>" + b"x" * HUGE)
        elif self.path == "/slow":
            released.wait(60)
            self._send(200, PAGE.encode())
        else:
            self._send(404, b"")


class _Quiet(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # a client that stops reading at the bound resets the connection


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


WITHOUT_TRAFILATURA = """
import sys

class Gone:
    def find_spec(self, name, path=None, target=None):
        if name == "trafilatura" or name.startswith("trafilatura."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)

sys.meta_path.insert(0, Gone())
"""


def start(
    port: int, env: dict[str, str], options: str = "", prelude: str = ""
) -> subprocess.Popen[str]:
    """``sluicer serve`` on ``port``, in a process of its own, once it answers.

    Its environment is this one's without the two variables the server reads,
    and then ``env``: nothing leaks from the shell that ran the check.
    """
    code = prelude + "\nfrom sluicer.cli import main\nmain()\n"
    inherited = {
        name: value
        for name, value in os.environ.items()
        if name not in ("SLUICER_ALLOW_PRIVATE", "SLUICER_API_TOKEN")
    }
    process = subprocess.Popen(
        [sys.executable, "-c", code, "serve", "--port", str(port), *options.split()],
        env={**inherited, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            said = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"the server on {port} exited: {said}")
        with contextlib.suppress(OSError):
            status, _, _ = request(port, "GET", "/health")
            if status == 200:
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
    raw: bytes | None = None,
) -> tuple[int, dict[str, str], Any]:
    """One request over a real connection; the status, headers and parsed body."""
    sent = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        sent.setdefault("Content-Type", "application/json")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in sent.items():
            connection.putheader(name, value)
        if data is not None and "Content-Length" not in sent:
            connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
        response = connection.getresponse()
        text = response.read()
        return response.status, dict(response.getheaders()), json.loads(text)
    finally:
        connection.close()


class Check:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.codes: set[str] = set()
        self.called: set[str] = set()
        self.output: dict[str, Any] = {}
        self.error_answer: dict[str, Any] = {}

    def expect(
        self,
        what: str,
        got: tuple[int, dict[str, str], Any],
        status: int,
        code: str | None = None,
        tool: str | None = None,
    ) -> Any:
        """Hold one answer to its status, its code and its published schema."""
        answer = got[2]
        if got[0] != status:
            self.failures.append(f"{what}: status {got[0]}, not {status}: {answer}")
        error = answer.get("error") if isinstance(answer, dict) else None
        if code is not None:
            if not error or error.get("code") != code:
                self.failures.append(f"{what}: code is not {code}: {answer}")
            self.codes.add(code)
        if tool is not None:
            self.called.add(tool)
            if error is None or error.get("code") in TOOL_CODES:
                self._fits(what, answer, self.output[tool])
        if error is not None:
            self._fits(what, answer, self.error_answer)
        return answer

    def _fits(self, what: str, answer: Any, schema: dict[str, Any]) -> None:
        try:
            jsonschema.Draft202012Validator(schema).validate(answer)
        except jsonschema.ValidationError as unfit:
            self.failures.append(f"{what}: does not fit its schema: {unfit.message}")


TOOL_CODES: set[str] = set()


def main() -> int:
    from sluicer import http_api

    TOOL_CODES.update(http_api.TOOL_STATUS)
    web = _Quiet(("127.0.0.1", 0), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{web.server_address[1]}"
    ports = {name: free_port() for name in "ABC"}
    check = Check()
    auth = {"Authorization": f"Bearer {TOKEN}"}
    servers = []
    try:
        servers.append(start(ports["A"], {http_api.TOKEN_ENV: TOKEN}))
        servers.append(start(ports["B"], {"SLUICER_ALLOW_PRIVATE": "1"}, "--timeout 3"))
        servers.append(start(ports["C"], {}, prelude=WITHOUT_TRAFILATURA))
        a, b, c = ports["A"], ports["B"], ports["C"]

        listed = check.expect(
            "A lists its tools", request(a, "GET", "/v1/tools", headers=auth), 200
        )
        tools = {tool["name"]: tool for tool in listed["tools"]}
        check.output = {name: tool["outputSchema"] for name, tool in tools.items()}
        document = check.expect(
            "A describes itself", request(a, "GET", "/openapi.json", headers=auth), 200
        )
        check.error_answer = {**document["components"]["schemas"]["ErrorAnswer"]}
        _references_resolve(check, document)
        for name in tools:
            if f"/v1/tools/{name}" not in document["paths"]:
                check.failures.append(f"openapi.json has no path for {name}")
        _same_tools_as_the_mcp_server(check, tools)

        def call(port: int, tool: str, arguments: Any, **options: Any) -> Any:
            return request(port, "POST", f"/v1/tools/{tool}", arguments, **options)

        # Every tool, on HTML handed in, through A.
        page = check.expect(
            "extract_declared",
            call(a, "extract_declared", {"html_or_url": PAGE}, headers=auth),
            200,
            tool="extract_declared",
        )
        if page.get("summary", {}).get("title", {}).get("value") != "Brake pad set":
            check.failures.append(f"extract_declared lost the title: {page}")
        words = check.expect(
            "page_markdown",
            call(a, "page_markdown", {"html_or_url": PAGE}, headers=auth),
            200,
            tool="page_markdown",
        )
        if "front axle" not in words.get("markdown", ""):
            check.failures.append(f"page_markdown lost the text: {words}")
        audited = check.expect(
            "audit_page",
            call(a, "audit_page", {"html_or_url": PAGE}, headers=auth),
            200,
            tool="audit_page",
        )
        if audited.get("ok") is not True or not audited.get("records"):
            check.failures.append(f"audit_page audited nothing: {audited}")
        v1 = (DRIFT / "shop_v1.html").read_text()
        learnt = check.expect(
            "compile_extractor",
            call(
                a,
                "compile_extractor",
                {"pages": [v1, (DRIFT / "shop_v1_page2.html").read_text()]},
                headers=auth,
            ),
            200,
            tool="compile_extractor",
        )
        extractor = learnt.get("extractor")
        kept = check.expect(
            "run_extractor, kept",
            call(
                a,
                "run_extractor",
                {"extractor": extractor, "html_or_url": v1},
                headers=auth,
            ),
            200,
            tool="run_extractor",
        )
        if kept.get("ok") is not True or len(kept.get("rows", [])) != 6:
            check.failures.append(
                f"run_extractor did not read the page it learnt: {kept}"
            )
        drifted = check.expect(
            "run_extractor, drifted",
            call(
                a,
                "run_extractor",
                {
                    "extractor": extractor,
                    "html_or_url": (DRIFT / "shop_prices_gone.html").read_text(),
                },
                headers=auth,
            ),
            200,
            tool="run_extractor",
        )
        if drifted.get("ok") is not False or not drifted.get("failed"):
            check.failures.append(
                f"a drifted page was not reported as drifted: {drifted}"
            )
        healed = check.expect(
            "heal_extractor",
            call(
                a,
                "heal_extractor",
                {
                    "extractor": extractor,
                    "pages": [(DRIFT / "shop_redesigned.html").read_text()],
                },
                headers=auth,
            ),
            200,
            tool="heal_extractor",
        )
        if healed.get("ok") is not True:
            check.failures.append(f"heal_extractor did not heal a redesign: {healed}")
        lost = check.expect(
            "heal_extractor, lost",
            call(
                a,
                "heal_extractor",
                {
                    "extractor": extractor,
                    "pages": [(DRIFT / "shop_prices_gone.html").read_text()],
                },
                headers=auth,
            ),
            200,
            tool="heal_extractor",
        )
        if lost.get("ok") is not False or lost.get("lost") is not True:
            check.failures.append(f"a heal that lost data was not reported: {lost}")

        # A real fetch, through B, which may reach the local stand-in for the web.
        fetched = check.expect(
            "fetch_page",
            call(b, "fetch_page", {"url": f"{site}/page"}),
            200,
            tool="fetch_page",
        )
        if fetched.get("fetch", {}).get(
            "rung"
        ) != "http" or "BP-2210" not in fetched.get("html", ""):
            check.failures.append(
                f"fetch_page did not bring the page: {str(fetched)[:200]}"
            )
        declared = check.expect(
            "extract_declared, fetched",
            call(b, "extract_declared", {"html_or_url": f"{site}/page"}),
            200,
            tool="extract_declared",
        )
        if declared.get("url") != f"{site}/page" or "fetch" not in declared:
            check.failures.append(
                f"extract_declared did not say what it fetched: {str(declared)[:200]}"
            )

        # One error of every kind the tools answer.
        check.expect(
            "literal HTML to fetch_page",
            call(a, "fetch_page", {"url": PAGE}, headers=auth),
            400,
            "bad_input",
            tool="fetch_page",
        )
        check.expect(
            "a private address",
            call(a, "fetch_page", {"url": f"{site}/page"}, headers=auth),
            403,
            "refused_address",
            tool="fetch_page",
        )
        check.expect(
            "robots.txt says no",
            call(b, "fetch_page", {"url": f"{site}/private/secret"}),
            403,
            "refused_by_robots",
            tool="fetch_page",
        )
        check.expect(
            "a page too heavy",
            call(b, "fetch_page", {"url": f"{site}/huge"}),
            413,
            "too_large",
            tool="fetch_page",
        )
        check.expect(
            "nothing listens there",
            call(b, "fetch_page", {"url": f"http://127.0.0.1:{free_port()}/"}),
            502,
            "fetch_failed",
            tool="fetch_page",
        )
        check.expect(
            "trafilatura is missing",
            call(c, "page_markdown", {"html_or_url": PAGE}),
            501,
            "missing_extra",
            tool="page_markdown",
        )

        # One of every kind the door answers itself.
        started = time.monotonic()
        check.expect(
            "a page that answers too late",
            call(b, "fetch_page", {"url": f"{site}/slow"}),
            504,
            "timed_out",
            tool="fetch_page",
        )
        if time.monotonic() - started > 10:
            check.failures.append(
                "the time budget was not kept: the answer took over 10 s"
            )
        check.expect("no token", request(a, "GET", "/v1/tools"), 401, "unauthorized")
        check.expect(
            "an unknown tool",
            call(a, "no_such_tool", {}, headers=auth),
            404,
            "not_found",
        )
        check.expect(
            "a GET on a tool",
            request(a, "GET", "/v1/tools/fetch_page", headers=auth),
            405,
            "method_not_allowed",
        )
        check.expect(
            "text/plain",
            request(
                a,
                "POST",
                "/v1/tools/fetch_page",
                raw=b'{"url": "x"}',
                headers={**auth, "Content-Type": "text/plain"},
            ),
            415,
            "unsupported_media_type",
        )
        check.expect(
            "a rebound name",
            request(a, "GET", "/health", headers={"Host": "attacker.example"}),
            421,
            "misdirected",
        )
        check.expect(
            "a body not JSON",
            request(
                a,
                "POST",
                "/v1/tools/fetch_page",
                raw=b"{",
                headers={**auth, "Content-Type": "application/json"},
            ),
            400,
            "bad_input",
        )
        check.expect(
            "a body over the bound",
            request(
                a,
                "POST",
                "/v1/tools/fetch_page",
                raw=b"",
                headers={
                    **auth,
                    "Content-Type": "application/json",
                    "Content-Length": str(http_api.MAX_BODY_BYTES + 1),
                },
            ),
            413,
            "too_large",
        )
        check.expect(
            "the health check needs no token", request(a, "GET", "/health"), 200
        )

        unasked = set(tools) - check.called
        for name in sorted(unasked):
            check.failures.append(
                f"{name} is served but this check never calls it: add a call"
            )
        unprovoked = set(http_api.STATUS) - check.codes - {"internal_error"}
        for code in sorted(unprovoked):
            check.failures.append(f"no request here provokes {code}")
    finally:
        released.set()
        for process in servers:
            stop(process)
        web.shutdown()

    for failure in check.failures:
        print("FAIL:", failure)
    if not check.failures:
        print(
            f"api: {len(check.called)} tools called over a real socket, "
            f"{len(check.codes)} error codes provoked, every answer fits its schema"
        )
    return 1 if check.failures else 0


def _references_resolve(check: Check, document: dict[str, Any]) -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str):
                target: Any = document
                for part in reference.removeprefix("#/").split("/"):
                    target = target.get(part) if isinstance(target, dict) else None
                if target is None:
                    check.failures.append(
                        f"openapi.json: {reference} resolves to nothing"
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)


def _same_tools_as_the_mcp_server(check: Check, tools: dict[str, Any]) -> None:
    import asyncio

    from sluicer.mcp_server import build_server

    over_mcp = {tool.name for tool in asyncio.run(build_server().list_tools())}
    if set(tools) != over_mcp:
        check.failures.append(
            f"HTTP lists {sorted(tools)}, the MCP server {sorted(over_mcp)}"
        )


if __name__ == "__main__":
    sys.exit(main())
