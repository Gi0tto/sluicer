"""Sluicer's RDFa readers, and extruct's, against the W3C RDFa test suite.

    uv run bench/rdfa_conformance.py           # the suite, then docs/scoreboard-rdfa.md
    uv run bench/rdfa_conformance.py --reuse   # reuse extruct's last answers

The suite is the one rdfa.info runs, from ``rdfa/rdfa.github.io`` at one pinned
commit, distributed under both the W3C Test Suite License and the W3C 3-clause
BSD License (its ``test-suite/LICENSE.md``). It is downloaded into
``bench/cache/rdfa`` the first time and never committed here. Every test whose
host languages include HTML5 is run, once for each RDFa 1.1 version it is
listed under -- RDFa 1.1, RDFa 1.1 Lite, and the processor graph, vocabulary
expansion and role sets -- from that version's own copy of the document.

Three readers are handed the same bytes and the test's address:

- ``extract()``'s reader, ``sluicer.declared.rdfa.read_rdfa``, which reads RDFa
  Lite into records and not into a graph. Its records are written as triples
  by ``records_as_graph`` below, the way a caller would have to read them.
- ``sluicer.compat.extruct``'s, the processor that answers what extruct does.
- extruct itself, in an environment of its own holding exactly
  ``bench/requirements/extruct.txt``.

Each answer is written as expanded JSON-LD and the test's own SPARQL ASK query
is evaluated on it by rdflib, in an environment holding exactly
``bench/requirements/rdflib.txt``; a test passes when the query answers what
the manifest's ``expectedResults`` says. Each query is asked again with the
subjects it names by address replaced by variables, and each answer's values
are held against the test's expected graph, subjects aside, since the records
of ``extract()``'s reader name no subject (``bench/tools/rdfa_ask.py`` says
how). Nothing here is timed or sampled, so the same checkout gives the same
scoreboard.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
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
sys.path.insert(0, str(ROOT / "src"))

import sluicer  # noqa: E402 -- the checkout's own
from sluicer.compat import extruct as compat  # noqa: E402
from sluicer.declared.rdfa import read_rdfa  # noqa: E402
from sluicer.document import load  # noqa: E402

REPOSITORY = "rdfa/rdfa.github.io"
COMMIT = "b388107da8900b6f2a0c42d95ab468e6cf554a4a"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"
# The SHA-256 of every file kept from the archive, path and bytes, in path
# order: the archive's own bytes are GitHub's to recompress, the files are not.
DIGEST = "63732010e287f0fe55fe088d073e7cf5903e14b2b0315887ce25680804df0bb6"
CACHE = HERE / "cache" / "rdfa"
SUITE = CACHE / "suite"
DOC = ROOT / "docs" / "scoreboard-rdfa.md"
PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
BASE = "http://rdfa.info/test-suite/test-cases"
VERSIONS = ["rdfa1.1", "rdfa1.1-lite", "rdfa1.1-proc", "rdfa1.1-vocab", "rdfa1.1-role"]
READERS = ["sluicer", "compat", "extruct"]

# What the scoreboard reads from the archive.
_PREFIX = f"rdfa.github.io-{COMMIT}/test-suite/"
_WANTED = re.compile(
    r"(manifest\.jsonld|LICENSE\.md|test-cases/rdfa1\.1[a-z-]*/html5/.*)"
)


# --- the suite ---------------------------------------------------------------


def ensure() -> Path:
    """The suite's directory at the pinned commit, downloading it the first time."""
    marker = SUITE / "COMMIT"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == COMMIT:
        return SUITE
    if SUITE.exists():
        shutil.rmtree(SUITE)
    SUITE.mkdir(parents=True)
    archive = CACHE / f"rdfa.github.io-{COMMIT[:12]}.tar.gz"
    if not archive.exists():
        print(f"downloading the RDFa test suite at {COMMIT[:12]} (2 MB, once)")
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(ARCHIVE) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith(_PREFIX) or not member.isfile():
                continue
            relative = member.name[len(_PREFIX) :]
            if not _WANTED.fullmatch(relative):
                continue
            source = tar.extractfile(member)
            if source is not None:
                target = SUITE / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
    found = digest(SUITE)
    if found != DIGEST:
        raise SystemExit(f"the suite's files are not the pinned ones: {found}")
    marker.write_text(COMMIT + "\n", encoding="utf-8")
    return SUITE


