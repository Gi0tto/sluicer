"""The spec's first two constraints, made executable.

"No LLM anywhere in the path. Not even as a fallback." and "No paid API."
Those are what this project is, and until now nothing checked them. This
test reads every source file and names any import that would break them.

A module arrives in two ways here, and both are read. An ``import`` statement
is the obvious one. The other is a name handed over as a string: every optional
extra in this package is loaded through ``sluicer.extras.import_extra`` by
name, so an AST walk that only looked at ``import`` statements would never see
the one door a new dependency is most likely to come through.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# A module is forbidden when it is one of these, or inside one of them.
FORBIDDEN = (
    # Network clients: fetching is scrapling's, behind the fetch extra, and a
    # second client would be a second way out that nothing announces.
    "requests",
    "httpx",
    "urllib.request",
    "socket",
    "aiohttp",
    # Model clients, hosted and local.
    "openai",
    "anthropic",
    "google.generativeai",
    "google.genai",
    "vertexai",
    "google.cloud.aiplatform",
    "litellm",
    "mistralai",
    "cohere",
    "ollama",
    "groq",
    "together",
    "replicate",
    "huggingface_hub",
    "transformers",
    "sentence_transformers",
    "vllm",
)

# A module is forbidden when its name starts with one of these at all: each is
# a family published as many top-level packages, ``langchain_openai`` and
# ``langchain_community`` as much as ``langchain`` itself.
FORBIDDEN_FAMILIES = ("langchain", "llama_index", "llama_cpp")

# The one exception, and why: telling whether an address is on the public
# internet means asking what a name resolves to. ``getaddrinfo`` opens no
# connection and sends nothing of the page's; the fetch itself stays scrapling's.
ALLOWED = {("sluicer/fetch/address.py", "socket")}

# The calls that import a module named by a string.
_IMPORTERS = frozenset({"import_extra", "import_module", "__import__"})


def _imported_modules(source: str, filename: str = "<source>") -> set[str]:
    """Every module name one source file imports, by statement or by name."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
            # "from urllib import request" imports urllib.request.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and _calls_an_importer(node):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)
    return found


def _calls_an_importer(call: ast.Call) -> bool:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id in _IMPORTERS
    return isinstance(function, ast.Attribute) and function.attr in _IMPORTERS


def _is_forbidden(module: str) -> bool:
    return any(
        module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN
    ) or module.startswith(FORBIDDEN_FAMILIES)


def test_no_source_file_imports_a_network_or_model_client():
    sources = sorted(SRC.rglob("*.py"))
    assert sources, f"no source files found under {SRC}"

    offenders = sorted(
        f"{path.relative_to(SRC)} imports {module}"
        for path in sources
        for module in _imported_modules(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if _is_forbidden(module)
        and (path.relative_to(SRC).as_posix(), module) not in ALLOWED
    )

    assert offenders == []


def test_the_scanner_sees_every_way_a_model_client_can_arrive():
    """The guard above passes on a clean tree; this is what makes it able to fail.

    Each line below brings a model client in a different way, and each has to be
    named. A scanner blind to one of them would keep the test above green while
    the constraint it enforces was broken.
    """
    source = "\n".join(
        (
            "import openai",
            "from anthropic import Anthropic",
            "from google import genai",
            "from langchain_openai import ChatOpenAI",
            "import llama_index.core",
            "from sluicer.extras import import_extra",
            "import_extra('litellm', 'model', doing='x', error=ImportError)",
            "import importlib",
            "importlib.import_module('mistralai')",
            "__import__('cohere')",
        )
    )

    caught = {module for module in _imported_modules(source) if _is_forbidden(module)}

    assert caught >= {
        "openai",
        "anthropic",
        "google.genai",
        "langchain_openai",
        "llama_index.core",
        "litellm",
        "mistralai",
        "cohere",
    }


def test_the_extras_this_package_really_loads_are_seen_and_allowed():
    """The string scan finds the real extras, and none of them is forbidden."""
    loaded = {
        module
        for path in SRC.rglob("*.py")
        for module in _imported_modules(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
    }

    assert {
        "trafilatura",
        "mf2py",
        "protego",
        "mcp.server.mcpserver",
        "scrapling.fetchers",
    } <= loaded
