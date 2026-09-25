"""The main text of trafilatura's evaluation pages, as Sluicer and trafilatura give it.

Run by ``bench/evaldata.py`` in an environment holding Sluicer, editable, and
the trafilatura the other scoreboards pin. Each page's output is scored as
trafilatura's own evaluation scores it (``snippets.py``): a "with" snippet
found is a true positive, a "without" snippet found a false positive, spaces
normalised on both sides.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import sys
from pathlib import Path

import trafilatura

import sluicer.markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snippets import counted


def _plain(markdown: str) -> str:
    """``markdown`` with its syntax taken out, roughly: link and image targets,
    emphasis, heading and list marks, table bars. Rough on purpose -- it also
    takes the underscores out of "Liebe_r" -- since it only asks how much of
    what the text holds the markdown holds too."""
    markdown = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    markdown = re.sub(r"(\*\*|__|\*|_)(\S.*?\S|\S)\1", r"\2", markdown)
    markdown = re.sub(r"^\s*(?:#+|[-*+])\s+", "", markdown, flags=re.MULTILINE)
    return markdown.replace("|", " ").replace("\\", "")


def main(pages_path: str, out_path: str) -> None:
    logging.disable(logging.CRITICAL)
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    outputs = {
        "sluicer.markdown": lambda html, url: sluicer.markdown.to_markdown(
            html, url=url
        ),
        "sluicer.markdown, its syntax taken out": lambda html, url: _plain(
            sluicer.markdown.to_markdown(html, url=url)
        ),
        "trafilatura text": lambda html, url: trafilatura.extract(html, url=url),
    }
    totals = {name: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for name in outputs}
    # Each page's own counts too: several snippets sit on one page, so an
    # interval is bootstrapped over pages, not over snippets (bench/PREREG.md).
    per_page: dict[str, dict[str, list[int]]] = {}
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        for name, produce in outputs.items():
            row = counted(page, produce(html, page["url"]))
            per_page.setdefault(page["id"], {})[name] = row
            for key, value in zip(("tp", "fp", "fn", "tn"), row, strict=True):
                totals[name][key] += value
    Path(out_path).write_text(
        json.dumps(
            {"pages": len(pages), "outputs": totals, "per_page": per_page}, indent=1
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"main text of {len(pages)} pages, {len(outputs)} ways")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