def digest(folder: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.name != "COMMIT":
            hasher.update(str(path.relative_to(folder)).encode() + b"\0")
            hasher.update(path.read_bytes() + b"\0")
    return hasher.hexdigest()


def tests(suite: Path) -> list[dict[str, Any]]:
    """Every HTML5 test, once for each RDFa 1.1 version it is listed under."""
    manifest = json.loads((suite / "manifest.jsonld").read_text(encoding="utf-8"))
    found = []
    for entry in manifest["@graph"]:
        if "html5" not in entry["hostLanguages"]:
            continue
        for version in VERSIONS:
            if version not in entry["versions"]:
                continue
            num = entry["num"]
            folder = suite / "test-cases" / version / "html5"
            found.append(
                {
                    "key": f"{version}/{num}",
                    "version": version,
                    "num": num,
                    "description": entry["description"],
                    "option": entry.get("queryParam") or None,
                    "expected": entry["expectedResults"],
                    "path": str(folder / f"{num}.html"),
                    "query": str(folder / f"{num}.sparql"),
                    "graph": str(folder / f"{num}.ttl"),
                    "url": f"{BASE}/{version}/html5/{num}.html",
                }
            )
    return found


# The feature a test is filed under: the first of these its document uses, in
# this order, so that a test of chaining with a datatype is filed under the
# datatype. A test asking for a processor option is filed under the option.
FEATURES = [
    ("processor graph", lambda t, h: "rdfagraph" in (t["option"] or "")),
    ("vocabulary expansion", lambda t, h: "vocab_expansion" in (t["option"] or "")),
    ("`role`", lambda t, h: re.search(r"\srole\s*=", h)),
    ("property copying (`rdfa:copy`)", lambda t, h: "rdfa:copy" in h),
    ("lists (`inlist`)", lambda t, h: re.search(r"\sinlist\b", h)),
    ("`<time>`", lambda t, h: "<time" in h),
    ("datatypes (`datatype`)", lambda t, h: re.search(r"\sdatatype\s*=", h)),
    ("languages (`lang`)", lambda t, h: re.search(r"\s(xml:)?lang\s*=", h)),
    ("`<base>`", lambda t, h: "<base" in h),
    ("reverse links (`rev`)", lambda t, h: re.search(r"\srev\s*=", h)),
    ("links and chaining (`rel`)", lambda t, h: re.search(r"\srel\s*=", h)),
    ("explicit subjects (`about`)", lambda t, h: re.search(r"\sabout\s*=", h)),
    ("`vocab` and `prefix`", lambda t, h: re.search(r"\s(vocab|prefix)\s*=", h)),
    ("`typeof` and `resource`", lambda t, h: re.search(r"\s(typeof|resource)\s*=", h)),
    ("`property` alone", lambda t, h: True),
]


def feature(test: dict[str, Any]) -> str:
    html = Path(test["path"]).read_text(encoding="utf-8", errors="replace")
    return next(name for name, uses in FEATURES if uses(test, html))


# --- the readers -------------------------------------------------------------

SCHEMA_ORG = "http://schema.org/"
# An address as the records write it: a scheme and `//`, or a scheme that
# never has one. The records do not say whether a value was an address or
# text, so this is the guess a caller has to make, made the same every time.
_ADDRESS = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S*|(urn|mailto|tel):\S+")


def records_as_graph(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``read_rdfa``'s records as expanded JSON-LD, one blank node per record.

    A name without a scheme is a schema.org term, since that is the one
    vocabulary the reader names short; a record inside another is the other's
    value, as a node of its own.
    """
    nodes: list[dict[str, Any]] = []

    def iri(name: str) -> str:
        return name if "://" in name else SCHEMA_ORG + name

    def node(record: dict[str, Any]) -> str:
        label = f"_:r{len(nodes)}"
        out: dict[str, Any] = {"@id": label}
        nodes.append(out)
        for key, declared in record.items():
            values = declared if isinstance(declared, list) else [declared]
            if key == "@type":
                out["@type"] = [iri(value) for value in values]
                continue
            objects = out.setdefault(iri(key), [])
            for value in values:
                if isinstance(value, dict):
                    objects.append({"@id": node(value)})
                elif _ADDRESS.fullmatch(value):
                    objects.append({"@id": value})
                else:
                    objects.append({"@value": value})
        return label

    for record in records:
        node(record)
    return nodes


def run_sluicer(found: list[dict[str, Any]]) -> dict[str, Any]:
    answers: dict[str, Any] = {"sluicer": {}, "compat": {}}
    for test in found:
        html = Path(test["path"]).read_bytes()
        for reader, read in (("sluicer", _records), ("compat", _compat)):
            answers[reader][test["key"]] = attempt(read, html, test["url"])
    return answers


def _records(html: bytes, url: str) -> list[dict[str, Any]]:
    return records_as_graph(read_rdfa(load(html, url=url)))


def _compat(html: bytes, url: str) -> Any:
    return compat.extract(html, base_url=url, syntaxes=["rdfa"])["rdfa"]


def attempt(read: Any, html: bytes, url: str) -> Any:
    try:
        return json.loads(json.dumps(read(html, url)))
    except Exception as error:  # noqa: BLE001 -- what a reader raised is its answer
        return {"__error__": f"{type(error).__name__}: {error}"}


def in_environment(requirements: str, tool: str, *args: Path) -> None:
    command = [
        "uv", "run", "--no-project", "--python", PYTHON,
        "--with-requirements", str(HERE / "requirements" / requirements),
        "python", str(HERE / "tools" / tool), *map(str, args),
    ]  # fmt: skip
    subprocess.run(command, cwd=ROOT, check=True)


# --- the run -----------------------------------------------------------------


def measure(reuse: bool) -> dict[str, Any]:
    suite = ensure()
    found = tests(suite)
    tests_file = CACHE / "tests.json"
    tests_file.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    theirs_file = CACHE / "extruct.json"
    if not (reuse and theirs_file.exists()):
        in_environment("extruct.txt", "rdfa_extruct_tool.py", tests_file, theirs_file)
    theirs = json.loads(theirs_file.read_text(encoding="utf-8"))
    answers = run_sluicer(found)
    answers["extruct"] = theirs["answers"]
    answers_file = CACHE / "answers.json"
    answers_file.write_text(json.dumps(answers), encoding="utf-8")
    results_file = CACHE / "results.json"
    in_environment("rdflib.txt", "rdfa_ask.py", tests_file, answers_file, results_file)
    asked = json.loads(results_file.read_text(encoding="utf-8"))
    named = set(asked["names_a_subject"])
    for test in found:
        test["feature"] = feature(test)
        test["results"] = {
            reader: asked["results"][reader][test["key"]] for reader in READERS
        }
        test["passed"] = {
            reader: test["results"][reader] is test["expected"] for reader in READERS
        }
        test["names_a_subject"] = test["key"] in named
        test["values"] = {
            reader: asked["values"][reader][test["key"]] for reader in READERS
        }
        # The query with its named subjects taken out, where it named any;
        # otherwise the suite's own, whose answer stands.
        test["unnamed"] = {
            reader: (
                asked["unnamed"][reader][test["key"]] is True
                if test["key"] in named
                else test["passed"][reader]
            )
            for reader in READERS
        }
    return {
        "tests": found,
        "extruct": theirs["version"],
        "rdflib": asked["rdflib"],
        "sluicer": sluicer.__version__,
    }


# --- the scoreboard ----------------------------------------------------------

NAMES = {
    "sluicer": "Sluicer's reader",
    "compat": "`sluicer.compat.extruct`",
    "extruct": "extruct",
}
SETS = {
    "rdfa1.1": "RDFa 1.1",
    "rdfa1.1-lite": "RDFa 1.1 Lite",
    "rdfa1.1-proc": "processor graph",
    "rdfa1.1-vocab": "vocabulary expansion",
    "rdfa1.1-role": "`role`",
}
# What ``read_rdfa`` does not read, on purpose, as ``docs/known-limits.md``
# says: the features a test is filed under that no fix in the reader is owed.
NOT_READ = {
    "processor graph": "an option no reader here takes",
    "vocabulary expansion": "an option no reader here takes",
    "`role`": "`role` is not RDFa Lite",
    "property copying (`rdfa:copy`)": "property copying is not read",
    "lists (`inlist`)": "`inlist` is not RDFa Lite",
    "`<time>`": "typed literals are not read",
    "datatypes (`datatype`)": "typed literals are not read",
    "languages (`lang`)": "languages are not read",
    "reverse links (`rev`)": "`rev` is not RDFa Lite",
    "links and chaining (`rel`)": "`rel` links are not read",
    "explicit subjects (`about`)": "`about` is not RDFa Lite",
}


def why_sluicer_fails(test: dict[str, Any]) -> str:
    """Why ``read_rdfa`` fails a test, first reason first."""
    if test["option"]:
        return "an option no reader here takes"
    if test["feature"] in NOT_READ:
        return NOT_READ[test["feature"]]
    if not re.search(r"\stypeof\s*=", Path(test["path"]).read_text(encoding="utf-8")):
        return "no `typeof`, so no record"
    if test["names_a_subject"] and test["unnamed"]["sluicer"]:
        return "records name no subject"
    if test["names_a_subject"]:
        return "records name no subject, and more is missing"
    return "not explained"


def scoreboard(run: dict[str, Any], commit: str, today: str) -> str:
    tests = run["tests"]
    header = (
        f"| set | tests | {NAMES['sluicer']} | {NAMES['compat']} | "
        f"extruct {run['extruct']} |"
    )
    lines = [
        "# RDFa, against the W3C test suite",
        "",
        "Sluicer's two RDFa readers, and extruct's, on the RDFa test suite the "
        "W3C's RDFa working group wrote and [rdfa.info](https://rdfa.info/test-suite/) "
        "runs: every test written for HTML5, each document handed to each reader, "
        "each answer read into a graph and asked the test's own SPARQL query.",
        "",
        "- **Sluicer's reader** is `extract()`'s, `sluicer.declared.rdfa`: RDFa "
        "Lite read into records, one per `typeof`, which name no subject and "
        "hold text and addresses, not a graph. Its records are written as "
        "triples the way a caller has to read them: each record a blank node, a "
        "short name a schema.org term, a value that begins with a scheme an "
        "address.",
        "- **`sluicer.compat.extruct`** is the processor that answers what "
        "extruct answers, graph and all.",
        f"- **extruct {run['extruct']}**, in an environment holding exactly "
        "`bench/requirements/extruct.txt`, with "
        '`extract(html, base_url=url, syntaxes=["rdfa"])`.',
        "",
        "What `extract()`'s reader leaves out on purpose -- links, `about`, "
        "typed literals, languages, the page as a subject -- is in "
        "[Known limits](known-limits.md); every test it fails is filed below "
        "under one of those, or listed as not explained.",
        "",
        f"Regenerated on {today} from commit `{commit}` by "
        "`uv run bench/rdfa_conformance.py`, with Sluicer "
        f"{run['sluicer']}, extruct {run['extruct']} and rdflib {run['rdflib']} "
        f"on Python {PYTHON}, against the suite at `{COMMIT[:12]}` of "
        f"[`{REPOSITORY}`](https://github.com/{REPOSITORY}), which is "
        "distributed under both the W3C Test Suite License and the W3C 3-clause "
        "BSD License. A test passes when its query answers what the suite "
        "expects.",
        "",
        header,
        "|---|---|---|---|---|",
    ]
    for version, name in SETS.items():
        rows = [t for t in tests if t["version"] == version]
        cells = [str(sum(t["passed"][r] for t in rows)) for r in READERS]
        lines.append(f"| {name} | {len(rows)} | " + " | ".join(cells) + " |")
    raised = sorted(
        t["key"]
        for t in tests
        if isinstance(t["results"]["extruct"], str)
        and t["results"]["extruct"].startswith("raised")
    )
    ours_raised = [
        t["key"]
        for t in tests
        for r in ("sluicer", "compat")
        if isinstance(t["results"][r], str)
    ]
    lines += [
        "",
        f"extruct raises on {len(raised)} of the {len(tests)} documents"
        + (f" ({', '.join(raised)})" if raised else "")
        + "; each is counted as failed. Sluicer's readers raise on "
        + (f"{len(ours_raised)}." if ours_raised else "none."),
        "",
    ]
    lines += _values_section(tests)
    lines += _unnamed_section(tests)
    lines += _feature_section(tests)
    lines += _losses_section(tests)
    lines += _every_test(tests)
    return "\n".join(lines) + "\n"


def _values_section(tests: list[dict[str, Any]]) -> list[str]:
    """Each reader's values against the tests' expected graphs, subjects aside."""
    held = [t for t in tests if not t["option"] and t["values"]["sluicer"] is not None]
    broken = [t for t in tests if not t["option"] and t["values"]["sluicer"] is None]
    lines = [
        "## Values, subjects aside",
        "",
        "Each answer held against the graph the suite expects, its `.ttl`, "
        "subjects aside: every triple is a predicate and a value -- a "
        "literal's words, spaces collapsed, its type and language left out; an "
        "address; or a node, for a resource the graph describes -- and a value "
        "is right when the expected graph has it, wrong when it does not, and "
        "missing when only the expected graph has it. `rdfa:usesVocabulary` is "
        "left out, and so are the tests asking for an option"
        + (
            " and the "
            + str(len(broken))
            + " whose expected graph rdflib cannot parse ("
            + ", ".join(_ref(t) for t in broken)
            + ")"
            if broken
            else ""
        )
        + ".",
        "",
        "| set | tests | reader | right | wrong | missing |",
        "|---|---|---|---|---|---|",
    ]
    for version, name in SETS.items():
        rows = [t for t in held if t["version"] == version]
        if not rows:
            continue
        for reader in READERS:
            right = sum(t["values"][reader]["right"] for t in rows)
            wrong = sum(len(t["values"][reader]["wrong"]) for t in rows)
            missing = sum(t["values"][reader]["missing"] for t in rows)
            lines.append(
                f"| {name} | {len(rows)} | {NAMES[reader]} | {right} | {wrong} | "
                f"{missing} |"
            )
    lines += ["", "Every wrong value, by reader:", ""]
    wrong = {
        reader: [(t, value) for t in held for value in t["values"][reader]["wrong"]]
        for reader in READERS
    }
    same = [(t["key"], v) for t, v in wrong["compat"]] == [
        (t["key"], v) for t, v in wrong["extruct"]
    ]
    groups = (
        [
            (NAMES["sluicer"], "sluicer"),
            (f"{NAMES['compat']} and extruct, alike", "compat"),
        ]
        if same
        else [(NAMES[reader], reader) for reader in READERS]
    )
    for name, reader in groups:
        listed = "; ".join(
            f"{_ref(t)} `{_short_iri(value[0])}` {_value_text(value)}"
            for t, value in wrong[reader]
        )
        lines.append(f"- {name}: " + (listed or "none") + ".")
    return [*lines, ""]


def _short_iri(iri: str) -> str:
    return re.split(r"[#/]", iri.rstrip("/#"))[-1] or iri


def _value_text(value: list[str]) -> str:
    kind = value[1]
    if kind == "node":
        return "a node"
    shown = value[2] if len(value[2]) <= 60 else value[2][:57] + "..."
    return f"`{shown}`" if kind == "text" else f"<{shown}>"


def _unnamed_section(tests: list[dict[str, Any]]) -> list[str]:
    asked = [t for t in tests if t["expected"] is True and t["names_a_subject"]]
    strict = sum(t["passed"]["sluicer"] for t in asked)
    relaxed = sum(t["unnamed"]["sluicer"] for t in asked)
    others = ", ".join(
        f"{NAMES[r]} {sum(t['unnamed'][r] for t in asked)}"
        for r in ("compat", "extruct")
    )
    return [
        "## With the subjects' names set aside",
        "",
        f"{len(asked)} of the {len(tests)} runs ask for a subject by its "
        "address -- the document's, an `about`, a `resource` -- which Sluicer's "
        "records never "
        f"carry, so its reader passes {strict} of them. Asked again with each "
        "address in a subject's place replaced by a variable, the same address "
        "by the same variable, and nothing else changed, it passes "
        f"{relaxed}; {others}.",
        "",
    ]


def _feature_section(tests: list[dict[str, Any]]) -> list[str]:
    """Pass counts by feature, every set together."""
    lines = [
        "## By feature",
        "",
        "Each test is filed under the first of these its document uses, so a "
        "test of chaining with a datatype is under datatypes. Sluicer's column "
        "counts the suite's queries; in brackets, the same with the subjects' "
        "names set aside.",
        "",
        "| feature | runs | Sluicer's reader | `compat.extruct` | extruct | "
        "Sluicer's reader does not read it |",
        "|---|---|---|---|---|---|",
    ]
    order = [name for name, _uses in FEATURES]
    for name in order:
        rows = [t for t in tests if t["feature"] == name]
        if not rows:
            continue
        ours = sum(t["passed"]["sluicer"] for t in rows)
        unnamed = sum(t["unnamed"]["sluicer"] for t in rows)
        cells = [f"{ours} ({unnamed})"] + [
            str(sum(t["passed"][r] for t in rows)) for r in ("compat", "extruct")
        ]
        why = NOT_READ.get(name, "")
        lines.append(f"| {name} | {len(rows)} | " + " | ".join(cells) + f" | {why} |")
    return [*lines, ""]


def _losses_section(tests: list[dict[str, Any]]) -> list[str]:
    lines = ["## Losses", ""]
    compat_only = [
        t for t in tests if t["passed"]["extruct"] and not t["passed"]["compat"]
    ]
    extruct_only = [
        t for t in tests if t["passed"]["compat"] and not t["passed"]["extruct"]
    ]
    lines += [
        f"`sluicer.compat.extruct` fails {len(compat_only)} test"
        f"{'' if len(compat_only) == 1 else 's'} extruct passes"
        + (": " + ", ".join(_ref(t) for t in compat_only) if compat_only else "")
        + f", and passes {len(extruct_only)} extruct fails"
        + (": " + ", ".join(_ref(t) for t in extruct_only) if extruct_only else "")
        + ". "
        + _both_fail_sentence(tests),
        "",
    ]
    failed = [t for t in tests if not t["passed"]["sluicer"]]
    reasons = Counter(why_sluicer_fails(t) for t in failed)
    lines += [
        f"Sluicer's reader fails {len(failed)} of the {len(tests)} runs, first "
        "reason first:",
        "",
        "| why | runs |",
        "|---|---|",
    ]
    lines += [f"| {why} | {n} |" for why, n in reasons.most_common()]
    unexplained = [t for t in failed if why_sluicer_fails(t) == "not explained"]
    lines += [
        "",
        "Not explained by what the reader leaves out on purpose: "
        + (", ".join(_ref(t) for t in unexplained) if unexplained else "none")
        + ".",
        "",
    ]
    return lines


def _both_fail_sentence(tests: list[dict[str, Any]]) -> str:
    """Whether, where both fail, the two answered the same values, as the run
    found."""
    both = [
        t
        for t in tests
        if not t["passed"]["compat"]
        and not t["passed"]["extruct"]
        and t["values"]["compat"] is not None
    ]
    apart = [t for t in both if t["values"]["compat"] != t["values"]["extruct"]]
    if not apart:
        return (
            f"On the {len(both)} runs both fail, the two give the same values, "
            "right, wrong and missing."
        )
    return (
        f"On {len(apart)} of the {len(both)} runs both fail, the two give "
        "different values: " + ", ".join(_ref(t) for t in apart) + "."
    )


def _ref(test: dict[str, Any]) -> str:
    return f"{test['num']} ({SETS[test['version']]})"


def _every_test(tests: list[dict[str, Any]]) -> list[str]:
    mark = {True: "pass", False: "**fail**"}
    lines = [
        "## Every test",
        "",
        "| set | test | feature | what it tests | Sluicer's reader | "
        "`compat.extruct` | extruct |",
        "|---|---|---|---|---|---|---|",
    ]
    for test in tests:
        description = " ".join(test["description"].split()).replace("|", "\\|")
        lines.append(
            f"| {SETS[test['version']]} | {test['num']} | {test['feature']} | "
            f"{description} | "
            + " | ".join(mark[test["passed"][r]] for r in READERS)
            + " |"
        )
    return lines


def show(run: dict[str, Any]) -> None:
    for version in VERSIONS:
        rows = [t for t in run["tests"] if t["version"] == version]
        counts = Counter(r for t in rows for r in READERS if t["passed"][r])
        print(f"{version:14} {len(rows):4} " + " ".join(
            f"{r}={counts[r]}" for r in READERS))  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reuse", action="store_true", help="reuse extruct's answers")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    run = measure(args.reuse)
    (CACHE / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    show(run)
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()  # fmt: skip
    DOC.write_text(
        scoreboard(run, commit, datetime.date.today().isoformat()), encoding="utf-8"
    )
    print(f"wrote {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
