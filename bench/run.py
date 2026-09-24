# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Regenerate the scoreboard: fetch the corpus, run every tool, score, publish.

    uv run bench/run.py                    # everything, then docs/scoreboard.md
    uv run bench/run.py --tools sluicer    # rerun one tool, reuse the others

Each tool runs in an environment of its own holding only what it needs, at
pinned versions: Sluicer from this checkout, installed editable; trafilatura
and newspaper4k from ``bench/requirements/``; metascraper from the lockfile in
``bench/metascraper/``. Everything after the corpus download runs offline.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import score  # noqa: E402

PYTHON = "3.12"
RESULTS = corpus.CACHE / "results"
SCOREBOARD = ROOT / "docs" / "scoreboard.md"
TOOLS = ("sluicer", "trafilatura", "metascraper", "newspaper4k")


def _uv(requirements: list[str], script: str, pages: Path, out: Path) -> list[str]:
    return [
        "uv", "run", "--no-project", "--python", PYTHON, *requirements,
        "python", str(HERE / "tools" / script), str(pages), str(out),
    ]  # fmt: skip


def _command(tool: str, pages: Path, out: Path) -> tuple[list[str], dict[str, str]]:
    env = dict(os.environ)
    if tool == "sluicer":
        return _uv(["--with-editable", str(ROOT)], "sluicer_tool.py", pages, out), env
    if tool == "trafilatura":
        requirements = [
            "--with-requirements",
            str(HERE / "requirements" / "trafilatura.txt"),
        ]
        return _uv(requirements, "trafilatura_tool.py", pages, out), env
    if tool == "newspaper4k":
        requirements = [
            "--with-requirements",
            str(HERE / "requirements" / "newspaper4k.txt"),
        ]
        return _uv(requirements, "newspaper_tool.py", pages, out), env
    modules = _install_metascraper()
    env["NODE_PATH"] = str(modules)
    return ["node", str(HERE / "metascraper" / "run.js"), str(pages), str(out)], env


def _install_metascraper() -> Path:
    """``npm ci`` from the committed lockfile into the cache, once per lockfile."""
    target = corpus.CACHE / "metascraper"
    lock = (HERE / "metascraper" / "package-lock.json").read_text(encoding="utf-8")
    stamp = target / "installed-from.lock"
    if not (stamp.exists() and stamp.read_text(encoding="utf-8") == lock):
        target.mkdir(parents=True, exist_ok=True)
        for name in ("package.json", "package-lock.json"):
            shutil.copy(HERE / "metascraper" / name, target / name)
        subprocess.run(
            ["npm", "ci", "--no-audit", "--no-fund", "--silent"],
            cwd=target,
            check=True,
        )
        stamp.write_text(lock, encoding="utf-8")
    return target / "node_modules"


def run(tools: list[str]) -> None:
    pages = corpus.ensure()
    RESULTS.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        command, env = _command(tool, pages, RESULTS / f"{tool}.json")
        subprocess.run(command, cwd=ROOT, env=env, check=True)


def _git(*args: str) -> str:
    try:
        found = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return found.stdout.strip()


def _corpus_scripts(pages: list[dict[str, Any]]) -> tuple[int, int]:
    """How many pages carry a <script> at all, and how many carry JSON-LD."""
    scripts = json_ld = 0
    for page in pages:
        html = gzip.decompress((corpus.CACHE / page["path"]).read_bytes()).lower()
        scripts += b"<script" in html
        json_ld += b"application/ld+json" in html
    return scripts, json_ld


def publish() -> None:
    pages_list = json.loads(corpus.PAGES.read_text(encoding="utf-8"))
    pages = {page["id"]: page for page in pages_list}
    runs = {
        tool: json.loads((RESULTS / f"{tool}.json").read_text(encoding="utf-8"))
        for tool in TOOLS
        if (RESULTS / f"{tool}.json").exists()
    }
    per_page = {tool: score.outcomes(r["results"], pages) for tool, r in runs.items()}
    SCOREBOARD.write_text(
        _document(pages_list, pages, runs, per_page), encoding="utf-8"
    )
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


PREREG = "https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md"


