"""sluicer.compat.extruct beside extruct itself, page by page and syntax by syntax.

    uv run bench/extruct_compat.py    # every corpus, then docs/extruct.md's table

Three corpora: sluicer's own test fixtures, the 360 WCXB pages as their servers
sent them (``bench/realweb.py`` fetches and pins them), and the 140 product
pages of Zyte's benchmark (``bench/products.py``). extruct runs in an
environment of its own, holding exactly ``bench/requirements/extruct.txt``;
the compatibility layer runs from this checkout. Both are handed the same bytes
and the page's address, with every other argument at its default.

A syntax on a page is **identical** when both answers are equal as JSON, and
for RDFa when they are the same graph: extruct names its blank nodes at random
and orders its nodes by a hash Python seeds per process, so the two are
compared as multisets of triples, each blank node named by what it is linked
to. Every difference is put in the first category whose test explains it, and
a difference no test explains is counted as **unexplained**, never dropped.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from sluicer.compat import extruct as compat  # noqa: E402 -- the checkout's own

CACHE = HERE / "cache" / "extruct"
DOC = ROOT / "docs" / "extruct.md"
# extruct runs on the interpreter running this, since ``urljoin`` itself
# changed between Python versions: 3.14 keeps an empty fragment 3.12 drops.
PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
SYNTAXES = ["json-ld", "microdata", "opengraph", "rdfa", "microformat", "dublincore"]
UNIFORM = ["microdata", "opengraph", "microformat", "dublincore"]
CORPORA = {
    "served": "WCXB, as served",
    "products": "Zyte's product pages",
    "fixtures": "sluicer's test fixtures",
}


# --- the pages ---------------------------------------------------------------


def pages() -> list[dict[str, Any]]:
    """Every page of the three corpora, keyed ``corpus/id``."""
    found = [
        {"key": f"fixtures/{path.relative_to(ROOT / 'tests' / 'fixtures')}",
         "path": str(path), "url": None}
        for path in sorted((ROOT / "tests" / "fixtures").rglob("*.html"))
    ]  # fmt: skip
    manifest = json.loads((HERE / "realweb-manifest.json").read_text(encoding="utf-8"))
    bodies = HERE / "cache" / "realweb" / "bodies"
    missing = []
    for entry in manifest["pages"]:
        if not entry["included"]:
            continue
        path = bodies / entry["archive"] / f"{entry['id']}-{entry['timestamp']}.html.gz"
        if not path.exists():
            missing.append(entry["id"])
        found.append(
            {"key": f"served/{entry['id']}", "path": str(path), "url": entry["url"]}
        )
    if missing:
        raise SystemExit(
            f"{len(missing)} served pages are not in bench/cache/realweb: run "
            "`uv run bench/realweb.py --tools sluicer` once to fetch the captures"
        )
    # Downloads Zyte's benchmark on first use.
    import products

    bench = products.ensure()
    truth = json.loads(
        (bench / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
    )
    for page_id, labels in truth.items():
        path = bench / "dataset" / "html" / f"{page_id}.html.gz"
        found.append(
            {"key": f"products/{page_id}", "path": str(path), "url": labels.get("url")}
        )
    return found


def read_bytes(page: dict[str, Any]) -> bytes:
    data = Path(page["path"]).read_bytes()
    return gzip.decompress(data) if page["path"].endswith(".gz") else data


# --- the two runs ------------------------------------------------------------


def run_extruct(pages_file: Path, out: Path) -> dict[str, Any]:
    command = [
        "uv", "run", "--no-project", "--python", PYTHON,
        "--with-requirements", str(HERE / "requirements" / "extruct.txt"),
        "python", str(HERE / "tools" / "extruct_tool.py"), str(pages_file), str(out),
    ]  # fmt: skip
    subprocess.run(command, cwd=ROOT, check=True)
    loaded: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return loaded


def run_compat(found: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    seconds = 0.0
    for page in found:
        html, url = read_bytes(page), page["url"]
        answer: dict[str, Any] = {"syntax": {}, "uniform": {}}
        for syntax in SYNTAXES:
            answer["syntax"][syntax] = _plain(
                compat.extract(html, base_url=url, syntaxes=[syntax])[syntax]
            )
        for syntax in UNIFORM:
            answer["uniform"][syntax] = _plain(
                compat.extract(html, base_url=url, syntaxes=[syntax], uniform=True)[
                    syntax
                ]
            )
        started = time.perf_counter()
        # Recorded as extruct's is, so "raises on none" is counted, not said.
        try:
            compat.extract(html, base_url=url)
            answer["default"] = "ok"
        except Exception as raised:  # noqa: BLE001 -- the count is the point
            answer["default"] = type(raised).__name__
        seconds += time.perf_counter() - started
        results[page["key"]] = answer
    return {"seconds": seconds, "pages": results}


def _plain(value: Any) -> Any:
    """``value`` as JSON would carry it: tuples are lists."""
    return json.loads(json.dumps(value))


# --- comparing ---------------------------------------------------------------


def same(syntax: str, ours: Any, theirs: Any) -> bool:
    if syntax == "rdfa" and isinstance(theirs, list):
        return triples(ours) == triples(theirs)
    return equal(ours, theirs)


def equal(a: Any, b: Any) -> bool:
    """JSON equality, NaN equal to itself: extruct reads a NaN in JSON-LD."""
    if (
        isinstance(a, float)
        and isinstance(b, float)
        and math.isnan(a)
        and math.isnan(b)
    ):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and a == b


def triples(graph: list[dict[str, Any]]) -> Counter[tuple[str, ...]]:
    """An expanded JSON-LD graph as a multiset of triples, blank nodes by colour.

    A blank node's name is replaced by a colour refined three times from the
    triples it takes part in, which names blank nodes the same in two graphs
    that differ only in how they were labelled.
    """
    raw: list[tuple[str, str, str]] = []
    for node in graph:
        subject = node["@id"]
        for key, values in node.items():
            if key == "@id":
                continue
            for value in values:
                if key == "@type":
                    raw.append((subject, "@type", f"<{value}>"))
                elif "@id" in value:
                    raw.append((subject, key, value["@id"]))
                else:
                    raw.append((subject, key, json.dumps(value, sort_keys=True)))
    blank = {term for triple in raw for term in (triple[0], triple[2])
             if term.startswith("_:")}  # fmt: skip
    colour = dict.fromkeys(blank, "_")
    for _round in range(3):
        colour = {
            node: "_:" + str(hash(tuple(sorted(
                (s == node, p, colour.get(s, s), colour.get(o, o))
                for s, p, o in raw if node in (s, o)
            ))))
            for node in blank
        }  # fmt: skip
    return Counter((colour.get(s, s), p, colour.get(o, o)) for s, p, o in raw)


# --- why they differ ---------------------------------------------------------

# Every category a difference can be put in, with who is right in it. A page
# whose difference no test explains is "unexplained", and is listed.
VERDICTS = {
    "extruct raises": (
        "sluicer: extruct raises on a JSON-LD block that is not JSON, or holds "
        'only whitespace, and with `errors="strict"` that block loses every '
        "syntax on the page; sluicer skips the block"
    ),
    "not Dublin Core": (
        "sluicer: extruct files any name after its last dot, so `description`, "
        '`title` and `rel="license"` are Dublin Core to it'
    ),
    "`itemref`": (
        "sluicer: extruct lists the item named as top-level and gives the "
        "property naming it `null`; the WHATWG standard nests it"
    ),
    "`<time>` without `datetime`": (
        'sluicer: extruct answers `""`; the standard\'s value is the text'
    ),
    "an address attribute that is absent": (
        "sluicer: the standard's value is `\"\"`; extruct answers the page's own URL"
    ),
    "`<base href>`": (
        "sluicer: the standard resolves against the document's base URL, "
        "which `<base href>` sets"
    ),
    "bytes that are not UTF-8": (
        "sluicer: extruct reads every page as UTF-8, whatever it declares"
    ),
}
_TREES: dict[str, Any] = {}


def tree(page: dict[str, Any]) -> Any:
    import lxml.html

    if page["key"] not in _TREES:
        _TREES[page["key"]] = lxml.html.fromstring(read_bytes(page))
    return _TREES[page["key"]]


def _raised(theirs: Any) -> bool:
    return isinstance(theirs, dict) and "__error__" in theirs


def _replaced_characters(page: dict[str, Any], ours: Any, theirs: Any) -> bool:
    try:
        read_bytes(page).decode("utf-8")
    except UnicodeDecodeError:
        return "\ufffd" in json.dumps(theirs) and "\ufffd" not in json.dumps(ours)
    return False


_SHAPE = object()


def leaves(ours: Any, theirs: Any) -> list[tuple[Any, Any]]:
    """The pairs of values where two answers of the same shape differ.

    Where the shapes themselves differ -- a key one lacks, a list of another
    length, a value of another type -- the pair is ``(_SHAPE, _SHAPE)``.
    """
    if isinstance(ours, dict) and isinstance(theirs, dict):
        if ours.keys() != theirs.keys():
            return [(_SHAPE, _SHAPE)]
        return [pair for key in ours for pair in leaves(ours[key], theirs[key])]
    if isinstance(ours, list) and isinstance(theirs, list):
        if len(ours) != len(theirs):
            return [(_SHAPE, _SHAPE)]
        return [
            pair for a, b in zip(ours, theirs, strict=True) for pair in leaves(a, b)
        ]
    if type(ours) is not type(theirs):
        return [(_SHAPE, _SHAPE)]
    return [] if equal(ours, theirs) else [(ours, theirs)]


def microdata_why(page: dict[str, Any], ours: Any, theirs: Any) -> str | None:
    """Each differing value explained, or None when one is not.

    On a page whose ``itemref`` names an element, the items themselves move,
    so every difference there is counted under itemref.
    """
    root = tree(page)
    ids = set(root.xpath("//@id"))
    if any(ref in ids for refs in root.xpath("//@itemref") for ref in refs.split()):
        return "`itemref`"
    base = next((b.strip() for b in root.xpath("//base/@href") if b.strip()), None)
    causes = set()
    for a, b in leaves(ours, theirs):
        if a is _SHAPE:
            return None
        if b == "" and a and root.xpath("//time[@itemprop][not(@datetime)]"):
            causes.add("`<time>` without `datetime`")
        elif a == "" and b == page["url"]:
            causes.add("an address attribute that is absent")
        elif base is not None and isinstance(a, str) and isinstance(b, str):
            causes.add("`<base href>`")
        else:
            return None
    return " and ".join(sorted(causes)) or None


def dublincore_why(page: dict[str, Any], ours: Any, theirs: Any) -> str | None:
    """ "not Dublin Core" when extruct's answer, less what is not, is sluicer's."""

    def is_dublin_core(element: dict[str, str], declared: set[str]) -> bool:
        name = element.get("name", element.get("rel", ""))
        prefix, dot, _rest = name.partition(".")
        return bool(dot) and prefix.strip().lower() in declared

    kept = []
    for obj in theirs:
        spaces = obj.get("namespaces", obj.get("@context")) or {}
        declared = {"dc", "dcterms"} | {key.strip().lower() for key in spaces}
        kept.append(
            {
                key: (
                    [e for e in value if is_dublin_core(e, declared)]
                    if key in ("elements", "terms")
                    else value
                )
                for key, value in obj.items()
            }
        )
    return "not Dublin Core" if equal(ours, kept) else None


SPECIFIC = {"microdata": microdata_why, "dublincore": dublincore_why}


def explain(syntax: str, page: dict[str, Any], ours: Any, theirs: Any) -> str:
    if _raised(theirs):
        return "extruct raises"
    specific = SPECIFIC.get(syntax)
    why = specific(page, ours, theirs) if specific else None
    if why:
        return why
    if _replaced_characters(page, ours, theirs):
        return "bytes that are not UTF-8"
    return "unexplained"


# --- the report --------------------------------------------------------------


def compare(
    found: list[dict[str, Any]], ours: dict[str, Any], theirs: dict[str, Any]
) -> dict[str, Any]:
    report: dict[str, Any] = {"syntax": {}, "uniform": {}, "default": Counter()}
    by_key = {page["key"]: page for page in found}
    for mode, names in (("syntax", SYNTAXES), ("uniform", UNIFORM)):
        for syntax in names:
            table: dict[str, Counter[str]] = {}
            examples: dict[str, list[str]] = {}
            for key, page in by_key.items():
                corpus = key.split("/", 1)[0]
                a = ours["pages"][key][mode][syntax]
                b = theirs["pages"][key][mode][syntax]
                counts = table.setdefault(corpus, Counter())
                if same(syntax, a, b):
                    counts["identical"] += 1
                    continue
                why = explain(syntax, page, a, b)
                counts[why] += 1
                examples.setdefault(why, []).append(key)
            report[mode][syntax] = {"counts": table, "examples": examples}
    for key in by_key:
        report["default"][
            key.split("/", 1)[0], theirs["pages"][key]["default"] == "ok"
        ] += 1
    return report


NAMES = {
    "json-ld": "JSON-LD",
    "microdata": "microdata",
    "opengraph": "OpenGraph",
    "rdfa": "RDFa",
    "microformat": "microformats",
    "dublincore": "Dublin Core",
}
START = "<!-- measured by bench/extruct_compat.py: start -->"
END = "<!-- measured by bench/extruct_compat.py: end -->"


def table(
    report: dict[str, Any],
    found: list[dict[str, Any]],
    ours: dict[str, Any],
    theirs: dict[str, Any],
) -> str:
    """The measured section of ``docs/extruct.md``."""
    totals = Counter(page["key"].split("/", 1)[0] for page in found)
    urls = {page["key"]: page["url"] or page["key"] for page in found}
    lines = [
        f"Measured with extruct {theirs['version']} on Python {PYTHON}, by "
        "`bench/extruct_compat.py`. A cell is the "
        "pages on which the two answers are identical, out of the pages in the "
        "corpus; for RDFa, the same graph.",
        "",
        "| syntax | " + " | ".join(CORPORA[c] for c in CORPORA) + " |",
        "|---|" + "---|" * len(CORPORA),
    ]
    for mode, prefix in (("syntax", ""), ("uniform", "uniform ")):
        for syntax, measured in report[mode].items():
            cells = [
                f"{measured['counts'].get(corpus, Counter())['identical']} / "
                f"{totals[corpus]}"
                for corpus in CORPORA
            ]
            lines.append(f"| {prefix}{NAMES[syntax]} | " + " | ".join(cells) + " |")
    failed = sum(
        1 for key in theirs["pages"] if theirs["pages"][key]["default"] != "ok"
    )
    ours_failed = sum(
        1 for key in ours["pages"] if ours["pages"][key].get("default") != "ok"
    )
    lines += [
        "",
        f"`extruct.extract(html, base_url=url)`, every argument else at its "
        f"default, raises on {failed} of the {len(found)} pages; sluicer's raises "
        f"on {ours_failed or 'none'}. {_speed(theirs['version'])}",
        "",
        "Every difference, by what explains it:",
        "",
        "| syntax | explained by | pages | who is right | for example |",
        "|---|---|---|---|---|",
    ]
    for syntax, measured in report["syntax"].items():
        for why, keys in measured["examples"].items():
            verdict = VERDICTS.get(why, "not yet explained")
            example = min(keys, key=lambda key: list(CORPORA).index(key.split("/")[0]))
            lines.append(
                f"| {NAMES[syntax]} | {why} | {len(keys)} | {verdict} | "
                f"{_short(urls[example])} |"
            )

    def declares(answer: dict[str, Any]) -> bool:
        found = answer["syntax"]["dublincore"]
        return isinstance(found, list) and any(
            o["elements"] or o["terms"] for o in found
        )

    theirs_dc = sum(declares(answer) for answer in theirs["pages"].values())
    ours_dc = sum(declares(answer) for answer in ours["pages"].values())
    lines += [
        "",
        f"extruct answers Dublin Core on {theirs_dc} of the {len(found)} pages; "
        f"{ours_dc} of them write a name under a Dublin Core prefix.",
        _uniform_sentence(report),
    ]
    return "\n".join(lines)


def _speed(version: str) -> str:
    """The same call's time on every page, from ``bench/timing.py``'s run of
    both, which is refused unless it is of this commit, these versions and
    this interpreter: it said the seconds of this script's own one pass."""
    import timing

    import sluicer

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8",
    ).stdout.strip()  # fmt: skip
    runs = {
        "extruct": {"version": version},
        "sluicer.compat.extruct": {"version": sluicer.__version__},
    }
    timing.published("extruct", runs, commit)
    record = timing.read("extruct")
    assert record is not None
    if record["python"] != PYTHON:
        raise SystemExit(
            f"refusing to print the extruct timing: it ran on Python "
            f"{record['python']}, this comparison on {PYTHON}"
        )
    median = {
        tool: timing.summary(timed, record["pages"])["median"]
        for tool, timed in record["tools"].items()
    }
    return (
        f"The same call over every page takes {median['extruct']:.1f} s in "
        f"extruct and {median['sluicer.compat.extruct']:.1f} s in sluicer, the "
        "median of five passes measured as [speed and weight](speed.md) says."
    )


