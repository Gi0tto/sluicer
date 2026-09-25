# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Regenerate the conformance page: the W3C JSON-LD test suite's HTML tests.

    uv run bench/w3c_jsonld.py      # the suite at its pinned commit, then the page

The JSON-LD 1.1 test suite -- https://github.com/w3c/json-ld-api, ``tests/``,
under the W3C Software and Document License -- has 50 tests of JSON-LD inside
HTML (``html-manifest.jsonld``): which scripts a processor extracts, which
script text is an error, which base IRI a page sets, and what expanding,
compacting, flattening or turning the result into RDF gives. It is fetched at
one pinned commit into ``bench/cache/w3c-jsonld/`` and never committed here.

Sluicer's JSON-LD reader, ``sluicer.compat.extruct`` and extruct each read
every page (``bench/tools/jsonld_w3c_read.py``); PyLD, a JSON-LD processor,
processes each answer with the test's options and the result is compared with
the suite's expected one (``bench/tools/jsonld_w3c_score.py``). PyLD also reads
every page itself, which checks the harness. ``bench/PREREG.md`` fixes the
rules, under "The W3C JSON-LD tests in HTML".
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import run as board  # noqa: E402
import stats  # noqa: E402

REPOSITORY = "w3c/json-ld-api"
COMMIT = "ffdb326121ea89b7b8280e76a5caea923834bcef"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"
CACHE = HERE / "cache" / "w3c-jsonld"
SUITE = CACHE / f"json-ld-api-{COMMIT}" / "tests"
RESULTS = CACHE / "results"
DOC = ROOT / "docs" / "conformance-jsonld.md"
BASE = "https://w3c.github.io/json-ld-api/tests/"
READERS = ("sluicer", "sluicer.compat.extruct", "extruct")
NAMES = {
    "pyld": "PyLD",
    "sluicer": "Sluicer's JSON-LD reader",
    "sluicer.compat.extruct": "sluicer.compat.extruct",
    "extruct": "extruct",
}


def ensure() -> Path:
    """The suite's tests at the pinned commit, downloaded and unpacked once."""
    if (SUITE / "html-manifest.jsonld").exists():
        return SUITE
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"json-ld-api-{COMMIT[:12]}.tar.gz"
    if not archive.exists():
        print(f"downloading {REPOSITORY} at {COMMIT[:12]} (about 2 MB, once)")
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(ARCHIVE) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)
    prefix = f"json-ld-api-{COMMIT}/"
    with tarfile.open(archive, "r:gz") as tar:
        wanted = [
            member
            for member in tar.getmembers()
            if member.name.startswith(prefix + "tests/")
            or member.name == prefix + "LICENSE.md"
        ]
        tar.extractall(CACHE, members=wanted, filter="data")
    return SUITE


def _tests(suite: Path) -> list[dict[str, Any]]:
    manifest = json.loads((suite / "html-manifest.jsonld").read_text(encoding="utf-8"))
    return [
        {
            "id": test["@id"].lstrip("#"),
            "path": str(suite / test["input"].split("#")[0]),
            "url": BASE + test["input"],
        }
        for test in manifest["sequence"]
    ]


def run() -> dict[str, Any]:
    suite = ensure()
    RESULTS.mkdir(parents=True, exist_ok=True)
    tests = RESULTS / "tests.json"
    tests.write_text(json.dumps(_tests(suite), indent=1) + "\n", encoding="utf-8")
    answers = []
    for tool in READERS:
        out = RESULTS / f"{tool}.json"
        environment = board.requirements("sluicer" if tool != "extruct" else tool)
        command = [
            "uv", "run", "--no-project", "--python", board.PYTHON, *environment,
            "python", str(HERE / "tools" / "jsonld_w3c_read.py"), tool, str(tests),
            str(out),
        ]  # fmt: skip
        subprocess.run(command, cwd=ROOT, check=True)
        answers.append(str(out))
    scored = RESULTS / "scored.json"
    command = [
        "uv", "run", "--no-project", "--python", board.PYTHON,
        *board.requirements("pyld"), "python",
        str(HERE / "tools" / "jsonld_w3c_score.py"), str(suite), *answers, str(scored),
    ]  # fmt: skip
    subprocess.run(command, cwd=ROOT, check=True)
    loaded: dict[str, Any] = json.loads(scored.read_text(encoding="utf-8"))
    return loaded


# --- the page -------------------------------------------------------------------


def _passes(scored: dict[str, Any], who: str) -> list[int]:
    return [int(row["outcomes"][who]["passed"]) for row in scored["tests"]]


