"""Scrapling's adaptive selectors on SWDE, beside Sluicer's extractors.

Run by ``bench/swde.py`` in an environment holding ``requirements/scrapling.txt``
and nothing else. As the drift benchmark asks Scrapling: on the seed page an
example came from, the first element whose text is the example is found with
``find_by_text``, its selector is the one Scrapling generates for it, and
``css(selector, auto_save=True)`` saves it. On every other page of the site
``css(selector, adaptive=True)`` asks for it again, in Scrapling's own storage;
Scrapling relocates by similarity when the selector matches nothing. The tool
sees the seed pages' examples and nothing of the test pages' labels.
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

from scrapling.parser import Selector


def read(root: Path, folder: str, page_id: str) -> tuple[str, str | None]:
    """A page's HTML and address: SWDE writes the address as a ``<base>`` first."""
    html = (root / folder / f"{page_id}.htm").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    found = re.search(r'<base href="([^"]+)"', html[:4096])
    return html, found.group(1) if found else None


def one_site(root: Path, store: Path, site: dict[str, Any]) -> dict[str, Any]:
    store.unlink(missing_ok=True)
    first_url = read(root, site["folder"], site["seeds"][0])[1] or site["id"]
    storage = {"storage_file": str(store), "url": first_url}
    selectors: dict[str, str] = {}
    unlearnt: dict[str, str] = {}
    started = time.perf_counter()
    for name, example in site["examples"].items():
        html, _ = read(root, site["folder"], example["seed"])
        page = Selector(html, url=first_url, adaptive=True, storage_args=storage)
        found = page.find_by_text(example["value"], first_match=False, partial=False)
        if len(found) == 0:
            unlearnt[name] = "find_by_text found no element with the example's text"
            continue
        selector = found[0].generate_css_selector
        page.css(selector, auto_save=True, identifier=name)
        selectors[name] = selector
    seconds = time.perf_counter() - started
    answers: dict[str, dict[str, list[Any]]] = {}
    relocated = 0
    for page_id in site["tests"]:
        if not selectors:
            break
        html, _ = read(root, site["folder"], page_id)
        started = time.perf_counter()
        page = Selector(html, url=first_url, adaptive=True, storage_args=storage)
        row: dict[str, list[Any]] = {}
        for name, selector in selectors.items():
            try:
                plain = page.css(selector)
                hits = (
                    plain
                    if len(plain)
                    else page.css(selector, adaptive=True, identifier=name)
                )
                relocated += not len(plain) and bool(len(hits))
            except Exception:  # noqa: BLE001 -- another project's code
                hits = []
            text = " ".join(str(hits[0].get_all_text()).split()) if len(hits) else ""
            # Scrapling has no check of its own: nothing it returns is flagged.
            row[name] = [text or None, False]
        seconds += time.perf_counter() - started
        answers[page_id] = row
    return {
        "learnt": selectors,
        "unlearnt": unlearnt,
        "answers": answers,
        "relocated": relocated,
        "seconds": round(seconds, 3),
    }


def main(sites_path: str, out_path: str) -> None:
    sites = json.loads(Path(sites_path).read_text(encoding="utf-8"))
    root = Path(sites_path).parent / "pages"
    stores = Path(sites_path).parent / "scrapling"
    stores.mkdir(exist_ok=True)
    results: dict[str, Any] = {}
    with concurrent.futures.ProcessPoolExecutor(os.cpu_count()) as pool:
        futures = {
            site["id"]: pool.submit(one_site, root, stores / f"{site['id']}.db", site)
            for site in sites
        }
        for site_id, future in futures.items():
            results[site_id] = future.result()
            print(f"  scrapling {site_id}", flush=True)
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "scrapling",
                "version": importlib.metadata.version("scrapling"),
                "sites": results,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
