"""Extractors learnt once, replayed for nothing, and loud when a page drifts.

A scraper that returns nulls for weeks after a site changed its markup is the
most common way scraping fails, and the most expensive, because nothing says it
failed. An ``Extractor`` is the other way round. It is learnt from a few pages
of one template -- what the pages declare, and the listing they repeat -- and
written to a small JSON file. Replayed on a new page it does no induction and
costs nothing, and it checks the page against what it learnt: the listing is
where it was, the rows are there, every field that was always filled still is
and still looks the same, every question the summary answered is still
answered. A page that breaks any of that is a failed run, never a quiet one.

When a run fails, ``heal`` learns the page again and says what moved: each old
field is matched to its new place by the values it used to hold, so a field
that moved keeps the name downstream code reads.

No model is asked anything, anywhere: the same pages always give the same
extractor, and the same page always gives the same verdict.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from lxml.html import HtmlElement

from sluicer import __version__
from sluicer.api import extract
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import Document, absolute, load
from sluicer.structure.groups import repeating_groups
from sluicer.structure.records import _label, records_from
from sluicer.structure.shape import kind

FORMAT = 1
"""The version of the file format ``to_json`` writes and ``from_json`` reads."""

REQUIRED_MISSING = 0.2
"""The share of rows that may lack a field every learnt row carried."""

SHAPE_KEPT = 0.5
"""The share of a field's values that must keep the one shape it was learnt with."""

_SAMPLES = 5

# The summary questions whose answers have a shape worth holding a page to. A
# title, an author or a description is free text, and its shape says nothing.
_SHAPED = frozenset(
    {"price", "currency", "published", "modified", "sku", "availability"}
)

Page = tuple[str | bytes, str | None]
"""One page: its HTML, and the address it came from (None for none)."""


class NothingToLearn(ValueError):
    """The pages declare nothing and repeat nothing, so there is no extractor."""


@dataclass(frozen=True)
class ListingField:
    """One column of a listing.

    ``name`` is what a row calls it and never changes once learnt; ``path`` is
    where it sits in the markup today, and is what ``heal`` moves.
    ``missing`` is the share of learnt rows without it, so 0 means required.
    ``shape`` is the one shape every learnt value had, or None when they had
    several or the field is an address.
    """

    name: str
    path: str
    missing: float
    shape: str | None
    samples: tuple[str, ...]


@dataclass(frozen=True)
class Listing:
    """Where a page's repeated rows are, what one looks like, and what it holds."""

    container: str
    member: str
    rows: tuple[int, int]
    fields: tuple[ListingField, ...]


@dataclass(frozen=True)
class Extractor:
    """What a template's pages were learnt to hold, as a replayable contract.

    ``summary`` maps each summary question every page answered to the one shape
    of its answers, or None when unknown. ``types`` are the declared record
    types every page carried.
    """

    learnt_from: tuple[str, ...]
    summary: dict[str, str | None]
    types: tuple[str, ...]
    listing: Listing | None
    notes: tuple[str, ...] = ()
    version: str = __version__

    def to_json(self) -> str:
        """The extractor as the JSON file it is kept in, stable key order."""
        body: dict[str, Any] = {
            "format": FORMAT,
            "sluicer": self.version,
            "learnt_from": list(self.learnt_from),
            "summary": self.summary,
            "types": list(self.types),
            "listing": None,
            "notes": list(self.notes),
        }
        if self.listing is not None:
            body["listing"] = {
                "container": self.listing.container,
                "member": self.listing.member,
                "rows": list(self.listing.rows),
                "fields": [
                    {
                        "name": f.name,
                        "path": f.path,
                        "missing": f.missing,
                        "shape": f.shape,
                        "samples": list(f.samples),
                    }
                    for f in self.listing.fields
                ],
            }
        return json.dumps(body, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Extractor:
        """Read an extractor back from its file.

        Raises:
            ValueError: the text is not an extractor this version can read.
        """
        body = json.loads(text)
        if not isinstance(body, dict) or body.get("format") != FORMAT:
            raise ValueError(f"not a sluicer extractor of format {FORMAT}")
        listing = None
        if body.get("listing"):
            raw = body["listing"]
            listing = Listing(
                container=raw["container"],
                member=raw["member"],
                rows=(int(raw["rows"][0]), int(raw["rows"][1])),
                fields=tuple(
                    ListingField(
                        name=f["name"],
                        path=f["path"],
                        missing=float(f["missing"]),
                        shape=f["shape"],
                        samples=tuple(f["samples"]),
                    )
                    for f in raw["fields"]
                ),
            )
        return cls(
            learnt_from=tuple(body.get("learnt_from", [])),
            summary=dict(body.get("summary", {})),
            types=tuple(body.get("types", [])),
            listing=listing,
            notes=tuple(body.get("notes", [])),
            version=str(body.get("sluicer", "")),
        )


@dataclass(frozen=True)
class Check:
    """One expectation, and what the page did with it."""

    name: str
    expected: str
    got: str
    ok: bool


@dataclass
class Run:
    """An extractor replayed on one page. ``ok`` is False when any check failed."""

    url: str | None
    ok: bool
    rows: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)


