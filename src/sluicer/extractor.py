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

import itertools
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from lxml.html import HtmlElement

from sluicer import __version__
from sluicer.api import extract
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import Document, base_url, join, load
from sluicer.normalise import amount, iso_date
from sluicer.structure.groups import chrome, repeating_groups
from sluicer.structure.records import _label, records_from
from sluicer.structure.shape import kind

FORMAT = 1
"""The version of the file format ``to_json`` writes and ``from_json`` reads."""

REQUIRED_MISSING = 0.2
"""The share of rows that may lack a field every learnt row carried."""

SHAPE_KEPT = 0.5
"""The share of a field's values that must keep the one shape it was learnt with."""

_SAMPLES = 5

# The fewest values a shape is learnt from and checked on.
_SHAPE_EVIDENCE = 5

# A field learnt in at least this share of rows must not vanish from all of them.
_COMMON = 0.5

# A field learnt with this many different values must not collapse to one,
# checked on pages of at least _SHAPE_EVIDENCE rows: three rows that say the
# same thing by chance -- three day-tables headed alike -- are no placeholder.
_VARIED = 3

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
    reads: str | None = None
    """``amount`` or ``date`` when every learnt value read as one (see
    ``sluicer.normalise``), which the shape alone cannot say: ``12.99`` and
    ``2025-01-02`` are both digits and punctuation, and two columns that swap
    them keep their shapes."""


@dataclass(frozen=True)
class Listing:
    """Where a page's repeated rows are, what one looks like, and what it holds.

    ``empty`` is the largest share of a learnt page's members that carried
    nothing -- a spacer, an ad slot of the same class -- so a page whose rows
    turned into empty shells is told from one that always had a few.
    """

    container: str
    member: str
    rows: tuple[int, int]
    fields: tuple[ListingField, ...]
    empty: float = 0.0
    chosen: bool = False
    """The columns were chosen by examples (``compile --want``): ``heal``
    finds the listing again by the values its columns held, and adds none."""


@dataclass(frozen=True)
class PageField:
    """One value a page holds once, found where an example pointed.

    ``path`` is the element's place, as a listing's container is written, and
    ``@name`` after it when the value is an attribute. ``reads`` is ``amount``
    or ``date`` when every learnt value read as one -- one is enough, since the
    person pointing at a price said it was one -- and ``shape`` is learnt as a
    listing field's is, from five values or more.
    """

    name: str
    path: str
    shape: str | None
    samples: tuple[str, ...]
    reads: str | None = None


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
    fields: tuple[PageField, ...] = ()
    """Values the page holds once, learnt from examples where it has no
    listing that holds them (``compile --want``)."""

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
                "empty": self.listing.empty,
                **({"chosen": True} if self.listing.chosen else {}),
                "fields": [
                    {
                        "name": f.name,
                        "path": f.path,
                        "missing": f.missing,
                        "shape": f.shape,
                        "reads": f.reads,
                        "samples": list(f.samples),
                    }
                    for f in self.listing.fields
                ],
            }
        if self.fields:
            body["fields"] = [
                {
                    "name": f.name,
                    "path": f.path,
                    "shape": f.shape,
                    "reads": f.reads,
                    "samples": list(f.samples),
                }
                for f in self.fields
            ]
        return json.dumps(body, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Extractor:
        """Read an extractor back from its file.

        Every key is checked, and its type: a file missing a part would replay
        as an extractor that checks nothing, which passes every page.

        Raises:
            ValueError: the text is not a whole extractor this version can read.
        """
        try:
            body = json.loads(text)
            return _extractor_of(body)
        except (KeyError, TypeError, IndexError, AttributeError) as broken:
            raise ValueError(f"not a whole sluicer extractor: {broken!r}") from None


def _extractor_of(body: Any) -> Extractor:
    if not isinstance(body, dict) or type(body.get("format")) is not int:
        raise ValueError("not a sluicer extractor")
    if body["format"] != FORMAT:
        raise ValueError(f"an extractor of format {body['format']}, not {FORMAT}")
    listing = None
    if body["listing"] is not None:
        raw = body["listing"]
        rows = [int(n) for n in raw["rows"]]
        if len(rows) != 2:
            raise ValueError("a listing's rows are the fewest and the most")
        listing = Listing(
            container=_text(raw["container"]),
            member=_text(raw["member"]),
            rows=(rows[0], rows[1]),
            # Absent from a 0.2 file, which learnt nothing about empty rows.
            empty=float(raw.get("empty", 0.0)),
            chosen=raw.get("chosen", False) is True,
            fields=tuple(
                ListingField(
                    name=_text(f["name"]),
                    path=_text(f["path"]),
                    missing=float(f["missing"]),
                    shape=None if f["shape"] is None else _text(f["shape"]),
                    # Absent from a 0.3 file, which learnt no reading.
                    reads=_reading(f.get("reads")),
                    samples=tuple(_text(v) for v in f["samples"]),
                )
                for f in raw["fields"]
            ),
        )
        if not listing.fields:
            raise ValueError("a listing with no fields checks nothing")
    summary = body["summary"]
    if not isinstance(summary, dict):
        raise ValueError("the summary is a mapping of question to shape")
    return Extractor(
        learnt_from=tuple(_text(v) for v in body["learnt_from"]),
        summary={
            _text(q): None if shp is None else _text(shp) for q, shp in summary.items()
        },
        types=tuple(_text(v) for v in body["types"]),
        listing=listing,
        notes=tuple(_text(v) for v in body.get("notes", [])),
        version=str(body.get("sluicer", "")),
        # Absent from a file with none, and from every file before 0.4.
        fields=tuple(
            PageField(
                name=_text(f["name"]),
                path=_text(f["path"]),
                shape=None if f["shape"] is None else _text(f["shape"]),
                reads=_reading(f.get("reads")),
                samples=tuple(_text(v) for v in f["samples"]),
            )
            for f in body.get("fields", [])
        ),
    )


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"expected text, found {value!r}")
    return value


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
    fields: dict[str, str] = field(default_factory=dict)
    """The page's own values, by the names the examples gave them."""


