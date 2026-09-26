# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Regenerate docs/scoreboard-tools.md: every tool on the same pages.

    uv run bench/timing.py tools                # first: the seconds, at this commit
    uv run bench/tools_compare.py               # every tool, then the scoreboard
    uv run bench/tools_compare.py --tools sluicer   # rerun one, reuse the others

The tools people reach for to turn a web page into its title, author, date
and text -- Sluicer, trafilatura, newspaper4k, markitdown, Scrapling's
markdown and metascraper -- each in an environment of its own, pinned, on the
same pages as served with their scripts: WCXB's test pages as the archives
kept them (``bench/realweb.py``), trafilatura's evaluation set
(``bench/evaldata.py``), and the pages added by hand in
``bench/tools-added.json``. What is asked, how an answer counts and what is
compared were fixed in ``bench/PREREG.md`` before any of it was run.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import corpus  # noqa: E402
import evaldata  # noqa: E402
import realweb  # noqa: E402
import run as board  # noqa: E402
import score  # noqa: E402
import stats  # noqa: E402
from snippets import counted  # noqa: E402

CACHE = corpus.CACHE / "tools"
RESULTS = CACHE / "results"
ADDED = HERE / "tools-added.json"
SCOREBOARD = ROOT / "docs" / "scoreboard-tools.md"
PREREG = board.PREREG
REQUIREMENTS = HERE / "requirements"

TOOLS = (
    "sluicer",
    "trafilatura",
    "newspaper4k",
    "markitdown",
    "scrapling",
    "metascraper",
)
VISIBLE = "sluicer --visible"
# What each tool is asked, as bench/PREREG.md lists it: a question it does not
# answer is not scored for it.
ANSWERS = {
    "sluicer": ("title", "author", "date", "text"),
    VISIBLE: ("title", "author", "date"),
    "trafilatura": ("title", "author", "date", "text"),
    "newspaper4k": ("title", "author", "date", "text"),
    "markitdown": ("title", "text"),
    "scrapling": ("title", "text"),
    "metascraper": ("title", "author", "date"),
}
INSTALL = {
    "sluicer": 'pip install "sluicer[markdown]"',
    "trafilatura": "pip install trafilatura==2.2.0",
    "newspaper4k": "pip install newspaper4k==0.9.6",
    "markitdown": "pip install markitdown==0.1.8",
    "scrapling": 'pip install "scrapling[rag]==0.4.15"',
    "metascraper": "npm install metascraper@5.58.1 metascraper-title@5.56.2 "
    "metascraper-author@5.56.2 metascraper-date@5.56.2",
}
SETS = {
    "served": "WCXB's test pages as served",
    "trafilatura": "trafilatura's evaluation set",
    "added": "the page added by hand",
}
# trafilatura's evaluation bounds the snippets per side and page.
MAX_CHUNKS = evaldata.MAX_CHUNKS


def environment(tool: str) -> list[str]:
    """What ``uv run`` puts in a tool's own environment (bench/PREREG.md)."""
    if tool == "sluicer":
        return [
            "--with-editable", str(ROOT),
            "--with-requirements", str(REQUIREMENTS / "trafilatura.txt"),
        ]  # fmt: skip
    if tool == "scrapling":
        return ["--with-requirements", str(REQUIREMENTS / "scrapling-markdown.txt")]
    return ["--with-requirements", str(REQUIREMENTS / f"{tool}.txt")]


# --- the pages ------------------------------------------------------------------


def _write(name: str, entries: list[dict[str, Any]]) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.json"
    path.write_text(json.dumps(entries, indent=1) + "\n", encoding="utf-8")
    return path


def _relative(path: Path) -> str:
    """A body's path as the tools read it: relative to the page list."""
    return os.path.relpath(path, CACHE)


def ensure_served() -> Path:
    """WCXB's test pages as served, each with WCXB's labels, main text too."""
    corpus.ensure()
    manifest = json.loads(realweb.MANIFEST.read_text(encoding="utf-8"))
    realweb.refetch(manifest)
    pages = {
        page["id"]: page
        for page in json.loads(corpus.PAGES.read_text(encoding="utf-8"))
    }
    entries = []
    for entry in manifest["pages"]:
        if not entry["included"]:
            continue
        page = pages[entry["id"]]
        truth = json.loads(
            (corpus.CORPUS / "test" / "ground-truth" / f"{entry['id']}.json").read_text(
                encoding="utf-8"
            )
        )["ground_truth"]
        body = realweb._body_path(entry["id"], entry).with_suffix(".html.gz")
        entries.append(
            {
                **page,
                "path": _relative(body),
                "with": list(truth.get("with") or [])[:MAX_CHUNKS],
                "without": list(truth.get("without") or [])[:MAX_CHUNKS],
                "main_content": truth.get("main_content") or None,
                "metadata": True,
            }
        )
    return _write("served", entries)