@dataclass(frozen=True)
class Change:
    """One difference ``heal`` found between the old extractor and the page.

    ``kind`` is one of container, member, kept, moved, vanished, new,
    summary-lost, summary-gained, type-lost, type-gained.
    """

    kind: str
    before: str | None
    after: str | None


def shape(text: str) -> str:
    """The character classes a value is made of: L letters, N digits,
    P punctuation, S symbols such as currency signs, in that order.

    ``£51.77`` is ``NPS``, ``In stock`` is ``L``, ``2026-09-22`` is ``NP``.
    """
    classes = {unicodedata.category(char)[0] for char in text if not char.isspace()}
    return "".join(c for c in "LNPS" if c in classes)


def compile_extractor(
    pages: Sequence[Page],
    listing: bool | None = None,
    names: Sequence[str] | None = None,
) -> Extractor:
    """Learn an extractor from pages of one template.

    Args:
        pages: the pages, each as ``(html, url)``.
        listing: learn the listing the pages repeat. None, the default, learns
            one only when the pages declare nothing about a thing, the rule
            ``extract(induce=True)`` follows; True looks for one anyway.
        names: what to call each page in ``learnt_from``; its address by default.

    Raises:
        NothingToLearn: the pages declare nothing and repeat nothing.
    """
    if not pages:
        raise NothingToLearn("an extractor needs at least one page")
    docs = [load(html, url=url) for html, url in pages]
    results = [extract(html, url=url) for html, url in pages]
    summary = _learn_summary([r.summary for r in results], len(pages))
    types = _common(
        [
            {
                name
                for record in r.records
                if record.source in ABOUT_A_THING
                for name in record.types
            }
            for r in results
        ]
    )
    declares_a_thing = any(
        f.source in ABOUT_A_THING
        for r in results
        for record in r.records
        for f in record.fields.values()
    )
    learnt: Listing | None = None
    notes: list[str] = []
    if listing or (listing is None and not declares_a_thing):
        learnt, notes = _learn_listing(docs)
    if not summary and not types and learnt is None:
        raise NothingToLearn(
            "these pages declare nothing and repeat nothing an extractor could keep"
        )
    return Extractor(
        learnt_from=tuple(
            (names[n - 1] if names else None) or url or f"page {n}"
            for n, (_, url) in enumerate(pages, 1)
        ),
        summary=summary,
        types=tuple(sorted(types)),
        listing=learnt,
        notes=tuple(notes),
    )


def run_extractor(
    extractor: Extractor, html: str | bytes, url: str | None = None
) -> Run:
    """Replay ``extractor`` on one page and check it against what it learnt."""
    doc = load(html, url=url)
    result = extract(html, url=url)
    run = Run(url=url, ok=True, summary={k: v.value for k, v in result.summary.items()})
    for question, learnt_shape in extractor.summary.items():
        answer = result.summary.get(question)
        if answer is None:
            run.checks.append(
                Check("summary", f"the summary answers {question}", "no answer", False)
            )
        elif learnt_shape and shape(answer.value) != learnt_shape:
            run.checks.append(
                Check(
                    "shape",
                    f"summary {question} shaped {learnt_shape}",
                    f"{answer.value!r} ({shape(answer.value) or 'empty'})",
                    False,
                )
            )
        else:
            run.checks.append(
                Check("summary", f"the summary answers {question}", "yes", True)
            )
    declared = {
        name
        for record in result.records
        if record.source in ABOUT_A_THING
        for name in record.types
    }
    for name in extractor.types:
        present = name in declared
        run.checks.append(
            Check("type", f"a declared {name}", "yes" if present else "none", present)
        )
    if extractor.listing is not None:
        run.rows = _replay_listing(extractor.listing, doc, run.checks)
    run.ok = all(check.ok for check in run.checks)
    return run


