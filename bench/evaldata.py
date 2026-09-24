# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Regenerate the scoreboard on trafilatura's evaluation set.

    uv run bench/evaldata.py                  # everything, then the scoreboard
    uv run bench/evaldata.py --tools sluicer  # rerun one tool, reuse the others

trafilatura -- https://github.com/adbar/trafilatura, Apache-2.0 -- keeps the
990 pages it evaluates its own extraction on, saved with their scripts, each
annotated by hand with snippets its main text must hold and snippets it must
not, and, on 851 of them, the page's title, author and publication date. They
are fetched at one pinned commit into ``bench/cache/evaldata/`` and never
committed here.

Two measurements. The title, author and date, scored by ``bench/score.py`` as
on the other scoreboards, on the 851 annotated pages; an empty annotation means
the page shows none. And the main text: ``sluicer.markdown``, which is
trafilatura's own extraction written as markdown with links and tables kept,
against trafilatura's plain text, scored as trafilatura's evaluation scores it
(``tests/eval_common.py``): a snippet counts when the output holds it, spaces
normalised, at most six per side and page.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import run as board
import score

REPOSITORY = "adbar/trafilatura"
COMMIT = "c852cae9708a59f04521b19395d8ed49771a5c78"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / "cache" / "evaldata"
PAGES = CACHE / "pages.json"
LABELLED = CACHE / "labelled.json"
RESULTS = CACHE / "results"
BODY = RESULTS / "body.json"
SCOREBOARD = ROOT / "docs" / "scoreboard-evaldata.md"

# trafilatura's evaluation bounds the snippets per side so that one document
# with many cannot outweigh the rest (tests/eval_common.py, MAX_CHUNKS).
MAX_CHUNKS = 6


