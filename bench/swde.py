# /// script
# requires-python = ">=3.10"
# dependencies = ["py7zr==1.1.3"]
# ///
"""Regenerate the scoreboard on SWDE: extractors learnt from examples.

    uv run bench/swde.py                    # everything, then the scoreboard
    uv run bench/swde.py --tools sluicer    # rerun one tool, reuse the other

SWDE, the Structured Web Data Extraction dataset (Hao, Cai, Pang and Zhang,
SIGIR 2011, Microsoft Reciprocal License), is 124,291 detail pages from 80 web
sites in 8 verticals, crawled around 2010, each labelled with the values of
three to five attributes: a book's title and ISBN, a restaurant's phone, a
camera's price. It is the benchmark wrapper induction is measured on. It is
fetched at one pinned commit of a GitHub mirror of its CodePlex release into
``bench/cache/swde/``, each archive checked against its SHA-256, and never
committed here.

What is measured is what ``sluicer compile --want`` promises: point at a value
on a few pages of one template, and read it on every other page of that
template. For each site the first three pages, in the dataset's order, are the
seeds; each attribute's example is its first labelled value on the first seed
that has one. Every other page of the site is a test page. The tools see the
seed pages and the examples, never a test page's labels.

Scrapling's adaptive selectors, which promise to find an element again when a
page changes, are asked the same thing, as the drift benchmark asks them.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import html
import json
import shutil
import statistics
import subprocess
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

MIRROR = "woailaosang/swde"
COMMIT = "e9b60dbbcb899d70e813e8b899b84e3540d540da"
RAW = f"https://raw.githubusercontent.com/{MIRROR}/{COMMIT}/swde/sourceCode/sourceCode"
ARCHIVES = {
    "groundtruth": "473d248296878daf2b08f65f0e530f54eb336064d6d4617acf723a12b9d74db9",
    "auto": "43494053906dde1ac44c72d30ecdc66aea060b2c02daed3379c88e382f2e79f5",
    "book": "34899c1f7f44b6858c8d1a24924b4b16cf9d9dd85a41a0c30de0315c04569c1f",
    "camera": "549f29713295cff31d0ccaa1420d80efc9c6470affea983770a8db47f149f913",
    "job": "0a0c8e4fabbc7150cf7313acba2386721d9e3011655e0cac79d6140b8acee408",
    "movie": "1323f66fd1d7fcc13d03137fdb6ccbd9faf1e05e882b880981b203fd90d4153f",
    "nbaplayer": "34f3e391b6f72cc21c139c5354b0cfd0722830dc3302ba1808f354a9ec2d75f5",
    "restaurant": "b4f24a058e11d835b8fff383bb2fa7f68997d0c36ca6086fdf969798ab8b2b4f",
    "university": "acc7b3df25fc06accadbf1a04108f8edaa8eaecaf0d26b2da8b3276d0fe91ad2",
}
VERTICALS = [name for name in ARCHIVES if name != "groundtruth"]
SEEDS = 3
PYTHON = "3.12"
TOOLS = ("sluicer", "scrapling")

CACHE = HERE / "cache" / "swde"
PAGES = CACHE / "pages"
BUNDLES = CACHE / "bundles"
SITES = CACHE / "sites.json"
LABELS = CACHE / "labels.json"
RESULTS = CACHE / "results"
SCOREBOARD = ROOT / "docs" / "scoreboard-swde.md"


# -- the dataset -----------------------------------------------------------------


def ensure() -> None:
    """The archives at the pinned commit, checked, unpacked, and each site's
    pages packed into one file, once.

    One compressed file per site, rather than 124,291 pages on disk: a virus
    scanner that reads every file opened read each page again on every run.
    """
    marker = BUNDLES / "made-from"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == COMMIT:
        return
    unpacked = PAGES / "unpacked-from"
    if unpacked.exists() and unpacked.read_text(encoding="utf-8").strip() == COMMIT:
        # Unpacked and checked by an earlier run that made no bundles yet.
        BUNDLES.mkdir(parents=True, exist_ok=True)
        for vertical in VERTICALS:
            if (PAGES / vertical).exists():
                _bundle(vertical)
        marker.write_text(COMMIT + "\n", encoding="utf-8")
        return
    import py7zr

    archives = CACHE / "archives"
    archives.mkdir(parents=True, exist_ok=True)
    # Unpacking over a half-unpacked tree stalls py7zr: start from nothing.
    shutil.rmtree(PAGES, ignore_errors=True)
    shutil.rmtree(BUNDLES, ignore_errors=True)
    PAGES.mkdir(parents=True)
    BUNDLES.mkdir(parents=True)
    for name, digest in ARCHIVES.items():
        path = archives / f"{name}.7z"
        if not path.exists() or _sha256(path) != digest:
            print(f"downloading {name}.7z at {COMMIT[:12]}", flush=True)
            with urllib.request.urlopen(f"{RAW}/{name}.7z") as response:
                path.write_bytes(response.read())
        if _sha256(path) != digest:
            raise SystemExit(f"{name}.7z does not hash to its pin: stopping")
        print(f"unpacking {name}.7z", flush=True)
        with py7zr.SevenZipFile(path) as archive:
            archive.extractall(PAGES)
        if name != "groundtruth":
            _bundle(name)
    marker.write_text(COMMIT + "\n", encoding="utf-8")


def _bundle(vertical: str) -> None:
    """Each of a vertical's sites as one compressed file, and its pages gone.

    Sites are packed side by side: reading the pages is the slow part, and a
    virus scanner reads each one as it is opened. A bundle is written under
    another name and renamed when whole, so one that exists is complete and a
    run stopped halfway resumes where it was.
    """
    folders = [
        folder
        for folder in sorted((PAGES / vertical).iterdir())
        if not (BUNDLES / f"{folder.name.split('(')[0]}.json.gz").exists()
    ]
    with concurrent.futures.ProcessPoolExecutor(8) as pool:
        for site_id, count in pool.map(_pack, folders):
            print(f"  packed {site_id}: {count} pages", flush=True)
    shutil.rmtree(PAGES / vertical)


def _pack(folder: Path) -> tuple[str, int]:
    site_id = folder.name.split("(")[0]
    pages = {
        page.stem: page.read_text(encoding="utf-8-sig", errors="replace")
        for page in sorted(folder.glob("*.htm"))
    }
    partial = BUNDLES / f"{site_id}.json.gz.partial"
    partial.write_bytes(
        gzip.compress(json.dumps(pages, ensure_ascii=False).encode(), 6)
    )
    partial.replace(BUNDLES / f"{site_id}.json.gz")
    return site_id, len(pages)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def half(site_id: str) -> str:
    """``development`` or ``held-out``: in each vertical, sites in alphabetical
    order alternate, the first in development. Fixed on 24 September 2026,
    before any full result was read. Rules are made while reading only the
    development sites' pages and errors; the held-out sites are only scored."""
    vertical = site_id.split("-")[0]
    names = sorted(s for s in _SITE_NAMES if s.split("-")[0] == vertical)
    return "development" if names.index(site_id) % 2 == 0 else "held-out"


