"""Sluicer's summary over the test split, from the checkout under test.

Run by ``bench/run.py`` in an environment holding this checkout, installed
editable, and nothing else. Only the ``extract`` call is timed, here and by
``bench/timing.py``, which times the same function. ``--visible``'s guesses are
read after it, untimed, and recorded beside the summary's answers, never in
their place (``bench/PREREG.md``).
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

import sluicer

FIELDS = {"title": "title", "author": "author", "date": "published"}

# What the interpreter brings whatever is installed, and so not the tool's.
_INTERPRETER = {"pip", "setuptools", "wheel"}


def extract(html: bytes, url: str | None) -> Any:
    """The call a scoreboard scores and ``bench/timing.py`` times."""
    return sluicer.extract(html, url=url, visible=False).summary


def guesses(html: bytes, url: str | None, summary: Any) -> dict[str, str | None]:
    """What ``--visible`` reads off the page for each field, or None.

    The call with ``visible=True`` must give the summary ``extract`` gave: a
    page where it does not stops the run, since the summary would no longer
    hold only what the page declares.
    """
    result = sluicer.extract(html, url=url, visible=True)
    for question in FIELDS.values():
        if result.summary.get(question) != summary.get(question):
            raise SystemExit(
                f"the summary's {question} changed when --visible was asked: "
                f"{summary.get(question)!r} became {result.summary.get(question)!r}"
            )
    return {
        field: (guess.value if (guess := result.visible.get(question)) else None)
        for field, question in FIELDS.items()
    }


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    results, seconds = [], 0.0
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        started = time.perf_counter()
        summary = extract(html, page["url"])
        seconds += time.perf_counter() - started
        row = {"id": page["id"]}
        for field, question in FIELDS.items():
            answer = summary.get(question)
            row[field] = answer.value if answer else None
            row[f"{field}_from"] = f"{answer.source} {answer.key}" if answer else None
        row["visible"] = guesses(html, page["url"], summary)
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