def ensure_trafilatura() -> Path:
    """trafilatura's evaluation pages; the metadata of the annotated ones."""
    evaldata.ensure()
    annotated = {
        page["id"] for page in json.loads(evaldata.LABELLED.read_text(encoding="utf-8"))
    }
    entries = [
        {
            **page,
            "path": _relative(evaldata.CACHE / page["path"]),
            "metadata": page["id"] in annotated,
        }
        for page in json.loads(evaldata.PAGES.read_text(encoding="utf-8"))
    ]
    return _write("trafilatura", entries)


def ensure_added() -> Path:
    """The pages added by hand, each the capture its SHA-256 pins."""
    listed = json.loads(ADDED.read_text(encoding="utf-8"))["pages"]
    entries = []
    for page in listed:
        path = CACHE / "added" / f"{page['id']}-{page['timestamp']}.html.gz"
        if path.exists():
            body = gzip.decompress(path.read_bytes())
        else:
            body, _meta = realweb._fetch_wayback(page)
        if hashlib.sha256(body).hexdigest() != page["sha256"]:
            raise SystemExit(
                f"{page['id']}: the capture {page['timestamp']} no longer holds "
                "the pinned bytes"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(body, mtime=0))
        entries.append({**page, "path": _relative(path), "metadata": True})
    return _write("added", entries)


ENSURE = {
    "served": ensure_served,
    "trafilatura": ensure_trafilatura,
    "added": ensure_added,
}


# --- running the tools ----------------------------------------------------------


def _out(page_set: str, tool: str) -> Path:
    suffix = ".json" if tool == "metascraper" else ".json.gz"
    return RESULTS / page_set / f"{tool}{suffix}"


def _command(tool: str, pages: Path, out: Path, python: str) -> list[str]:
    return [
        "uv", "run", "--no-project", "--python", python, *environment(tool),
        "python", str(HERE / "tools" / f"compare_{tool}.py"), str(pages), str(out),
    ]  # fmt: skip


def run(tools: list[str]) -> None:
    import timing

    python = timing.interpreter(board.PYTHON)
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    for page_set, ensure in ENSURE.items():
        pages = ensure()
        (RESULTS / page_set).mkdir(parents=True, exist_ok=True)
        for tool in tools:
            out = _out(page_set, tool)
            if tool == "metascraper":
                command, tool_env = board._command(tool, pages, out)
                tool_env.pop("VIRTUAL_ENV", None)
            else:
                command, tool_env = _command(tool, pages, out, python), env
            print(f"{page_set}: {tool}", flush=True)
            subprocess.run(command, cwd=ROOT, env=tool_env, check=True)