# SWDE's 80 sites, as its website list names them.
_SITE_NAMES = frozenset(
    f"{vertical}-{site}"
    for vertical, sites in {
        "auto": "aol autobytel automotive autoweb carquotes cars kbb motortrend "
        "msn yahoo",
        "book": "abebooks amazon barnesandnoble bookdepository booksamillion "
        "borders buy christianbook deepdiscount waterstones",
        "camera": "amazon beachaudio buy compsource ecost jr newegg onsale "
        "pcnation thenerds",
        "job": "careerbuilder dice hotjobs job jobcircle jobtarget monster nettemps "
        "rightitjobs techcentric",
        "movie": "allmovie amctv boxofficemojo hollywood iheartmovies imdb metacritic "
        "msn rottentomatoes yahoo",
        "nbaplayer": "espn fanhouse foxsports msnca nba si slam usatoday wiki yahoo",
        "restaurant": "fodors frommers gayot opentable pickarestaurant restaurantica "
        "tripadvisor urbanspoon usdiners zagat",
        "university": "collegeboard collegenavigator collegeprowler collegetoolkit "
        "ecampustours embark matchcollege princetonreview studentaid usnews",
    }.items()
    for site in sites.split()
)


def _clean(value: str) -> str:
    """A label as the page shows it: SWDE stores values with their entities
    undecoded (``&amp;``, ``&#34;``, ``&nbsp;``), then spaces collapsed."""
    return " ".join(html.unescape(value).split())


