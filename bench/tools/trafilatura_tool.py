"""trafilatura's metadata extraction over the test split.

Run in an environment holding exactly ``bench/requirements/trafilatura.txt``.
Only the ``extract_metadata`` call is timed, here and by ``bench/timing.py``,
which times the same function.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

import trafilatura

# What the interpreter brings whatever is installed, and so not the tool's.
_INTERPRETER = {"pip", "setuptools", "wheel"}


def extract(html: bytes, url: str | None) -> Any:
    """The call a scoreboard scores and ``bench/timing.py`` times."""
    try:
        return trafilatura.extract_metadata(html, default_url=url)
    except Exception:  # noqa: BLE001 -- a tool that raises answered nothing
        return None


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    results, seconds = [], 0.0
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        started = time.perf_counter()
        found = extract(html, page["url"])
        seconds += time.perf_counter() - started
        results.append(
            {
                "id": page["id"],
                "title": getattr(found, "title", None),
                "author": getattr(found, "author", None),
                "date": getattr(found, "date", None),
            }
        )
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "trafilatura",
                "version": trafilatura.__version__,
                "seconds": seconds,
                "packages": len(
                    {d.metadata["Name"] for d in importlib.metadata.distributions()}
                    - _INTERPRETER
                ),
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    print(
        f"trafilatura {trafilatura.__version__}: {len(results)} pages, {seconds:.2f} s"
    )


if __name__ == "__main__":
    main(*sys.argv[1:3])
