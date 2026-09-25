# /// script
# requires-python = ">=3.10"
# dependencies = ["lxml>=5.3", "click>=8.2", "mf2py==2.0.2"]
# ///
"""What pages declare about themselves, counted on a sample of Common Crawl.

    .venv/bin/python bench/declared_report.py --pin          # choose, download
    .venv/bin/python bench/declared_report.py                # count, report
    .venv/bin/python bench/declared_report.py --report-only  # report the counts

What the sample is, what a page is and what is counted were fixed in
``bench/PREREG.md`` before a WARC was downloaded. ``--pin`` applies the rule
written there to the crawl's listing, downloads the four files it names into
``bench/commoncrawl/`` (ignored, never committed), and writes their paths,
sizes and SHA-256 into ``bench/declared-manifest.json``. A plain run
downloads whatever the manifest pins and is missing, stops if a file does not
hash to its pin, reads every page through ``sluicer.warc`` and
``sluicer.extract``, writes the counts to ``bench/declared-counts.json`` and
the report, ``docs/state-of-declared-data.md``, from them alone.

Run from the checkout's own environment, so the Sluicer counted is this one.
The counts are the same on every run: the files are read whole, in order,
each in a process of its own, and summed.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import importlib.metadata
import ipaddress
import json
import math
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

# The checkout's own Sluicer, whatever is installed. ``_extract_document`` is
# ``extract`` on a page already parsed, so each page is parsed once and its
# JSON-LD blocks read from the same tree; ``_parse`` is the lenient reading
# of one block, which the report counts beside the strict one.
import lxml.etree  # noqa: E402

import sluicer  # noqa: E402
from sluicer.api import Extraction, _extract_document  # noqa: E402
from sluicer.declared.headers import charset, lowered  # noqa: E402
from sluicer.declared.jsonld import _is_ld_json, _parse  # noqa: E402
from sluicer.declared.merge import ABOUT_A_THING  # noqa: E402
from sluicer.declared.opengraph import read_opengraph  # noqa: E402
from sluicer.declared.twitter import read_twitter  # noqa: E402
from sluicer.declared.types import type_name  # noqa: E402
from sluicer.document import Document, load  # noqa: E402
from sluicer.summary import FIELDS  # noqa: E402
from sluicer.warc import Skipped, WarcError, WarcPage, read_warc  # noqa: E402

CRAWL = "CC-MAIN-2026-39"
DATA = "https://data.commoncrawl.org/"
LISTING = f"crawl-data/{CRAWL}/warc.paths.gz"
FILES = 4
DOWNLOADS = HERE / "commoncrawl"
MANIFEST = HERE / "declared-manifest.json"
COUNTS = HERE / "declared-counts.json"
REPORT = ROOT / "docs" / "state-of-declared-data.md"
USER_AGENT = (
    "sluicer-bench/1.0 (+https://github.com/Gi0tto/sluicer/tree/main/bench; "
    "counts declared data on a few Common Crawl WARC files, one at a time)"
)
# Waits before each retry, in seconds: Common Crawl answers 503 when asked
# too fast, and the answer is to ask more slowly.
_BACKOFF = (10, 30, 60, 120, 300)
_BETWEEN_FILES = 10
_CHUNK = 1024 * 1024


# -- the sample ----------------------------------------------------------------


def picked(lines: list[str], files: int = FILES) -> list[str]:
    """The listing's lines at the middle of each of ``files`` equal parts.

    ``bench/PREREG.md``'s rule: with N lines, index ⌊(2k+1)·N/(2·files)⌋ for
    k = 0 .. files-1. Position alone, so no file is chosen for what it holds.
    """
    n = len(lines)
    return [lines[(2 * k + 1) * n // (2 * files)] for k in range(files)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def download(path: str, into: Path) -> Path:
    """``path`` on data.commoncrawl.org, saved under ``into``, once.

    Written to a ``.part`` file and renamed when whole, so an interrupted
    download is never taken for a file. Retried with backoff on 503, 429 and
    other 5xx answers and on a connection that breaks.
    """
    target = into / path
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    last = "no attempt"
    for attempt in range(len(_BACKOFF) + 1):
        if attempt:
            time.sleep(_BACKOFF[attempt - 1])
        request = urllib.request.Request(
            DATA + path, headers={"User-Agent": USER_AGENT}
        )
        try:
            with (
                urllib.request.urlopen(request, timeout=120) as answer,
                partial.open("wb") as out,
            ):
                while block := answer.read(_CHUNK):
                    out.write(block)
        except urllib.error.HTTPError as error:
            last = f"HTTP {error.code}"
            if error.code == 429 or error.code >= 500:
                continue
            raise SystemExit(f"{DATA}{path}: {last}") from None
        except OSError as error:
            last = type(error).__name__
            continue
        partial.rename(target)
        return target
    raise SystemExit(f"{DATA}{path}: {last} after {len(_BACKOFF) + 1} attempts")


def pin() -> dict[str, Any]:
    """Apply PREREG's rule to the listing, download the files, write the pins."""
    listing = download(LISTING, DOWNLOADS)
    lines = gzip.decompress(listing.read_bytes()).decode().split()
    chosen = picked(lines)
    files = []
    for n, path in enumerate(chosen):
        if n:
            time.sleep(_BETWEEN_FILES)
        print(f"downloading {path}", file=sys.stderr, flush=True)
        local = download(path, DOWNLOADS)
        files.append(
            {
                "index": lines.index(path),
                "path": path,
                "bytes": local.stat().st_size,
                "sha256": sha256(local),
            }
        )
    manifest = {
        "crawl": CRAWL,
        "listing": {
            "path": LISTING,
            "lines": len(lines),
            "sha256": sha256(listing),
        },
        "rule": "index floor((2k+1)*N/8), k = 0..3, in the listing's order",
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def ensure(manifest: dict[str, Any]) -> list[Path]:
    """The pinned files, downloaded when missing; stops on a hash that differs."""
    paths = []
    for n, pinned in enumerate(manifest["files"]):
        local = DOWNLOADS / pinned["path"]
        if not local.exists():
            if n:
                time.sleep(_BETWEEN_FILES)
            print(f"downloading {pinned['path']}", file=sys.stderr, flush=True)
            local = download(pinned["path"], DOWNLOADS)
        found = sha256(local)
        if found != pinned["sha256"]:
            raise SystemExit(
                f"{local} hashes to {found}, not its pin {pinned['sha256']}"
            )
        paths.append(local)
    return paths


# -- the intervals ---------------------------------------------------------------

# The 97.5th percentile of the normal distribution, for a 95% interval.
_Z = 1.959963984540054


def wilson(k: int, n: int, z: float = _Z) -> tuple[float, float] | None:
    """The Wilson score interval of ``k`` in ``n``, or None when ``n`` is 0.

    Wilson's rather than the normal approximation's, which leaves [0, 1] and
    collapses to a point at 0 and at n. Written here rather than shared: a
    ``bench/stats.py`` may arrive with the paired bootstrap PREREG plans, and
    this one helper should then move there.
    """
    if n <= 0:
        return None
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    # At 0 and at n the bound is exactly 0 or 1; rounding would leave a hair.
    low = 0.0 if k == 0 else max(0.0, centre - half)
    high = 1.0 if k == n else min(1.0, centre + half)
    return low, high


# -- the counting ----------------------------------------------------------------

# Sluicer's readers, in its order of precedence, and the names the report
# gives them.
READERS = {
    "jsonld": "JSON-LD",
    "microdata": "microdata",
    "microformats": "microformats",
    "rdfa": "RDFa",
    "dublincore": "Dublin Core",
    "opengraph": "OpenGraph",
    "twitter": "Twitter card",
    "html": "HTML meta names",
}
# The summary's questions whose answers ``Extraction.normalised`` reads.
NORMALISED = (
    "published",
    "modified",
    "price",
    "price_regular",
    "price_low",
    "price_high",
    "currency",
    "gtin",
)
_DATES = frozenset({"published", "modified"})
_PRICES = frozenset({"price", "price_regular", "price_low", "price_high"})
_GTIN_LENGTHS = frozenset({8, 12, 13, 14})
_PAGE_TITLE = "//title[not(ancestor::svg or ancestor::math)]"
_LONGEST_SHAPE = 32
_PROGRESS = 5_000


class _Refused(ValueError):
    """NaN or Infinity, which JSON does not have."""


def _refuse(name: str) -> None:
    raise _Refused(name)


def shape(text: str) -> str:
    """``text`` with every digit written 9 and every letter a, cut short."""
    return "".join(
        "9" if c.isdecimal() else "a" if c.isalpha() else c
        for c in " ".join(text.split())[:_LONGEST_SHAPE]
    )


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _top_level_domain(host: str) -> str:
    if not host:
        return "(no host)"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host.rsplit(".", 1)[-1]
    return "(an address)"


def _typed(value: object) -> Iterator[list[str]]:
    """The types of every typed object in a parsed JSON-LD block, nested ones too."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(reversed(item))
        elif isinstance(item, dict):
            declared = item.get("@type")
            names = declared if isinstance(declared, list) else [declared]
            found = [
                name
                for text in names
                if isinstance(text, str) and (name := type_name(text)) is not None
            ]
            if found:
                yield list(dict.fromkeys(found))
            pending.extend(reversed(list(item.values())))


def _block_kind(raw: str) -> tuple[str, object | None]:
    """How far one JSON-LD block is from JSON, and what Sluicer reads of it."""
    try:
        json.loads(raw, parse_constant=_refuse)
        kind = "valid"
    except (ValueError, RecursionError):
        try:
            json.loads(raw, strict=False, parse_constant=_refuse)
            kind = "control_characters"
        except (ValueError, RecursionError):
            kind = "recovered"
    parsed = _parse(raw)
    if parsed is None:
        return "lost", None
    return kind, parsed


def _normalised_text(text: str) -> str:
    return " ".join(text.split()).casefold()


@dataclass
class Tally:
    """Every count the report is written from, for one file or several summed.

    Counters and sets only, so two tallies sum in any order to the same one.
    """

    pages: int = 0
    truncated: int = 0
    failed: Counter[str] = field(default_factory=Counter)
    left_out: Counter[str] = field(default_factory=Counter)
    hosts: set[str] = field(default_factory=set)
    top_level_domains: Counter[str] = field(default_factory=Counter)
    vocabularies: Counter[str] = field(default_factory=Counter)
    vocabulary_hosts: dict[str, set[str]] = field(default_factory=dict)
    any: Counter[str] = field(default_factory=Counter)
    any_hosts: dict[str, set[str]] = field(default_factory=dict)
    combinations: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    jsonld_typed: int = 0
    jsonld_classes: Counter[str] = field(default_factory=Counter)
    merging: Counter[str] = field(default_factory=Counter)
    folded_by: Counter[str] = field(default_factory=Counter)
    answered: Counter[str] = field(default_factory=Counter)
    conflicting: Counter[str] = field(default_factory=Counter)
    between: dict[str, Counter[str]] = field(default_factory=dict)
    titles: Counter[str] = field(default_factory=Counter)
    blocks: Counter[str] = field(default_factory=Counter)
    read: Counter[str] = field(default_factory=Counter)
    unread_shapes: dict[str, Counter[str]] = field(default_factory=dict)
    gtin: Counter[str] = field(default_factory=Counter)
    links: Counter[str] = field(default_factory=Counter)
    rights: Counter[str] = field(default_factory=Counter)
    directives: dict[str, Counter[str]] = field(default_factory=dict)

    def add(self, page: WarcPage) -> None:
        """Count one page, or the reason it could not be read."""
        sent = lowered(page.headers)
        try:
            doc = load(page.body, url=page.url or None, charset=charset(sent))
            found = _extract_document(doc, sent, microformats=True)
            self._count(page, doc, found)
        except Exception as error:  # noqa: BLE001 -- counted, never dropped
            self.failed[type(error).__name__] += 1

    def _count(self, page: WarcPage, doc: Document, found: Extraction) -> None:
        # Everything is worked out before anything is counted, so a page that
        # fails halfway is in ``failed`` and nowhere else.
        blocks = [_block_kind(raw) for raw in _jsonld_blocks(doc)]
        titles = _titles(doc, found)
        host = _host(page.url)
        self.pages += 1
        self.truncated += bool(page.truncated)
        self.hosts.add(host)
        self.top_level_domains[_top_level_domain(host)] += 1
        self._vocabularies(found, host)
        self._types(found)
        self._jsonld(blocks)
        self._conflicts(found, titles)
        self._normalised(found)
        self._links(page, found)
        self._rights(found)

    def _vocabularies(self, found: Extraction, host: str) -> None:
        for source in found.sources:
            self.vocabularies[source] += 1
            self.vocabulary_hosts.setdefault(source, set()).add(host)
        about_things = [s for s in found.sources if s in ABOUT_A_THING]
        kinds = ["anything"] if found.sources else ["nothing"]
        if about_things:
            kinds.append("about_things")
        for kind in kinds:
            self.any[kind] += 1
            self.any_hosts.setdefault(kind, set()).add(host)
        self.combinations[" + ".join(found.sources) or "(nothing)"] += 1
        if about_things:
            self.merging["pages_with_things"] += 1
        if len(about_things) > 1:
            self.merging["several_vocabularies"] += 1
        folds = set()
        for record in found.records:
            sources = [
                s
                for s in dict.fromkeys(f.source for f in record.fields.values())
                if s in ABOUT_A_THING
            ]
            if len(sources) > 1:
                order = list(READERS)
                folds.add(" + ".join(sorted(sources, key=order.index)))
        if folds:
            self.merging["folded"] += 1
            self.folded_by.update(folds)

    def _types(self, found: Extraction) -> None:
        self.types.update(
            {
                name
                for record in found.records
                if record.source in ABOUT_A_THING
                for name in record.types
            }
        )

    def _jsonld(self, blocks: list[tuple[str, object | None]]) -> None:
        if not blocks:
            return
        self.blocks["pages"] += 1
        self.blocks["blocks"] += len(blocks)
        kinds = Counter(kind for kind, _ in blocks)
        self.blocks.update(kinds)
        if kinds["valid"] < len(blocks):
            self.blocks["pages_with_invalid"] += 1
        if kinds["lost"]:
            self.blocks["pages_losing_one"] += 1
        for _, parsed in blocks:
            for names in _typed(parsed):
                self.jsonld_typed += 1
                self.jsonld_classes.update(names)

    def _conflicts(self, found: Extraction, titles: list[str]) -> None:
        self.answered.update(found.summary.keys())
        for conflict in found.conflicts:
            self.conflicting[conflict.question] += 1
            first, other = conflict.answers[0], conflict.answers[1]
            pair = f"{first.source} / {other.source}"
            self.between.setdefault(conflict.question, Counter())[pair] += 1
        if found.conflicts:
            self.conflicting["(any)"] += 1
        if len(titles) > 1:
            self.titles["declared_twice"] += 1
            distinct = list(dict.fromkeys(titles))
            if len(distinct) > 1:
                self.titles["differ"] += 1
                if any(
                    one not in other and other not in one
                    for n, one in enumerate(distinct)
                    for other in distinct[n + 1 :]
                ):
                    self.titles["differ_beyond_containment"] += 1

    def _normalised(self, found: Extraction) -> None:
        for question in NORMALISED:
            answer = found.summary.get(question)
            if answer is None:
                continue
            if question in found.normalised:
                self.read[question] += 1
            elif question in _DATES or question in _PRICES:
                family = "date" if question in _DATES else "price"
                shapes = self.unread_shapes.setdefault(family, Counter())
                shapes[shape(answer.value)] += 1
        answer = found.summary.get("gtin")
        if answer is not None:
            self.gtin["answered"] += 1
            digits = re.sub(r"[\s-]", "", answer.value)
            if not digits.isdecimal() or len(digits) not in _GTIN_LENGTHS:
                self.gtin["not_a_gtin_shape"] += 1
            elif "gtin" in found.normalised:
                self.gtin["valid"] += 1
            else:
                self.gtin["wrong_check_digit"] += 1

    def _links(self, page: WarcPage, found: Extraction) -> None:
        links = found.links
        canonical = links.get("canonical")
        if canonical:
            self.links["canonical"] += 1
            self.links[
                "canonical_self" if canonical == page.url else "canonical_elsewhere"
            ] += 1
        if links.get("canonical_conflict"):
            self.links["canonical_conflict"] += 1
        alternates = links.get("alternates") or []
        if any(a.get("hreflang") for a in alternates):
            self.links["hreflang"] += 1
        if any((a.get("hreflang") or "").lower() == "x-default" for a in alternates):
            self.links["x_default"] += 1

    def _rights(self, found: Extraction) -> None:
        rights = found.rights
        if rights.get("robots"):
            self.rights["robots_meta"] += 1
            self._directives("robots_directives", rights["robots"])
        if rights.get("agents"):
            self._directives("crawler_named", rights["agents"])
        http = rights.get("http") or {}
        if http.get("robots") or http.get("agents"):
            self.rights["x_robots_tag"] += 1
            self._directives(
                "x_robots_directives",
                [
                    *(http.get("robots") or []),
                    *(d for ds in (http.get("agents") or {}).values() for d in ds),
                ],
            )
        if "tdm_reservation" in rights:
            self._directives("tdm_reservation", [rights["tdm_reservation"]])
        if "tdm_policy" in rights:
            self.rights["tdm_policy"] += 1
        if "tdm_reservation" in http:
            self._directives("http_tdm_reservation", [http["tdm_reservation"]])
        if "tdm_policy" in http:
            self.rights["http_tdm_policy"] += 1
        if rights.get("license"):
            self.rights["license"] += 1

    def _directives(self, name: str, said: Any) -> None:
        self.directives.setdefault(name, Counter()).update(dict.fromkeys(said, 1))

    @classmethod
    def combined(cls, tallies: list[Tally]) -> Tally:
        """The tallies summed: counters added, sets joined, in any order alike."""
        total = cls()
        for one in tallies:
            for name, value in vars(one).items():
                held = getattr(total, name)
                if isinstance(value, int):
                    setattr(total, name, held + value)
                elif isinstance(value, (Counter, set)):
                    held.update(value)
                else:
                    for key, inner in value.items():
                        held.setdefault(key, type(inner)()).update(inner)
        return total

    def counts(self) -> dict[str, Any]:
        """What the report is written from, as JSON, every list in one order."""
        hosts = self.hosts
        return {
            "pages": self.pages,
            "truncated": self.truncated,
            "failed": top(self.failed),
            "left_out": top(self.left_out),
            "hosts": len(hosts),
            "top_level_domains": top(self.top_level_domains, 20),
            "vocabularies": {
                "pages": _in_order(self.vocabularies),
                "hosts": _in_order(
                    {k: len(v) for k, v in self.vocabulary_hosts.items()}
                ),
            },
            "any": {
                k: self.any[k]
                for k in ("about_things", "anything", "nothing")
                if self.any[k]
            },
            "any_hosts": {k: len(v) for k, v in sorted(self.any_hosts.items())},
            "combinations": top(self.combinations, 15),
            "types": {"distinct": len(self.types), "pages": top(self.types, 25)},
            "jsonld_nodes": {
                "typed": self.jsonld_typed,
                "classes": top(self.jsonld_classes, 20),
            },
            "merging": {
                **{
                    k: self.merging[k]
                    for k in ("pages_with_things", "several_vocabularies", "folded")
                },
                "folded_by": top(self.folded_by),
            },
            "conflicts": {
                "answered": {q: self.answered[q] for q in FIELDS if self.answered[q]},
                "conflicting": {
                    q: n for q, n in top(self.conflicting).items() if q != "(any)"
                },
                "between": {q: top(c, 3) for q, c in sorted(self.between.items())},
                "pages_with_any": self.conflicting["(any)"],
            },
            "titles": {
                k: self.titles[k]
                for k in ("declared_twice", "differ", "differ_beyond_containment")
            },
            "jsonld_blocks": {
                k: self.blocks[k]
                for k in (
                    "pages",
                    "blocks",
                    "valid",
                    "control_characters",
                    "recovered",
                    "lost",
                    "pages_with_invalid",
                    "pages_losing_one",
                )
            },
            "normalised": {
                "answered": {q: self.answered[q] for q in NORMALISED},
                "read": {q: self.read[q] for q in NORMALISED if self.read[q]},
                "unread_shapes": {
                    family: top(shapes, 10)
                    for family, shapes in sorted(self.unread_shapes.items())
                },
            },
            "gtin": {
                k: self.gtin[k]
                for k in ("answered", "not_a_gtin_shape", "wrong_check_digit", "valid")
            },
            "links": {
                k: self.links[k]
                for k in (
                    "canonical",
                    "canonical_self",
                    "canonical_elsewhere",
                    "canonical_conflict",
                    "hreflang",
                    "x_default",
                )
            },
            "rights": {
                "robots_meta": self.rights["robots_meta"],
                "robots_directives": top(self._said("robots_directives"), 15),
                "crawler_named": top(self._said("crawler_named"), 15),
                "x_robots_tag": self.rights["x_robots_tag"],
                "x_robots_directives": top(self._said("x_robots_directives"), 15),
                "tdm_reservation": top(self._said("tdm_reservation"), 5),
                "tdm_policy": self.rights["tdm_policy"],
                "http_tdm_reservation": top(self._said("http_tdm_reservation"), 5),
                "http_tdm_policy": self.rights["http_tdm_policy"],
                "license": self.rights["license"],
            },
        }

    def _said(self, name: str) -> Counter[str]:
        return self.directives.get(name, Counter())


def top(counts: Mapping[str, int], n: int | None = None) -> dict[str, int]:
    """The ``n`` largest counts, largest first, a tie broken by name."""
    ordered = sorted(
        ((k, v) for k, v in counts.items() if v), key=lambda kv: (-kv[1], kv[0])
    )
    return dict(ordered if n is None else ordered[:n])


def _in_order(counts: Mapping[str, int]) -> dict[str, int]:
    """Counts per reader, in Sluicer's order of precedence."""
    return {name: counts[name] for name in READERS if counts.get(name)}


def _jsonld_blocks(doc: Document) -> list[str]:
    """Every JSON-LD block on the page with something in it, as the reader sees it."""
    found = []
    for script in doc.tree.xpath("//script[@type]"):
        if not _is_ld_json(script.get("type") or ""):
            continue
        raw = (script.text_content() or "").strip()
        if raw:
            found.append(raw)
    return found


def _titles(doc: Document, found: Extraction) -> list[str]:
    """The page's title wherever it declares one, spaces collapsed, case folded.

    The subject's own name when the summary took the title from a vocabulary
    about things, ``og:title``, ``twitter:title`` and ``<title>``.
    """
    places = []
    answer = found.summary.get("title")
    if answer is not None and answer.source in ABOUT_A_THING:
        places.append(answer.value)
    places.append(read_opengraph(doc).get("title", ""))
    places.append(read_twitter(doc).get("title", ""))
    heads = doc.tree.xpath(_PAGE_TITLE)
    if heads:
        places.append(heads[0].text_content() or "")
    return [text for text in map(_normalised_text, places) if text]


def count_file(path: Path) -> Tally:
    """Every page of one WARC file, counted, and every record left out."""
    tally = Tally()
    skipped = Skipped()
    try:
        for page in read_warc(path, skipped):
            if page.status != 200:
                reason = (
                    "resource record"
                    if page.status is None
                    else "status 2xx but not 200"
                )
                tally.left_out[reason] += 1
                continue
            tally.add(page)
            if tally.pages % _PROGRESS == 0:
                print(f"{path.name}: {tally.pages} pages", file=sys.stderr, flush=True)
    except WarcError as broken:
        tally.failed[f"file broke off: {broken}"] += 1
    tally.left_out.update(skipped.reasons)
    return tally


def versions() -> dict[str, str]:
    """What read the pages: Sluicer's last commit in ``src/``, and its parsers."""
    try:
        src = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "src"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        src = "unknown"
    return {
        "src": src,
        "version": sluicer.__version__,
        "lxml": ".".join(map(str, lxml.etree.LXML_VERSION[:3])),
        "libxml2": ".".join(map(str, lxml.etree.LIBXML_VERSION)),
        "mf2py": importlib.metadata.version("mf2py"),
        "python": platform.python_version(),
    }


def count(paths: list[Path]) -> dict[str, Any]:
    """Every file counted, each in a process of its own, and summed in order."""
    with ProcessPoolExecutor(max_workers=len(paths)) as pool:
        tallies = list(pool.map(count_file, paths))
    counts = Tally.combined(tallies).counts()
    counts["files"] = [
        {"pages": t.pages, "left_out": top(t.left_out), "failed": top(t.failed)}
        for t in tallies
    ]
    counts["sluicer"] = versions()
    return counts


# -- the report ------------------------------------------------------------------

# What Web Data Commons published for its latest extraction, the October 2024
# Common Crawl, copied from its statistics page on 2026-09-25. The only
# numbers in the report not counted here, each shown beside its source.
WDC: dict[str, Any] = {
    "url": "https://webdatacommons.org/structureddata/2024-12/stats/stats.html",
    "crawl": "CC-MAIN-2024-42",
    "month": "October 2024",
    "released": "2025-01-10",
    "parsed_html_urls": 2_391_039_772,
    "urls_with_triples": 1_245_622_627,
    "overall_row_urls": 1_221_984_070,
    "stated_share": "51.25%",
    "formats": {
        "jsonld": ("html-embedded-jsonld", 833_818_654),
        "microdata": ("html-microdata", 574_648_578),
        "rdfa": ("html-rdfa", 49_636_704),
        "microformats": ("html-mf-hcard", 179_698_044),
    },
    "jsonld_entities": 9_689_931_985,
    # The twenty classes of its embedded JSON-LD with the most entities.
    "jsonld_classes": {
        "ListItem": 1_729_382_329,
        "ImageObject": 1_017_058_167,
        "Organization": 717_376_736,
        "Offer": 615_787_153,
        "BreadcrumbList": 584_841_237,
        "WebSite": 487_070_935,
        "WebPage": 440_700_249,
        "Person": 430_420_245,
        "SearchAction": 412_174_624,
        "EntryPoint": 337_691_324,
        "Product": 305_921_140,
        "ReadAction": 259_702_233,
        "PropertyValueSpecification": 176_425_583,
        "PostalAddress": 146_109_030,
        "Article": 127_181_135,
        "Brand": 123_165_371,
        "SiteNavigationElement": 102_973_869,
        "CollectionPage": 98_508_349,
        "DefinedRegion": 75_515_917,
        "AggregateRating": 72_186_634,
    },
}

_QUESTIONS = {
    "price": "price",
    "currency": "currency",
    "published": "published",
    "modified": "modified",
}


# What a cell holds when there is nothing to divide by, or nothing to say.
_DASH = "\N{EN DASH}"


def _n(value: int) -> str:
    return f"{value:,}"


def _share(k: int, n: int) -> str:
    """``k`` of ``n`` as a percentage with its Wilson interval, or a dash."""
    interval = wilson(k, n)
    if interval is None:
        return _DASH
    low, high = interval
    return f"{100 * k / n:.1f}% ({100 * low:.1f}-{100 * high:.1f})"


def _pct(k: int, n: int) -> str:
    return _DASH if not n else f"{100 * k / n:.1f}%"


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "|".join("---" for _ in head) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def render(counts: dict[str, Any], manifest: dict[str, Any]) -> str:
    """``docs/state-of-declared-data.md``, from the counts and the manifest alone."""
    pages = counts["pages"]
    hosts = counts["hosts"]
    files = manifest["files"]
    made = counts["sluicer"]
    vocab = counts["vocabularies"]
    any_ = counts["any"]
    any_hosts = counts.get("any_hosts", {})
    size = sum(f["bytes"] for f in files)
    out: list[str] = [
        "# The state of declared data",
        "",
        "What web pages declare about themselves -- JSON-LD, microdata, RDFa,",
        "microformats, OpenGraph, the Twitter card, Dublin Core, HTML's own meta",
        "names -- counted by Sluicer on "
        f"{_n(pages)} pages of Common Crawl's `{manifest['crawl']}`: every HTML",
        f"page answered 200 in {len(files)} of the crawl's "
        f"{_n(manifest['listing']['lines'])} WARC files, chosen",
        "by a rule fixed before any was downloaded. Each is read as",
        "`sluicer.extract` reads a page, with its provenance, and the conflicts",
        "between what one page declares twice are counted with the rest.",
        "",
        f"Counted on {counts.get('counted_on', 'an unrecorded day')} by "
        f"`bench/declared_report.py`, with Sluicer {made['version']} at the "
        f"last commit to `src/`, `{made['src']}` (lxml {made['lxml']}, libxml2 "
        f"{made['libxml2']}, mf2py {made['mf2py']}). Every number below is "
        "written by the script from its counts, `bench/declared-counts.json`,",
        "except Web Data Commons', which are cited where they stand.",
        "",
        '!!! warning "A few WARC files are not the web"',
        f"    {len(files)} files of one crawl, {_n(hosts)} hosts. Common Crawl "
        "chooses what it",
        "    fetches by its own ranking of hosts, obeys robots.txt, keeps a",
        "    body only up to a length and marks the rest truncated, and takes",
        "    many pages from one host, so pages are not independent draws. The",
        "    intervals, 95% Wilson intervals over pages, are therefore narrower",
        "    than the sample's real uncertainty; for the vocabularies the share",
        "    of hosts is given too. What a crawler that skips scripts, a",
        "    logged-in page or a page behind an anti-bot wall declares is not here.",
        "",
        "## The sample",
        "",
        "The crawl is the first listed in Common Crawl's `collinfo.json` whose",
        "WARC listing is published. From its listing, pinned by SHA-256 in",
        "`bench/declared-manifest.json`, the files are the lines at the middle",
        f"of each of {len(files)} equal parts of the list, by position alone "
        f"({_n(size // 1_000_000)} MB",
        "compressed in all). `bench/PREREG.md` fixed the rule and every count",
        "before a file was downloaded.",
        "",
    ]
    out += _table(
        ["line", "file", "MB", "pages", "SHA-256"],
        [
            [
                _n(f["index"]),
                f"`{f['path'].rsplit('/', 1)[-1]}`",
                _n(f["bytes"] // 1_000_000),
                _n(counted["pages"]) if counted else _DASH,
                f"`{f['sha256'][:16]}…`",
            ]
            for f, counted in zip(
                files, counts.get("files") or [None] * len(files), strict=True
            )
        ],
    )
    left_out = counts["left_out"]
    out += [
        "",
        f"A page is a `response` record answered 200 and read as HTML: "
        f"{_n(pages)} pages, from {_n(hosts)} hosts. "
        f"{_n(counts['truncated'])} of them "
        f"({_pct(counts['truncated'], pages)}) were truncated by the crawler and "
        "are read as it kept them. Left out, and counted by why:",
        "",
    ]
    out += _table(
        ["left out", "records"], [[reason, _n(n)] for reason, n in left_out.items()]
    )
    failed = counts["failed"]
    out += [
        "",
        (
            "Pages Sluicer could not read: "
            + ", ".join(f"{_n(n)} ({name})" for name, n in failed.items())
            + "."
            if failed
            else "Every page was read: none raised an error."
        ),
        "",
        "The top-level domains of the pages' hosts, the twenty commonest:",
        "",
    ]
    out += _table(
        ["top-level domain", "pages", "share"],
        [
            [f"`.{tld}`" if not tld.startswith("(") else tld, _n(n), _pct(n, pages)]
            for tld, n in counts["top_level_domains"].items()
        ],
    )

    out += [
        "",
        "## What pages declare",
        "",
        "A vocabulary counts on a page when Sluicer's reader for it found",
        "something (`Extraction.sources`). RDFa is RDFa Lite, and OpenGraph's",
        "`<meta property>` tags are OpenGraph's, never RDFa's; HTML's meta",
        "names are the closed list HTML itself defines (`description`,",
        "`author`, `keywords`, `generator`, `application-name`,",
        "`theme-color`). A host counts when any of its pages declares it.",
        "",
    ]
    rows = [
        [
            label,
            _n(vocab["pages"].get(name, 0)),
            _share(vocab["pages"].get(name, 0), pages),
            _share(vocab["hosts"].get(name, 0), hosts),
        ]
        for name, label in READERS.items()
    ]
    rows += [
        [
            "**any about things** (the first four)",
            _n(any_.get("about_things", 0)),
            _share(any_.get("about_things", 0), pages),
            _share(any_hosts.get("about_things", 0), hosts),
        ],
        [
            "**anything at all**",
            _n(any_.get("anything", 0)),
            _share(any_.get("anything", 0), pages),
            _share(any_hosts.get("anything", 0), hosts),
        ],
        [
            "**nothing**",
            _n(any_.get("nothing", 0)),
            _share(any_.get("nothing", 0), pages),
            _share(any_hosts.get("nothing", 0), hosts),
        ],
    ]
    out += _table(["vocabulary", "pages", "share of pages", "share of hosts"], rows)
    out += [
        "",
        "The combinations pages declare, the fifteen commonest, in Sluicer's",
        "order of precedence:",
        "",
    ]
    out += _table(
        ["readers that found something", "pages", "share"],
        [
            [
                " + ".join(READERS.get(p, p) for p in combo.split(" + ")),
                _n(n),
                _pct(n, pages),
            ]
            for combo, n in counts["combinations"].items()
        ],
    )

    out += _wdc(counts)
    out += _types(counts)
    out += _merging(counts)
    out += _conflicts(counts)
    out += _blocks(counts)
    out += _normalisation(counts)
    out += _links_and_rights(counts)
    out += [
        "",
        "## Reproduce it",
        "",
        "```bash",
        ".venv/bin/python bench/declared_report.py          "
        "# the pinned files, then this page",
        ".venv/bin/python bench/declared_report.py --report-only"
        "   # this page from the counts",
        "```",
        "",
        "The first run downloads the pinned files from `data.commoncrawl.org`,",
        "one at a time, into `bench/commoncrawl/`, and stops if one does not",
        "hash to its pin. The counts are the same on every run: every page of",
        "every file is read, and the files' counts are summed.",
        "",
    ]
    return "\n".join(out)


def _wdc(counts: dict[str, Any]) -> list[str]:
    pages = counts["pages"]
    vocab = counts["vocabularies"]["pages"]
    parsed = WDC["parsed_html_urls"]
    out = [
        "",
        "## Beside Web Data Commons",
        "",
        "[Web Data Commons](https://webdatacommons.org/structureddata/) (Bizer,",
        "Meusel, Primpeli, Brinkmann; University of Mannheim) extracts the",
        "structured data of a whole Common Crawl with Any23. Its latest",
        f"extraction, released {WDC['released']}, is of the {WDC['month']} crawl,",
        f"`{WDC['crawl']}`; the figures below are from [its statistics page]"
        f"({WDC['url']}),",
        "read on 2026-09-25. It is two years older than this crawl, and it reads",
        "differently: full RDFa rather than RDFa Lite, microformats one format",
        "at a time, and JSON-LD only where it parses. Read the two columns side",
        "by side, never as one series.",
        "",
    ]
    rows = [
        [
            "pages with any of JSON-LD, microdata, RDFa, microformats",
            f"{_n(WDC['urls_with_triples'])} of {_n(parsed)} "
            f"({_pct(WDC['urls_with_triples'], parsed)}; the page states "
            f"{WDC['stated_share']}, and its per-format table's total is "
            f"{_n(WDC['overall_row_urls'])})",
            _share(counts["any"].get("about_things", 0), pages),
        ]
    ]
    for name, (label, urls) in WDC["formats"].items():
        what = READERS[name]
        if name == "microformats":
            what = "microformats (any; WDC's commonest, hCard, alone)"
        rows.append(
            [
                f"{what} -- WDC's `{label}`",
                f"{_n(urls)} ({_pct(urls, parsed)})",
                _share(vocab.get(name, 0), pages),
            ]
        )
    out += _table(["pages declaring", f"WDC, {WDC['month']}", "here"], rows)
    return out


def _types(counts: dict[str, Any]) -> list[str]:
    types = counts["types"]
    pages = counts["pages"]
    nodes = counts["jsonld_nodes"]
    typed = nodes["typed"]
    out = [
        "",
        "## Types",
        "",
        "The types of the records Sluicer reads from the vocabularies about",
        f"things, by the pages declaring each: {_n(types['distinct'])} distinct "
        "types, the",
        "twenty-five commonest. A schema.org type is written by its name",
        "whatever the page wrote (`http://schema.org/Product`, `schema:Product`);",
        "any other keeps its whole IRI, and microformats their class.",
        "",
    ]
    out += _table(
        ["type", "pages", "share of pages"],
        [[f"`{t}`", _n(n), _share(n, pages)] for t, n in types["pages"].items()],
    )
    out += [
        "",
        "Every typed object in every JSON-LD block, nested ones included, as",
        f"written and before references are resolved: {_n(typed)} typed objects, the",
        "twenty commonest classes, beside the share of Web Data Commons' "
        f"{_n(WDC['jsonld_entities'])} JSON-LD entities",
        f"of {WDC['month']} (an entity of two types counts in both, here and there;",
        "WDC's is an RDF node, so two objects with one `@id` are one entity",
        "there and two here). A dash is a class outside WDC's twenty.",
        "",
    ]
    wdc = WDC["jsonld_classes"]
    out += _table(
        ["class", "objects", "share here", "share in WDC"],
        [
            [
                f"`{c}`",
                _n(n),
                _pct(n, typed),
                _pct(wdc[c], WDC["jsonld_entities"]) if c in wdc else _DASH,
            ]
            for c, n in nodes["classes"].items()
        ],
    )
    return out


def _merging(counts: dict[str, Any]) -> list[str]:
    merging = counts["merging"]
    things = merging["pages_with_things"]
    several = merging["several_vocabularies"]
    folded = merging["folded"]
    out = [
        "",
        "## One thing, declared in two vocabularies",
        "",
        "Sluicer folds records of one type declared in two vocabularies about",
        "things -- a Product in JSON-LD and again in microdata -- into one, the",
        "earlier vocabulary's fields winning and the later one filling gaps.",
        f"Of the {_n(things)} pages declaring a thing, {_n(several)} "
        f"({_share(several, things)}) declare",
        "them in two or more of those vocabularies, and on "
        f"{_n(folded)} ({_share(folded, several)} of those) one record",
        "holds fields from two or more: the fold added what the first",
        "vocabulary left out. A fold that added no field is not seen here.",
        "",
    ]
    out += _table(
        ["folded from", "pages"],
        [
            [" + ".join(READERS.get(p, p) for p in pair.split(" + ")), _n(n)]
            for pair, n in merging["folded_by"].items()
        ],
    )
    return out


def _conflicts(counts: dict[str, Any]) -> list[str]:
    conflicts = counts["conflicts"]
    answered = conflicts["answered"]
    titles = counts["titles"]
    pages = counts["pages"]
    out = [
        "",
        "## Conflicts",
        "",
        "A conflict is a question the page answers twice with two meanings",
        "(`Extraction.conflicts`): two prices that are two amounts, two",
        "currencies, two publication or modification dates that are two days",
        "or two instants. `126` and `126.00` agree, and a value no rule can read",
        "disagrees with nothing. Sluicer compares these four questions only.",
        f"Of the {_n(pages)} pages, {_n(conflicts['pages_with_any'])} "
        f"({_share(conflicts['pages_with_any'], pages)}) declare at least one "
        "conflict.",
        "",
    ]
    rows = []
    for question in _QUESTIONS:
        k = conflicts["conflicting"].get(question, 0)
        n = answered.get(question, 0)
        between = conflicts["between"].get(question, {})
        rows.append(
            [
                question,
                _n(n),
                _n(k),
                _share(k, n),
                ", ".join(
                    f"{' / '.join(READERS.get(s, s) for s in pair.split(' / '))} "
                    f"({_n(m)})"
                    for pair, m in between.items()
                )
                or _DASH,
            ]
        )
    out += _table(
        [
            "question",
            "pages answering it",
            "in conflict",
            "share",
            "the summary's answer / the other, most often",
        ],
        rows,
    )
    twice = titles["declared_twice"]
    out += [
        "",
        "A title is not compared: a page's `<title>` adds the site's name, its",
        "`og:title` drops it, and the two are one title. How often they differ:",
        f"{_n(twice)} pages ({_share(twice, pages)}) declare a title in two or more of",
        "the subject's name, `og:title`, `twitter:title` and `<title>`; on",
        f"{_n(titles['differ'])} of them ({_share(titles['differ'], twice)}) "
        "the texts differ once",
        "spaces are collapsed and case folded, and on "
        f"{_n(titles['differ_beyond_containment'])}",
        f"({_share(titles['differ_beyond_containment'], twice)}) two differ "
        "with neither holding the other.",
    ]
    return out


def _blocks(counts: dict[str, Any]) -> list[str]:
    blocks = counts["jsonld_blocks"]
    total = blocks["blocks"]
    invalid = total - blocks["valid"]
    out = [
        "",
        "## JSON-LD that is not JSON",
        "",
        f"{_n(blocks['pages'])} pages carry {_n(total)} "
        '`<script type="application/ld+json">`',
        "blocks with something in them. Each is read three ways, in order: as",
        "`json.loads` reads JSON, NaN and Infinity refused; as written but with",
        "a raw control character allowed inside a string, the newline a CMS",
        "leaves in a description; and as Sluicer's lenient reader reads it,",
        "unwrapping an HTML comment or CDATA, a byte order mark, JavaScript's",
        "comments and a trailing comma, never mending a string's text.",
        "",
    ]
    out += _table(
        ["block", "blocks", "share of blocks"],
        [
            ["JSON", _n(blocks["valid"]), _share(blocks["valid"], total)],
            [
                "JSON once a raw control character is allowed",
                _n(blocks["control_characters"]),
                _share(blocks["control_characters"], total),
            ],
            [
                "recovered by Sluicer's lenient reader",
                _n(blocks["recovered"]),
                _share(blocks["recovered"], total),
            ],
            ["lost", _n(blocks["lost"]), _share(blocks["lost"], total)],
        ],
    )
    recovered = blocks["control_characters"] + blocks["recovered"]
    out += [
        "",
        f"Of the {_n(invalid)} blocks that are not JSON, Sluicer reads "
        f"{_n(recovered)} ({_share(recovered, invalid)}).",
        f"{_n(blocks['pages_with_invalid'])} pages "
        f"({_share(blocks['pages_with_invalid'], blocks['pages'])} of those with "
        "a block) carry one that is not",
        f"JSON, and {_n(blocks['pages_losing_one'])} "
        f"({_share(blocks['pages_losing_one'], blocks['pages'])}) one that no "
        "reading recovers.",
    ]
    return out


def _normalisation(counts: dict[str, Any]) -> list[str]:
    normalised = counts["normalised"]
    gtin = counts["gtin"]
    out = [
        "",
        "## What a declared value means",
        "",
        "The summary keeps what the page wrote; `Extraction.normalised` reads",
        "it into one form -- ISO 8601, a decimal, an ISO 4217 code, a GTIN whose",
        "check digit is right -- only where the text leaves no doubt:",
        "`03/04/2025` is two dates and `1,299` two amounts, and neither is read.",
        "",
    ]
    rows = []
    for question in NORMALISED:
        n = normalised["answered"].get(question, 0)
        k = normalised["read"].get(question, 0)
        rows.append([question, _n(n), _n(k), _share(k, n)])
    out += _table(["question", "pages answering it", "read", "share read"], rows)
    answered = gtin["answered"]
    out += [
        "",
        f"Of {_n(answered)} GTINs, {_n(gtin['valid'])} "
        f"({_share(gtin['valid'], answered)}) are right,",
        f"{_n(gtin['wrong_check_digit'])} "
        f"({_share(gtin['wrong_check_digit'], answered)}) "
        "have a GTIN's shape and a wrong check digit, and",
        f"{_n(gtin['not_a_gtin_shape'])} "
        f"({_share(gtin['not_a_gtin_shape'], answered)}) "
        "are not 8, 12, 13 or 14 digits at all once",
        "spaces and hyphens are dropped.",
    ]
    for family, label in (("date", "dates"), ("price", "prices")):
        shapes = normalised["unread_shapes"].get(family, {})
        if not shapes:
            continue
        out += [
            "",
            f"The {label} not read, by shape (every digit written 9, every letter",
            "a), the ten commonest:",
            "",
        ]
        out += _table(
            ["shape", "answers"],
            [[f"`{s}`" if s.strip() else "(blank)", _n(n)] for s, n in shapes.items()],
        )
    return out


def _links_and_rights(counts: dict[str, Any]) -> list[str]:
    links = counts["links"]
    rights = counts["rights"]
    pages = counts["pages"]
    canonical = links["canonical"]
    out = [
        "",
        "## Where else a page lives",
        "",
        "From `<link>` in the page and `Link` in its headers (`Extraction.links`).",
        "",
    ]
    out += _table(
        ["declares", "pages", "share"],
        [
            ["a canonical", _n(canonical), _share(canonical, pages)],
            [
                "… the page's own address, exactly",
                _n(links["canonical_self"]),
                _share(links["canonical_self"], canonical),
            ],
            [
                "… another address",
                _n(links["canonical_elsewhere"]),
                _share(links["canonical_elsewhere"], canonical),
            ],
            [
                "two different canonicals",
                _n(links["canonical_conflict"]),
                _share(links["canonical_conflict"], pages),
            ],
            [
                "`hreflang` alternates",
                _n(links["hreflang"]),
                _share(links["hreflang"], pages),
            ],
            [
                "… with `x-default`",
                _n(links["x_default"]),
                _share(links["x_default"], links["hreflang"]),
            ],
        ],
    )
    out += [
        "",
        "## How a page may be used",
        "",
        "What the page's `<meta>` tags and its headers declare",
        "(`Extraction.rights`): the robots directives, and TDMRep's reservation",
        "of text and data mining rights, a W3C Community Group report written",
        "for the EU's DSM Directive, Article 4. A page that declares nothing",
        "declares nothing, which is not the same as allowing everything; and",
        "robots.txt and `/.well-known/tdmrep.json`, the site's own rules, are",
        "not read here.",
        "",
    ]
    reserved = rights["tdm_reservation"]
    http_reserved = rights["http_tdm_reservation"]
    out += _table(
        ["declares", "pages", "share"],
        [
            [
                '`<meta name="robots">`',
                _n(rights["robots_meta"]),
                _share(rights["robots_meta"], pages),
            ],
            [
                "`X-Robots-Tag`",
                _n(rights["x_robots_tag"]),
                _share(rights["x_robots_tag"], pages),
            ],
            [
                "`tdm-reservation` in the page",
                _n(sum(reserved.values())),
                _share(sum(reserved.values()), pages),
            ],
            [
                "`tdm-policy` in the page",
                _n(rights["tdm_policy"]),
                _share(rights["tdm_policy"], pages),
            ],
            [
                "`TDM-Reservation` in the headers",
                _n(sum(http_reserved.values())),
                _share(sum(http_reserved.values()), pages),
            ],
            [
                "`TDM-Policy` in the headers",
                _n(rights["http_tdm_policy"]),
                _share(rights["http_tdm_policy"], pages),
            ],
            ["`rel=license`", _n(rights["license"]), _share(rights["license"], pages)],
        ],
    )
    for key, label in (
        ("robots_directives", '`<meta name="robots">`\'s directives'),
        ("crawler_named", "the crawlers named in its place"),
        ("x_robots_directives", "`X-Robots-Tag`'s directives"),
        ("tdm_reservation", "`tdm-reservation`'s values in the page"),
        ("http_tdm_reservation", "`TDM-Reservation`'s values in the headers"),
    ):
        said = rights[key]
        if not said:
            continue
        out += ["", f"{label[0].upper()}{label[1:]}, by pages:", ""]
        out += _table(
            ["said", "pages"], [[f"`{text}`", _n(n)] for text, n in said.items()]
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--pin", action="store_true", help="choose the sample and download it"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="write the report from bench/declared-counts.json",
    )
    options = parser.parse_args(argv)
    if options.pin:
        pin()
        return 0
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not options.report_only:
        paths = ensure(manifest)
        started = time.monotonic()
        counts = count(paths)
        counts["counted_on"] = datetime.date.today().isoformat()
        COUNTS.write_text(
            json.dumps(counts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"{counts['pages']} pages in {time.monotonic() - started:.0f} s",
            file=sys.stderr,
        )
    counts = json.loads(COUNTS.read_text(encoding="utf-8"))
    REPORT.write_text(render(counts, manifest), encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