def _uniform_sentence(report: dict[str, Any]) -> str:
    """Whether uniform mode differs where its syntax does, and for the same
    reasons, as this run found: it was written once and printed every run."""
    apart = [
        NAMES[syntax]
        for syntax, measured in report["uniform"].items()
        if measured["examples"] != report["syntax"][syntax]["examples"]
    ]
    if not apart:
        return (
            "Uniform mode differs on exactly the pages the syntax it reshapes "
            "differs on, for the same reasons."
        )
    return (
        "Uniform mode differs on other pages, or for other reasons, than the "
        f"syntax it reshapes, for {', '.join(apart)}."
    )


def _short(url: str) -> str:
    """An example's address, without its scheme and its query."""
    return re.sub(r"^https?://(www\.)?", "", url).split("?")[0]


def publish(section: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    before, found_start, rest = text.partition(START)
    _old, found_end, after = rest.partition(END)
    if not (found_start and found_end):
        raise SystemExit(f"{DOC} has lost its markers {START!r} and {END!r}")
    DOC.write_text(f"{before}{START}\n{section}\n{END}{after}", encoding="utf-8")


def show(report: dict[str, Any]) -> None:
    for mode in ("syntax", "uniform"):
        for syntax, measured in report[mode].items():
            print(f"== {mode} {syntax}")
            for corpus, counts in measured["counts"].items():
                print(f"   {corpus:9} {dict(counts)}")
            for why, keys in measured["examples"].items():
                print(f"   {why}: {', '.join(keys[:6])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reuse", action="store_true", help="reuse extruct's last run")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    found = pages()
    pages_file = CACHE / "pages.json"
    pages_file.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    theirs_file = CACHE / "extruct.json"
    if args.reuse and theirs_file.exists():
        theirs = json.loads(theirs_file.read_text(encoding="utf-8"))
    else:
        theirs = run_extruct(pages_file, theirs_file)
    ours = run_compat(found)
    (CACHE / "sluicer.json").write_text(json.dumps(ours), encoding="utf-8")
    report = compare(found, ours, theirs)
    show(report)
    unexplained = [
        key
        for mode in ("syntax", "uniform")
        for measured in report[mode].values()
        for key in measured["examples"].get("unexplained", [])
    ]
    publish(table(report, found, ours, theirs))
    print(f"wrote {DOC.relative_to(ROOT)}")
    if unexplained:
        raise SystemExit(f"{len(unexplained)} differences no test explains")


if __name__ == "__main__":
    main()
