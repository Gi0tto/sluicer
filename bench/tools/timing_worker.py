"""One tool's timed pass over a table's pages, for ``bench/timing.py``.

    python timing_worker.py TOOL PAGES [HARNESS]

Run in the tool's own environment, a fresh process each time, as
``bench/PREREG.md`` fixes it under "How a second is measured": it reads every
page into memory, runs the tool's extraction call on every page once untimed,
a warm-up that is thrown away, then times one pass over every page, the call
alone. The call is the tool's harness's own ``extract``, the function its
scoreboard scores. The last line it prints is JSON: the tool, its version,
the interpreter, the seconds, the process's peak resident size, and what the
environment holds.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import importlib.util
import json
import platform
import resource
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Each tool's harness in this directory, and the distribution whose version
# the scoreboard names.
HARNESSES = {
    "sluicer": ("sluicer_tool", "sluicer"),
    "trafilatura": ("trafilatura_tool", "trafilatura"),
    "newspaper4k": ("newspaper_tool", "newspaper4k"),
    "extruct": ("extruct_tool", "extruct"),
    "sluicer.compat.extruct": ("compat_tool", "sluicer"),
}
# What the interpreter brings whatever is installed, and so not the tool's,
# as the harnesses count packages.
_INTERPRETER = {"pip", "setuptools", "wheel"}


def _harness(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pages(pages_path: Path) -> list[tuple[bytes, str | None]]:
    """Every page's bytes and address; a path is the page list's own
    (relative to it, as the scoreboards write them) or absolute."""
    pages = json.loads(pages_path.read_text(encoding="utf-8"))
    found = []
    for page in pages:
        path = Path(page["path"])
        if not path.is_absolute():
            path = pages_path.parent / path
        data = path.read_bytes()
        found.append(
            (gzip.decompress(data) if path.suffix == ".gz" else data, page["url"])
        )
    return found


def _editable_bytes(dist: importlib.metadata.Distribution) -> int:
    """What an editable install's packages hold, as a wheel would: its
    RECORD lists only a ``.pth``, so its top-level packages' files are
    counted from where they are, bytecode caches left out."""
    total = 0
    tops = {
        top
        for top, names in importlib.metadata.packages_distributions().items()
        if dist.metadata["Name"] in names
    }
    for top in tops:
        spec = importlib.util.find_spec(top)
        for location in (spec.submodule_search_locations or []) if spec else []:
            for path in Path(location).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    total += path.stat().st_size
    return total


def environment() -> tuple[int, int]:
    """The packages the environment holds, the interpreter's own left out,
    and their installed size in bytes: every file each one's RECORD lists,
    bytecode caches left out, or for an editable install its packages."""
    seen: dict[str, importlib.metadata.Distribution] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name and name not in _INTERPRETER:
            seen.setdefault(name, dist)
    total = 0
    for dist in seen.values():
        direct = dist.read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            total += _editable_bytes(dist)
            continue
        for file in dist.files or []:
            if "__pycache__" in file.parts:
                continue
            located = Path(str(dist.locate_file(file)))
            if located.is_file():
                total += located.stat().st_size
    return len(seen), total


def _peak_rss() -> int:
    """The process's peak resident size in bytes: ``getrusage`` counts it in
    bytes on macOS and in kilobytes on Linux."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def main(tool: str, pages_path: str, harness_name: str | None = None) -> None:
    """``harness_name``, when given, is the harness of a table that asks the
    tool more than its scoreboard's harness does (``docs/scoreboard-tools.md``
    asks for the text too); it names the distribution it scores."""
    if harness_name is None:
        name, distribution = HARNESSES[tool]
        harness = _harness(name)
    else:
        harness = _harness(harness_name)
        distribution = harness.DISTRIBUTION
    prepare = getattr(harness, "prepare", lambda html: html)
    pages = [(prepare(html), url) for html, url in _pages(Path(pages_path))]
    for page, url in pages:
        harness.extract(page, url)
    seconds = 0.0
    for page, url in pages:
        started = time.perf_counter()
        harness.extract(page, url)
        seconds += time.perf_counter() - started
    packages, size = environment()
    print(
        json.dumps(
            {
                "tool": tool,
                "version": importlib.metadata.version(distribution),
                "runtime": f"Python {platform.python_version()}",
                "seconds": seconds,
                "peak_rss": _peak_rss(),
                "packages": packages,
                "install_bytes": size,
            }
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:4])
