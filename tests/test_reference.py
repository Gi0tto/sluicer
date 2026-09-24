"""The reference pages say what the code does, because the code wrote them.

``scripts/reference.py`` writes ``docs/reference/`` from the commands' own
help, the MCP server's own tool list and the public docstrings. The Python page
is held to it exactly. The other two are held to what cannot differ between
the versions of click and the MCP SDK the suite runs against -- every command
and every tool is there, with its own description -- since the floors job
formats help and schemas with older releases than the ones the pages were
generated with.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "docs" / "reference"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "reference", ROOT / "scripts" / "reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_python_reference_is_the_code_s_own():
    written = (PAGES / "python.md").read_text(encoding="utf-8")
    assert written == _generator().python_page(), "run: uv run scripts/reference.py"


def test_every_command_is_in_the_command_line_reference():
    from sluicer.cli import main

    written = (PAGES / "cli.md").read_text(encoding="utf-8")
    for name, command in main.commands.items():
        assert f"## `sluicer {name}`" in written, name
        first = (command.help or "").strip().splitlines()[0]
        assert first in written, (name, first)


def test_every_tool_is_in_the_mcp_reference(monkeypatch):
    pytest.importorskip("mcp.server.mcpserver")
    from sluicer.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    written = (PAGES / "mcp.md").read_text(encoding="utf-8")
    assert f"The {len(tools)} tools" in written
    for tool in tools:
        assert f"## `{tool.name}`" in written, tool.name
        first = inspect.cleandoc(tool.description or "").splitlines()[0]
        assert first in written, (tool.name, first)
