"""Every text the repository reads or writes names its encoding.

Python's default is the locale's: UTF-8 on Linux and macOS, the ANSI code page
on Windows, cp1252 across most of Europe. The first run on Windows found eleven
tests reading UTF-8 fixtures as cp1252, and extractor files a test wrote in
cp1252 that the command line, rightly, read as UTF-8. This test reads every
Python file of the repository and refuses a read, a write or a text subprocess
that leaves the encoding to the machine it runs on.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKED = ("src", "tests", "scripts", "examples", "bench")
# Modules whose ``open`` is not a text file's: a gzip stream opens binary
# unless told otherwise, and the others open no file at all.
NOT_FILES = frozenset({"gzip", "tarfile", "zipfile", "webbrowser", "urllib"})


def _mode(call: ast.Call, position: int) -> ast.expr | None:
    mode = call.args[position] if len(call.args) > position else None
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    return mode


def _in_text(mode: ast.expr | None) -> bool:
    if mode is None:
        return True
    return isinstance(mode, ast.Constant) and "b" not in str(mode.value)


def _leaves_encoding_to_the_machine(call: ast.Call) -> bool:
    if any(keyword.arg == "encoding" for keyword in call.keywords):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "read_text":
        return not call.args
    if isinstance(func, ast.Attribute) and func.attr == "write_text":
        return len(call.args) < 2
    if isinstance(func, ast.Name) and func.id == "open":
        return _in_text(_mode(call, 1))
    if isinstance(func, ast.Attribute) and func.attr == "open":
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id in NOT_FILES:
            return False
        return _in_text(_mode(call, 0))
    return any(
        keyword.arg in {"text", "universal_newlines"}
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _python_files() -> list[Path]:
    return sorted(
        path
        for folder in CHECKED
        for path in (ROOT / folder).rglob("*.py")
        if "cache" not in path.relative_to(ROOT).parts
    )


def test_every_text_read_write_and_subprocess_names_its_encoding():
    files = _python_files()
    assert len(files) > 100, "the files to check were not found"
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
        for path in files
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and _leaves_encoding_to_the_machine(node)
    ]
    assert offenders == []


def test_the_check_sees_what_it_is_for():
    """A check that cannot fail protects nothing: each shape it refuses, once."""
    refused = [
        'Path("a").read_text()',
        'Path("a").write_text("x")',
        'open("a")',
        'open("a", "w")',
        'Path("a").open()',
        'Path("a").open("a")',
        'subprocess.run(["x"], text=True)',
    ]
    allowed = [
        'Path("a").read_text(encoding="utf-8")',
        'Path("a").write_text("x", encoding="utf-8")',
        'open("a", "rb")',
        'Path("a").open("r+b")',
        'gzip.open("a")',
        'subprocess.run(["x"], text=True, encoding="utf-8")',
        'subprocess.run(["x"], capture_output=True)',
    ]

    def judged(code: str) -> bool:
        call = ast.parse(code).body[0].value  # type: ignore[attr-defined]
        return _leaves_encoding_to_the_machine(call)

    assert [code for code in refused if not judged(code)] == []
    assert [code for code in allowed if judged(code)] == []