def labels() -> dict[str, dict[str, dict[str, list[str]]]]:
    """Every site's labels: site, then attribute, then page, then its values."""
    found: dict[str, dict[str, dict[str, list[str]]]] = {}
    for vertical in VERTICALS:
        for path in sorted((PAGES / "groundtruth" / vertical).glob("*.txt")):
            head, *rows = path.read_text(encoding="utf-8-sig").splitlines()
            _vertical, site, attribute = head.split("\t")
            table = found.setdefault(f"{vertical}-{site}", {}).setdefault(attribute, {})
            for row in rows[1:]:
                page_id, _count, *values = row.split("\t")
                table[page_id] = [
                    v for v in (_clean(x) for x in values if x != "<NULL>") if v
                ]
    return found


def prepare() -> None:
    """The sites the tools are given, and the labels only the scorer reads."""
    ensure()
    truth = labels()
    if set(truth) != _SITE_NAMES:
        raise SystemExit("the sites in the data are not the 80 the split was fixed on")
    sites = []
    for site_id, attributes in sorted(truth.items()):
        bundle = BUNDLES / f"{site_id}.json.gz"
        ids = sorted(json.loads(gzip.decompress(bundle.read_bytes())))
        seeds, tests = ids[:SEEDS], ids[SEEDS:]
        examples = {}
        for attribute, table in attributes.items():
            seed = next((s for s in seeds if table.get(s)), None)
            if seed is not None:
                examples[attribute] = {"value": table[seed][0], "seed": seed}
        sites.append(
            {
                "id": site_id,
                "vertical": site_id.split("-")[0],
                "half": half(site_id),
                "bundle": bundle.name,
                "seeds": seeds,
                "examples": examples,
                "tests": tests,
            }
        )
    SITES.write_text(json.dumps(sites, ensure_ascii=False, indent=1), encoding="utf-8")
    LABELS.write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")


# -- running the tools -------------------------------------------------------------


def _command(tool: str) -> list[str]:
    if tool == "sluicer":
        requirements = ["--with-editable", str(ROOT)]
    else:
        requirements = [
            "--with-requirements",
            str(HERE / "requirements" / "scrapling.txt"),
        ]
    return [
        "uv", "run", "--no-project", "--python", PYTHON, *requirements, "python",
        str(HERE / "tools" / f"swde_{tool}.py"), str(SITES),
        str(RESULTS / f"{tool}.json"),
    ]  # fmt: skip


def run(tools: list[str]) -> None:
    prepare()
    RESULTS.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        print(f"running {tool}", flush=True)
        subprocess.run(_command(tool), cwd=ROOT, check=True)


# -- scoring -----------------------------------------------------------------------


def outcomes(
    site: dict[str, Any], truth: dict[str, dict[str, list[str]]], result: dict[str, Any]
) -> dict[str, Counter[str]]:
    """Per attribute, what each test page came to.

    With a label: hit, wrong, or missed; without one: silent, or invented. A
    wrong answer, an invention or a miss is ``-flagged`` when the tool's own
    checks said so on that page. An attribute the tool could not learn from
    the seeds is ``unlearnt`` on every labelled page: it was said at learning
    time, before any page was read.
    """
    counts: dict[str, Counter[str]] = {}
    for attribute, table in truth.items():
        tally: Counter[str] = Counter()
        learnt = attribute in result["learnt"]
        for page_id in site["tests"]:
            wanted = table.get(page_id, [])
            if not learnt:
                tally["unlearnt" if wanted else "silent"] += 1
                continue
            value, flagged = (
                result["answers"].get(page_id, {}).get(attribute, [None, False])
            )
            mark = "-flagged" if flagged else ""
            if value is None:
                tally[("missed" + mark) if wanted else "silent"] += 1
            elif not wanted:
                tally["invented" + mark] += 1
            elif _edges(value) in {_edges(label) for label in wanted}:
                tally["hit"] += 1
            else:
                tally["wrong" + mark] += 1
        counts[attribute] = tally
    return counts


# What SWDE's labels carry of the template at their ends: a label is a whole
# text node, so ``ISBN-13<b>: 9780316125581`` is labelled ": 9780316125581" and
# ``$61,200 | More Details`` is labelled "$61,200 |". Taken off both sides of
# every comparison, for every tool alike.
_SEPARATORS = " :|,;-\u2013\u2014>/\u00b7\u2022"


def _edges(text: str) -> str:
    return " ".join(text.split()).strip(_SEPARATORS)