LOSSES = frozenset({"vanished", "summary-lost", "type-lost", "listing-lost"})
"""The kinds of change that are data the page no longer has."""


@dataclass(frozen=True)
class Change:
    """One difference ``heal`` found between the old extractor and the page.

    ``kind`` is one of container, member, kept, moved, new, summary-gained,
    type-gained, or one of ``LOSSES``: vanished, summary-lost, type-lost,
    listing-lost.
    """

    kind: str
    before: str | None
    after: str | None
    evidence: dict[str, int] | None = None
    """For a field kept or moved, what the match rests on: ``seen`` of the
    ``samples`` it was learnt with were found in the new place, and the next
    best place held ``runner_up`` of them. Reported, never used to decide: a
    close runner-up is a reason for a person to look, not for heal to guess."""


def shape(text: str) -> str:
    """The character classes a value is made of: L letters, N digits,
    P punctuation, S symbols such as currency signs, in that order.

    ``£51.77`` is ``NPS``, ``In stock`` is ``L``, ``2026-09-22`` is ``NP``.
    """
    classes = {unicodedata.category(char)[0] for char in text if not char.isspace()}
    return "".join(c for c in "LNPS" if c in classes)


def _fits(value: str, learnt: str) -> bool:
    """Whether ``value`` has the shape it was learnt with, or a part of it.

    ``42`` fits a price learnt as ``41.90``; ``Call us`` does not.
    """
    own = shape(value)
    return bool(own) and set(own) <= set(learnt)


def compile_extractor(
    pages: Sequence[Page],
    listing: bool | None = None,
    names: Sequence[str] | None = None,
    want: Mapping[str, str] | None = None,
) -> Extractor:
    """Learn an extractor from pages of one template.

    Args:
        pages: the pages, each as ``(html, url)``.
        listing: learn the listing the pages repeat. None, the default, learns
            one unless a page declares its own subject -- a product, an
            article -- whose page it is; True looks for one anyway.
        names: what to call each page in ``learnt_from``; its address by default.
        want: example values, by the name each is to have: ``{"price":
            "41.90", "title": "Brake pad set"}``. When a repeated group's rows
            hold every one -- the first such group, in page order -- they
            choose the listing and its columns, which are only the ones named.
            When no one group holds them all, or with ``listing=False``, they
            are the page's own values, a product page's price and title, each
            learnt where it sits on the page, the page's own place before its
            furniture and its listings. A value matches when it says the
            same with its spaces collapsed, or is the same amount.

    Raises:
        NothingToLearn: the pages declare nothing and repeat nothing, or no
            repeated group holds every example in ``want``.
        ValueError: ``want`` with ``listing=False``, or a name that is empty.
    """
    if not pages:
        raise NothingToLearn("an extractor needs at least one page")
    if want is not None and (not want or any(not name.strip() for name in want)):
        raise ValueError("every example needs a name and a value: name=value")
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
    # A page about one thing -- a product page, an article -- is read by what
    # it declares, and its related-items strip is not its listing. A listing
    # page declaring only a breadcrumb or an ItemList has no subject, so its
    # rows are learnt.
    has_a_subject = any(
        r.summary.get("type") is not None and r.summary["type"].key == "@type"
        for r in results
    )
    learnt: Listing | None = None
    notes: list[str] = []
    fields: tuple[PageField, ...] = ()
    if want and listing is False:
        fields, notes = _learn_fields(docs, want, None)
    elif want:
        try:
            learnt, notes = _learn_wanted(docs, want)
        except NothingToLearn as no_listing:
            # A product page that declares nothing: the examples are its own.
            fields, notes = _learn_fields(docs, want, no_listing)
    elif listing or (listing is None and not has_a_subject):
        learnt, notes = _learn_listing(docs)
    if listing and learnt is None:
        notes.append("no listing was found on these pages")
    if not summary and not types and learnt is None and not fields:
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
        fields=fields,
    )


def run_extractor(
    extractor: Extractor, html: str | bytes, url: str | None = None
) -> Run:
    """Replay ``extractor`` on one page and check it against what it learnt.

    An extractor that checks nothing fails: a run with no checks is a pass
    nobody could have earned.
    """
    doc = load(html, url=url)
    result = extract(html, url=url)
    run = Run(url=url, ok=True, summary={k: v.value for k, v in result.summary.items()})
    for question, learnt_shape in extractor.summary.items():
        answer = result.summary.get(question)
        if answer is None:
            run.checks.append(
                Check("summary", f"the summary answers {question}", "no answer", False)
            )
        elif learnt_shape and not _fits(answer.value, learnt_shape):
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
    if extractor.fields:
        run.fields = _replay_fields(extractor.fields, doc, run.checks)
    if not run.checks:
        run.checks.append(
            Check("extractor", "an extractor that checks something", "nothing", False)
        )
    run.ok = all(check.ok for check in run.checks)
    return run