def fitted(commits: str) -> list[str]:
    """The note every scoreboard whose pages Sluicer's rules were made on
    opens with: until 0.7.1 they said nothing of it, and one said "Nothing is
    tuned to these pages"."""
    return [
        '!!! warning "Sluicer\'s rules were made on these pages"',
        "    Rules were written, measured on these pages and kept because the",
        f"    numbers here rose ({commits}, among others), so this measures",
        "    Sluicer on pages it was fitted to, not on pages it has never seen.",
        "    Of the scoreboards, only SWDE's held-out half is a held-out test;",
        f"    [`bench/PREREG.md`]({PREREG}) says which pages each rule was made on.",
        "",
    ]


def _name(run: dict[str, Any]) -> str:
    return f"{run['tool']} {run['version']}"


def _summary_table(runs, per_page, pages, types=None) -> list[str]:
    lines = [
        "| tool | title | author | date | authors invented | dates invented |",
        "|---|---|---|---|---|---|",
    ]
    for tool, run in runs.items():
        counts = score.tally(per_page[tool], pages, types)
        rates = " | ".join(f"{score.hit_rate(counts[f]):.3f}" for f in score.FIELDS)
        lines.append(
            f"| {_name(run)} | {rates} | {counts['author']['invention']} "
            f"| {counts['date']['invention']} |"
        )
    return lines


