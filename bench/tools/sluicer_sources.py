"""Which vocabularies each page declares, as Sluicer's readers see them.

Run by ``bench/realweb.py`` in the same environment as ``sluicer_tool.py``:
this checkout, installed editable, and nothing else. Not timed, not scored:
it counts what the pages carry, so the scoreboard can say what served pages
hold that WCXB's copies do not.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import sluicer


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    found = {}
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        found[page["id"]] = sluicer.extract(html, url=page["url"]).sources
    Path(out_path).write_text(json.dumps(found), encoding="utf-8")
    print(f"sluicer sources: {len(found)} pages")


if __name__ == "__main__":
    main(*sys.argv[1:3])
