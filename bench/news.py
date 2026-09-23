# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Regenerate the scoreboard on news in many languages, from fundus's fixtures.

    uv run bench/news.py                    # everything, then docs/scoreboard-news.md
    uv run bench/news.py --tools sluicer    # rerun one tool, reuse the others

fundus -- https://github.com/flairNLP/fundus, MIT -- keeps, for each news
publisher it parses, a page as it fetched it, scripts intact but stored
re-encoded as UTF-8 under the page's own charset declaration, and the
title, authors and publishing date its hand-written parser for that
publisher reads from it, reviewed in its pull requests. They are fetched at
one pinned commit into ``bench/cache/fundus/`` and never committed here.
Which labels belong to which page is decided by fundus's own code, as its
test suite pairs them (``bench/tools/fundus_labels.py``).

The tools, their environments and the scoring are ``bench/run.py``'s.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import run as board
import score

REPOSITORY = "flairNLP/fundus"
COMMIT = "c1b86b67501872595dc5cccda3ce1c81d6c6f966"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / "cache" / "fundus"
CHECKOUT = CACHE / f"fundus-{COMMIT}"
PAGES = CACHE / "pages.json"
RESULTS = CACHE / "results"
SCOREBOARD = ROOT / "docs" / "scoreboard-news.md"

# The language a page declares, as <html lang> writes it: "de", "pt-BR".
_LANG = re.compile(rb"<html\b[^>]*?\blang\s*=\s*[\"']?([A-Za-z]{2,3})", re.I)


def ensure() -> Path:
    """The page list at the pinned commit, downloading and pairing it once."""
    marker = CACHE / "COMMIT"
    if PAGES.exists() and marker.exists() and marker.read_text().strip() == COMMIT:
        return PAGES
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"fundus-{COMMIT[:12]}.tar.gz"
    if not archive.exists():
        print(f"downloading fundus at {COMMIT[:12]} (about 17 MB, once)", flush=True)
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(ARCHIVE) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)
    if CHECKOUT.exists():
        shutil.rmtree(CHECKOUT)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(CACHE, filter="data")
    command = [
        "uv", "run", "--no-project", "--python", board.PYTHON,
        "--with-editable", str(CHECKOUT), "--with", "pytest",
        "python", str(HERE / "tools" / "fundus_labels.py"),
        str(CHECKOUT), str(PAGES),
    ]  # fmt: skip
    subprocess.run(command, cwd=ROOT, check=True)
    marker.write_text(COMMIT + "\n")
    return PAGES


def run(tools: list[str]) -> None:
    pages = ensure()
    RESULTS.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        command, env = board._command(tool, pages, RESULTS / f"{tool}.json")
        subprocess.run(command, cwd=ROOT, env=env, check=True)


def _language(page: dict[str, Any]) -> str:
    """The page's declared language, lowercased, or "none"."""
    import gzip

    head = gzip.decompress((CACHE / page["path"]).read_bytes())[:20_000]
    found = _LANG.search(head)
    if not found:
        return "none"
    code = found.group(1).decode("ascii").lower()
    # Norwegian Bokmål is Norwegian here: nb and no are one language on a page.
    return "no" if code == "nb" else code


def publish() -> None:
    pages_list = json.loads(PAGES.read_text())
    pages = {page["id"]: page for page in pages_list}
    runs = {
        tool: json.loads((RESULTS / f"{tool}.json").read_text())
        for tool in board.TOOLS
        if (RESULTS / f"{tool}.json").exists()
    }
    per_page = {tool: score.outcomes(r["results"], pages) for tool, r in runs.items()}
    languages = {page["id"]: _language(page) for page in pages_list}
    SCOREBOARD.write_text(_document(pages_list, pages, runs, per_page, languages))
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