def _full_table(runs, per_page, pages, types=None) -> list[str]:
    lines = [
        "| tool | field | hit | wrong | silent miss | correct silence | invention "
        "| hit rate | right when answering |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for tool, run in runs.items():
        counts = score.tally(per_page[tool], pages, types)
        for field in score.FIELDS:
            c = counts[field]
            lines.append(
                f"| {_name(run)} | {field} | {c['hit']} | {c['wrong']} | {c['silent']}"
                f" | {c['correct_silence']} | {c['invention']}"
                f" | {score.hit_rate(c):.3f} | {score.right_when_answering(c):.3f} |"
            )
    return lines


def _losses(runs, per_page, pages) -> list[str]:
    """Where Sluicer loses, counted from this run rather than asserted."""
    if "sluicer" not in per_page:
        return []
    others = [tool for tool in per_page if tool != "sluicer"]
    lines = []
    for field in ("author", "date"):
        missed = [
            page_id
            for page_id, fields in per_page["sluicer"].items()
            if fields[field] in ("wrong", "silent")
        ]
        found_elsewhere = [
            page_id
            for page_id in missed
            if any(per_page[tool][page_id][field] == "hit" for tool in others)
        ]
        lines.append(
            f"- **{field.capitalize()}.** Sluicer misses {len(missed)} labelled "
            f"pages, and on {len(found_elsewhere)} of them another tool finds the "
            f"{field}."
        )
    sluicer = {row["id"]: row for row in runs["sluicer"]["results"]}
    wrong_titles = [
        page_id
        for page_id, fields in per_page["sluicer"].items()
        if fields["title"] == "wrong"
    ]
    inside = [
        page_id
        for page_id in wrong_titles
        if score._norm(pages[page_id]["title"])
        in score._norm(sluicer[page_id]["title"] or "")
    ]
    lines.append(
        f"- **Title.** Of {len(wrong_titles)} wrong titles, {len(inside)} contain the "
        "label whole: the page declares a longer title than the heading the "
        "labels use."
    )
    return lines


def _inventions(counts: dict[str, Any]) -> list[str]:
    """What each tool answered where the label is empty, counted from this run.

    It said "Sluicer gives none where the page states none" whatever the run,
    beside a table in which Sluicer invented 42 authors.
    """
    said = []
    for tool in counts:
        made = [
            f"{n} {field}{'' if n == 1 else 's'}"
            for field in score.FIELDS
            if (n := counts[tool][field]["invention"])
        ]
        said.append(f"{tool} {_listed(made) if made else 'nothing'}")
    return [
        "Right when answering counts every answer a tool gives, inventions",
        "included. Where a page's label is empty, the tools answered all the",
        f"same: {'; '.join(said)}. On a product or category page with no",
        "publication date, a date is not a small error but a fact that is not",
        "there.",
    ]


def _listed(items: list[str]) -> str:
    """``a, b and c``."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _gaps(per_page, pages) -> str:
    """Where Sluicer's hit rate is below another tool's, widest gap first."""
    counts = {tool: score.tally(per_page[tool], pages) for tool in per_page}
    gaps = []
    for field in score.FIELDS:
        best = max(
            (tool for tool in counts if tool != "sluicer"),
            key=lambda tool: score.hit_rate(counts[tool][field]),
            default=None,
        )
        if best is None:
            continue
        ours = score.hit_rate(counts["sluicer"][field])
        theirs = score.hit_rate(counts[best][field])
        if theirs > ours:
            gaps.append((theirs - ours, field, best, ours, theirs))
    if not gaps:
        return "Sluicer's hit rate is the highest on every field."
    return (
        "Sluicer's hit rate is below another tool's on "
        + _listed(
            [
                f"{field} ({ours:.3f} against {best}'s {theirs:.3f})"
                for _, field, best, ours, theirs in sorted(gaps, reverse=True)
            ]
        )
        + "."
    )


def _wins(runs, per_page, pages) -> list[str]:
    """What Sluicer does better, stated only where this run shows it."""
    if "sluicer" not in per_page:
        return []
    counts = {tool: score.tally(per_page[tool], pages) for tool in per_page}
    lines = []
    for field in score.FIELDS:
        ranked = sorted(
            counts, key=lambda tool: -score.right_when_answering(counts[tool][field])
        )
        cells = ", ".join(
            f"{tool} {score.right_when_answering(counts[tool][field]):.3f}"
            for tool in ranked
        )
        least = min(counts[tool][field]["invention"] for tool in counts)
        tied = [tool for tool in counts if counts[tool][field]["invention"] == least]
        fewest = (
            f"every tool ties at {least}"
            if len(tied) == len(counts)
            else f"{', '.join(tied)} ({least})"
        )
        lines.append(
            f"- **{field.capitalize()}**, right when answering: {cells}. Fewest "
            f"inventions: {fewest}."
        )
    lines += ["", *_inventions(counts)]
    # A tie would make "smallest" mean "first listed"; name every one.
    fastest = min(runs, key=lambda tool: runs[tool]["seconds"])
    least = min(run["packages"] for run in runs.values())
    smallest = " and ".join(t for t in runs if runs[t]["packages"] == least)
    lines += [
        "",
        f"Fastest: {fastest}. Smallest install: {smallest}.",
    ]
    return lines


def _document(pages_list, pages, runs, per_page) -> str:
    scripts, json_ld = _corpus_scripts(pages_list)
    commercial = [p for p in pages_list if p["page_type"] in score.COMMERCIAL]
    labelled = {
        field: sum(1 for p in pages_list if score.as_text(p[field]))
        for field in score.FIELDS
    }
    today = datetime.date.today().isoformat()
    commit = _git("rev-parse", "--short", "HEAD")
    # Its own output does not make the tree it measured dirty.
    changed = _git("status", "--porcelain", "--", ".", ":!docs/scoreboard.md")
    dirty = " (with uncommitted changes)" if changed else ""
    node = subprocess.run(
        ["node", "--version"], capture_output=True, text=True, encoding="utf-8"
    )
    lines = [
        "# Scoreboard",
        "",
        "How often Sluicer's `summary` gets a page's title, author and publication",
        "date right, measured beside the tools people use for the same job, on a",
        "public annotated corpus, with the losses in the same table as the wins.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        "`uv run bench/run.py`; the method and every pin are in",
        "[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).",
        "",
        *fitted("`659f3a6`, `709856e`, `b86aa19`"),
        '!!! warning "Read this before the numbers"',
        (
            "    WCXB removed every `<script>` from its pages: of the "
            if scripts == 0
            else "    WCXB removed `<script>` elements from its pages: of the "
        )
        + f"{len(pages_list)} test",
        f"    pages, {scripts} carry a `<script>` and {json_ld} carry JSON-LD. JSON-LD "
        "is the",
        "    vocabulary Sluicer reads first, and the one many pages declare their",
        "    article or product in, so here Sluicer is measured without its",
        "    strongest reader.",
        "    The other tools read JSON-LD too, but they also read visible text, and",
        "    this corpus leaves them that. The same labels on the same pages as",
        "    their servers sent them, scripts intact, are in",
        "    [the scoreboard on pages as served](scoreboard-served.md).",
        "",
        "## Results",
        "",
        f"Hit rate is hits over the pages that carry a label ({labelled['title']} "
        f"titles, {labelled['author']} authors, {labelled['date']} dates on the "
        f"{len(pages_list)} test pages). An invention is an answer on a page whose "
        "label is empty: WCXB leaves labels empty on purpose, so that column is "
        "how often a tool makes something up.",
        "",
        f"All {len(pages_list)} test pages:",
        "",
        *_summary_table(runs, per_page, pages),
        "",
        f"The {len(commercial)} article, listing, collection and product pages:",
        "",
        *_summary_table(runs, per_page, pages, score.COMMERCIAL),
        "",
        "## Speed and size",
        "",
        "| tool | seconds for all pages | packages installed |",
        "|---|---|---|",
        *[
            f"| {_name(run)} | {run['seconds']:.2f} | {run['packages']} |"
            for run in runs.values()
        ],
        "",
        "Seconds count only the extraction call, one page after another on one",
        "core; packages count everything the tool's own environment holds.",
        "",
        "## Where Sluicer loses, and why",
        "",
        *_losses(runs, per_page, pages),
        "",
        *([_gaps(per_page, pages), ""] if "sluicer" in per_page else []),
        "The other tools also read bylines and dates from the visible text of",
        "the page, where no vocabulary declares them; Sluicer reads only what the",
        "page states in markup that means something, and answers nothing rather",
        "than guess from prose. That is a choice with a cost, and the gap above",
        "is the cost.",
        "",
        "## Where it wins",
        "",
        *_wins(runs, per_page, pages),
        "",
        "## Every outcome",
        "",
        "Right when answering is hits over every answer given, inventions",
        "included.",
        "",
        f"All {len(pages_list)} test pages:",
        "",
        *_full_table(runs, per_page, pages),
        "",
        f"The {len(commercial)} article, listing, collection and product pages:",
        "",
        *_full_table(runs, per_page, pages, score.COMMERCIAL),
        "",
        "## Method",
        "",
        f"- **Corpus.** The test split of [WCXB]"
        f"(https://github.com/{corpus.REPOSITORY}), the Web Content Extraction "
        f"Benchmark by Murrough Foley, CC-BY-4.0, at commit `{corpus.COMMIT[:12]}`.",
        "  It is downloaded, never committed. Its labels are `title`, `author` and",
        "  `publish_date`.",
        "- **Outcomes.** With a label: hit, wrong, or silent miss. Without one:",
        "  correct silence, or invention.",
        "- **Title.** Lowercased, whitespace collapsed; equal, or one contains the",
        "  other and the shorter is at least 0.6 of the longer.",
        "- **Author.** Letter runs, lowercased, less *by, and, the, staff, team,",
        "  editor(s), writer, de, von*; a hit when the shared tokens cover half the",
        "  label's and a quarter of the answer's.",
        "- **Date.** Both parsed with dateutil under a fixed default; a hit when",
        "  the answer writes every part of the date the label writes, alike. Dots",
        "  are day first, slashes month first; with a UTC offset on both, the",
        "  answer is read in the label's. The rule is in `bench/PREREG.md`.",
        "- **Sluicer.** `extract(html, url=...).summary`, fields `title`, `author`,",
        "  `published`, base install, from this checkout.",
        "- **trafilatura.** `extract_metadata(html, default_url=...)`.",
        "- **metascraper.** The `title`, `author` and `date` rules, given the HTML",
        f"  and the page's address, on Node {node.stdout.strip() or 'unknown'}.",
        "- **newspaper4k.** `Article.download(input_html=...)` then `parse()`, with",
        "  image fetching off and the network taken away.",
        f"- **Environments.** Python {PYTHON} for the Python tools. Each tool is",
        "  pinned, dependencies included, in `bench/requirements/` and",
        "  `bench/metascraper/package-lock.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tools",
        default=",".join(TOOLS),
        help="comma-separated tools to rerun; the others' last results are reused",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    run([tool.strip() for tool in args.tools.split(",") if tool.strip()])
    publish()
    print(f"done in {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
