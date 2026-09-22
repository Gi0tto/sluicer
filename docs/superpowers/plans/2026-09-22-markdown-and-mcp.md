# Markdown and MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Sluicer the two things the field survey says an agent-facing extractor cannot ship without: clean markdown for a page, and an MCP server so Claude Code, Codex and anything else that speaks the protocol can call it directly.

**Architecture:** Both are thin surfaces over what already exists. Markdown delegates main-content extraction to `trafilatura`, which does that job full time, behind an optional extra and a lazy import, exactly as the fetch layer treats `scrapling`. The MCP server exposes three tools that call `extract`, `to_markdown` and the ladder, and adds no logic of its own.

**Tech Stack:** Python 3.10+, `lxml`, `click`; `trafilatura` under the `markdown` extra; `mcp` under the `mcp` extra. No new base dependency.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`. The survey that motivates the MCP server is `docs/field-survey.md`.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL code.
- No LLM call anywhere in the path, not even as a fallback.
- No paid API, and no feature that requires somebody's key to work.
- Deterministic: the same input always produces the same output.
- English only: code, comments, docstrings, test names, commit messages, docs.
- **Unit tests never touch the network.** Optional dependencies are faked through `sys.modules`, the way `tests/test_scrapling_rungs.py` already does.
- `import sluicer` must keep working with every optional extra absent.
- Every public function is typed, and annotations must be honest.
- A missing optional extra raises a dedicated exception carrying an install hint, never a bare `ImportError`, and the command line turns it into one line rather than a traceback. `FetchExtraMissing` in `src/sluicer/fetch/scrapling_rungs.py` is the pattern; follow it, including that only a genuinely absent package counts.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/markdown.py` | `MarkdownExtraMissing`, `to_markdown()` |
| `src/sluicer/cli.py` | extended: a `markdown` command |
| `src/sluicer/mcp_server.py` | the MCP server and its three tools |
| `pyproject.toml` | two new optional-dependency groups, one new console script |

---

### Task 1: Markdown from a page

**Files:**
- Create: `src/sluicer/markdown.py`, `tests/test_markdown.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `MarkdownExtraMissing(ImportError)` and `to_markdown(html: str | bytes, url: str | None = None) -> str`, re-exported from the package root.

**The contract:** returns the page's main content as markdown, with the boilerplate gone. An empty string means the page had no main content to give, which is a fact about the page, not an error. A page that cannot be parsed at all is already handled by `load()` and yields an empty string here too.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_markdown.py
import sys
import types

import pytest


def fake_trafilatura(monkeypatch, output="# Brake pad set\n\nReal content."):
    """Stand in for trafilatura so no test needs it installed."""
    seen = {}

    def extract(html, **kwargs):
        seen["called_with"] = (html, kwargs)
        return output

    module = types.ModuleType("trafilatura")
    module.extract = extract
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    return seen


def test_a_page_becomes_markdown(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    result = to_markdown("<html><body><h1>Brake pad set</h1></body></html>")

    assert result == "# Brake pad set\n\nReal content."
    assert seen["called_with"][1]["output_format"] == "markdown"


def test_a_page_with_no_main_content_gives_an_empty_string(monkeypatch):
    fake_trafilatura(monkeypatch, output=None)
    from sluicer.markdown import to_markdown

    assert to_markdown("<html><body></body></html>") == ""


def test_bytes_are_accepted(monkeypatch):
    seen = fake_trafilatura(monkeypatch)
    from sluicer.markdown import to_markdown

    to_markdown("<html><body>hi</body></html>".encode())

    assert isinstance(seen["called_with"][0], str)


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    import importlib

    class _NoTrafilatura:
        def find_module(self, name, path=None):
            return None

        def find_spec(self, name, path=None, target=None):
            if name == "trafilatura" or name.startswith("trafilatura."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    monkeypatch.delitem(sys.modules, "trafilatura", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoTrafilatura(), *sys.meta_path])

    import sluicer.markdown as markdown_module

    importlib.reload(markdown_module)
    with pytest.raises(markdown_module.MarkdownExtraMissing) as raised:
        markdown_module.to_markdown("<html><body>hi</body></html>")

    assert "sluicer[markdown]" in str(raised.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.markdown'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/markdown.py
"""A page's main content, as markdown, with the furniture removed.

Pulling the article out of a page and leaving the navigation behind is its own
problem, and `trafilatura` works on it full time. Sluicer does not reimplement
it; it hands the document over and passes the result back. The dependency is
optional because the base install reads structured data, and a reader who never
asks for markdown should not carry the tree that produces it.
"""

from __future__ import annotations

class MarkdownExtraMissing(ImportError):
    """The optional markdown extra is not installed.

    This means the package is absent, not that something inside a working
    installation failed to import. A broken install is a bug and must surface
    as one.
    """


_MISSING = (
    "Turning a page into markdown needs trafilatura, which is not installed. "
    "Install it with: uv pip install 'sluicer[markdown]'"
)


def _trafilatura():
    try:
        import trafilatura
    except ModuleNotFoundError as missing:
        if missing.name == "trafilatura":
            raise MarkdownExtraMissing(_MISSING) from missing
        raise
    return trafilatura


def to_markdown(html: str | bytes, url: str | None = None) -> str:
    """Return the page's main content as markdown, or an empty string.

    An empty string means the page had no main content to give. That is a fact
    about the page rather than a failure, and the caller decides what it means.
    """
    produced = _trafilatura().extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        url=url,
    )
    return produced or ""
```

