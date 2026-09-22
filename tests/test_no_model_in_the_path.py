"""The spec's first two constraints, made executable.

"No LLM anywhere in the path. Not even as a fallback." and "No paid API."
Those are what this project is, and until now nothing checked them. This
test reads every source file and names any import that would break them.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN = (
    "requests",
    "httpx",
    "urllib.request",
    "socket",
    "aiohttp",
    "openai",
    "anthropic",
    "google.generativeai",
)


def _imported_modules(path: Path) -> set[str]:
    """Every module name one source file imports."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
            # "from urllib import request" imports urllib.request.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _is_forbidden(module: str) -> bool:
    return any(module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN)


def test_no_source_file_imports_a_network_or_model_client():
    sources = sorted(SRC.rglob("*.py"))
    assert sources, f"no source files found under {SRC}"

    offenders = sorted(
        f"{path.relative_to(SRC)} imports {module}"
        for path in sources
        for module in _imported_modules(path)
        if _is_forbidden(module)
    )

    assert offenders == []
