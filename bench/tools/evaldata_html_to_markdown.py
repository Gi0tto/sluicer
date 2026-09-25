"""The main text of trafilatura's evaluation pages, as html-to-markdown gives it.

Run by ``bench/evaldata.py`` in an environment holding html-to-markdown alone,
pinned by ``bench/requirements/html-to-markdown.txt``: xberg-io's converter,
MIT, never a dependency of Sluicer. Two outputs, its defaults otherwise, as
``bench/PREREG.md`` fixed them: ``convert(html).content``, its markdown, and
the same with ``output_format="plain"``, its plain text. It converts the whole
page and chooses no main text. It takes text, so each page is decoded first
(``snippets.as_text``), and each output is scored as ``evaldata_body.py``
scores Sluicer's and trafilatura's.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import sys
from pathlib import Path

from html_to_markdown import ConversionOptions, convert

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snippets import as_text, counted

OUTPUTS = {
    "html-to-markdown": None,
    "html-to-markdown, plain text": ConversionOptions(output_format="plain"),
}


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    totals = {name: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for name in OUTPUTS}
    per_page: dict[str, dict[str, list[int]]] = {}
    for page in pages:
        html = as_text(gzip.decompress((root / page["path"]).read_bytes()))
        for name, options in OUTPUTS.items():
            row = counted(page, convert(html, options).content)
            per_page.setdefault(page["id"], {})[name] = row
            for key, value in zip(("tp", "fp", "fn", "tn"), row, strict=True):
                totals[name][key] += value
    version = importlib.metadata.version("html-to-markdown")
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "html-to-markdown",
                "version": version,
                "pages": len(pages),
                "outputs": totals,
                "per_page": per_page,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"html-to-markdown {version}: main text of {len(pages)} pages")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