def metrics(tally: Counter[str]) -> dict[str, float]:
    hits = tally["hit"]
    answers = hits + sum(
        v for k, v in tally.items() if k.startswith(("wrong", "invented"))
    )
    labelled = hits + sum(
        v for k, v in tally.items() if k.startswith(("wrong", "missed", "unlearnt"))
    )
    precision = hits / answers if answers else 0.0
    recall = hits / labelled if labelled else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def score() -> dict[str, Any]:
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    truth = json.loads(LABELS.read_text(encoding="utf-8"))
    board: dict[str, Any] = {"tools": {}, "pages": sum(len(s["tests"]) for s in sites)}
    for tool in TOOLS:
        data = json.loads((RESULTS / f"{tool}.json").read_text(encoding="utf-8"))
        per: dict[tuple[str, str], Counter[str]] = {}
        for site in sites:
            for attribute, tally in outcomes(
                site, truth[site["id"]], data["sites"][site["id"]]
            ).items():
                per[(site["id"], attribute)] = tally
        board["tools"][tool] = {
            "version": data["version"],
            "per": per,
            "seconds": sum(s["seconds"] for s in data["sites"].values()),
            "relocated": sum(s.get("relocated", 0) for s in data["sites"].values()),
            "broken_runs": sum(s.get("broken_runs", 0) for s in data["sites"].values()),
        }
    return board


def _mean_f1(
    per: dict[tuple[str, str], Counter[str]], keys: list[tuple[str, str]]
) -> float:
    return statistics.fmean(metrics(per[k])["f1"] for k in keys)


def _pooled(per: dict[tuple[str, str], Counter[str]]) -> Counter[str]:
    total: Counter[str] = Counter()
    for tally in per.values():
        total.update(tally)
    return total


def _answers_wrong(tally: Counter[str]) -> tuple[int, int]:
    """Wrong answers and inventions, and how many of them the tool flagged."""
    wrong = sum(v for k, v in tally.items() if k.startswith(("wrong", "invented")))
    flagged = tally["wrong-flagged"] + tally["invented-flagged"]
    return wrong, flagged


def _row(
    label: str, per: dict[tuple[str, str], Counter[str]], keys: list[tuple[str, str]]
) -> str:
    pooled: Counter[str] = Counter()
    for key in keys:
        pooled.update(per[key])
    m = metrics(pooled)
    return (
        f"| {label} | {_mean_f1(per, keys):.3f} | {m['precision']:.3f} | "
        f"{m['recall']:.3f} |"
    )