def _name(scored: dict[str, Any], who: str) -> str:
    return f"{NAMES[who]} {scored['readers'][who]['version']}"


KINDS = ("expand", "compact", "flatten", "toRdf")


def _table(scored: dict[str, Any]) -> list[str]:
    tests = scored["tests"]
    counts = Counter(row["kind"] for row in tests)
    lines = [
        "| reads the page | all | "
        + " | ".join(f"{kind} ({counts[kind]})" for kind in KINDS)
        + " | negative tests |",
        "|---|---|" + "---|" * len(KINDS) + "---|",
    ]
    negatives = [row for row in tests if row["negative"]]
    for who in ("pyld", *READERS):
        passed = _passes(scored, who)
        cells = [stats.rate(sum(passed), len(passed))]
        for kind in KINDS:
            rows = [row for row in tests if row["kind"] == kind]
            cells.append(
                f"{sum(r['outcomes'][who]['passed'] for r in rows)}/{len(rows)}"
            )
        cells.append(
            f"{sum(r['outcomes'][who]['passed'] for r in negatives)}/{len(negatives)}"
        )
        lines.append(f"| {_name(scored, who)} | " + " | ".join(cells) + " |")
    return lines


def _within_reach(scored: dict[str, Any]) -> list[str]:
    """The tests a reader can pass at all, and how each did on them."""
    reach = [row for row in scored["tests"] if not row["asks"]]
    passed = {
        who: sum(row["outcomes"][who]["passed"] for row in reach) for who in READERS
    }
    rates = [f"{NAMES[who]} {stats.rate(passed[who], len(reach))}" for who in READERS]
    return [
        f"{len(scored['tests']) - len(reach)} of the tests ask for what no reader's "
        "answer can give: a script named by its fragment, the first of several "
        "scripts alone, or the base a page's `<base href>` sets. On the other "
        f"{len(reach)}, which a reader passes or fails by what it answers, "
        f"{board._listed(rates)}.",
    ]


def _comparisons(scored: dict[str, Any]) -> list[str]:
    lines = [
        "| first | against | difference in tests passed (95% interval) | verdict |",
        "|---|---|---|---|",
    ]
    pairs = [("sluicer", "extruct"), ("sluicer", "sluicer.compat.extruct")]
    ones = [1] * len(scored["tests"])
    for ours, theirs in pairs:
        found = stats.rate_difference(
            _passes(scored, ours), ones, _passes(scored, theirs), ones
        )
        lines.append(
            f"| {_name(scored, ours)} | {_name(scored, theirs)} | "
            f"{stats.difference(found)} | {found.verdict} |"
        )
    return [*lines, "", *board.many(len(pairs))]


def _losses(scored: dict[str, Any], who: str) -> list[str]:
    """Every test ``who`` fails, and why."""
    lines = []
    for row in scored["tests"]:
        outcome = row["outcomes"][who]
        if outcome["passed"]:
            continue
        said = outcome.get("why", "")
        lines.append(f"| `{row['id']}` | {row['name']} | {outcome['did']} | {said} |")
    if not lines:
        return ["It passes every test."]
    return [
        "| test | what it asks | the answer | why it fails |",
        "|---|---|---|---|",
        *lines,
    ]


# What each reason a reader fails is, as the page counts them; the scorer's
# ``REASONS`` names the same keys.
REASONS = {
    "fragment": "name one script by its fragment",
    "first": "want the first of several scripts",
    "refuse": "want an error the reader did not give",
    "base": "set their base with the page's `<base href>`",
    "graph": "hold a `@graph` the reader answers node by node",
    "json": "get an answer that is not the scripts' JSON",
    "differs": "get another result",
}


def _reasons(scored: dict[str, Any], who: str) -> str:
    """How many of ``who``'s failures each reason explains."""
    counted = Counter(
        row["outcomes"][who].get("reason", "differs")
        for row in scored["tests"]
        if not row["outcomes"][who]["passed"]
    )
    total = sum(counted.values())
    parts = [f"{count} {REASONS[reason]}" for reason, count in counted.most_common()]
    return f"{total} tests fail. By the first reason that holds, " + (
        board._listed(parts) + "." if parts else "none."
    )


