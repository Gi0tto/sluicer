"""The loop every tool of ``docs/scoreboard-tools.md`` runs, in its own environment.

Imported by the ``compare_*.py`` harnesses, each in an environment holding one
tool, so it needs nothing but Python. A harness defines ``extract(page, url)``,
the call the scoreboard scores and ``bench/timing.py`` times, which returns
the tool's ``title``, ``author``, ``date`` and ``text`` (None for a question it
does not answer), and never raises: a tool that raises answered nothing, and
what it raised is recorded (``answered``). It may define ``prepare(html)``,
run before the clock starts, and ``after(html, url, row)``, run after it,
untimed, to add to the row.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

QUESTIONS = ("title", "author", "date", "text")
# What the interpreter brings whatever is installed, and so not the tool's.
_INTERPRETER = {"pip", "setuptools", "wheel"}


def answered(call: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """``call``, made to answer nothing, with what it raised, where it raises."""

    def guarded(*args: Any) -> dict[str, Any]:
        try:
            return call(*args)
        except Exception as error:  # noqa: BLE001 -- a raise is an answer of nothing
            return {
                **dict.fromkeys(QUESTIONS),
                "raised": f"{type(error).__name__}: {str(error)[:200]}",
            }

    return guarded


def text_or_none(value: Any) -> str | None:
    """A tool's answer as text, None where it gave none."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value if item)
    text = str(value).strip()
    return text or None


def run(harness: Any, distribution: str, pages_path: str, out_path: str) -> None:
    """Every page of ``pages_path`` through ``harness``, into ``out_path``,
    gzipped JSON: the tool, its version, the seconds of its timed calls, and a
    row per page."""
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    prepare = getattr(harness, "prepare", lambda html: html)
    after = getattr(harness, "after", None)
    results, seconds = [], 0.0
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        prepared = prepare(html)
        started = time.perf_counter()
        found = harness.extract(prepared, page["url"])
        seconds += time.perf_counter() - started
        row = {"id": page["id"], **found}
        if after is not None and "raised" not in found:
            after(html, page["url"], row)
        results.append(row)
    version = importlib.metadata.version(distribution)
    document = {
        "tool": harness.NAME,
        "version": version,
        "seconds": seconds,
        "packages": len(
            {d.metadata["Name"] for d in importlib.metadata.distributions()}
            - _INTERPRETER
        ),
        "results": results,
    }
    Path(out_path).write_bytes(
        gzip.compress(json.dumps(document).encode("utf-8"), mtime=0)
    )
    raised = sum(1 for row in results if "raised" in row)
    print(
        f"{harness.NAME} {version}: {len(results)} pages, {seconds:.2f} s, "
        f"{raised} raised"
    )
