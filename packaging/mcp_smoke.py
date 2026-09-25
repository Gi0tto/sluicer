"""Start an MCP server over stdio and check it lists the tools Sluicer has.

    python3 packaging/mcp_smoke.py -- docker run -i --rm ghcr.io/gi0tto/sluicer:0.8.0
    python3 packaging/mcp_smoke.py -- uv run --directory bundle server.py

The release workflow runs the image and the MCPB bundle this way before either
is published: a build that installs but whose server cannot answer
``tools/list`` is caught here rather than by the first person who adds it.
The tools expected are the ones ``packaging/mcpb/manifest.json`` lists, which a
test holds to the tools the server registers. Standard library only, since it
runs on a bare runner, beside the thing it tests and not inside it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "mcpb" / "manifest.json"
# The first start installs the server's dependencies (uv) or pulls nothing but
# is still a cold container: generous, since a slow runner is not a failure.
TIMEOUT = 300


def expected_tools() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return sorted(tool["name"] for tool in manifest["tools"])


def _read_answer(stream, wanted: int, lines: list[str]) -> dict:
    """The JSON-RPC answer with id ``wanted``, skipping notifications."""
    while True:
        line = stream.readline()
        if not line:
            raise SystemExit(f"the server closed stdout before answering {wanted}")
        lines.append(line)
        message = json.loads(line)
        if message.get("id") == wanted:
            if "error" in message:
                raise SystemExit(f"the server answered {wanted} with {message}")
            return message["result"]


def check(command: list[str]) -> list[str]:
    """The tools ``command``'s server lists, after checking they are expected."""
    server = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert server.stdin is not None and server.stdout is not None
    timer = threading.Timer(TIMEOUT, server.kill)
    timer.start()
    seen: list[str] = []

    def send(message: dict) -> None:
        assert server.stdin is not None
        server.stdin.write(json.dumps(message) + "\n")
        server.stdin.flush()

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "sluicer-release-smoke", "version": "1"},
                },
            }
        )
        info = _read_answer(server.stdout, 1, seen)["serverInfo"]
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = _read_answer(server.stdout, 2, seen)["tools"]
    finally:
        timer.cancel()
        server.stdin.close()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
    names = sorted(tool["name"] for tool in listed)
    unannotated = [
        tool["name"]
        for tool in listed
        if not (tool.get("annotations") or {}).get("readOnlyHint")
    ]
    if names != expected_tools():
        raise SystemExit(f"listed {names}, expected {expected_tools()}")
    if unannotated:
        raise SystemExit(f"these tools do not say they only read: {unannotated}")
    print(f"{info['name']} {info['version']} lists its {len(names)} tools over stdio")
    return names


def main(argv: list[str]) -> None:
    if "--" not in argv:
        raise SystemExit(__doc__)
    check(argv[argv.index("--") + 1 :])


if __name__ == "__main__":
    main(sys.argv[1:])