def heal(
    extractor: Extractor,
    pages: Sequence[Page],
    names: Sequence[str] | None = None,
) -> tuple[Extractor, list[Change]]:
    """Learn ``pages`` again and match what moved to what ``extractor`` knew.

    Every old field is matched to at most one new place: the one holding most of
    the values it used to hold, then one of the same shape, and a field with no
    match is reported as vanished. A field that moved keeps its old name, so a
    row read with the healed extractor has the columns it always had.

    Returns:
        The healed extractor, and every change found, in a stable order.
    """
    fresh = compile_extractor(
        pages, listing=True if extractor.listing else None, names=names
    )
    changes: list[Change] = []
    for question in extractor.summary:
        if question not in fresh.summary:
            changes.append(Change("summary-lost", question, None))
    for question in fresh.summary:
        if question not in extractor.summary:
            changes.append(Change("summary-gained", None, question))
    for name in extractor.types:
        if name not in fresh.types:
            changes.append(Change("type-lost", name, None))
    for name in fresh.types:
        if name not in extractor.types:
            changes.append(Change("type-gained", None, name))
    listing = fresh.listing
    if extractor.listing is not None and listing is not None:
        listing, listing_changes = _heal_listing(extractor.listing, listing, pages)
        changes.extend(listing_changes)
    elif extractor.listing is not None:
        changes.append(Change("container", extractor.listing.container, None))
    healed = Extractor(
        learnt_from=fresh.learnt_from,
        summary=fresh.summary,
        types=fresh.types,
        listing=listing,
        notes=fresh.notes,
    )
    return healed, changes


# -- learning -----------------------------------------------------------------


def _common(sets: list[set[str]]) -> set[str]:
    return set.intersection(*sets) if sets else set()


def _learn_summary(
    summaries: list[dict[str, Any]], pages: int
) -> dict[str, str | None]:
    """The questions every page answered, with their shared shape where known.

    A shape is kept only for a structured answer -- a price, a date, a SKU --
    and only from two pages or more that agree on it: one page says nothing
    about what varies from page to page.
    """
    answered = _common([set(s) for s in summaries])
    learnt: dict[str, str | None] = {}
    for question in (q for q in summaries[0] if q in answered):
        shapes = {shape(s[question].value) for s in summaries}
        keep = pages >= 2 and len(shapes) == 1 and question in _SHAPED
        learnt[question] = shapes.pop() if keep else None
    return learnt


def _learn_listing(docs: list[Document]) -> tuple[Listing | None, list[str]]:
    found: list[tuple[str, str, list[HtmlElement]]] = []
    for doc in docs:
        group = _listing_of(doc)
        if group is not None:
            members = group
            found.append((path_of(members[0].getparent()), kind(members[0]), members))
    if not found:
        return None, []
    places = Counter((container, member) for container, member, _ in found)
    (container, member), _count = min(
        places.items(), key=lambda item: (-item[1], _first_index(found, item[0]))
    )
    notes = []
    if len(places) > 1 or len(found) < len(docs):
        notes.append(
            f"the listing is at {container} on {places[(container, member)]} of "
            f"{len(docs)} pages; the others were ignored"
        )
    rows: list[dict[str, str]] = []
    counts: list[int] = []
    for (c, m, members), doc in zip(found, docs, strict=False):
        if (c, m) != (container, member):
            continue
        page_rows = _rows_of(members, doc)
        counts.append(len(page_rows))
        rows.extend(page_rows)
    paths = list(dict.fromkeys(path for row in rows for path in row))
    fields = tuple(
        _profile(path, path, [row.get(path) for row in rows]) for path in paths
    )
    return Listing(container, member, (min(counts), max(counts)), fields), notes