def publish(board: dict[str, Any]) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8",
    ).stdout.strip()  # fmt: skip
    sl, sc = board["tools"]["sluicer"], board["tools"]["scrapling"]
    keys = sorted(sl["per"])
    names = {
        "sluicer": f"**sluicer {sl['version']}**",
        "scrapling": f"Scrapling {sc['version']}, adaptive",
    }
    lines = [
        "# Scoreboard, extractors learnt from examples",
        "",
        "What `sluicer compile --want` promises, measured: point at a value on a",
        "few pages of one template, and read it on every other page of that",
        "template. The pages are [SWDE](https://github.com/woailaosang/swde), the",
        "Structured Web Data Extraction dataset (Hao, Cai, Pang and Zhang, SIGIR",
        f"2011): {board['pages'] + 3 * len({s for s, _ in keys}):,} detail pages from "
        f"{len({s for s, _ in keys})} sites in 8",
        "verticals, crawled around 2010, each labelled with the values of three to",
        "five attributes. It is the dataset wrapper induction is measured on.",
        "",
        "For each site the first three pages, in the dataset's order, are the",
        "seeds, and each attribute's example is its first labelled value on the",
        "first seed that has one. The tools are given the seeds and the examples;",
        f"every other page, {board['pages']:,} in all, is read and scored. Beside",
        "Sluicer, [Scrapling](https://github.com/D4Vinci/Scrapling)'s adaptive",
        "selectors, which promise to find an element again when a page changes,",
        "are asked the same thing, as [the drift benchmark](drift.md) asks them.",
        "",
        f"Regenerated on {datetime.date.today().isoformat()} from commit `{commit}` by "
        f"`uv run bench/swde.py`, against the mirror at `{COMMIT[:12]}`, every",
        f"archive checked against its SHA-256. Sluicer took {sl['seconds']:.0f} s "
        f"of CPU to learn and run its {len({s for s, _ in keys})} extractors, "
        f"Scrapling {sc['seconds']:.0f} s.",
        "",
        '!!! warning "Read this before the numbers"',
        "    These pages declare almost nothing, so every value here is learnt from",
        "    where the example sits. A value that is part of a longer text, as in",
        "    `Price: $129.00` in one cell, cannot be pointed at by either tool, and",
        "    counts as not learnt. SWDE's labels were made by regular expressions",
        "    over text nodes and stored with their HTML entities undecoded; they",
        "    are decoded here before any comparison.",
        "",
        "## Every site and attribute",
        "",
        "F1 is averaged over the site-attributes, as SWDE's results are reported;",
        "precision and recall pool every page.",
        "",
        "| system | mean F1 | precision | recall |",
        "|---|---|---|---|",
        _row(names["sluicer"], sl["per"], keys),
        _row(names["scrapling"], sc["per"], keys),
        "",
        "| system | wrong answers | of them flagged by the run "
        "| not learnt (site-attributes) |",
        "|---|---|---|---|",
    ]
    for tool, data in (("sluicer", sl), ("scrapling", sc)):
        wrong, flagged = _answers_wrong(_pooled(data["per"]))
        unlearnt = sum(1 for tally in data["per"].values() if tally["unlearnt"])
        shown = (
            f"{flagged:,} ({flagged / wrong:.0%})"
            if tool == "sluicer" and wrong
            else "no checks"
        )
        lines.append(
            f"| {names[tool]} | {wrong:,} | {shown} | {unlearnt} of {len(keys)} |"
        )
    lines += [
        "",
        "A wrong answer is a value that is not the page's, or a value where the",
        "page has none. Sluicer's run checks each value it learnt: that its place",
        "is still there, and that it still reads and is shaped as it was learnt.",
        "A wrong answer those checks caught makes `sluicer run` exit 3; one they",
        "did not is silent. Scrapling returns what it finds and has no check.",
        "",
        "## By half",
        "",
        "The sites were split before any full result was read (commit",
        "`fc72378`): in each vertical, in alphabetical order, they alternate",
        "between development and held-out. Sluicer's rules are made reading the",
        "development sites only; the held-out ones are only scored. One",
        "exception: all ten camera sites were read while the benchmark was being",
        "built, before the split, so the held-out camera sites are not a clean",
        "test.",
        "",
        "| half | site-attributes | sluicer F1 | Scrapling F1 |",
        "|---|---|---|---|",
    ]
    for name in ("development", "held-out"):
        hkeys = [k for k in keys if half(k[0]) == name]
        lines.append(
            f"| {name} | {len(hkeys)} | {_mean_f1(sl['per'], hkeys):.3f} | "
            f"{_mean_f1(sc['per'], hkeys):.3f} |"
        )
    lines += [
        "",
        "## By vertical",
        "",
        "| vertical | site-attributes | sluicer F1 | Scrapling F1 |",
        "|---|---|---|---|",
    ]
    for vertical in VERTICALS:
        vkeys = [k for k in keys if k[0].split("-")[0] == vertical]
        lines.append(
            f"| {vertical} | {len(vkeys)} | {_mean_f1(sl['per'], vkeys):.3f} | "
            f"{_mean_f1(sc['per'], vkeys):.3f} |"
        )
    lines += [
        "",
        "## By attribute",
        "",
        "| vertical | attribute | sluicer F1 | Scrapling F1 |",
        "|---|---|---|---|",
    ]
    attributes = sorted({(k[0].split("-")[0], k[1]) for k in keys})
    for vertical, attribute in attributes:
        akeys = [
            k for k in keys if k[0].split("-")[0] == vertical and k[1] == attribute
        ]
        lines.append(
            f"| {vertical} | {attribute} | {_mean_f1(sl['per'], akeys):.3f} | "
            f"{_mean_f1(sc['per'], akeys):.3f} |"
        )
    lines += ["", *READING, ""]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")


# Written by hand, after reading the wrong answers: what they were, and why.
READING: list[str] = []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tools", nargs="+", choices=TOOLS, default=list(TOOLS))
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()
    if not args.score_only:
        run(args.tools)
    board = score()
    publish(board)
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")
    for tool, data in board["tools"].items():
        keys = list(data["per"])
        pooled = _pooled(data["per"])
        print(
            f"{tool} {data['version']}: mean F1 {_mean_f1(data['per'], keys):.3f} "
            f"over {len(keys)} site-attributes; {dict(sorted(pooled.items()))}"
        )


if __name__ == "__main__":
    main()
