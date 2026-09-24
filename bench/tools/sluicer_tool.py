"""Sluicer's summary over the test split, from the checkout under test.

Run by ``bench/run.py`` in an environment holding this checkout, installed
editable, and nothing else. Only the ``extract`` call is timed.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import sys
import time
from pathlib import Path

import sluicer

FIELDS = {"title": "title", "author": "author", "date": "published"}

# What the interpreter brings whatever is installed, and so not the tool's.
_INTERPRETER = {"pip", "setuptools", "wheel"}


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    results, seconds = [], 0.0
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        started = time.perf_counter()
        summary = sluicer.extract(html, url=page["url"]).summary
        seconds += time.perf_counter() - started
        row = {"id": page["id"]}
        for field, question in FIELDS.items():
            answer = summary.get(question)
            row[field] = answer.value if answer else None
            row[f"{field}_from"] = f"{answer.source} {answer.key}" if answer else None
        results.append(row)
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "sluicer",
                "version": sluicer.__version__,
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
    print(f"sluicer {sluicer.__version__}: {len(results)} pages, {seconds:.2f} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