def _first_index(
    found: list[tuple[str, str, list[HtmlElement]]], key: tuple[str, str]
) -> int:
    return next(n for n, (c, m, _) in enumerate(found) if (c, m) == key)


def _listing_of(doc: Document) -> list[HtmlElement] | None:
    """The page's most promising repeated group that yields records."""
    for group in repeating_groups(doc.tree):
        if records_from(group):
            return group
    return None


def _profile(name: str, path: str, values: list[str | None]) -> ListingField:
    present = [value for value in values if value]
    shapes = {shape(value) for value in present}
    address = "@" in path.rsplit(">", 1)[-1]
    return ListingField(
        name=name,
        path=path,
        missing=round(1 - len(present) / len(values), 4) if values else 1.0,
        shape=shapes.pop() if len(shapes) == 1 and not address else None,
        samples=tuple(dict.fromkeys(present))[:_SAMPLES],
    )


# -- replaying ----------------------------------------------------------------


def path_of(element: HtmlElement) -> str:
    """Where ``element`` sits, from ``<html>`` down: ``html>body>div.page>ol.row``.

    Each step is the tag and its first hand-written class -- the names induction
    gives fields, so a generated class never pins a path -- and ``[n]`` when a
    parent has more than one child of that tag and class.
    """
    steps: list[str] = []
    node: HtmlElement | None = element
    while node is not None and isinstance(node.tag, str):
        parent = node.getparent()
        label = _step_label(node)
        if parent is not None:
            same = [
                c for c in parent if isinstance(c.tag, str) and _step_label(c) == label
            ]
            if len(same) > 1:
                label += f"[{same.index(node) + 1}]"
        steps.append(label)
        node = parent
    return ">".join(reversed(steps))


def _step_label(element: HtmlElement) -> str:
    if element.tag in ("html", "body"):
        # Their classes are state, not structure: scripts swap ``no-js`` for
        # ``js`` and templates stamp the page type on ``<body>``.
        return str(element.tag)
    written = _label(element)
    return f"{element.tag}.{written}" if written else str(element.tag)


def _find(doc: Document, path: str) -> HtmlElement | None:
    steps = path.split(">")
    root = doc.tree
    if not steps or _step_label(root) != steps[0].split("[")[0]:
        return None
    node = root
    for step in steps[1:]:
        label, _, ordinal = step.partition("[")
        index = int(ordinal.rstrip("]")) - 1 if ordinal else 0
        same = [c for c in node if isinstance(c.tag, str) and _step_label(c) == label]
        if index >= len(same):
            return None
        node = same[index]
    return node


def _rows_of(members: list[HtmlElement], doc: Document) -> list[dict[str, str]]:
    rows = []
    for record in records_from(members):
        rows.append(
            {name: _value(name, f.value, doc) for name, f in record.fields.items()}
        )
    return rows


def _value(name: str, value: object, doc: Document) -> str:
    text = str(value)
    return absolute(doc, text) if "@" in name.rsplit(">", 1)[-1] else text


def _replay_listing(
    listing: Listing, doc: Document, checks: list[Check]
) -> list[dict[str, str]]:
    container = _find(doc, listing.container)
    if container is None:
        checks.append(
            Check("listing", f"the listing at {listing.container}", "not found", False)
        )
        return []
    checks.append(
        Check("listing", f"the listing at {listing.container}", "found", True)
    )
    members = [
        c for c in container if isinstance(c.tag, str) and kind(c) == listing.member
    ]
    by_path = {f.path: f.name for f in listing.fields}
    rows = (
        [
            {by_path[path]: value for path, value in row.items() if path in by_path}
            for row in _rows_of(members, doc)
        ]
        if members
        else []
    )
    fewest = max(1, math.ceil(listing.rows[0] / 2))
    enough = len(rows) >= fewest
    checks.append(Check("rows", f"at least {fewest} rows", str(len(rows)), enough))
    if not rows:
        return rows
    for f in listing.fields:
        values = [row.get(f.name) for row in rows]
        present = [v for v in values if v]
        if f.missing == 0:
            missing = 1 - len(present) / len(rows)
            ok = missing <= REQUIRED_MISSING
            checks.append(
                Check(
                    "field",
                    f"{f.name} in at least {1 - REQUIRED_MISSING:.0%} of rows",
                    f"in {1 - missing:.0%}",
                    ok,
                )
            )
        if f.shape and present:
            kept = sum(1 for v in present if shape(v) == f.shape) / len(present)
            example = next((v for v in present if shape(v) != f.shape), present[0])
            checks.append(
                Check(
                    "shape",
                    f"{f.name} shaped {f.shape} in at least {SHAPE_KEPT:.0%} of rows",
                    f"{kept:.0%}, e.g. {example!r}",
                    kept >= SHAPE_KEPT,
                )
            )
    return rows