def _load(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    loaded: dict[str, Any] = json.loads(data)
    return loaded


# --- scoring ----------------------------------------------------------------------

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_RULE = re.compile(r"^[\s=:-]+$", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(\S.*?\S|\S)\1")
_MARK = re.compile(r"^\s*(?:#+|[-*+]|\d+[.)])\s+", re.MULTILINE)


def plain(text: str | None) -> str:
    """Any tool's text as plain text, by one rule for all (bench/PREREG.md): a
    link or an image becomes its text, emphasis, heading and list marks,
    setext underlines, table bars and backslash escapes are taken out, and
    spaces collapsed."""
    if not text:
        return ""
    for _nested in range(2):  # an image inside a link
        text = _LINK.sub(r"\1", text)
    text = text.replace("|", " ")
    text = _RULE.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _MARK.sub("", text)
    text = text.replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()


def word_scores(predicted: str, reference: str) -> tuple[float, float, float]:
    """Word-level precision, recall and F1, as WCXB's README computes them:
    lowercased ``\\w+`` words, counted as a multiset. No text scores 0."""
    pred = Counter(re.findall(r"\w+", predicted.lower()))
    ref = Counter(re.findall(r"\w+", reference.lower()))
    if not ref:
        return (1.0, 1.0, 1.0) if not pred else (0.0, 0.0, 0.0)
    if not pred:
        return 0.0, 0.0, 0.0
    overlap = sum((pred & ref).values())
    precision = overlap / sum(pred.values())
    recall = overlap / sum(ref.values())
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def with_visible(run: dict[str, Any]) -> dict[str, Any]:
    """Sluicer's run, each question answered by the summary where it answers
    and by ``--visible``'s guess where it does not; never flagged, since a
    guess carries no warning."""
    rows = []
    for row in run["results"]:
        guesses = row.get("visible") or {}
        rows.append(
            {
                "id": row["id"],
                **{
                    field: row.get(field)
                    if score.as_text(row.get(field))
                    else guesses.get(field)
                    for field in score.FIELDS
                },
                "flagged": [
                    field
                    for field in row.get("flagged", [])
                    if score.as_text(row.get(field))
                ],
            }
        )
    return {**run, "tool": VISIBLE, "results": rows}


def load(page_set: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """A set's pages, in id order, and every tool's run on them."""
    pages = sorted(
        json.loads((CACHE / f"{page_set}.json").read_text(encoding="utf-8")),
        key=lambda page: page["id"],
    )
    runs = {
        tool: _load(_out(page_set, tool))
        for tool in TOOLS
        if _out(page_set, tool).exists()
    }
    if "sluicer" in runs:
        runs = {"sluicer": runs["sluicer"], VISIBLE: with_visible(runs["sluicer"]),
                **{t: r for t, r in runs.items() if t != "sluicer"}}  # fmt: skip
    ids = [page["id"] for page in pages]
    for tool, found in runs.items():
        if sorted(row["id"] for row in found["results"]) != ids:
            raise SystemExit(
                f"{tool}'s results on {page_set} are of other pages: run "
                f"`uv run bench/tools_compare.py --tools {tool.split()[0]}`"
            )
    return pages, runs


def meta_outcomes(
    pages: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, dict[str, str]]:
    """Every annotated page's outcome per field, by ``bench/score.py``."""
    labelled = {page["id"]: page for page in pages if page["metadata"]}
    return score.outcomes(
        (row for row in run["results"] if row["id"] in labelled), labelled
    )


def text_rows(
    pages: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Per page: the snippets found, leaked, missed and kept out; whether no
    ``without`` snippet leaked; whether the text was silently empty; and, where
    WCXB writes the whole text, the word-level scores."""
    rows = {row["id"]: row for row in run["results"]}
    found = {}
    for page in pages:
        row = rows[page["id"]]
        text = plain(row.get("text"))
        snippets = counted(page, text)
        words = (
            word_scores(text, page["main_content"])
            if page.get("main_content")
            else None
        )
        found[page["id"]] = {
            "snippets": snippets,
            "has_without": bool(page["without"]),
            "clean": snippets[1] == 0,
            "has_with": bool(page["with"]),
            "empty": "raised" not in row and not text,
            "raised": "raised" in row,
            "words": words,
        }
    return found


def silent_wrong(
    per_page: dict[str, dict[str, str]], run: dict[str, Any], field: str
) -> dict[str, Any]:
    """The answers on ``field`` that are wrong or invented with no warning
    beside them, those with one, and the answers given."""
    flagged_rows = {
        row["id"] for row in run["results"] if field in (row.get("flagged") or [])
    }
    wrong = [
        page_id
        for page_id, fields in sorted(per_page.items())
        if fields[field] in ("wrong", "invention")
    ]
    given = sum(
        1 for fields in per_page.values() if fields[field] in score.TRIALS["right"]
    )
    return {
        "silent": [page_id for page_id in wrong if page_id not in flagged_rows],
        "flagged": [page_id for page_id in wrong if page_id in flagged_rows],
        "given": given,
    }


# --- what is compared -------------------------------------------------------------

SNIPPET_RATES = ("precision", "recall", "F1")


def _snippet_columns(
    rows: dict[str, dict[str, Any]], ids: list[str]
) -> list[list[int]]:
    return [[rows[page_id]["snippets"][i] for page_id in ids] for i in range(3)]


def _clean_columns(rows: dict[str, dict[str, Any]], ids: list[str]) -> list[list[int]]:
    trials = [int(rows[page_id]["has_without"]) for page_id in ids]
    hits = [
        int(rows[page_id]["has_without"] and rows[page_id]["clean"]) for page_id in ids
    ]
    return [hits, trials]


def _word_columns(
    rows: dict[str, dict[str, Any]], ids: list[str], part: int = 2
) -> list[list[float]]:
    """One of the word scores (precision 0, recall 1, F1 2) per page that
    WCXB writes the whole text of, and a 1 per such page."""
    return [
        [rows[i]["words"][part] if rows[i]["words"] else 0.0 for i in ids],
        [1.0 if rows[i]["words"] else 0.0 for i in ids],
    ]


def text_measures(
    rows: dict[str, dict[str, Any]], ids: list[str]
) -> dict[str, tuple[float, float, float] | str]:
    """The text's rates with their intervals: the snippets' bootstrapped over
    pages, the pages kept clean by Wilson, the mean word scores bootstrapped."""
    columns = _snippet_columns(rows, ids)
    found: dict[str, Any] = {}
    for rate in SNIPPET_RATES:
        found[rate] = stats.interval(
            columns, lambda s, rate=rate: evaldata._snippet_rates(s)[rate]
        )
    hits, trials = _clean_columns(rows, ids)
    found["clean"] = stats.rate(sum(hits), sum(trials))
    if any(rows[i]["words"] for i in ids):
        for part, name in enumerate(("word precision", "word recall", "word F1")):
            found[name] = stats.interval(
                _word_columns(rows, ids, part), lambda s: stats.ratio(s[0], s[1])
            )
    return found


TEXT_COMPARED = ("precision", "recall", "F1", "pages kept clean", "word F1")


def text_comparison(
    ours: dict[str, dict[str, Any]], theirs: dict[str, dict[str, Any]], measure: str
) -> stats.Comparison | None:
    """Sluicer's text against another's on one measure, paired by page."""
    ids = sorted(set(ours) & set(theirs))
    if measure in SNIPPET_RATES:
        return stats.compare(
            [*_snippet_columns(ours, ids), *_snippet_columns(theirs, ids)],
            lambda s: (
                evaldata._snippet_rates(s[:3])[measure]
                - evaldata._snippet_rates(s[3:])[measure]
            ),
        )
    if measure == "pages kept clean":
        return stats.rate_difference(
            *_clean_columns(ours, ids), *_clean_columns(theirs, ids)
        )
    if not any(ours[i]["words"] for i in ids):
        return None
    return stats.compare(
        [*_word_columns(ours, ids), *_word_columns(theirs, ids)],
        lambda s: stats.ratio(s[0], s[1]) - stats.ratio(s[2], s[3]),
    )


def comparisons(
    per_page: dict[str, dict[str, dict[str, str]]],
    texts: dict[str, dict[str, dict[str, Any]]],
) -> dict[tuple[str, str, str, str], stats.Comparison]:
    """Sluicer, and Sluicer declared then ``--visible``, against every other
    tool on every rate both answer: ``(ours, tool, question, measure)``."""
    found: dict[tuple[str, str, str, str], stats.Comparison] = {}
    for ours in ("sluicer", VISIBLE):
        if ours not in per_page:
            continue
        for tool in per_page:
            if tool in ("sluicer", VISIBLE):
                continue
            for field in score.FIELDS:
                if field not in ANSWERS[tool]:
                    continue
                for measure in board.MEASURES:
                    found[(ours, tool, field, measure)] = score.paired(
                        per_page[ours], per_page[tool], field, measure
                    )
    if "sluicer" in texts:
        for tool in texts:
            if tool == "sluicer":
                continue
            for measure in TEXT_COMPARED:
                compared = text_comparison(texts["sluicer"], texts[tool], measure)
                if compared is not None:
                    found[("sluicer", tool, "text", measure)] = compared
    return found


# --- the page ---------------------------------------------------------------------


def _name(run: dict[str, Any]) -> str:
    return f"{run['tool']} {run['version']}"


def _names(runs: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        tool: (
            f"sluicer {run['version']}, declared then `--visible`"
            if tool == VISIBLE
            else _name(run)
        )
        for tool, run in runs.items()
    }


def _meta_table(runs, per_page, pages, measure: str) -> list[str]:
    labelled = {page["id"]: page for page in pages if page["metadata"]}
    names = _names(runs)
    lines = ["| tool | title | author | date |", "|---|---|---|---|"]
    for tool in runs:
        counts = score.tally(per_page[tool], labelled)
        cells = [
            score.rate(counts[field], measure) if field in ANSWERS[tool] else "--"
            for field in score.FIELDS
        ]
        lines.append(f"| {names[tool]} | " + " | ".join(cells) + " |")
    return lines


def _silent_table(runs, per_page) -> list[str]:
    names = _names(runs)
    lines = [
        "| tool | title | author | date | wrong, with a warning |",
        "|---|---|---|---|---|",
    ]
    for tool in runs:
        cells, flagged = [], 0
        for field in score.FIELDS:
            if field not in ANSWERS[tool]:
                cells.append("--")
                continue
            found = silent_wrong(per_page[tool], runs[tool], field)
            flagged += len(found["flagged"])
            cells.append(
                f"{len(found['silent'])} of {found['given']}: "
                + stats.rate(len(found["silent"]), found["given"])
            )
        lines.append(f"| {names[tool]} | " + " | ".join(cells) + f" | {flagged} |")
    return lines


def _text_table(runs, texts, pages) -> list[str]:
    ids = [page["id"] for page in pages]
    with_words = any(page.get("main_content") for page in pages)
    head = (
        "| tool | snippets found | snippets leaked | precision | recall | F1 "
        "| pages kept clean | silent empty | raised |"
    )
    lines = [head, "|---|---|---|---|---|---|---|---|---|"]
    words = [
        "| tool | word precision | word recall | word F1 |",
        "|---|---|---|---|",
    ]
    for tool, rows in texts.items():
        measures = text_measures(rows, ids)
        tp = sum(rows[i]["snippets"][0] for i in ids)
        fp = sum(rows[i]["snippets"][1] for i in ids)
        fn = sum(rows[i]["snippets"][2] for i in ids)
        tn = sum(rows[i]["snippets"][3] for i in ids)
        empty = sum(1 for i in ids if rows[i]["empty"] and rows[i]["has_with"])
        raised = sum(1 for i in ids if rows[i]["raised"])
        rates = " | ".join(stats.bounded(*measures[rate]) for rate in SNIPPET_RATES)
        lines.append(
            f"| {_name(runs[tool])} | {tp}/{tp + fn} | {fp}/{fp + tn} | {rates} "
            f"| {measures['clean']} | {empty} | {raised} |"
        )
        if with_words:
            words.append(
                f"| {_name(runs[tool])} | "
                + " | ".join(
                    stats.bounded(*measures[name])
                    for name in ("word precision", "word recall", "word F1")
                )
                + " |"
            )
    return [*lines, "", *(words if with_words else [])]


def _comparison_table(runs, found) -> list[str]:
    names = _names(runs)
    lines = [
        "| side | against | question | rate | difference (95% interval) | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for (ours, tool, field, measure), compared in found.items():
        rate = board.MEASURES.get(measure, measure)
        lines.append(
            f"| {names[ours]} | {names[tool]} | {field} | {rate} "
            f"| {stats.difference(compared)} | {compared.verdict} |"
        )
    return [*lines, "", *board.many(len(found))]


def _standing(runs, found, ours: str = "sluicer") -> list[str]:
    """Where Sluicer is ahead, behind, or not told apart, question by
    question, as the paired comparisons call it and nowhere else."""
    names = _names(runs)
    said = []
    keys = sorted(
        {(field, measure) for (side, _t, field, measure) in found if side == ours},
        key=lambda k: (["title", "author", "date", "text"].index(k[0]), k[1]),
    )
    for field, measure in keys:
        by: dict[str, list[str]] = {"better": [], "worse": [], "inconclusive": []}
        for (side, tool, f, m), compared in found.items():
            if side == ours and f == field and m == measure:
                by[compared.verdict].append(names[tool])
        parts = []
        if by["better"]:
            parts.append(f"ahead of {board._listed(by['better'])}")
        if by["worse"]:
            parts.append(f"behind {board._listed(by['worse'])}")
        if by["inconclusive"]:
            parts.append(f"not told apart from {board._listed(by['inconclusive'])}")
        rate = board.MEASURES.get(measure, measure)
        said.append(f"- **{field}, {rate}**: {'; '.join(parts)}.")
    return said


def _quoted(value: Any, limit: int = 90) -> str:
    text = score.as_text(value) or ""
    text = re.sub(r"\s+", " ", text).replace("|", "/").replace("`", "'")
    return f"`{text[:limit]}{'...' if len(text) > limit else ''}`"


def _examples(runs, per_page, pages, count: int = 3) -> list[str]:
    """The first ``count`` silent wrong answers per tool and question, by id."""
    by_id = {page["id"]: page for page in pages}
    names = _names(runs)
    lines = []
    for tool, run in runs.items():
        rows = {row["id"]: row for row in run["results"]}
        for field in score.FIELDS:
            if field not in ANSWERS[tool]:
                continue
            found = silent_wrong(per_page[tool], run, field)
            if not found["silent"]:
                continue
            shown = []
            for page_id in found["silent"][:count]:
                page = by_id[page_id]
                label = page[field]
                shown.append(
                    f"  - `{page_id}` <{page['url']}>: "
                    + (f"label {_quoted(label)}" if label else "no label")
                    + f", answered {_quoted(rows[page_id].get(field))}"
                )
            lines += [
                f"- **{names[tool]}, {field}**: {len(found['silent'])} silent "
                "wrong answers; the first by id:",
                *shown,
            ]
    return lines


# ``bench/score.py``'s outcomes, as a reader of one page's answers reads them.
OUTCOME_WORDS = {
    "hit": "right",
    "wrong": "wrong",
    "silent": "no answer",
    "correct_silence": "none, rightly",
    "invention": "invented",
}


def _added(runs, per_page, texts, pages) -> list[str]:
    """Every tool's every answer on the pages added by hand."""
    names = _names(runs)
    lines = []
    for page in pages:
        lines += [
            f"**<{page['url']}>**, as the Wayback Machine captured it at "
            f"`{page['timestamp']}`. {page['why']} Labels: title "
            f"{_quoted(page['title'])}, author {_quoted(page['author'])}, date "
            f"{_quoted(page['date'])}.",
            "",
            "| tool | title | author | date | snippets found | snippets leaked |",
            "|---|---|---|---|---|---|",
        ]
        for tool, run in runs.items():
            row = next(r for r in run["results"] if r["id"] == page["id"])
            cells = []
            for field in score.FIELDS:
                if field not in ANSWERS[tool]:
                    cells.append("--")
                    continue
                outcome = OUTCOME_WORDS[per_page[tool][page["id"]][field]]
                source = row.get(f"{field}_from") if tool == "sluicer" else None
                cells.append(
                    f"{_quoted(row.get(field), 60)} ({outcome}"
                    + (f", from {source}" if source else "")
                    + ")"
                    if score.as_text(row.get(field))
                    else outcome
                )
            if tool in texts:
                found, leaked, missed, kept = texts[tool][page["id"]]["snippets"]
                cells += [
                    f"{found} of {found + missed}",
                    f"{leaked} of {leaked + kept}",
                ]
            else:
                cells += ["--", "--"]
            lines.append(f"| {names[tool]} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def _scored(page_set: str) -> dict[str, Any]:
    """One set's pages, runs, outcomes, texts and comparisons."""
    pages, runs = load(page_set)
    per_page = {tool: meta_outcomes(pages, run) for tool, run in runs.items()}
    texts = {
        tool: text_rows(pages, run)
        for tool, run in runs.items()
        if "text" in ANSWERS[tool]
    }
    return {
        "pages": pages,
        "runs": runs,
        "per_page": per_page,
        "texts": texts,
        "found": comparisons(per_page, texts),
    }


def _counts(pages: list[dict[str, Any]]) -> str:
    annotated = [page for page in pages if page["metadata"]]
    labelled = {
        field: sum(1 for p in annotated if score.as_text(p[field]))
        for field in score.FIELDS
    }
    with_text = sum(1 for page in pages if page.get("main_content"))
    return (
        f"{len(pages)} pages; {len(annotated)} annotated for their metadata, "
        f"{labelled['title']} with a title, {labelled['author']} with an author, "
        f"{labelled['date']} with a date; {sum(len(p['with']) for p in pages)} "
        f"`with` and {sum(len(p['without']) for p in pages)} `without` snippets"
        + (f"; the whole main text on {with_text}" if with_text else "")
    )


def publish() -> None:
    import timing

    sets = {page_set: _scored(page_set) for page_set in SETS}
    commit = board._git("rev-parse", "--short", "HEAD")
    served_runs = {
        tool: run for tool, run in sets["served"]["runs"].items() if tool != VISIBLE
    }
    seconds = timing.published("tools", served_runs, commit)
    SCOREBOARD.write_text(_document(sets, seconds, commit), encoding="utf-8")
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


def _document(sets: dict[str, dict[str, Any]], seconds: list[str], commit: str) -> str:
    served, traf, added = sets["served"], sets["trafilatura"], sets["added"]
    today = datetime.date.today().isoformat()
    dirty = " (with uncommitted changes)" if board.changed() else ""
    lines = [
        "# Every tool, on the same pages",
        "",
        "The tools people reach for to turn a web page into its title, author,",
        "date and text, each in an environment of its own, pinned, given the same",
        "bytes of the same pages as their servers sent them, scripts intact, and",
        "scored one way: which answers are right, which are wrong with nothing to",
        "say so, how much of the main text each keeps, and how much of the",
        "site's menus and footers comes with it.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        "`uv run bench/tools_compare.py`; what is asked and how it is scored were",
        f"fixed in [`bench/PREREG.md`]({PREREG}) before any tool was run.",
        "",
        *board.fitted("`659f3a6`, `8e723ed`, `bebff9d`"),
        '!!! note "What this is not"',
        "    Sluicer's text is trafilatura's extraction written as markdown, by",
        "    design (`sluicer.markdown`), so on the text the two differ by how",
        "    trafilatura is called, not by two ways of finding it. Sluicer's",
        "    summary holds only what a page declares in markup; `--visible` adds",
        "    what the page shows, kept apart. Firecrawl is left out: its service",
        "    needs an account and a key, and its self-hosted form is a Docker",
        "    Compose of several services, not a package to pin beside the others.",
        "    Scrapy has no reading of its own for a title, a date or a text, only",
        "    the selectors someone writes.",
        "",
        "## The pages",
        "",
        f"- **{SETS['served']}**: WCXB's test pages as the Wayback Machine and",
        "  Common Crawl kept them, pinned by `bench/realweb-manifest.json`, with",
        "  WCXB's labels (drafted with a language model, then reviewed by people):",
        f"  {_counts(served['pages'])}.",
        f"- **{SETS['trafilatura']}**: the pages trafilatura evaluates itself on,",
        "  annotated by hand by its authors, at the commit `bench/evaldata.py` pins:",
        f"  {_counts(traf['pages'])}.",
        f"- **{SETS['added']}**: one page, written into",
        "  `bench/tools-added.json` with labels written by hand. One page carries",
        "  no rate; it is shown answer by answer, below, and pooled into nothing.",
        "",
        "A dash is a question the tool does not answer, never a zero.",
        "",
        "## Where Sluicer stands",
        "",
        "As the paired comparisons below call it, and nowhere else: ahead or",
        "behind only where the 95% interval of the difference leaves out zero.",
        "",
        f"On {SETS['served']}:",
        "",
        *_standing(served["runs"], served["found"]),
        "",
        f"With `--visible`'s guesses where the summary is silent, on {SETS['served']}:",
        "",
        *_standing(served["runs"], served["found"], VISIBLE),
        "",
        f"On {SETS['trafilatura']}:",
        "",
        *_standing(traf["runs"], traf["found"]),
        "",
        "With `--visible`'s guesses where the summary is silent, on "
        f"{SETS['trafilatura']}:",
        "",
        *_standing(traf["runs"], traf["found"], VISIBLE),
        "",
    ]
    for key in ("served", "trafilatura"):
        data = sets[key]
        lines += [
            f"## Title, author and date: {SETS[key]}",
            "",
            "Hit rate, over the pages whose label is not empty:",
            "",
            *_meta_table(data["runs"], data["per_page"], data["pages"], "hit"),
            "",
            "Right when answering, over every answer given, inventions included:",
            "",
            *_meta_table(data["runs"], data["per_page"], data["pages"], "right"),
            "",
            "**Silent wrong**: an answer wrong or invented with nothing in the",
            "tool's output to warn of it, over the answers given. The one warning",
            "any of these tools gives is Sluicer's `conflicts`, a question the page",
            "answers two ways that mean different things; those are counted in the",
            "last column and not as silent. A guess of `--visible` carries none.",
            "A title counts wrong by `bench/score.py`'s rule, so a page's longer",
            "title, its site's name added, is wrong where the label is the",
            "heading alone and the shorter is under 0.6 of the longer.",
            "",
            *_silent_table(data["runs"], data["per_page"]),
            "",
            f"## The main text: {SETS[key]}",
            "",
            "Every tool's text written as plain text by one rule first, so",
            "markdown is not scored for its syntax. A `with` snippet the text",
            "holds is found; a `without` snippet, the page's menus, footers and",
            "banners, has leaked. Precision, recall and F1 over the summed",
            "snippets, each with a 95% interval bootstrapped over pages. *Pages",
            "kept clean*: no `without` snippet leaked, over the pages that have",
            "one, with its Wilson interval. *Silent empty*: no text and no error,",
            "on a page with main text.",
            "",
            *_text_table(data["runs"], data["texts"], data["pages"]),
            "",
        ]
        if key == "served":
            lines += [
                "The word scores are WCXB's own: each text against the page's",
                "whole labelled main text, words counted as a multiset, averaged",
                "over the pages, each with a 95% interval bootstrapped over pages.",
                "",
            ]
    lines += [
        "## The page added by hand",
        "",
        *_added(added["runs"], added["per_page"], added["texts"], added["pages"]),
        "## Silent wrong answers, by example",
        "",
        "The first three of each tool's, per question, in page id order, with",
        "the label and the answer. All of them are in each tool's results.",
        "",
    ]
    for key in ("served", "trafilatura"):
        data = sets[key]
        lines += [
            f"### {SETS[key][0].upper()}{SETS[key][1:]}",
            "",
            *_examples(data["runs"], data["per_page"], data["pages"]),
            "",
        ]
    lines += [
        "## Speed and install",
        "",
        "| tool | install line |",
        "|---|---|",
        *(f"| {tool} | `{INSTALL[tool]}` |" for tool in TOOLS),
        "",
        "Seconds per page are for everything the tool is asked here, on the",
        f"{len(served['pages'])} pages as served; Sluicer's `--visible` is not timed.",
        "",
        *seconds,
        "",
        "## How sure, and what differs",
        "",
        "Sluicer, and Sluicer declared then `--visible`, against each other",
        "tool, on every rate both answer, paired by page.",
        "",
    ]
    for key in ("served", "trafilatura"):
        data = sets[key]
        lines += [
            f"### {SETS[key][0].upper()}{SETS[key][1:]}",
            "",
            *_comparison_table(data["runs"], data["found"]),
            "",
        ]
    lines += [
        "## Method",
        "",
        "- **Title, author, date**: `bench/score.py`, as on every scoreboard.",
        "- **Sluicer**: `extract(html, url=...).summary`'s `title`, `author`,",
        "  `published`, and `sluicer.markdown.to_markdown(html, url=...)`; with",
        "  `--visible`, the guess of `extract(..., visible=True)` where the summary",
        "  has no answer.",
        "- **trafilatura**: `extract_metadata(html, default_url=...)` and",
        '  `extract(html, url=..., output_format="markdown")`.',
        "- **newspaper4k**: `download(input_html=...)` and `parse()`, network taken",
        "  away and images off; its text is plain text.",
        "- **markitdown**: `MarkItDown().convert_stream(...)` of the bytes, told",
        "  they are HTML from the page's address: `.title` and `.markdown`.",
        "- **Scrapling**: `Response(...).markdown(main_content_only=True)`, as its",
        "  site-to-markdown spider asks it, and `<title>`'s text; given the page",
        "  decoded as html-to-markdown is given it, since its fetchers pass the",
        "  charset the server sent.",
        "- **metascraper**: its `title`, `author` and `date` rules, as on the other",
        "  scoreboards.",
        f"- **Environments**: Python {board.PYTHON}, each tool pinned with its",
        "  dependencies in `bench/requirements/` or `bench/metascraper/`.",
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
    parser.add_argument(
        "--publish", action="store_true", help="write the page from the last results"
    )
    args = parser.parse_args()
    started = time.perf_counter()
    if not args.publish:
        run([tool.strip() for tool in args.tools.split(",") if tool.strip()])
    publish()
    print(f"done in {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
