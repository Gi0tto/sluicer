"""Sluicer's extractors on SWDE, from the checkout under test.

Run by ``bench/swde.py`` in an environment holding this checkout, installed
editable, and nothing else. For each site, one extractor is compiled from its
seed pages with every example as a ``want``, as ``sluicer compile --want`` does;
a value that is on none of them is named by the error, dropped, and the rest
compiled again. The extractor is then run on every other page of the site. The
tool sees the seed pages' examples and nothing of the test pages' labels.
"""

from __future__ import annotations

import concurrent.futures
import importlib.metadata
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from sluicer.extractor import NothingToLearn, compile_extractor, run_extractor

# The checks a run makes about one field: that it was found, and that it still
# reads and is shaped as it was learnt.
_FIELD_CHECKS = frozenset({"field", "reads", "shape"})
_NAMED = re.compile(r"holds (\w+)=")


def read(root: Path, folder: str, page_id: str) -> tuple[str, str | None]:
    """A page's HTML and address: SWDE writes the address as a ``<base>`` first."""
    html = (root / folder / f"{page_id}.htm").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    found = re.search(r'<base href="([^"]+)"', html[:4096])
    return html, found.group(1) if found else None


def one_site(root: Path, site: dict[str, Any]) -> dict[str, Any]:
    seeds = [read(root, site["folder"], page_id) for page_id in site["seeds"]]
    want = {name: example["value"] for name, example in site["examples"].items()}
    unlearnt: dict[str, str] = {}
    extractor = None
    started = time.perf_counter()
    while want:
        try:
            extractor = compile_extractor(seeds, listing=False, want=want)
            break
        except NothingToLearn as failure:
            named = _NAMED.search(str(failure))
            if named is None or named.group(1) not in want:
                unlearnt.update({name: str(failure) for name in want})
                want = {}
                break
            unlearnt[named.group(1)] = str(failure)
            del want[named.group(1)]
    seconds = time.perf_counter() - started
    answers: dict[str, dict[str, list[Any]]] = {}
    broken = 0
    for page_id in site["tests"]:
        if extractor is None:
            break
        html, url = read(root, site["folder"], page_id)
        started = time.perf_counter()
        run = run_extractor(extractor, html, url)
        seconds += time.perf_counter() - started
        broken += not run.ok
        row: dict[str, list[Any]] = {}
        for name in want:
            flagged = any(
                not check.ok
                for check in run.checks
                if check.name in _FIELD_CHECKS and check.expected.startswith(name + " ")
            )
            row[name] = [run.fields.get(name), flagged]
        answers[page_id] = row
    return {
        "learnt": {f.name: f.path for f in extractor.fields} if extractor else {},
        "unlearnt": unlearnt,
        "answers": answers,
        "broken_runs": broken,
        "seconds": round(seconds, 3),
    }


def main(sites_path: str, out_path: str) -> None:
    sites = json.loads(Path(sites_path).read_text(encoding="utf-8"))
    root = Path(sites_path).parent / "pages"
    results: dict[str, Any] = {}
    with concurrent.futures.ProcessPoolExecutor(os.cpu_count()) as pool:
        futures = {site["id"]: pool.submit(one_site, root, site) for site in sites}
        for site_id, future in futures.items():
            results[site_id] = future.result()
            print(f"  sluicer {site_id}", flush=True)
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "sluicer",
                "version": importlib.metadata.version("sluicer"),
                "sites": results,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