def _by_language(runs, per_page, pages, languages, field: str) -> list[str]:
    """One row per declared language: each tool's hits over the labelled pages."""
    counted: dict[str, dict[str, Any]] = defaultdict(dict)
    for tool in runs:
        for page_id, outcomes in per_page[tool].items():
            row = counted[languages[page_id]].setdefault(tool, [0, 0])
            result = outcomes[field]
            if result in ("hit", "wrong", "silent"):
                row[1] += 1
                row[0] += result == "hit"
    totals = defaultdict(int)
    for page_id in pages:
        totals[languages[page_id]] += 1
    order = sorted(counted, key=lambda lang: (-totals[lang], lang))
    names = " | ".join(board._name(r) for r in runs.values())
    lines = [f"| language | pages | {names} |", "|---|---|" + "---|" * len(runs)]
    for lang in order:
        cells = []
        for tool in runs:
            hit, labelled = counted[lang].get(tool, [0, 0])
            cells.append(f"{hit}/{labelled}" if labelled else "-")
        lines.append(f"| {lang} | {totals[lang]} | " + " | ".join(cells) + " |")
    return lines


def _document(pages_list, pages, runs, per_page, languages) -> str:
    labelled = {
        field: sum(1 for p in pages_list if score.as_text(p[field]))
        for field in score.FIELDS
    }
    groups = len({p["country"] for p in pages_list})
    declared = {lang for lang in languages.values() if lang != "none"}
    today = datetime.date.today().isoformat()
    commit = board._git("rev-parse", "--short", "HEAD")
    own = ":!docs/scoreboard-news.md"
    changed = board._git("status", "--porcelain", "--", ".", own)
    dirty = " (with uncommitted changes)" if changed else ""
    speed = [
        "| tool | seconds for all pages | packages installed |",
        "|---|---|---|",
        *(
            f"| {board._name(r)} | {r['seconds']:.2f} | {r['packages']} |"
            for r in runs.values()
        ),
    ]
    lines = [
        "# Scoreboard, news in many languages",
        "",
        "The same questions as the [scoreboard](scoreboard.md) -- a page's title,",
        f"author and publication date -- on news pages from {groups} countries'",
        f"publishers, in {len(declared)} declared languages, with their scripts:",
        "as fundus fetched them, stored re-encoded as UTF-8.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        f"`uv run bench/news.py`, against fundus at `{COMMIT[:12]}`; the method is in",
        "[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).",
        "",
        '!!! warning "Read this before the numbers"',
        "    The labels are what fundus's parser for each publisher reads, and a",
        "    parser reads the page a person sees: the headline shown, the byline.",
        "    A page often declares something else -- a headline written for",
        "    search, the publisher as the author -- and Sluicer answers what is",
        "    declared, so a disagreement is counted here as wrong even when the",
        "    declaration is the page's own. Many of fundus's parsers read the",
        "    page's JSON-LD themselves, so part of the agreement is circular. And",
        "    the pages are one or two per publisher, German-heavy: read a",
        "    language's row as a handful of pages, not a rate.",
        "",
        "## Results",
        "",
        f"Hit rate is hits over the pages that carry a label ({labelled['title']} "
        f"titles, {labelled['author']} authors, {labelled['date']} dates on the "
        f"{len(pages_list)} pages). fundus leaves a label empty where its parser "
        "found nothing, so an invention here is an answer where the page shows "
        "none, not necessarily one it does not declare.",
        "",
        *board._summary_table(runs, per_page, pages),
        "",
        *board._full_table(runs, per_page, pages),
        "",
        "## By language",
        "",
        "Each page is counted under the language its `<html lang>` declares.",
        "",
        "### Title",
        "",
        *_by_language(runs, per_page, pages, languages, "title"),
        "",
        "### Author",
        "",
        *_by_language(runs, per_page, pages, languages, "author"),
        "",
        "### Date",
        "",
        *_by_language(runs, per_page, pages, languages, "date"),
        "",
        "## Speed and size",
        "",
        *speed,
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tools",
        default=",".join(board.TOOLS),
        help="comma-separated tools to rerun; the others' last results are reused",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    run([tool.strip() for tool in args.tools.split(",") if tool.strip()])
    publish()
    print(f"done in {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
