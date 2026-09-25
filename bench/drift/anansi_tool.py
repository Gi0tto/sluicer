"""anansi's self-healing selectors, asked on the drift pairs what Scrapling is.

    python anansi_tool.py JOBS OUT

Run by ``run.py`` in an environment holding anansi alone, pinned by
``bench/requirements/anansi.txt``: mdowis/anansi, Apache-2.0, never a
dependency of Sluicer. Each job is one pair's item, the one Scrapling is asked
about. As ``bench/PREREG.md`` fixed it: the element on A is the innermost whose
text is the item's title, of several the one whose link is the item's; its
selector is the one anansi writes for an element; a fresh store per pair is
asked for that selector on A, then on B, with the pair's address both times.
The captures' bytes are handed over as they are. The answer is judged by
``run.py``, which compares titles as the drift page does.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _href_near(tag: Tag) -> str | None:
    """The link an element is, or sits in, or holds, as ``run.py`` finds it
    for Scrapling."""
    node: Any = tag
    for _ in range(4):
        if not isinstance(node, Tag):
            break
        if node.get("href"):
            return str(node["href"])
        node = node.parent
    inner = tag.select_one("a[href]")
    return str(inner["href"]) if inner is not None else None


def element(soup: BeautifulSoup, title: str, raw_href: str | None) -> Tag | None:
    """The innermost element whose text is ``title``; of several, the one
    whose link is ``raw_href``, else the first."""
    wanted = " ".join(title.split())
    holding = [tag for tag in soup.find_all(True) if _text(tag) == wanted]
    innermost = [
        tag
        for tag in holding
        if not any(_text(child) == wanted for child in tag.find_all(True))
    ]
    if not innermost:
        return None
    return next(
        (tag for tag in innermost if raw_href and _href_near(tag) == raw_href),
        innermost[0],
    )


async def follow(job: dict[str, Any], store: Path) -> dict[str, Any]:
    from anansi.parser.adaptive import AdaptiveParser

    a = Path(job["a"]).read_bytes()
    b = Path(job["b"]).read_bytes()
    found = element(BeautifulSoup(a, "lxml"), job["title"], job["raw_href"])
    if found is None:
        return {"result": "title not found on A"}
    parser = AdaptiveParser(db_path=store)
    selector = parser._tag_to_selector(found)
    # anansi's extract is typed for text; its BeautifulSoup reads bytes too.
    await parser.extract(a, {"item": selector}, url=job["url"])  # type: ignore[arg-type]
    healed = not BeautifulSoup(b, "lxml").select(selector)
    answer = await parser.extract(b, {"item": selector}, url=job["url"])  # type: ignore[arg-type]
    got = answer.get("item")
    return {
        "wanted": job["title"],
        "got": " ".join(str(got).split()) if got else None,
        "selector": selector,
        "healed": healed,
    }


async def main(jobs_path: str, out_path: str) -> None:
    from anansi.db import close_all

    jobs = json.loads(Path(jobs_path).read_text(encoding="utf-8"))
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as stores:
        for job in jobs:
            try:
                results[job["id"]] = await follow(job, Path(stores) / f"{job['id']}.db")
            except Exception as failure:  # noqa: BLE001 -- another project's code
                results[job["id"]] = {
                    "result": f"error: {type(failure).__name__}: {failure}"[:120]
                }
        await close_all()
    Path(out_path).write_text(
        json.dumps(
            {
                "version": importlib.metadata.version("anansi-scraper"),
                "results": results,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"anansi: {len(results)} pairs")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
