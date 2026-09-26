"""Write what the native Python package answers on the pages the JS tests read.

Run from the checkout, in its environment, with the markdown extra:

    uv run --extra markdown python js/scripts/expected.py

Every case below becomes one file under ``js/test/expected/``: the page, how
it is handed over, the options, and the native answer as ``dataclasses.asdict``
gives it -- the same JSON ``sluicer extract`` prints. The node tests hand the
same page to the npm package, which runs the same code in Pyodide, and require
the same answer. CI runs this script again and fails when a committed file
differs, so the files are always this commit's native answers.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import sluicer
from sluicer.extractor import Extractor, compile_extractor, run_extractor

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "js" / "test" / "expected"

# name: page (from the checkout's root), address, options, and whether the
# page is handed over as its bytes or as text. One page per reader, and one
# for each option the JS package passes on.
EXTRACT: dict[str, dict[str, Any]] = {
    "brake-pads": {
        "page": "examples/brake-pads.html",
        "url": "https://example.com/p/bp-2210",
    },
    "brake-pads-as-text": {
        "page": "examples/brake-pads.html",
        "url": "https://example.com/p/bp-2210",
        "as": "text",
    },
    "brake-pads-with-headers": {
        "page": "examples/brake-pads.html",
        "url": "https://example.com/p/bp-2210",
        "options": {
            "headers": {
                "Link": '<https://example.com/p/bp-2210?v=2>; rel="canonical"',
                "X-Robots-Tag": "noai, noimageai",
            }
        },
    },
    "jsonld": {
        "page": "tests/fixtures/product_jsonld.html",
        "url": "https://shop.example/p/1",
    },
    "microdata": {
        "page": "tests/fixtures/product_microdata.html",
        "url": "https://shop.example/p/2",
    },
    "rdfa": {"page": "js/test/pages/rdfa.html", "url": "https://shop.example/p/1187"},
    "dublincore": {
        "page": "js/test/pages/dublincore.html",
        "url": "https://library.example/hume/taste",
    },
    "opengraph": {
        "page": "tests/fixtures/site_opengraph_and_a_story_list.html",
        "url": "https://news.example/",
    },
    "twitter": {
        "page": "js/test/pages/twitter.html",
        "url": "https://example.com/guides/pads",
    },
    "html": {
        "page": "js/test/pages/htmlmeta.html",
        "url": "https://example.com/notes/discs",
    },
    "all-three": {
        "page": "tests/fixtures/product_all_three.html",
        "url": "https://shop.example/p/3",
    },
    "latin1-declared": {
        "page": "tests/fixtures/product_latin1_declared.html",
        "url": "https://shop.example/p/4",
    },
    "xhtml": {"page": "tests/fixtures/product_xhtml.html", "url": None},
    "induced": {
        "page": "tests/fixtures/listing_no_declared_data.html",
        "url": "https://shop.example/c/pads",
        "options": {"induce": True},
    },
    "visible-article": {
        "page": "examples/site/article.html",
        "url": "http://127.0.0.1:8000/article.html",
        "options": {"visible": True},
    },
    "visible-notes": {
        "page": "examples/site/notes.html",
        "url": "http://127.0.0.1:8000/notes.html",
        "options": {"visible": True},
    },
    "plain": {"page": "tests/fixtures/plain.html", "url": None},
}

SHOP = "tests/fixtures/drift"
LEARNT_FROM = [f"{SHOP}/shop_v1.html", f"{SHOP}/shop_v1_page2.html"]
REPLAYED_ON = [
    f"{SHOP}/shop_v1.html",
    f"{SHOP}/shop_prices_gone.html",
    f"{SHOP}/shop_redesigned.html",
]

# The same pages, learnt from examples of their values and named, and written
# by selectors instead of learnt: compile's other options, each passed on.
WANT = {"title": "A Light in the Attic", "price": "£51.77"}
NAMES = ["first page", "second page"]
SELECT = {"title": "a.title::text", "price": "span.price::text"}
ROWS = "li.product"

MARKDOWN = {
    "article": {
        "page": "examples/site/article.html",
        "url": "http://127.0.0.1:8000/article.html",
    },
}


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    for name, case in EXTRACT.items():
        options = case.get("options", {})
        answer = sluicer.extract(_page(case), url=case["url"], **options)
        _write("extract", name, {**_described(case), "answer": asdict(answer)})

    pages = [(_read(path), _address(path)) for path in LEARNT_FROM]
    extractor = compile_extractor(pages)
    _write(
        "extractor",
        "compiled",
        {
            "pages": [{"page": path, "url": _address(path)} for path in LEARNT_FROM],
            "answer": json.loads(extractor.to_json()),
        },
    )
    kept = Extractor.from_json(extractor.to_json())
    for path in REPLAYED_ON:
        run = run_extractor(kept, _read(path), _address(path))
        _write(
            "extractor",
            f"run-{Path(path).stem}",
            {"page": path, "url": _address(path), "answer": asdict(run)},
        )

    wanted = compile_extractor(pages, want=WANT, names=NAMES)
    _write(
        "extractor",
        "compiled-want",
        {
            "pages": [{"page": path, "url": _address(path)} for path in LEARNT_FROM],
            "options": {"want": WANT, "names": NAMES},
            "answer": json.loads(wanted.to_json()),
        },
    )

    written = compile_extractor(pages, select=SELECT, rows=ROWS)
    _write(
        "written",
        "compiled",
        {
            "pages": [{"page": path, "url": _address(path)} for path in LEARNT_FROM],
            "options": {"select": SELECT, "rows": ROWS},
            "answer": json.loads(written.to_json()),
        },
    )
    kept = Extractor.from_json(written.to_json())
    for path in REPLAYED_ON:
        run = run_extractor(kept, _read(path), _address(path))
        _write(
            "written",
            f"run-{Path(path).stem}",
            {"page": path, "url": _address(path), "answer": asdict(run)},
        )
    alone = compile_extractor([], select={"heading": "h1"})
    _write(
        "written",
        "compiled-from-no-page",
        {
            "pages": [],
            "options": {"select": {"heading": "h1"}},
            "answer": json.loads(alone.to_json()),
        },
    )
    run = run_extractor(alone, _read(LEARNT_FROM[0]), _address(LEARNT_FROM[0]))
    _write(
        "written",
        "run-from-no-page",
        {
            "page": LEARNT_FROM[0],
            "url": _address(LEARNT_FROM[0]),
            "answer": asdict(run),
        },
    )

    for name, case in MARKDOWN.items():
        markdown = sluicer.to_markdown(_page(case), url=case["url"])
        _write("markdown", name, {**_described(case), "answer": markdown})
    written = sum(1 for _ in OUT.rglob("*.json"))
    print(f"wrote {written} files under {OUT.relative_to(ROOT)}")
    return 0


def _page(case: dict[str, Any]) -> str | bytes:
    raw = _read(case["page"])
    return raw.decode("utf-8") if case.get("as") == "text" else raw


def _read(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def _address(path: str) -> str:
    return f"https://shop.example/{Path(path).name}"


def _described(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": case["page"],
        "url": case["url"],
        "as": case.get("as", "bytes"),
        "options": case.get("options", {}),
    }


def _write(kind: str, name: str, body: dict[str, Any]) -> None:
    path = OUT / kind / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