def heal(
    extractor: Extractor,
    pages: Sequence[Page],
    names: Sequence[str] | None = None,
) -> tuple[Extractor, list[Change]]:
    """Learn ``pages`` again and match what moved to what ``extractor`` knew.

    Every old field is matched to at most one new place: the one holding most of
    the values it used to hold, else its own, when that still holds values of
    the old shape -- a listing's items change between visits. A numbered slot
    whose own place is still there never moves to another slot of its group:
    the third tag of a row is a count, and one tag turning up in another slot
    moved nothing. A field found in none of these ways is vanished, even if
    some new field has the same shape, because a guess would move the wrong
    column under the old name. A field that moved keeps its old name, so a row
    read with the healed extractor has the columns it always had.

    Returns:
        The healed extractor, and every change found, in a stable order. Any
        change in ``LOSSES`` is data the page no longer has.

    Raises:
        NothingToLearn: the new pages hold nothing an extractor could be
            learnt from -- no declared answer, no type, no listing.
    """
    old_listing = extractor.listing
    if old_listing is not None and old_listing.chosen:
        found = _learn_by_values(
            [load(html, url=url) for html, url in pages], old_listing
        )
        try:
            fresh = compile_extractor(pages, listing=False, names=names)
        except NothingToLearn:
            if found is None:
                raise
            fresh = Extractor(
                learnt_from=tuple(
                    (names[n - 1] if names else None) or url or f"page {n}"
                    for n, (_, url) in enumerate(pages, 1)
                ),
                summary={},
                types=(),
                listing=None,
            )
        fresh = Extractor(
            fresh.learnt_from, fresh.summary, fresh.types, found, fresh.notes
        )
    else:
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
    fields, field_changes = _heal_fields(
        extractor.fields, [load(html, url=url) for html, url in pages]
    )
    changes.extend(field_changes)
    listing = fresh.listing
    if extractor.listing is not None and listing is not None:
        listing, listing_changes = _heal_listing(extractor.listing, listing, pages)
        changes.extend(listing_changes)
    elif extractor.listing is not None:
        changes.append(Change("listing-lost", extractor.listing.container, None))
    healed = Extractor(
        learnt_from=fresh.learnt_from,
        summary=fresh.summary,
        types=fresh.types,
        listing=listing,
        notes=fresh.notes,
        fields=fields,
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
    found: list[tuple[str, str, list[HtmlElement], Document]] = []
    for doc in docs:
        group = _listing_of(doc)
        if group is not None:
            found.append((path_of(group[0].getparent()), kind(group[0]), group, doc))
    if not found:
        return None, []
    places = Counter((container, member) for container, member, _, _ in found)
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
    empty = 0.0
    for c, m, members, doc in found:
        if (c, m) != (container, member):
            continue
        page_rows = _rows_of(members, doc)
        counts.append(len(page_rows))
        rows.extend(page_rows)
        # Counted as a replay counts: every child of the learnt kind.
        replayed = _members(members[0].getparent(), member)
        if replayed:
            carried = len(_rows_of(replayed, doc))
            empty = max(empty, round(1 - carried / len(replayed), 4))
    paths = list(dict.fromkeys(path for row in rows for path in row))
    fields = tuple(
        _profile(path, path, [row.get(path) for row in rows]) for path in paths
    )
    rows_range = (min(counts), max(counts))
    return Listing(container, member, rows_range, fields, empty), notes


def _learn_wanted(
    docs: list[Document], want: Mapping[str, str]
) -> tuple[Listing, list[str]]:
    """The listing whose rows hold every example, and only the columns named.

    Groups are taken in each page's order, as ``repeating_groups`` ranks them;
    the first whose rows hold every example, on any page, is the listing, and
    each example's column is the first field, in row order, that held it.
    """
    chosen: tuple[str, str] | None = None
    columns: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    missing: set[str] = set(want)
    for doc in docs:
        for group in repeating_groups(doc.tree, furniture_too=True):
            group_rows = _rows_of(group, doc)
            if not group_rows:
                continue
            held = {
                name: _holding(group_rows, example) for name, example in want.items()
            }
            missing &= {name for name, paths in held.items() if not paths}
            if all(held.values()):
                chosen = (path_of(group[0].getparent()), kind(group[0]))
                columns = {name: paths[0] for name, paths in held.items()}
                ambiguous = {n: p for n, p in held.items() if len(p) > 1}
                break
        if chosen is not None:
            break
    if chosen is None:
        said = ", ".join(f"{name}={want[name]!r}" for name in sorted(missing) or want)
        raise NothingToLearn(
            f"no repeated group on these pages holds {said}"
            if missing
            else "no one repeated group holds every example together"
        )
    container, member = chosen
    rows: list[dict[str, str]] = []
    counts: list[int] = []
    empty = 0.0
    for doc in docs:
        found, _ = _find(doc, container)
        members = _members(found, member) if found is not None else []
        page_rows = _rows_of(members, doc) if members else []
        if not page_rows:
            continue
        counts.append(len(page_rows))
        rows.extend(page_rows)
        empty = max(empty, round(1 - len(page_rows) / len(members), 4))
    notes = [
        f"{name}={want[name]!r} was in {len(paths)} places in a row; "
        f"the first, {paths[0]}, was taken"
        for name, paths in ambiguous.items()
    ]
    if len(counts) < len(docs):
        notes.append(
            f"the listing is at {container} on {len(counts)} of {len(docs)} pages; "
            "the others were ignored"
        )
    fields = tuple(
        _profile(name, path, [row.get(path) for row in rows])
        for name, path in columns.items()
    )
    listing = Listing(
        container, member, (min(counts), max(counts)), fields, empty, chosen=True
    )
    return listing, notes


def _learn_by_values(docs: list[Document], old: Listing) -> Listing | None:
    """The listing, every column of it, whose rows hold most of ``old``'s values.

    How a listing learnt from examples is found again: by what it held, as it
    was first found, and in the furniture too. None when no group holds any.
    """
    samples = {sample for f in old.fields for sample in f.samples}
    best: tuple[int, str, str] | None = None
    for doc in docs:
        for group in repeating_groups(doc.tree, furniture_too=True):
            held = {value for row in _rows_of(group, doc) for value in row.values()}
            score = len(samples & held)
            if score and (best is None or score > best[0]):
                best = (score, path_of(group[0].getparent()), kind(group[0]))
    if best is None:
        return None
    _score, container, member = best
    rows: list[dict[str, str]] = []
    counts: list[int] = []
    empty = 0.0
    for doc in docs:
        found, _ = _find(doc, container)
        members = _members(found, member) if found is not None else []
        page_rows = _rows_of(members, doc) if members else []
        if page_rows:
            counts.append(len(page_rows))
            rows.extend(page_rows)
            empty = max(empty, round(1 - len(page_rows) / len(members), 4))
    # Never empty: the group was found on one of these pages, at this path.
    paths = list(dict.fromkeys(path for row in rows for path in row))
    fields = tuple(
        _profile(path, path, [row.get(path) for row in rows]) for path in paths
    )
    return Listing(container, member, (min(counts), max(counts)), fields, empty)


# Elements whose text is not the page's: a script's JSON can hold the price,
# and a path into it breaks with the next deploy.
_NOT_TEXT = frozenset({"script", "style", "noscript", "template", "head", "title"})
# Attributes that hold a page's values rather than its styling or wiring.
_VALUE_ATTRIBUTES = ("content", "href", "src", "alt", "title", "value", "datetime")
# The most elements looked at on one page for one example.
_MOST_ELEMENTS = 50_000


def _learn_fields(
    docs: list[Document], want: Mapping[str, str], no_listing: NothingToLearn | None
) -> tuple[tuple[PageField, ...], list[str]]:
    """Each example's place on the page itself, and what it held on every page.

    The place is the deepest element whose text is the example, or an
    attribute of one that is, on the first page that has it; every page is
    then read at that place.

    Raises:
        NothingToLearn: an example is on none of the pages, which names it,
            and why no listing held it either.
    """
    places: dict[str, str] = {}
    notes: list[str] = []
    for name, example in want.items():
        found = next((p for doc in docs if (p := _places(doc, example))), None)
        if found is None:
            also = f", and {no_listing}" if no_listing is not None else ""
            raise NothingToLearn(
                f"no element on these pages holds {name}={example!r}{also}"
            )
        if len(found) > 1:
            notes.append(
                f"{name}={example!r} was in {len(found)} places on the page; "
                f"the first, {found[0]}, was taken"
            )
        places[name] = found[0]
    fields = []
    for name, path in places.items():
        values = [v for doc in docs if (v := _value_at(doc, path))]
        if len(values) < len(docs):
            notes.append(f"{name} is at {path} on {len(values)} of {len(docs)} pages")
        present = list(dict.fromkeys(values))
        shapes = {shape(value) for value in values}
        reads = next(
            (r for r, read in _READERS.items() if all(read(v) for v in values)), None
        )
        fields.append(
            PageField(
                name=name,
                path=path,
                shape=shapes.pop()
                if len(shapes) == 1 and len(values) >= _SHAPE_EVIDENCE
                else None,
                samples=tuple(present[:_SAMPLES]),
                reads=None if _is_address(path) else reads,
            )
        )
    return tuple(fields), notes


def _places(doc: Document, example: str) -> list[str]:
    """Every place on the page whose value is ``example``, the deepest first.

    An element's text counts when it is the whole of the element's text; an
    ancestor that holds nothing else says the same, and is passed over for
    the element it holds. Then the attributes, in document order.
    """
    wanted = " ".join(example.split())
    worth = amount(wanted)
    base = base_url(doc)

    def same(text: str) -> bool:
        said = " ".join(text.split())
        return said == wanted or (worth is not None and amount(said) == worth)

    # Children before their parents, so a parent whose child's text is already
    # longer than the example -- the body, every wrapper up to it -- is passed
    # over without reading its text, which is the whole page's.
    elements = list(itertools.islice(doc.tree.iter(), _MOST_ELEMENTS))
    order = {element: n for n, element in enumerate(elements)}
    # Decided from the parent's answer, in one pass: climbing to the root for
    # every element is the depth times the size of a page nested deep.
    no_text: set[HtmlElement] = set()
    for element in elements:
        if element.tag in _NOT_TEXT or element.getparent() in no_text:
            no_text.add(element)
    room = 4 * len(wanted) + 256
    too_long: set[HtmlElement] = set()
    texts: list[HtmlElement] = []
    for element in reversed(elements):
        if not isinstance(element.tag, str):
            continue
        if any(child in too_long for child in element):
            too_long.add(element)
            continue
        text = element.text_content()
        if len(text) > room:
            too_long.add(element)
        elif element not in no_text and same(text):
            texts.append(element)
    texts.sort(key=order.__getitem__)
    attributes: list[str] = []
    for element in elements:
        if not isinstance(element.tag, str) or element in no_text:
            continue
        for attribute in _VALUE_ATTRIBUTES:
            value = element.get(attribute)
            if value is None:
                continue
            if attribute in ("href", "src"):
                value = join(base, value)
            if same(value):
                attributes.append(f"{path_of(element)}@{attribute}")
    holding = set(texts)
    deepest = [
        element
        for element in texts
        if not any(child in holding for child in element.iterdescendants())
    ]
    # The page's own place first: a product's title is also its breadcrumb's
    # last step and a related strip's link, both earlier in the document, and
    # neither is where a person pointing at the title means.
    repeated = {
        member
        for group in repeating_groups(doc.tree, furniture_too=True)
        for member in group
    }

    def aside(element: HtmlElement) -> tuple[bool, bool]:
        climb = [element, *element.iterancestors()]
        return (
            any(chrome(node) or _a_trail(node) for node in climb),
            any(node in repeated for node in climb),
        )

    ranked = sorted(range(len(deepest)), key=lambda n: (*aside(deepest[n]), n))
    return [path_of(deepest[n]) for n in ranked] + attributes


def _a_trail(element: HtmlElement) -> bool:
    """Whether ``element`` is a breadcrumb trail, by the name every CSS framework
    and the WAI's own breadcrumb pattern give one; its last step is the page's
    title, said again."""
    named = " ".join(
        element.get(attribute) or "" for attribute in ("class", "id", "aria-label")
    )
    return "breadcrumb" in named.lower()


def _value_at(doc: Document, path: str) -> str | None:
    """The value at a page field's place: its text, or the attribute named."""
    where, _, attribute = path.partition("@")
    element, _found = _find(doc, where)
    if element is None:
        return None
    if attribute:
        value = element.get(attribute)
        if value is None:
            return None
        if attribute in ("href", "src"):
            value = join(base_url(doc), value)
        return " ".join(value.split()) or None
    return " ".join(element.text_content().split()) or None


def _replay_fields(
    fields: tuple[PageField, ...], doc: Document, checks: list[Check]
) -> dict[str, str]:
    """Each page field's value, checked as it was learnt."""
    values: dict[str, str] = {}
    for f in fields:
        value = _value_at(doc, f.path)
        checks.append(
            Check(
                "field",
                f"{f.name} at {f.path}",
                "found" if value else "not found",
                value is not None,
            )
        )
        if value is None:
            continue
        values[f.name] = value
        if f.reads:
            read = _READERS[f.reads]
            checks.append(
                Check(
                    "reads",
                    f"{f.name} to read as {'an' if f.reads == 'amount' else 'a'} "
                    f"{f.reads}",
                    repr(value),
                    read(value) is not None,
                )
            )
        if f.shape:
            checks.append(
                Check(
                    "shape",
                    f"{f.name} shaped {f.shape}",
                    f"{value!r} ({shape(value) or 'empty'})",
                    _fits(value, f.shape),
                )
            )
    return values


def _holding(rows: list[dict[str, str]], example: str) -> list[str]:
    """Every field path, in row order, whose value is ``example`` in some row."""
    wanted = " ".join(example.split())
    worth = amount(wanted)
    found: dict[str, None] = {}
    for row in rows:
        for path, value in row.items():
            said = " ".join(value.split())
            if said == wanted or (worth is not None and amount(said) == worth):
                found.setdefault(path)
    return list(found)


def _first_index(
    found: list[tuple[str, str, list[HtmlElement], Document]], key: tuple[str, str]
) -> int:
    return next(n for n, (c, m, _, _) in enumerate(found) if (c, m) == key)


def _listing_of(doc: Document) -> list[HtmlElement] | None:
    """The page's most promising repeated group that yields records."""
    for group in repeating_groups(doc.tree):
        if records_from(group):
            return group
    return None


def _profile(name: str, path: str, values: list[str | None]) -> ListingField:
    present = [value for value in values if value]
    shapes = {shape(value) for value in present}
    # A shape learnt from a handful of values is a coincidence, not a rule.
    shaped = len(shapes) == 1 and len(present) >= _SHAPE_EVIDENCE
    return ListingField(
        name=name,
        path=path,
        missing=round(1 - len(present) / len(values), 4) if values else 1.0,
        shape=shapes.pop() if shaped and not _is_address(path) else None,
        samples=tuple(dict.fromkeys(present))[:_SAMPLES],
        reads=_reads(present) if not _is_address(path) else None,
    )


_READERS: dict[str, Callable[[str], str | None]] = {
    "amount": amount,
    "date": iso_date,
}


def _reads(values: list[str]) -> str | None:
    """What every one of ``values`` reads as, when there are enough to say."""
    if len(values) < _SHAPE_EVIDENCE:
        return None
    for reading, read in _READERS.items():
        if all(read(value) is not None for value in values):
            return reading
    return None


def _reading(declared: Any) -> str | None:
    if declared is None:
        return None
    if declared not in _READERS:
        raise ValueError(f"a field reads as amount or date, not {declared!r}")
    return str(declared)


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


def _find(doc: Document, path: str) -> tuple[HtmlElement | None, str]:
    """The element at ``path``, or None and why.

    A step written without ``[n]`` was the only one of its kind when learnt, so
    it must still be the only one: a second listing of the same kind inserted
    before it -- a sponsored strip -- is ambiguous, not the first match.
    """
    steps = path.split(">")
    root = doc.tree
    if _step_label(root) != steps[0].split("[")[0]:
        return None, "not found"
    node = root
    for step in steps[1:]:
        label, _, ordinal = step.partition("[")
        same = [c for c in node if isinstance(c.tag, str) and _step_label(c) == label]
        if not ordinal and len(same) > 1:
            return None, f"{len(same)} places that match {label}, where there was one"
        index = int(ordinal.rstrip("]")) - 1 if ordinal else 0
        if index >= len(same):
            return None, "not found"
        node = same[index]
    return node, "found"


def _members(container: HtmlElement, member: str) -> list[HtmlElement]:
    """The children that are rows: the learnt tag, carrying the learnt classes.

    A row that gains a class -- ``on-sale``, ``is-new`` -- is still a row.
    """
    tag, *classes = member.split(".")
    wanted = set(classes)
    return [
        child
        for child in container
        if isinstance(child.tag, str)
        and child.tag == tag
        and wanted <= set((child.get("class") or "").split())
    ]


def _rows_of(members: list[HtmlElement], doc: Document) -> list[dict[str, str]]:
    base = base_url(doc)
    rows = []
    for record in records_from(members):
        rows.append(
            {
                name: join(base, str(f.value)) if _is_address(name) else str(f.value)
                for name, f in record.fields.items()
            }
        )
    return rows


def _a_later_repeat(path: str, paths: set[str]) -> bool:
    """Whether ``path`` runs through the second or later of a slot the group
    numbered, at any step.

    ``div.tags>a.tag3`` is, when ``div.tags>a.tag1`` was learnt too; so is
    ``div.meta>span2>a@href``, the link in a row's second span, when anything
    under ``div.meta>span1`` was learnt. Found by the drift benchmark: a code
    host's trending rows hold a language, then stars, then forks, each a span,
    and a row with no language renumbers the rest.
    """
    head = path.partition("@")[0]
    steps = head.split(">")
    learnt = {other.partition("@")[0] for other in paths}
    for index, step in enumerate(steps):
        slot = _slot_number(step)
        if slot is None or slot[1] < 2:
            continue
        first = ">".join([*steps[:index], f"{slot[0]}1"])
        if any(other == first or other.startswith(first + ">") for other in learnt):
            return True
    return False


def _a_numbered_slot(path: str, paths: set[str]) -> bool:
    """Whether ``path`` runs through the first of a slot the group numbered.

    The first slot shows the group is there, so it is still held to some rows;
    not to every row, since a row with one item fewer shifts what the first
    slot holds: a language span, absent from a repository with no language,
    hands the first slot to the stars.
    """
    head = path.partition("@")[0]
    steps = head.split(">")
    learnt = {other.partition("@")[0] for other in paths}
    for index, step in enumerate(steps):
        slot = _slot_number(step)
        if slot is None or slot[1] != 1:
            continue
        second = ">".join([*steps[:index], f"{slot[0]}2"])
        if any(other == second or other.startswith(second + ">") for other in learnt):
            return True
    return False


def _slot_number(step: str) -> tuple[str, int] | None:
    """A step's name and the number induction gave it, or None if it has none.

    A bare heading's own digit is its tag, not a number: ``h2`` is not the
    second ``h``, and ``h23`` is the third ``h2``.
    """
    heading = re.fullmatch(r"(h[1-6])(\d*)", step)
    if heading:
        return (heading[1], int(heading[2])) if heading[2] else None
    digits = len(step) - len(step.rstrip("0123456789"))
    if not digits:
        return None
    return step[:-digits], int(step[-digits:])


def _slot_of(path: str) -> str:
    """The group a numbered slot belongs to: ``div.tags>a.tag`` for
    ``div.tags>a.tag3``, and ``path`` itself when it is not numbered."""
    head, at, attribute = path.partition("@")
    return head.rstrip("0123456789") + at + attribute


def _unnumbered(path: str) -> str:
    """``path`` as it reads whether or not the group's numbering shifted.

    Induction numbers a slot the moment one row repeats it, for the whole group:
    ``span.tag`` becomes ``span.tag1`` because one row gained a second tag, and
    ``div.flair>span>b.count`` becomes ``div.flair>span1>b.count`` because one
    row gained a second badge. Every step drops the ``1`` of a first slot; a
    second slot, ``span2``, stays apart.
    """
    head, at, attribute = path.partition("@")
    steps = [
        step[:-1] if step.endswith("1") and not step[-2:-1].isdigit() else step
        for step in head.split(">")
    ]
    return ">".join(steps) + at + attribute


def _replay_listing(
    listing: Listing, doc: Document, checks: list[Check]
) -> list[dict[str, str]]:
    container, found = _find(doc, listing.container)
    if container is None:
        checks.append(
            Check("listing", f"the listing at {listing.container}", found, False)
        )
        return []
    checks.append(Check("listing", f"the listing at {listing.container}", found, True))
    members = _members(container, listing.member)
    raw = _rows_of(members, doc) if members else []
    rows = []
    for row in raw:
        loose = {_unnumbered(path): value for path, value in row.items()}
        kept = {}
        for f in listing.fields:
            value = row.get(f.path, loose.get(_unnumbered(f.path)))
            if value is not None:
                kept[f.name] = value
        rows.append(kept)
    # Never zero; a short page of the same template -- the last of a
    # pagination, a small category -- is not a drift.
    checks.append(Check("rows", "at least 1 row", str(len(rows)), bool(rows)))
    if not rows:
        return rows
    if len(members) >= _SHAPE_EVIDENCE:
        # Skeletons waiting for a script are members with nothing in them: a
        # short page that is not short.
        empty = 1 - len(rows) / len(members)
        allowed = listing.empty + REQUIRED_MISSING
        checks.append(
            Check(
                "rows",
                f"at most {allowed:.0%} of the listing's members empty",
                f"{len(members) - len(rows)} of {len(members)} empty",
                empty <= allowed,
            )
        )
    paths = {f.path for f in listing.fields}
    for f in listing.fields:
        present = [row[f.name] for row in rows if row.get(f.name)]
        share = len(present) / len(rows)
        learnt = 1 - f.missing
        if _a_later_repeat(f.path, paths):
            # The third tag of a card is a count, not a column: pages differ in
            # how many their rows carry, and none of them has drifted.
            pass
        elif learnt == 1 and not _a_numbered_slot(f.path, paths):
            floor = 1 - REQUIRED_MISSING
            checks.append(
                Check(
                    "field",
                    f"{f.name} in at least {floor:.0%} of rows",
                    f"in {share:.0%}",
                    share >= floor,
                )
            )
        elif learnt >= _COMMON:
            # Most rows had it, and how many varies from page to page; gone from
            # every row is gone.
            checks.append(
                Check("field", f"{f.name} in some rows", f"in {share:.0%}", share > 0)
            )
        if f.reads and len(present) >= _SHAPE_EVIDENCE:
            read = _READERS[f.reads]
            readable = sum(1 for v in present if read(v) is not None) / len(present)
            unread = next((v for v in present if read(v) is None), present[0])
            checks.append(
                Check(
                    "reads",
                    f"{f.name} to read as {'an' if f.reads == 'amount' else 'a'} "
                    f"{f.reads} in at least {SHAPE_KEPT:.0%} of rows",
                    f"{readable:.0%}, e.g. {unread!r}",
                    readable >= SHAPE_KEPT,
                )
            )
        if f.shape and len(present) >= _SHAPE_EVIDENCE:
            kept_shape = sum(1 for v in present if _fits(v, f.shape)) / len(present)
            example = next((v for v in present if not _fits(v, f.shape)), present[0])
            checks.append(
                Check(
                    "shape",
                    f"{f.name} shaped {f.shape} in at least {SHAPE_KEPT:.0%} of rows",
                    f"{kept_shape:.0%}, e.g. {example!r}",
                    kept_shape >= SHAPE_KEPT,
                )
            )
        if len(f.samples) >= _VARIED and len(present) >= _SHAPE_EVIDENCE:
            distinct = len(set(present))
            checks.append(
                Check(
                    "values",
                    f"{f.name} to differ from row to row, as it did",
                    f"every row says {present[0]!r}" if distinct == 1 else "they do",
                    distinct > 1,
                )
            )
    return rows


# -- healing ------------------------------------------------------------------


def _heal_fields(
    old: tuple[PageField, ...], docs: list[Document]
) -> tuple[tuple[PageField, ...], list[Change]]:
    """Each page field where it still is, or where its old values are now.

    A field stays when its place still holds a value that reads as it did;
    otherwise it moves to where the new pages show one of its old values, the
    page's own place first, as it was learnt; a field found in neither way is
    vanished and kept out, since a guess would read the wrong value under the
    old name.
    """
    kept: list[PageField] = []
    changes: list[Change] = []
    for f in old:
        values = [v for doc in docs if (v := _value_at(doc, f.path))]
        read = _READERS[f.reads] if f.reads else None
        if values and (read is None or all(read(v) for v in values)):
            kept.append(_relearnt(f, f.path, values))
            continue
        moved = next(
            (
                place
                for sample in f.samples
                for doc in docs
                if (place := next(iter(_places(doc, sample)), None))
            ),
            None,
        )
        if moved is None:
            changes.append(Change("vanished", f.name, None))
            continue
        found = [v for doc in docs if (v := _value_at(doc, moved))]
        changes.append(Change("moved", f.name, moved))
        kept.append(_relearnt(f, moved, found))
    return tuple(kept), changes


def _relearnt(f: PageField, path: str, values: list[str]) -> PageField:
    """``f`` at ``path``, its samples those of the new pages, its reading kept."""
    shapes = {shape(v) for v in values}
    return PageField(
        name=f.name,
        path=path,
        shape=shapes.pop()
        if f.shape and len(shapes) == 1 and len(values) >= _SHAPE_EVIDENCE
        else None,
        samples=tuple(dict.fromkeys(values))[:_SAMPLES] or f.samples,
        reads=f.reads,
    )


def _heal_listing(
    old: Listing, new: Listing, pages: Sequence[Page]
) -> tuple[Listing, list[Change]]:
    changes: list[Change] = []
    if old.container != new.container:
        changes.append(Change("container", old.container, new.container))
    if old.member != new.member:
        changes.append(Change("member", old.member, new.member))
    values: dict[str, list[str]] = {f.path: [] for f in new.fields}
    for html, url in pages:
        doc = load(html, url=url)
        container, _found = _find(doc, new.container)
        if container is None:
            continue
        for row in _rows_of(_members(container, new.member), doc):
            for path, value in row.items():
                values.setdefault(path, []).append(_comparable(path, value))
    fresh = {f.path: f for f in new.fields}
    links = {
        path: _links_by_path(held) for path, held in values.items() if _is_address(path)
    }

    def seen_in(old_field: ListingField, path: str) -> int:
        """How many of the old field's samples ``path`` holds on the new pages."""
        samples = {_comparable(old_field.path, v) for v in old_field.samples}
        if _is_address(path) != _is_address(old_field.path):
            return 0
        if _is_address(path):
            return sum(1 for v in samples if _a_link_in(v, links.get(path, {})))
        held = set(values.get(path, []))
        return sum(1 for v in samples if v in held)

    def overlap(old_field: ListingField, path: str) -> float:
        samples = {_comparable(old_field.path, v) for v in old_field.samples}
        return seen_in(old_field, path) / len(samples) if samples else 0.0

    def still_there(old_field: ListingField) -> bool:
        # Its own place, holding values of the shape it was learnt with: a
        # listing's items change between two visits, and that is no move.
        held = [v for v in values.get(old_field.path, []) if v]
        if not held or old_field.shape is None:
            return bool(held)
        fitting = sum(1 for v in held if _fits(v, old_field.shape))
        return fitting / len(held) >= SHAPE_KEPT

    # Every candidate pairing, best first: the values an old field held, seen
    # again in a new place. The same place counts only as one candidate among
    # the others, so two columns that swapped are two moves, not two keeps; and
    # it is the last candidate when it holds new values of the old shape. Of
    # two places that hold as much, the one more rows carry: a name that is
    # both a heading and an icon's alt text is the heading, since not every
    # row has an icon.
    scored = []
    for order, f in enumerate(old.fields):
        for path in fresh:
            numbered = _slot_of(f.path) != f.path
            sibling = path != f.path and _slot_of(path) == _slot_of(f.path)
            if numbered and sibling and still_there(f):
                # The third tag or author of a row is a count, not a column:
                # one tag or author turning up in another slot moved nothing.
                continue
            seen = overlap(f, path)
            same_place = path == f.path
            if seen > 0 or (same_place and (not f.samples or still_there(f))):
                missing = fresh[path].missing
                scored.append((-seen, not same_place, missing, order, path, f))
    claimed: dict[str, str] = {}
    matched: dict[str, str] = {}
    for *_rank, path, f in sorted(scored, key=lambda s: s[:5]):
        if f.name in matched or path in claimed:
            continue
        claimed[path] = f.name
        matched[f.name] = path
    for f in old.fields:
        if f.name not in matched:
            continue
        kind_ = "kept" if matched[f.name] == f.path else "moved"
        others = [seen_in(f, path) for path in fresh if path != matched[f.name]]
        evidence = {
            "seen": seen_in(f, matched[f.name]),
            "samples": len({_comparable(f.path, v) for v in f.samples}),
            "runner_up": max(others, default=0),
        }
        changes.append(Change(kind_, f.name, matched[f.name], evidence))
    for f in old.fields:
        if f.name not in matched:
            changes.append(Change("vanished", f.name, None))
    for path in fresh:
        if path not in claimed and not old.chosen:
            changes.append(Change("new", None, path))
    taken = set(claimed.values())
    fields = tuple(
        ListingField(
            name=claimed.get(f.path, f.path),
            path=f.path,
            missing=f.missing,
            shape=f.shape,
            samples=f.samples,
            reads=f.reads,
        )
        for f in new.fields
        # A new column keeps its path as its name, unless a moved one took it;
        # a listing whose columns were chosen gains none.
        if f.path in claimed or (f.path not in taken and not old.chosen)
    )
    position = {f.name: n for n, f in enumerate(old.fields)}
    fields = tuple(
        sorted(fields, key=lambda f: (position.get(f.name, len(position)), f.name))
    )
    listing = Listing(
        new.container, new.member, new.rows, fields, new.empty, chosen=old.chosen
    )
    return listing, changes


def _comparable(path: str, value: str) -> str:
    """``value`` as heal compares it: an address by its path and query only.

    A page read from a file has no host to resolve against, a relative link
    read from one keeps no leading slash, and a site that moves its images to a
    new CDN has not moved a field.
    """
    if not _is_address(path):
        return value
    parts = urlsplit(value)
    kept = parts.path + ("?" + parts.query if parts.query else "")
    while kept.startswith(("./", "/")):
        kept = kept[2:] if kept.startswith("./") else kept[1:]
    return kept


def _links_by_path(held: list[str]) -> dict[str, list[frozenset[str]]]:
    """Comparable addresses by their path, each as the set of its parameters."""
    by_path: dict[str, list[frozenset[str]]] = {}
    for value in held:
        path, _, query = value.partition("?")
        by_path.setdefault(path, []).append(frozenset(query.split("&")) - {""})
    return by_path


def _a_link_in(value: str, by_path: dict[str, list[frozenset[str]]]) -> bool:
    """Whether ``value`` is among the addresses: the same path, and all the
    parameters of one among the other's. A site that tags every link with
    ``?ref_=list_1`` has not changed where its links go; ``?id=2`` is another
    item than ``?id=1``."""
    path, _, query = value.partition("?")
    mine = frozenset(query.split("&")) - {""}
    return any(mine <= theirs or theirs <= mine for theirs in by_path.get(path, ()))


def _is_address(path: str) -> bool:
    """Whether a field holds an address: induction names those ``...@href``."""
    return "@" in path.rsplit(">", 1)[-1]