def document(scored: dict[str, Any]) -> str:
    today = datetime.date.today().isoformat()
    commit = board._git("rev-parse", "--short", "HEAD")
    dirty = " (with uncommitted changes)" if board.changed() else ""
    tests = scored["tests"]
    pyld_passed = sum(_passes(scored, "pyld"))
    lines = [
        "# Conformance: JSON-LD in HTML",
        "",
        "The W3C's JSON-LD 1.1 test suite has 50 tests of JSON-LD inside HTML:",
        "which of a page's scripts a processor extracts (the first, the one a",
        "fragment names, or all of them), which script text is an error, which",
        "base IRI the page sets, and what expanding, compacting, flattening or",
        "turning the result into RDF gives. Sluicer's JSON-LD reader, its extruct",
        "interface and extruct itself read every page; each answer, as the reader",
        "gives it, is processed by PyLD, a JSON-LD processor, with the test's",
        "options, and compared with the suite's expected result by the suite's",
        "own rules.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        f"`uv run bench/w3c_jsonld.py`, against the suite at `{COMMIT[:12]}`; the",
        "rules are in [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md).",
        "",
        '!!! warning "Read this before the numbers"',
        "    A reader of JSON-LD is not a JSON-LD processor, and these are a",
        "    processor's tests. A reader is given a page and its address and",
        "    answers the JSON its scripts hold; it takes no option, so it cannot",
        "    be told to read only the first script or the one a fragment names,",
        "    and its answer carries no base IRI. Every test that asks for one of",
        "    those fails for every reader alike, and is listed below as such.",
        "    What the page measures is what a reader's answer keeps of what a",
        "    processor needs: the scripts' JSON as written, and a refusal where",
        "    the text is not JSON-LD.",
        "",
        "## Results",
        "",
        f"Tests passed, of the {len(tests)}, with the Wilson interval of the",
        "share. PyLD reading every page itself is the check that the harness",
        f"scores a processor as the suite does: it passes {pyld_passed} of",
        f"{len(tests)}.",
        "",
        *_table(scored),
        "",
        *_within_reach(scored),
        "",
        *_comparisons(scored),
        "",
    ]
    for who in READERS:
        lines += [
            f"## Where {NAMES[who]} fails",
            "",
            _reasons(scored, who),
            "",
            *_losses(scored, who),
            "",
        ]
    lines += [
        "## Where PyLD fails",
        "",
        *_losses(scored, "pyld"),
        "",
        "## Method",
        "",
        f"- **Suite.** [`w3c/json-ld-api`](https://github.com/{REPOSITORY}) at "
        f"commit `{COMMIT[:12]}`, `tests/html-manifest.jsonld` and the pages",
        "  and expected results it names, under the W3C Software and Document",
        "  License. Downloaded into `bench/cache/`, never committed here.",
        "- **Readers.** Each is given the page's bytes and its address,",
        "  `https://w3c.github.io/json-ld-api/tests/` and the test's input, its",
        "  fragment included. Sluicer's reader is `read_jsonld` on",
        "  `sluicer.document.load(html, url=...)`, what Sluicer's records are",
        "  made from; the other two are `extract(html, base_url=url,",
        '  syntaxes=["json-ld"])`. Sluicer\'s reader answers a number as the',
        "  text the page wrote, `41.90` and not `41.9`, since a record holds",
        "  every value as text; a processor reads that as a string. None of",
        "  these pages writes a number.",
        "- **Processing.** The answer, a list of values, is the document PyLD",
        "  expands, compacts (with the test's context), flattens or turns into",
        "  N-Quads, with the test's `base` option or else the page's address as",
        "  its base, and JSON-LD 1.1's processing mode.",
        "- **Comparison.** The suite's JSON-LD object comparison: objects member",
        "  by member, arrays in any order but a `@list`'s, language tags in any",
        "  case; flattened results also with blank nodes relabelled, when they",
        "  are the same graph; RDF by canonical N-Quads (URDNA2015).",
        "- **Negative tests.** A processor must raise the test's error. A",
        "  reader passes one by answering nothing or by raising.",
        "- **PyLD** reads each page itself through a document loader that serves",
        "  the suite from disk, with the test's options, `extractAllScripts`",
        "  included; it passes a negative test only with the test's error code.",
        "- **Environments.** Python "
        f"{board.PYTHON}; extruct from `bench/requirements/extruct.txt`, PyLD from",
        "  `bench/requirements/pyld.txt`, Sluicer from this checkout.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    scored = run()
    DOC.write_text(document(scored), encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")
    for who in ("pyld", *READERS):
        print(f"{who}: {sum(_passes(scored, who))} of {len(scored['tests'])}")


if __name__ == "__main__":
    main()