def ensure() -> Path:
    """The page lists at the pinned commit, downloading and unpacking them once."""
    marker = CACHE / "COMMIT"
    if (
        PAGES.exists()
        and marker.exists()
        and marker.read_text(encoding="utf-8").strip() == COMMIT
    ):
        return PAGES
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"trafilatura-{COMMIT[:12]}.tar.gz"
    if not archive.exists():
        print(f"downloading trafilatura at {COMMIT[:12]} (once)", flush=True)
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(ARCHIVE) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)
    stored = CACHE / "pages"
    if stored.exists():
        shutil.rmtree(stored)
    stored.mkdir()
    prefix = f"trafilatura-{COMMIT}/tests/"
    with tarfile.open(archive, "r:gz") as tar:
        members = {m.name: m for m in tar.getmembers() if m.name.startswith(prefix)}

        def read(name: str) -> bytes | None:
            member = members.get(prefix + name)
            handle = tar.extractfile(member) if member is not None else None
            return handle.read() if handle is not None else None

        evaldata = json.loads(read("evaldata.json") or b"{}")
        pages, labelled = [], []
        for url, item in evaldata.items():
            name = item.get("file")
            body = (read(f"eval/{name}") or read(f"cache/{name}")) if name else None
            if body is None:
                continue
            (stored / f"{name}.gz").write_bytes(gzip.compress(body, mtime=0))
            page = {
                "id": name,
                "path": f"pages/{name}.gz",
                "url": url,
                "page_type": "article",
                "with": list(item.get("with") or [])[:MAX_CHUNKS],
                "without": list(item.get("without") or [])[:MAX_CHUNKS],
                "title": item.get("title") or None,
                "author": item.get("author") or None,
                "date": item.get("date") or None,
            }
            pages.append(page)
            # Only an entry annotated for its metadata says a page shows no
            # author; the others say nothing about it.
            if "author" in item:
                labelled.append(page)
    PAGES.write_text(
        json.dumps(pages, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LABELLED.write_text(
        json.dumps(labelled, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    marker.write_text(COMMIT + "\n", encoding="utf-8")
    print(f"{len(pages)} pages, {len(labelled)} with their metadata annotated")
    return PAGES


def run(tools: list[str]) -> None:
    ensure()
    RESULTS.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        command, env = board._command(tool, LABELLED, RESULTS / f"{tool}.json")
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    if "sluicer" in tools or "trafilatura" in tools or not BODY.exists():
        requirements = [
            "--with-editable",
            str(ROOT),
            "--with-requirements",
            str(HERE / "requirements" / "trafilatura.txt"),
        ]
        command = board._uv(requirements, "evaldata_body.py", PAGES, BODY)
        subprocess.run(command, cwd=ROOT, check=True)


def publish() -> None:
    labelled = json.loads(LABELLED.read_text(encoding="utf-8"))
    pages = {page["id"]: page for page in labelled}
    runs = {
        tool: json.loads((RESULTS / f"{tool}.json").read_text(encoding="utf-8"))
        for tool in board.TOOLS
        if (RESULTS / f"{tool}.json").exists()
    }
    per_page = {tool: score.outcomes(r["results"], pages) for tool, r in runs.items()}
    body = json.loads(BODY.read_text(encoding="utf-8"))
    SCOREBOARD.write_text(
        _document(labelled, pages, runs, per_page, body), encoding="utf-8"
    )
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


def _body_table(body: dict[str, Any]) -> list[str]:
    lines = [
        "| output | snippets found | snippets kept out | precision | recall | F1 |",
        "|---|---|---|---|---|---|",
    ]
    for name, counts in body["outputs"].items():
        tp, fp, fn, tn = (counts[k] for k in ("tp", "fp", "fn", "tn"))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        lines.append(
            f"| {name} | {tp}/{tp + fn} | {tn}/{tn + fp} | {precision:.3f} | "
            f"{recall:.3f} | {f1:.3f} |"
        )
    return lines


def _found(body: dict[str, Any], output: str) -> str:
    """How many snippets ``output`` found, of those it could."""
    counts = body["outputs"][output]
    return f"{counts['tp']:,} of the {counts['tp'] + counts['fn']:,}"


def _document(labelled, pages, runs, per_page, body) -> str:
    counted = {
        field: sum(1 for p in labelled if score.as_text(p[field]))
        for field in score.FIELDS
    }
    today = datetime.date.today().isoformat()
    commit = board._git("rev-parse", "--short", "HEAD")
    changed = board._git(
        "status", "--porcelain", "--", ".", ":!docs/scoreboard-evaldata.md"
    )
    dirty = " (with uncommitted changes)" if changed else ""
    lines = [
        "# Scoreboard, trafilatura's evaluation set",
        "",
        "The same questions as the [scoreboard](scoreboard.md) -- a page's title,",
        "author and publication date -- on the pages trafilatura evaluates itself",
        f"on, {body['pages']} saved with their scripts, {len(labelled)} of them "
        "annotated for their metadata, and the main text beside them.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        f"`uv run bench/evaldata.py`, against trafilatura at `{COMMIT[:12]}`; the",
        "method is in [`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).",
        "",
        *board.fitted("`bebff9d`"),
        '!!! warning "Read this before the numbers"',
        "    trafilatura's authors annotated these pages to measure trafilatura,",
        "    so the labels follow what it is built to find: the byline and the date",
        "    a reader sees, which Sluicer does not read, as the known limits say.",
        "    The pages are mostly German blogs and small sites. An empty annotation",
        "    is a page the annotators saw no author or date on, so an invention",
        "    here is an answer where the page shows none, not one it does not",
        "    declare.",
        "",
        "## Title, author, date",
        "",
        f"Hit rate is hits over the pages that carry a label ({counted['title']} "
        f"titles, {counted['author']} authors, {counted['date']} dates on the "
        f"{len(labelled)} annotated pages).",
        "",
        *board._summary_table(runs, per_page, pages),
        "",
        *board._full_table(runs, per_page, pages),
        "",
        "## The main text",
        "",
        "`sluicer.markdown` is trafilatura's extraction, written as markdown with",
        "links and tables kept, so the page's text is trafilatura's by design;",
        "what this measures is what writing it as markdown costs. A link is",
        "written `[its text](its address)`, so a snippet that runs across one is",
        "not found as written: the markdown finds "
        f"{_found(body, 'sluicer.markdown')} snippets, and",
        "with its syntax taken out "
        f"{_found(body, 'sluicer.markdown, its syntax taken out')}, where "
        f"trafilatura's text finds {_found(body, 'trafilatura text')}.",
        "The syntax is taken out roughly, which also takes the underscore out",
        f"of `Liebe_r`. Scored on all {body['pages']} pages, as trafilatura "
        "scores itself.",
        "",
        *_body_table(body),
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