In `pyproject.toml`, add to the existing `[project.optional-dependencies]`:

```toml
markdown = ["trafilatura>=2.0"]
```

And re-export from `src/sluicer/__init__.py`, adding `MarkdownExtraMissing` and `to_markdown` to the imports and to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/markdown.py src/sluicer/__init__.py tests/test_markdown.py pyproject.toml
git commit -m "feat: a page's main content as markdown"
```

---

### Task 2: The markdown command

**Files:**
- Modify: `src/sluicer/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `sluicer markdown <path-or-url>`, printing markdown to stdout. It takes a URL exactly as `extract` does, through the same `fetch_url` seam, and reports a missing extra or an operational failure the same way.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_markdown_prints_the_main_content(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr("sluicer.cli.to_markdown", lambda html, url=None: "# Title\n\nBody.")
    page = tmp_path / "page.html"
    page.write_text("<html><body><h1>Title</h1></body></html>")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 0
    assert result.stdout.strip() == "# Title\n\nBody."


def test_markdown_without_the_extra_explains_itself(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.markdown import MarkdownExtraMissing

    def refuse(html, url=None):
        raise MarkdownExtraMissing(
            "Turning a page into markdown needs trafilatura, which is not installed. "
            "Install it with: uv pip install 'sluicer[markdown]'"
        )

    monkeypatch.setattr("sluicer.cli.to_markdown", refuse)
    page = tmp_path / "page.html"
    page.write_text("<html><body>hi</body></html>")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 1
    assert "sluicer[markdown]" in result.stderr
    assert isinstance(result.exception, SystemExit)


def test_markdown_of_a_page_with_nothing_to_say_exits_one(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    monkeypatch.setattr("sluicer.cli.to_markdown", lambda html, url=None: "")
    page = tmp_path / "page.html"
    page.write_text("<html><body></body></html>")

    result = CliRunner().invoke(main, ["markdown", str(page)])

    assert result.exit_code == 1
    assert "no main content" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL, no such command `markdown`

- [ ] **Step 3: Write minimal implementation**

Add a `markdown` command to `src/sluicer/cli.py`. Import `to_markdown` and `MarkdownExtraMissing` at module level so tests can replace them. Reuse the existing source-reading helper so a path, a URL, a missing file and a directory all behave exactly as they do for `extract`: the same messages, the same exit codes, the same seam. Print the markdown to stdout on success. When there is no main content, say so on stderr and exit 1. When the extra is missing, print the exception's message on stderr and exit 1.

If the existing `extract` command does its source reading inline, lift that into a small private helper first and have both commands use it, rather than copying it. Say in your report that you did so.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/cli.py tests/test_cli.py
git commit -m "feat: sluicer markdown"
```

---

### Task 3: The MCP server

**Files:**
- Create: `src/sluicer/mcp_server.py`, `tests/test_mcp_server.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `McpExtraMissing(ImportError)`, `build_server()` returning a configured server, and `main()` running it over stdio. A console script `sluicer-mcp` points at `main`.
- Three tools: `extract_declared(html_or_url)`, `page_markdown(html_or_url)`, `fetch_page(url)`.

**Why these three:** an agent wants the structured data, the readable text, or the raw page with the record of what it cost. Everything else Sluicer can do is reachable by composing those.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_server.py
import sys
import types

import pytest


def fake_mcp(monkeypatch):
    """Stand in for the mcp SDK, recording every tool the server registers."""
    registered = {}

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self, *args, **kwargs):
            def decorate(function):
                registered[function.__name__] = function
                return function

            return decorate

        def run(self):
            registered["__ran__"] = True

    server_module = types.ModuleType("mcp.server.fastmcp")
    server_module.FastMCP = FastMCP
    package = types.ModuleType("mcp")
    sub = types.ModuleType("mcp.server")
    monkeypatch.setitem(sys.modules, "mcp", package)
    monkeypatch.setitem(sys.modules, "mcp.server", sub)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", server_module)
    return registered


def test_the_server_registers_the_three_tools(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()

    assert set(registered) == {"extract_declared", "page_markdown", "fetch_page"}


def test_extract_declared_reads_html_given_directly(monkeypatch):
    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    result = registered["extract_declared"](
        '<html><head><script type="application/ld+json">'
        '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>'
    )

    assert result["sources"] == ["jsonld"]
    assert result["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    import importlib

    class _NoMcp:
        def find_spec(self, name, path=None, target=None):
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    for name in [n for n in list(sys.modules) if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_NoMcp(), *sys.meta_path])

    import sluicer.mcp_server as server_module

    importlib.reload(server_module)
    with pytest.raises(server_module.McpExtraMissing) as raised:
        server_module.build_server()

    assert "sluicer[mcp]" in str(raised.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.mcp_server'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/mcp_server.py
"""Sluicer as a tool an agent can call.

Nine percent of the live projects in this field now ship an MCP server, which
makes it table stakes rather than an edge: a tool an agent cannot install is a
tool an agent will not use. The server adds no logic. It exposes what the
library already does and gets out of the way.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sluicer.api import extract
from sluicer.markdown import to_markdown

_MISSING = (
    "Running the MCP server needs the mcp package, which is not installed. "
    "Install it with: uv pip install 'sluicer[mcp]'"
)


class McpExtraMissing(ImportError):
    """The optional mcp extra is not installed, as opposed to broken."""


def _fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as missing:
        if missing.name == "mcp" or (missing.name or "").startswith("mcp."):
            raise McpExtraMissing(_MISSING) from missing
        raise
    return FastMCP


def _html_of(html_or_url: str) -> tuple[str, dict[str, Any] | None]:
    """Return the page's HTML, fetching it when given a URL."""
    if html_or_url.startswith(("http://", "https://")):
        from sluicer.fetch import fetch

        fetched = fetch(html_or_url)
        return fetched.html, {
            "rung": fetched.rung,
            "status": fetched.status,
            "climbs": [asdict(climb) for climb in fetched.climbs],
        }
    return html_or_url, None


def build_server():
    """Build the server with its three tools registered."""
    server = _fastmcp()("sluicer")

    @server.tool()
    def extract_declared(html_or_url: str) -> dict:
        """Read the structured data a page declares, with per-field provenance."""
        html, fetched = _html_of(html_or_url)
        result = asdict(extract(html))
        if fetched is not None:
            result["fetch"] = fetched
        return result

    @server.tool()
    def page_markdown(html_or_url: str) -> str:
        """Return the page's main content as markdown, with boilerplate removed."""
        html, _ = _html_of(html_or_url)
        return to_markdown(html)

    @server.tool()
    def fetch_page(url: str) -> dict:
        """Fetch a page and report which rung it took and every climb."""
        html, fetched = _html_of(url)
        return {"html": html, "fetch": fetched}

    return server


def main() -> None:
    """Run the server over stdio."""
    build_server().run()
```

In `pyproject.toml`, add to `[project.optional-dependencies]`:

```toml
mcp = ["mcp>=1.2"]
```

and to `[project.scripts]`:

```toml
sluicer-mcp = "sluicer.mcp_server:main"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/mcp_server.py tests/test_mcp_server.py pyproject.toml
git commit -m "feat: an MCP server so an agent can call Sluicer"
```

---

## Out of scope

Crawling a site, sitemap and robots handling, SEO auditing, PDF and OCR, and the scoreboard. Each is its own plan.
