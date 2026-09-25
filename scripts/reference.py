# /// script
# requires-python = ">=3.10"
# dependencies = ["sluicer[mcp]"]
#
# [tool.uv.sources]
# sluicer = { path = "..", editable = true }
# ///
"""Write the documentation's reference pages from the code itself.

    uv run scripts/reference.py

``docs/reference/cli.md`` is every command's own ``--help``;
``docs/reference/mcp.md`` is every tool as the MCP server lists it to an
agent, its parameters from the server's own input schema;
``docs/reference/python.md`` is the public functions and types, their
signatures and their docstrings. Nothing is written by hand, so the reference
cannot say what the code does not do; ``tests/test_reference.py`` fails when a
page falls behind.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "docs" / "reference"

# What the Python reference documents, in the order a reader meets it.
PYTHON: list[tuple[str, str, list[str]]] = [
    (
        "Reading a page",
        "sluicer",
        [
            "extract",
            "aextract",
            "Extraction",
            "SummaryField",
            "Record",
            "Field",
            "induce",
        ],
    ),
    ("The main content as markdown", "sluicer", ["to_markdown"]),
    (
        "What a value means",
        "sluicer.normalise",
        ["iso_date", "amount", "currency", "gtin"],
    ),
    ("Fetching", "sluicer.fetch", ["fetch", "afetch", "Fetched"]),
    (
        "Extractors",
        "sluicer.extractor",
        ["compile_extractor", "run_extractor", "heal", "Extractor", "Run"],
    ),
    ("Many pages", "sluicer.crawl", ["map_site", "crawl", "extract_many"]),
    ("Feeds", "sluicer.feeds", ["read_feed"]),
    ("Web archives", "sluicer.warc", ["read_warc", "extract_warc"]),
    ("What changed", "sluicer.diff", ["compare"]),
    ("Audit", "sluicer.audit", ["audit"]),
]

_SECTION = re.compile(r"^(Args|Returns|Raises|Yields|Attributes):\s*$")
_LABELS = {
    "Args": "Arguments",
    "Returns": "Returns",
    "Raises": "Raises",
    "Yields": "Yields",
    "Attributes": "Attributes",
}
_QUALIFIED = re.compile(r"\b(?:collections\.abc|typing|sluicer(?:\.\w+)*|pathlib)\.")


def _escaped(text: str) -> str:
    """``text`` with ``<`` and ``>`` escaped outside its code, so a tag the text
    names -- ``<script>`` -- is shown, not opened. Fenced blocks and code
    spans, a span that runs across lines included, are left as written."""
    parts = re.split(r"(```[\s\S]*?```|``[\s\S]*?``|`[^`\n]*`)", text)
    return "".join(
        part if part.startswith("`") else part.replace("<", "&lt;").replace(">", "&gt;")
        for part in parts
    )


def _markdown(doc: str | None) -> str:
    """A Google-style docstring as markdown: its sections as labelled lists."""
    if not doc:
        return ""
    out: list[str] = []
    section: str | None = None
    for line in inspect.cleandoc(doc).splitlines():
        heading = _SECTION.match(line)
        if heading:
            section = heading.group(1)
            out += ["", f"**{_LABELS[section]}**", ""]
            continue
        if section is None:
            out.append(line)
            continue
        if not line.strip():
            out.append("")
            continue
        if not line.startswith(" "):
            section = None
            out.append(line)
            continue
        item = re.match(r"^ {4}([^\s:][^:]*?):\s+(.*)$", line)
        if section in ("Args", "Raises", "Attributes") and item:
            name, text = item.groups()
            label = name if " " in name else f"`{name}`"
            out.append(f"- {label}: {text}")
        elif (out and out[-1].startswith("- ")) or section in ("Returns", "Yields"):
            if out and out[-1] and not out[-1].startswith("**"):
                out[-1] += " " + line.strip()
            else:
                out.append(line.strip())
        else:
            out.append(line.strip())
    text = _escaped(_code_blocks("\n".join(out))).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _code_blocks(text: str) -> str:
    """Indented example lines, as the docstrings write commands, fenced."""
    lines, fenced, inside = text.splitlines(), [], False
    for index, line in enumerate(lines):
        indented = line.startswith("    ") and not line.lstrip().startswith("- ")
        opens = indented and (index == 0 or not lines[index - 1].strip())
        if opens and not inside:
            fenced.append("```text")
            inside = True
        if inside and not indented and line.strip():
            fenced.append("```")
            inside = False
        fenced.append(line[4:] if inside else line)
    if inside:
        fenced.append("```")
    return "\n".join(fenced)


def _type(annotation: Any) -> str:
    text = (
        annotation
        if isinstance(annotation, str)
        else inspect.formatannotation(annotation)
    )
    return _QUALIFIED.sub("", text)


def _default(value: Any) -> str:
    """A default as the code spells it: a function by its name, not by the
    address its ``repr`` gives, which changes on every run."""
    if callable(value) and hasattr(value, "__qualname__"):
        module = getattr(value, "__module__", "") or ""
        if module and not module.startswith("sluicer"):
            return f"{module}.{value.__qualname__}"
        return value.__qualname__
    return repr(value)


def _signature(name: str, obj: Callable[..., Any]) -> str:
    signature = inspect.signature(obj)
    parameters = []
    for parameter in signature.parameters.values():
        text = parameter.name
        if parameter.kind is parameter.VAR_KEYWORD:
            text = "**" + text
        elif parameter.kind is parameter.VAR_POSITIONAL:
            text = "*" + text
        if parameter.annotation is not parameter.empty:
            text += f": {_type(parameter.annotation)}"
        if parameter.default is not parameter.empty:
            text += f" = {_default(parameter.default)}"
        parameters.append(text)
    returned = ""
    if signature.return_annotation is not signature.empty:
        returned = f" -> {_type(signature.return_annotation)}"
    one_line = f"{name}({', '.join(parameters)}){returned}"
    if len(one_line) <= 80:
        return one_line
    inner = "".join(f"    {text},\n" for text in parameters)
    return f"{name}(\n{inner}){returned}"


def _python_entry(module: str, name: str) -> Iterator[str]:
    obj = getattr(importlib.import_module(module), name)
    qualified = f"{module}.{name}"
    yield f"### `{qualified}`"
    yield ""
    if inspect.isclass(obj):
        if dataclasses.is_dataclass(obj):
            yield "```python"
            yield f"class {name}:"
            for field in dataclasses.fields(obj):
                yield f"    {field.name}: {_type(field.type)}"
            yield "```"
        else:
            yield "```python"
            yield f"class {name}"
            yield "```"
    else:
        yield "```python"
        yield _signature(name, obj)
        yield "```"
    yield ""
    body = _markdown(obj.__doc__)
    if body:
        yield body
        yield ""


def python_page() -> str:
    lines = [
        "# Python",
        "",
        "The functions and types a program calls, with their signatures and their",
        "own docstrings. Generated from the code by `scripts/reference.py`.",
        "",
    ]
    for title, module, names in PYTHON:
        lines += [f"## {title}", ""]
        for name in names:
            lines += list(_python_entry(module, name))
    return "\n".join(lines).rstrip() + "\n"


def cli_page() -> str:
    from click.testing import CliRunner

    from sluicer.cli import main

    runner = CliRunner()

    def help_of(*args: str) -> str:
        result = runner.invoke(
            main, [*args, "--help"], prog_name="sluicer", terminal_width=88
        )
        assert result.exit_code == 0, result.output
        return result.output.rstrip()

    lines = [
        "# Command line",
        "",
        "Every command's own `--help`, as `sluicer` prints it. Generated from the",
        "code by `scripts/reference.py`.",
        "",
        "```text",
        "$ sluicer --help",
        help_of(),
        "```",
        "",
    ]
    for name in sorted(main.commands):
        lines += [f"## `sluicer {name}`", "", "```text", help_of(name), "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def _parameter_rows(schema: dict[str, Any]) -> list[str]:
    required = set(schema.get("required", []))
    rows = ["| parameter | type | default |", "|---|---|---|"]
    for name, spec in schema.get("properties", {}).items():
        kind = spec.get("type")
        if kind is None and "anyOf" in spec:
            kind = " or ".join(
                str(option.get("type", "object")) for option in spec["anyOf"]
            )
        default = "required" if name in required else f"`{spec.get('default')!r}`"
        rows.append(f"| `{name}` | {kind or 'object'} | {default} |")
    return rows


def _described(description: str, names: set[str]) -> str:
    """A tool's description as markdown: each ``name: text`` line that names
    one of its parameters, and the lines that continue it, as a list item."""
    out: list[str] = []
    in_item = False
    for line in inspect.cleandoc(description).splitlines():
        item = re.match(r"^(\w+): (.*)$", line)
        if item and item.group(1) in names:
            out.append(f"- `{item.group(1)}`: {item.group(2)}")
            in_item = True
        elif in_item and line.strip():
            out[-1] += " " + line.strip()
        else:
            in_item = False
            out.append(line)
    return _escaped("\n".join(out))


def mcp_page() -> str:
    from sluicer.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    lines = [
        "# MCP tools",
        "",
        f"The {len(tools)} tools the server lists to an agent, each with its",
        "description and parameters exactly as the agent receives them. Generated",
        "from the running server by `scripts/reference.py`; how to add the server to",
        "a client is in [In your agent](../agents.md).",
        "",
    ]
    for tool in tools:
        hints = tool.annotations
        says = []
        if hints is not None:
            if hints.read_only_hint:
                says.append("only reads")
            if hints.destructive_hint is False:
                says.append("changes nothing")
            if hints.idempotent_hint:
                says.append("gives the same answer when called again")
            if hints.open_world_hint:
                says.append("may reach the web")
        lines += [f"## `{tool.name}`", "", f"**{tool.title}**", ""]
        names = set(tool.input_schema.get("properties", {}))
        lines += [_described(tool.description or "", names), ""]
        lines += [*_parameter_rows(tool.input_schema), ""]
        if says:
            listed = (
                ", ".join(says[:-1]) + " and " + says[-1] if len(says) > 1 else says[0]
            )
            lines += [f"Its annotations say it {listed}.", ""]
    return "\n".join(lines).rstrip() + "\n"


def pages() -> dict[str, str]:
    return {"cli.md": cli_page(), "mcp.md": mcp_page(), "python.md": python_page()}


def main() -> None:
    PAGES.mkdir(parents=True, exist_ok=True)
    for name, text in pages().items():
        (PAGES / name).write_text(text, encoding="utf-8")
        print(f"wrote docs/reference/{name}")


if __name__ == "__main__":
    main()