# -- healing ------------------------------------------------------------------


def _heal_listing(
    old: Listing, new: Listing, pages: Sequence[Page]
) -> tuple[Listing, list[Change]]:
    changes: list[Change] = []
    if old.container != new.container:
        changes.append(Change("container", old.container, new.container))
    if old.member != new.member:
        changes.append(Change("member", old.member, new.member))
    values: dict[str, set[str]] = {f.path: set() for f in new.fields}
    for html, url in pages:
        doc = load(html, url=url)
        container = _find(doc, new.container)
        if container is None:
            continue
        members = [
            c for c in container if isinstance(c.tag, str) and kind(c) == new.member
        ]
        for row in _rows_of(members, doc) if members else []:
            for path, value in row.items():
                values.setdefault(path, set()).add(_comparable(path, value))
    fresh = {f.path: f for f in new.fields}
    claimed: dict[str, str] = {}
    for f in old.fields:
        if f.path in fresh:
            claimed[f.path] = f.name
            changes.append(Change("kept", f.name, f.path))
    scored = []
    for order, f in enumerate(old.fields):
        if f.path in fresh:
            continue
        for path, candidate in fresh.items():
            if path in claimed or _is_address(path) != _is_address(f.path):
                continue
            samples = {_comparable(f.path, sample) for sample in f.samples}
            seen = len(samples & values.get(path, set())) / max(1, len(samples))
            same_shape = f.shape is not None and f.shape == candidate.shape
            if seen == 0 and not same_shape:
                continue
            scored.append((-(seen * 10 + same_shape), order, path, f))
    matched: dict[str, str] = {}
    for _score, _order, path, f in sorted(scored, key=lambda s: (s[0], s[1], s[2])):
        if f.name in matched or path in claimed:
            continue
        claimed[path] = f.name
        matched[f.name] = path
    # Reported in the order the fields were learnt in, whatever order they
    # were matched in: best matches first is how to decide, not how to read.
    changes.extend(
        Change("moved", f.name, matched[f.name])
        for f in old.fields
        if f.name in matched
    )
    for f in old.fields:
        if f.path not in fresh and f.name not in matched:
            changes.append(Change("vanished", f.name, None))
    for path in fresh:
        if path not in claimed:
            changes.append(Change("new", None, path))
    taken = set(claimed.values())
    fields = tuple(
        ListingField(
            name=claimed.get(f.path, f.path),
            path=f.path,
            missing=f.missing,
            shape=f.shape,
            samples=f.samples,
        )
        for f in new.fields
        # A new column keeps its path as its name, unless a moved one took it.
        if f.path in claimed or f.path not in taken
    )
    position = {f.name: n for n, f in enumerate(old.fields)}
    fields = tuple(
        sorted(fields, key=lambda f: (position.get(f.name, len(position)), f.name))
    )
    return Listing(new.container, new.member, new.rows, fields), changes


def _comparable(path: str, value: str) -> str:
    """``value`` as heal compares it: an address by its path and query only.

    A page read from a file has no host to resolve against, and a site that
    moves its images to a new CDN has not moved a field.
    """
    if not _is_address(path):
        return value
    parts = urlsplit(value)
    return parts.path + ("?" + parts.query if parts.query else "")


def _is_address(path: str) -> bool:
    return "@" in path.rsplit(">", 1)[-1]
