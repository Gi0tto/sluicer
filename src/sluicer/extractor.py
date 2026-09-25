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

import bisect
import itertools
import json
import re
import unicodedata
import weakref
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from lxml import etree
from lxml.html import HtmlElement

from sluicer import __version__
from sluicer.api import _extract_document
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import Document, base_url, join, load
from sluicer.normalise import amount, iso_date
from sluicer.structure.groups import chrome, repeating_groups
from sluicer.structure.records import _label, records_from
from sluicer.structure.shape import kind

if TYPE_CHECKING:
    from sluicer.written import Written

FORMAT = 1
"""The version of the file format ``to_json`` writes and ``from_json`` reads."""
FORMAT_WITH_LABELS = 2
"""The format of a file with a field read by its label, ``Anchor``."""
FORMAT_WRITTEN = 3
"""The format of a file whose fields a person wrote as selectors (see
``sluicer.written``), which a reader of formats 1 and 2 refuses: it would
check the page against none of them."""

REQUIRED_MISSING = 0.2
"""The share of rows that may lack a field every learnt row carried."""

SHAPE_KEPT = 0.5
"""The share of a field's values that must keep the one shape it was learnt with."""

_SAMPLES = 5

# The fewest values a shape is learnt from and checked on.
_SHAPE_EVIDENCE = 5

# The share of one column's old values a group must hold to be where a listing
# chosen by examples went.
_HELD_AGAIN = 0.5

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
    siblings: tuple[int | None, ...] = ()
    """For each step of ``container`` below ``<html>``, how many elements
    matched it on every page learnt, or None where the pages differed. A
    numbered step, ``section.box[2]``, is only the second box while there are
    as many boxes: a box of the same kind inserted before it makes another
    the second. Empty for a file from before 0.7.1, which learnt none."""
    marks: tuple[str | None, ...] = ()
    """For each step of ``container`` below ``<html>``, where it is numbered,
    the text the element there began with, its rows aside -- a box's
    heading, "Books" -- when it did on every page learnt and no other element
    of its kind did; None elsewhere. An element that begins so is the one
    learnt, however many of its kind the page now has; one that does not,
    while another of its kind does, is another. Empty when there is none,
    and for a file from before 0.7.1."""


@dataclass(frozen=True)
class Anchor:
    """Where a page field is found by the template's own words rather than by
    its place: the text a label on every page, once.

    ``kind`` is ``after``, the text that follows the label's, as in
    ``<th>Price:</th><td>$9.99</td>`` or ``<b>ISBN:</b> 978...``; or ``prefix``,
    the rest of the text the label opens, as in ``<li>Pages: 310</li>``.
    """

    label: str
    kind: str


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
    anchor: Anchor | None = None
    """Set when the pages given contradicted the place, or no element held the
    value alone: the field is then read by its label, and ``path`` is where the
    example was."""
    label: str | None = None
    """For a field read by its place, the text every page it was learnt from
    put right before its value, once: a page that says it once, before
    something else, moved the value -- a table's rows in another order -- and
    fails. None when one page taught it, or the value is an attribute, or the
    pages put different words before it."""


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
    written: Written | None = None
    """Fields a person named by selector, and the rows they are read in
    (``compile --select``), in place of a learnt listing and page fields."""

    def to_json(self) -> str:
        """The extractor as the JSON file it is kept in, stable key order."""
        body: dict[str, Any] = {
            # A file whose fields are read by a label is format 2, which a
            # reader of format 1 refuses: it would read the place alone.
            "format": FORMAT_WRITTEN
            if self.written is not None
            else FORMAT_WITH_LABELS
            if any(f.anchor for f in self.fields)
            else FORMAT,
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
                **(
                    {"siblings": list(self.listing.siblings)}
                    if self.listing.siblings
                    else {}
                ),
                **({"marks": list(self.listing.marks)} if self.listing.marks else {}),
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
                    **(
                        {"anchor": {"label": f.anchor.label, "kind": f.anchor.kind}}
                        if f.anchor
                        else {}
                    ),
                    **({"label": f.label} if f.label else {}),
                }
                for f in self.fields
            ]
        if self.written is not None:
            from sluicer.written import written_json

            body["select"] = written_json(self.written)
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
    if body["format"] not in (FORMAT, FORMAT_WITH_LABELS, FORMAT_WRITTEN):
        raise ValueError(
            f"an extractor of format {body['format']}, "
            f"not {FORMAT}, {FORMAT_WITH_LABELS} or {FORMAT_WRITTEN}"
        )
    written = None
    if body["format"] == FORMAT_WRITTEN or "select" in body:
        from sluicer.written import written_of

        if body["format"] != FORMAT_WRITTEN:
            raise ValueError("a file of hand-written selectors is format 3")
        if body.get("listing") is not None or body.get("fields"):
            raise ValueError(
                "a hand-written extractor's fields are its selectors: it holds "
                "no learnt listing or page fields beside them"
            )
        written = written_of(body["select"])
        # A file written by hand needs only its selectors.
        body = {"learnt_from": [], "summary": {}, "types": [], "listing": None, **body}
    listing = None
    if body["listing"] is not None:
        listing = _listing_of_file(body["listing"])
    summary = body["summary"]
    if not isinstance(summary, dict):
        raise ValueError("the summary is a mapping of question to shape")
    fields = tuple(
        PageField(
            name=_text(f["name"]),
            path=_path(f["path"], attribute=True),
            shape=_shape(f["shape"]),
            reads=_reading(f.get("reads")),
            samples=tuple(_text(v) for v in _list(f["samples"], "samples")),
            anchor=_anchor_of(f.get("anchor")),
            # Absent from a file before 0.7.1, which learnt none.
            label=None if f.get("label") is None else _text(f["label"]),
        )
        # Absent from a file with none, and from every file before 0.4.
        for f in _list(body.get("fields", []), "fields")
    )
    _unique(f.name for f in fields)
    return Extractor(
        learnt_from=tuple(_text(v) for v in _list(body["learnt_from"], "learnt_from")),
        summary={_text(q): _shape(shp) for q, shp in summary.items()},
        types=tuple(_text(v) for v in _list(body["types"], "types")),
        listing=listing,
        notes=tuple(_text(v) for v in _list(body.get("notes", []), "notes")),
        version=str(body.get("sluicer", "")),
        fields=fields,
        written=written,
    )


def _listing_of_file(raw: Any) -> Listing:
    """A listing as its file holds it, every value checked: a value no check
    can be true of -- ``"missing": "nan"`` -- turns the check off without a
    word, and a run then passes a page it should fail."""
    rows = _list(raw["rows"], "rows")
    if (
        len(rows) != 2
        or any(type(n) is not int for n in rows)
        or not 0 <= rows[0] <= rows[1]
    ):
        raise ValueError(f"a listing's rows are the fewest and the most, not {rows!r}")
    container = _path(raw["container"])
    member = _text(raw["member"])
    if not _MEMBER.fullmatch(member):
        raise ValueError(f"{member!r} is not a row's kind, a tag and its classes")
    chosen = raw.get("chosen", False)
    if type(chosen) is not bool:
        raise ValueError(f"chosen is true or false, not {chosen!r}")
    siblings = _list(raw.get("siblings", []), "siblings")
    if siblings and (
        len(siblings) != container.count(">")
        or any(n is not None and (type(n) is not int or n < 1) for n in siblings)
    ):
        raise ValueError(
            "siblings are a count of one or more, or null, for each step of the "
            f"container below html, not {siblings!r}"
        )
    marks = _list(raw.get("marks", []), "marks")
    if marks and (
        len(marks) != container.count(">")
        or any(m is not None and (type(m) is not str or not m) for m in marks)
        or all(m is None for m in marks)
    ):
        raise ValueError(
            "marks are a text, or null, for each step of the container below "
            f"html, one text at least, not {marks!r}"
        )
    listing = Listing(
        container=container,
        member=member,
        rows=(rows[0], rows[1]),
        # Absent from a 0.2 file, which learnt nothing about empty rows.
        empty=_share(raw.get("empty", 0.0), "empty"),
        chosen=chosen,
        siblings=tuple(siblings),
        marks=tuple(marks),
        fields=tuple(
            ListingField(
                name=_text(f["name"]),
                path=_text(f["path"]),
                missing=_share(f["missing"], "missing"),
                shape=_shape(f["shape"]),
                # Absent from a 0.3 file, which learnt no reading.
                reads=_reading(f.get("reads")),
                samples=tuple(_text(v) for v in _list(f["samples"], "samples")),
            )
            for f in _list(raw["fields"], "fields")
        ),
    )
    if not listing.fields:
        raise ValueError("a listing with no fields checks nothing")
    _unique(f.name for f in listing.fields)
    return listing


# A step of a path: a tag and its first class, and [n] when it was one of n.
_STEP = r"[^\s\[\]>@]+(?:\[[1-9][0-9]*\])?"
_PATH = re.compile(rf"{_STEP}(?:>{_STEP})*")
_MEMBER = re.compile(r"[^\s\[\]>@.]+(?:\.[^\s\[\]>@.]+)*")


def _path(value: Any, attribute: bool = False) -> str:
    """A place as ``path_of`` writes it, and ``@name`` after it when allowed."""
    text = _text(value)
    where, at, name = text.partition("@") if attribute else (text, "", "")
    if not _PATH.fullmatch(where) or (at and not re.fullmatch(r"[\w:-]+", name)):
        raise ValueError(f"{text!r} is not a path to an element")
    return text


def _share(value: Any, what: str) -> float:
    """A share learnt of the rows, a number from 0 to 1."""
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError(f"{what} is a share from 0 to 1, not {value!r}")
    return float(value)


def _shape(value: Any) -> str | None:
    """A shape as ``shape`` writes it, or None for none."""
    if value is None:
        return None
    text = _text(value)
    if not set(text) <= set("LNPS"):
        raise ValueError(f"a shape is made of L, N, P and S, not {text!r}")
    return text


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{what} is a list, not {value!r}")
    return value


def _unique(names: Any) -> None:
    """Two fields of one name would read as one, the second over the first."""
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"two fields named {name!r}")
        seen.add(name)


def _anchor_of(raw: Any) -> Anchor | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"a label is read after or as a prefix, not {raw!r}")
    anchor = Anchor(label=_text(raw["label"]), kind=_text(raw["kind"]))
    if anchor.kind not in ("after", "prefix") or not anchor.label:
        raise ValueError(f"a label is read after or as a prefix, not {raw!r}")
    return anchor


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


LOSSES = frozenset(
    {"vanished", "summary-lost", "type-lost", "listing-lost", "ambiguous", "broken"}
)
"""The kinds of change that stop heal from writing: data the page no longer
has, a move two places had equal claim to, or a selector a person wrote that
the page broke, which a person decides."""


@dataclass(frozen=True)
class Change:
    """One difference ``heal`` found between the old extractor and the page.

    ``kind`` is one of container, member, kept, moved, new, summary-gained,
    type-gained, or one of ``LOSSES``: vanished, summary-lost, type-lost,
    listing-lost, ambiguous -- a move two new places had equal claim to, left
    out of the healed extractor for a person to decide -- or broken, a
    hand-written field, or the rows, whose selector the page no longer bears
    out, kept as written for a person to rewrite.
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

    ``£51.77`` is ``NPS``, ``In stock`` is ``L``, ``2026-09-22`` is ``NP``. A
    value of none of them -- a combining accent alone -- is the empty shape,
    which says nothing, and no field or answer is learnt with it.
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
    select: Mapping[str, str] | None = None,
    rows: str | None = None,
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
            hold every one, each in a column of its own -- the first such
            group, in page order -- they choose the listing and its columns,
            which are only the ones named.
            When no one group holds them all, or with ``listing=False``, they
            are the page's own values, a product page's price and title, each
            learnt where it sits on the page, the page's own place before its
            furniture and its listings. A value matches when it says the
            same with its spaces collapsed, or is the same amount.
        select: fields a person writes instead of examples, by the name each
            is to have: ``{"title": "h1", "price": "span.price::text"}``, each
            a selector, CSS or XPath (see ``sluicer.selectors.selector``).
            Nothing is learnt of where they are; from the pages, if any are
            given, each field's presence, shape and reading is, and what the
            pages declare. A selector that gives nothing on a page it is
            written from is an error that names it.
        rows: with ``select``, the selector of a listing's rows, each field
            then read inside each row: ``li.product``, and ``.//a`` for an
            XPath inside it.

    Raises:
        NothingToLearn: the pages declare nothing and repeat nothing, or no
            repeated group holds every example in ``want``, or a selector in
            ``select`` gives nothing on a page given.
        SelectorError: a selector in ``select`` or ``rows`` cannot be read;
            a ``ValueError``.
        ValueError: ``want`` with ``listing=False``, or a name that is empty;
            ``select`` with ``want`` or ``listing``, or ``rows`` without it.
    """
    if select is not None or rows is not None:
        if want is not None or listing is not None or select is None:
            raise ValueError(
                "select= names the fields by selector and rows= their listing's "
                "rows; want= and listing= are the learnt way, and one is chosen"
            )
        from sluicer.written import compile_written

        return compile_written(pages, select, rows, names)
    if not pages:
        raise NothingToLearn("an extractor needs at least one page")
    if want is not None and (not want or any(not name.strip() for name in want)):
        raise ValueError("every example needs a name and a value: name=value")
    return _compiled([load(html, url=url) for html, url in pages], listing, names, want)


def _compiled(
    docs: list[Document],
    listing: bool | None,
    names: Sequence[str] | None,
    want: Mapping[str, str] | None,
) -> Extractor:
    """``compile_extractor`` of pages parsed once, for it and for ``heal``."""
    results = [_extract_document(doc, {}) for doc in docs]
    summary = _learn_summary([r.summary for r in results], len(docs))
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
        learnt_from=_learnt_from(docs, names),
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
    result = _extract_document(doc, {})
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
    if extractor.written is not None:
        from sluicer.written import replay_written

        run.rows, run.fields = replay_written(extractor.written, doc, run.checks)
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
    docs = [load(html, url=url) for html, url in pages]
    old_listing = extractor.listing
    if extractor.written is not None:
        # A hand-written extractor learns only what the pages declare: its
        # selectors say where the rest is.
        try:
            fresh = _compile_again(docs, False, names)
        except NothingToLearn:
            fresh = _learnt_nothing(docs, names)
    elif old_listing is not None and old_listing.chosen:
        # Where it was, while it still keeps its contract there: a listing's
        # items change from one visit to the next, and a sidebar that lists
        # some of the same ones is not where it went.
        found = _still_listed(docs, old_listing) or _learn_by_values(docs, old_listing)
        try:
            fresh = _compile_again(docs, False, names)
        except NothingToLearn:
            if found is None:
                raise
            fresh = _learnt_nothing(docs, names)
        fresh = Extractor(
            fresh.learnt_from, fresh.summary, fresh.types, found, fresh.notes
        )
    else:
        try:
            fresh = _compile_again(docs, True if extractor.listing else None, names)
        except NothingToLearn:
            # Page fields are looked for by their own values, on pages that
            # declare nothing and repeat nothing as much as on any other.
            if not extractor.fields:
                raise
            fresh = _learnt_nothing(docs, names)
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
    fields, field_changes = _heal_fields(extractor.fields, docs)
    changes.extend(field_changes)
    listing = fresh.listing
    if extractor.listing is not None and listing is not None:
        listing, listing_changes = _heal_listing(extractor.listing, listing, docs)
        changes.extend(listing_changes)
    elif extractor.listing is not None:
        changes.append(Change("listing-lost", extractor.listing.container, None))
        # Kept as it was, so a run keeps failing where it is not: an
        # extractor written without it, with --force, would pass every page.
        listing = extractor.listing
    written = extractor.written
    if written is not None:
        from sluicer.written import heal_written

        written, written_changes = heal_written(written, docs)
        changes.extend(written_changes)
    healed = Extractor(
        learnt_from=fresh.learnt_from,
        summary=fresh.summary,
        types=fresh.types,
        listing=listing,
        notes=fresh.notes,
        fields=fields,
        written=written,
    )
    return healed, changes


def _compile_again(
    docs: list[Document], listing: bool | None, names: Sequence[str] | None
) -> Extractor:
    """``compile_extractor`` as heal asks it, on pages it has parsed already."""
    if not docs:
        raise NothingToLearn("an extractor needs at least one page")
    return _compiled(docs, listing, names, None)


def _learnt_from(docs: list[Document], names: Sequence[str] | None) -> tuple[str, ...]:
    """What each page is called: its name, else its address, else its place."""
    return tuple(
        (names[n - 1] if names else None) or doc.url or f"page {n}"
        for n, doc in enumerate(docs, 1)
    )


def _learnt_nothing(docs: list[Document], names: Sequence[str] | None) -> Extractor:
    """An extractor of ``docs`` that learnt nothing from them."""
    return Extractor(
        learnt_from=_learnt_from(docs, names),
        summary={},
        types=(),
        listing=None,
    )


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
        learnt[question] = (shapes.pop() or None) if keep else None
    return learnt


def _learn_listing(docs: list[Document]) -> tuple[Listing | None, list[str]]:
    found: list[tuple[str, str, list[HtmlElement], Document]] = []
    for doc in docs:
        group = _listing_of(doc)
        if group is not None:
            found.append(
                (path_of(group[0].getparent()), _kind_of(group[0]), group, doc)
            )
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
    learnt_on = [doc for c, m, _, doc in found if (c, m) == (container, member)]
    return Listing(
        container,
        member,
        rows_range,
        fields,
        empty,
        siblings=_siblings(learnt_on, container),
        marks=_marks(learnt_on, container, member),
    ), notes


def _learn_wanted(
    docs: list[Document], want: Mapping[str, str]
) -> tuple[Listing, list[str]]:
    """The listing whose rows hold every example, and only the columns named.

    Groups are taken in each page's order, as ``repeating_groups`` ranks them;
    the first whose rows hold every example, each in a column of its own, on
    any page, is the listing, and each example's column is the first field, in
    row order, that held it and no example before it needs. Two examples one
    column holds are no listing's: a product's table has its price and its SKU
    in two rows of one ``td``, and read as a listing both would be that ``td``.
    """
    chosen: tuple[str, str] | None = None
    columns: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    missing: set[str] = set(want)
    for doc in docs:
        for group in _groups(doc):
            group_rows = _rows_of(group, doc)
            if not group_rows:
                continue
            held = {
                name: _holding(group_rows, example) for name, example in want.items()
            }
            missing &= {name for name, paths in held.items() if not paths}
            own = _columns_of(held) if all(held.values()) else None
            if own is not None:
                chosen = (path_of(group[0].getparent()), _kind_of(group[0]))
                columns = own
                ambiguous = {n: p for n, p in held.items() if len(p) > 1}
                break
        if chosen is not None:
            break
    if chosen is None:
        said = ", ".join(f"{name}={want[name]!r}" for name in sorted(missing) or want)
        raise NothingToLearn(
            f"no repeated group on these pages holds {said}"
            if missing
            else "no one repeated group holds every example together, "
            "each in a column of its own"
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
        + (
            f"the first, {paths[0]}, was taken"
            if columns[name] == paths[0]
            else f"{columns[name]}, the first no other example needs, was taken"
        )
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
        container,
        member,
        (min(counts), max(counts)),
        fields,
        empty,
        chosen=True,
        siblings=_siblings(docs, container),
        marks=_marks(docs, container, member),
    )
    return listing, notes


def _columns_of(held: Mapping[str, list[str]]) -> dict[str, str] | None:
    """Each example's column, none shared, or None when they cannot all have
    one. Each takes, in turn, the first of the places that held it, in row
    order, that is free, else one an example before it can give up for
    another of its own: a matching, found in polynomial time however the
    places overlap."""
    owner: dict[str, str] = {}

    def claim(name: str, seen: set[str]) -> bool:
        free = next((p for p in held[name] if p not in owner), None)
        if free is not None:
            owner[free] = name
            return True
        for path in held[name]:
            if path in seen:
                continue
            seen.add(path)
            if claim(owner[path], seen):
                owner[path] = name
                return True
        return False

    for name in held:
        if not claim(name, set()):
            return None
    column = {name: path for path, name in owner.items()}
    return {name: column[name] for name in held}


def _still_listed(docs: list[Document], old: Listing) -> Listing | None:
    """``old`` learnt again where it is, when every page given that has its
    place replays it with no check failed, and one page at least does."""
    held = False
    for doc in docs:
        if _locate(doc, old)[0] is None:
            continue
        checks: list[Check] = []
        _replay_listing(old, doc, checks)
        if not all(check.ok for check in checks):
            return None
        held = True
    return _listing_at(docs, old.container, old.member) if held else None


def _learn_by_values(docs: list[Document], old: Listing) -> Listing | None:
    """The listing, every column of it, whose rows hold most of ``old``'s values.

    How a listing learnt from examples is found again: by what it held, as it
    was first found, and in the furniture too. A group qualifies only when it
    holds at least half of one column's old values: one related product that
    costs what a book used to is a coincidence, not where the books went.
    None when no group qualifies.
    """
    samples = {sample for f in old.fields for sample in f.samples}
    columns = [set(f.samples) for f in old.fields if f.samples]
    best: tuple[int, str, str] | None = None
    for doc in docs:
        for group in _groups(doc):
            held = {value for row in _rows_of(group, doc) for value in row.values()}
            score = len(samples & held)
            again = any(len(c & held) >= _HELD_AGAIN * len(c) for c in columns)
            if score and again and (best is None or score > best[0]):
                best = (score, path_of(group[0].getparent()), _kind_of(group[0]))
    if best is None:
        return None
    _score, container, member = best
    return _listing_at(docs, container, member)


def _listing_at(docs: list[Document], container: str, member: str) -> Listing:
    """The listing at ``container``, rows of ``member``, every column of it, as
    the pages that have it hold it. One of them must."""
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
    return Listing(
        container,
        member,
        (min(counts), max(counts)),
        fields,
        empty,
        siblings=_siblings(docs, container),
        marks=_marks(docs, container, member),
    )


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
    then read at that place. When the other pages given contradict the place
    -- it holds nothing on one, or a value that does not read as the example
    does -- or no element holds the example alone, the field is read after
    the label every page puts before it, when there is one.

    Raises:
        NothingToLearn: an example is on none of the pages, which names it,
            and why no listing held it either.
    """
    notes: list[str] = []
    fields = []
    for name, example in want.items():
        found = next((p for doc in docs if (p := _places(doc, example))), None)
        path = found[0] if found else ""
        against = _contradicted(docs, path, example) if found else None
        anchored = _anchor_for(docs, example) if found is None or against else None
        if found is None and anchored is None:
            also = f", and {no_listing}" if no_listing is not None else ""
            raise NothingToLearn(
                f"no element on these pages holds {name}={example!r}{also}"
            )
        anchor = None
        label = None
        if anchored is not None:
            anchor, where = anchored
            texts = [_text_nodes(doc) for doc in docs]
            values = [v for nodes in texts if (v := _value_after(nodes, anchor)[0])]
            notes.append(
                f"{name}={example!r} is read after the label {anchor.label!r}: "
                + (
                    f"at {path} the pages given also held {against}"
                    if found
                    else "no element holds it alone"
                )
            )
            path = path or where
        else:
            if found is not None and len(found) > 1:
                notes.append(
                    f"{name}={example!r} was in {len(found)} places on the page; "
                    f"the first, {found[0]}, was taken"
                )
            values = [v for doc in docs if (v := _value_at(doc, path))]
            if len(values) < len(docs):
                notes.append(
                    f"{name} is at {path} on {len(values)} of {len(docs)} pages"
                )
            label = _label_before(docs, path)
        present = list(dict.fromkeys(values))
        shapes = {shape(value) for value in values}
        reads = next(
            (r for r, read in _READERS.items() if all(read(v) for v in values)), None
        )
        fields.append(
            PageField(
                name=name,
                path=path,
                shape=(shapes.pop() or None)
                if len(shapes) == 1 and len(values) >= _SHAPE_EVIDENCE
                else None,
                samples=tuple(present[:_SAMPLES]),
                reads=None if anchor is None and _is_address(path) else reads,
                anchor=anchor,
                label=label,
            )
        )
    return tuple(fields), notes


# The longest text taken for a label: a label names a value, and a sentence
# that happens to stand before one on every page is not one.
_LABEL_MOST = 40


def _label_before(docs: list[Document], path: str) -> str | None:
    """The text every page given puts right before the value at ``path``, when
    it is one text, said once on each of them, and no longer than a label.

    Two pages at least must hold the value: one page cannot tell its
    template's words from its own. An attribute has no text before it."""
    where, _, attribute = path.partition("@")
    if len(docs) < 2 or attribute:
        return None
    texts = [_text_nodes(doc) for doc in docs]
    said: set[str] = set()
    held = 0
    for doc, nodes in zip(docs, texts, strict=True):
        element, _found = _find(doc, where)
        if element is None:
            continue
        first = _first_text_in(nodes, element)
        if not first or not _a_label(*nodes[first - 1]):
            return None
        said.add(nodes[first - 1][0])
        held += 1
    if held < 2 or len(said) != 1:
        return None
    label = said.pop()
    once = all(sum(1 for text, _ in nodes if text == label) == 1 for nodes in texts)
    return label if once and len(label) <= _LABEL_MOST else None


# The elements HTML gives a label, a table's header cell, a term's name.
_LABELLING = frozenset({"th", "dt", "label"})


def _a_label(text: str, owner: HtmlElement) -> bool:
    """Whether a text is written as a label: it ends with a colon, or HTML's
    own element for a label holds it. The text before a value on every page
    is often something else the template says -- a link to change the ZIP
    code, "Write a Review" -- and a line the page adds between the two moves
    nothing."""
    return text.endswith((":", "\uff1a")) or owner.tag in _LABELLING


def _first_text_in(
    nodes: list[tuple[str, HtmlElement]], element: HtmlElement
) -> int | None:
    """Where the first of ``element``'s own text is among a page's text nodes."""
    inside = set(element.iter())
    return next((n for n, (_, owner) in enumerate(nodes) if owner in inside), None)


def _label_moved(
    f: PageField, doc: Document, nodes: list[tuple[str, HtmlElement]]
) -> str | None:
    """What stands where ``f``'s label should, when the page still says the
    label and it no longer stands right before the value at ``f``'s place;
    None when it does, or the page does not say it, which says nothing: a
    label renamed is not a row moved.

    The label is the page's however often it is said -- a second "SKU" in
    an aside is no reason to trust the place -- and with or without its
    colon, in any case: "SKU:" is the label "SKU" was."""
    if f.label is None:
        return None
    element, _found = _find(doc, f.path.partition("@")[0])
    if element is None:
        return None
    first = _first_text_in(nodes, element)
    before = nodes[first - 1][0] if first else None
    if before is not None and _same_label(before, f.label):
        return None
    at = [n for n, (text, _) in enumerate(nodes) if _same_label(text, f.label)]
    if not at:
        return None
    held = _value_at(doc, f.path)
    if len(at) > 1:
        return (
            f"{f.label!r} is said {len(at)} times, never right before the place, "
            f"which holds {held!r}"
            + (f" after {before!r}" if before is not None else "")
        )
    said = nodes[at[0]][0]
    if at[0] + 1 >= len(nodes):
        return f"nothing after {said!r}"
    return (
        f"{said!r} is now before {nodes[at[0] + 1][0]!r}, and the place holds {held!r}"
    )


def _same_label(text: str, label: str) -> bool:
    """Whether ``text`` is ``label``, its colon and its case aside."""
    return _label_key(text) == _label_key(label)


def _label_key(text: str) -> str:
    return text.rstrip(":\uff1a").rstrip().casefold()


def _contradicted(docs: list[Document], path: str, example: str) -> str | None:
    """What one of the pages given holds at ``path`` against ``example``, or
    None when every page agrees: nothing there, a value that does not read as
    the example does (an amount, a date), or one far longer than it."""
    readers = [read for read in _READERS.values() if read(example) is not None]
    for doc in docs:
        value = _value_at(doc, path)
        if value is None:
            return "nothing on one of them"
        if any(read(value) is None for read in readers):
            return repr(value)
        if len(value) > 3 * len(example) + 10:
            return repr(value[:60] + "...")
    return None


# What learning and healing work out once per page and read many times, for
# each example and each field: the groups the page repeats, furniture too, and
# its text nodes. Kept while the page is, since a Document never changes.
_GROUPS: weakref.WeakKeyDictionary[Document, list[list[HtmlElement]]] = (
    weakref.WeakKeyDictionary()
)
_TEXTS: weakref.WeakKeyDictionary[Document, list[tuple[str, HtmlElement]]] = (
    weakref.WeakKeyDictionary()
)


def _groups(doc: Document) -> list[list[HtmlElement]]:
    """``repeating_groups`` of the page, furniture too, worked out once."""
    found = _GROUPS.get(doc)
    if found is None:
        found = _GROUPS[doc] = repeating_groups(doc.tree, furniture_too=True)
    return found


def _text_nodes(doc: Document) -> list[tuple[str, HtmlElement]]:
    """The page's text, node by node in document order, spaces collapsed, with
    the element each belongs to -- scripts, styles and the head left out.
    Worked out once per page; the list is shared, and never changed."""
    found = _TEXTS.get(doc)
    if found is None:
        found = _TEXTS[doc] = _read_text_nodes(doc)
    return found


def _read_text_nodes(doc: Document) -> list[tuple[str, HtmlElement]]:
    nodes: list[tuple[str, HtmlElement]] = []
    skipping = 0
    for event, element in itertools.islice(
        etree.iterwalk(doc.tree, events=("start", "end")), 4 * _MOST_ELEMENTS
    ):
        tag = element.tag
        if event == "start":
            if isinstance(tag, str) and tag in _NOT_TEXT:
                skipping += 1
            elif (
                not skipping
                and isinstance(tag, str)
                and (text := " ".join((element.text or "").split()))
            ):
                nodes.append((text, element))
            continue
        if isinstance(tag, str) and tag in _NOT_TEXT:
            skipping -= 1
        parent = element.getparent()
        if (
            not skipping
            and parent is not None
            and (text := " ".join((element.tail or "").split()))
        ):
            nodes.append((text, parent))
    return nodes


@dataclass(frozen=True)
class _TextIndex:
    """Where each of a page's texts is among its text nodes, and the texts in
    order, so a label is looked up rather than searched for."""

    at: dict[str, list[int]]
    ordered: list[str]

    @classmethod
    def of(cls, nodes: list[tuple[str, HtmlElement]]) -> _TextIndex:
        at: dict[str, list[int]] = {}
        for n, (text, _) in enumerate(nodes):
            at.setdefault(text, []).append(n)
        return cls(at, sorted(at))

    def opening(self, label: str) -> list[int]:
        """Every node whose text starts with ``label`` and says more."""
        found: list[int] = []
        for text in itertools.islice(
            self.ordered, bisect.bisect_left(self.ordered, label), None
        ):
            if not text.startswith(label):
                break
            if len(text) > len(label):
                found.extend(self.at[text])
        return sorted(found)


def _value_after(
    nodes: list[tuple[str, HtmlElement]],
    anchor: Anchor,
    index: _TextIndex | None = None,
) -> tuple[str | None, str]:
    """The value ``anchor`` points at among a page's text nodes, and why not.

    ``index`` is the nodes' own, for a caller that looks up many labels on
    one page: each is then found at once, not by reading the whole page."""
    if index is not None:
        at = (
            index.at.get(anchor.label, [])
            if anchor.kind == "after"
            else index.opening(anchor.label)
        )
    elif anchor.kind == "after":
        at = [n for n, (text, _) in enumerate(nodes) if text == anchor.label]
    else:
        at = [
            n
            for n, (text, _) in enumerate(nodes)
            if text.startswith(anchor.label) and len(text) > len(anchor.label)
        ]
    if len(at) != 1:
        return None, (
            f"no text {anchor.label!r}"
            if not at
            else f"{len(at)} places that say {anchor.label!r}, where there was one"
        )
    if anchor.kind == "prefix":
        return nodes[at[0]][0][len(anchor.label) :].strip() or None, "found"
    if at[0] + 1 >= len(nodes):
        return None, f"nothing after {anchor.label!r}"
    return nodes[at[0] + 1][0], "found"


def _anchor_for(docs: list[Document], example: str) -> tuple[Anchor, str] | None:
    """The label that stands before ``example`` on the first page that has it
    and before a value on every page given, with the place of the element
    that holds it; the label nearest to the value in the page's tree wins.

    A label is text every page has once, and no longer than a label is: the
    template's own words, as ``Price:`` or ``ISBN:``. One page cannot tell its
    template's words from its own, so a single page has no label."""
    if len(docs) < 2:
        return None
    wanted = " ".join(example.split())
    same = _says(example)
    pages = [_text_nodes(doc) for doc in docs]
    once = [
        {text for text, count in Counter(t for t, _ in nodes).items() if count == 1}
        for nodes in pages
    ]
    labels = set.intersection(*once) if once else set()
    # Every candidate label is checked on every page: looked up, since a page
    # of a thousand labelled rows has a thousand candidates.
    indexes = [_TextIndex.of(nodes) for nodes in pages]
    for p, nodes in enumerate(pages):
        best: tuple[int, Anchor, str] | None = None
        for n, (text, owner) in enumerate(nodes):
            candidates: list[tuple[int, Anchor]] = []
            if same(text) and n > 0:
                label, label_owner = nodes[n - 1]
                if label in labels and len(label) <= _LABEL_MOST and not same(label):
                    candidates.append(
                        (_up_to_meet(label_owner, owner), Anchor(label, "after"))
                    )
            elif (cut := text.find(wanted)) > 0:
                label = text[:cut].strip()
                if label and len(label) <= _LABEL_MOST and same(text[cut:].strip()):
                    candidates.append((0, Anchor(label, "prefix")))
            for near, anchor in candidates:
                values = [
                    _value_after(page, anchor, index)[0]
                    for page, index in zip(pages, indexes, strict=True)
                ]
                if any(v is None for v in values) or not same(values[p]):
                    continue
                if best is None or near < best[0]:
                    best = (near, anchor, path_of(owner))
        if best is not None:
            return best[1], best[2]
    return None


def _up_to_meet(label: HtmlElement, value: HtmlElement) -> int:
    """Levels from the value's element up to the first it shares with the
    label's: a label in the same row or item meets it at once."""
    shared = {id(element) for element in [label, *label.iterancestors()]}
    for steps, element in enumerate([value, *value.iterancestors()]):
        if id(element) in shared:
            return steps
    return len(shared)


def _places(doc: Document, example: str, own: bool = False) -> list[str]:
    """Every place on the page whose value is ``example``, the deepest first.

    An element's text counts when it is the whole of the element's text; an
    ancestor that holds nothing else says the same, and is passed over for
    the element it holds. Then the attributes, in document order. With
    ``own``, only the page's own places: none in its furniture, its
    breadcrumb trail or its listings.
    """
    wanted = " ".join(example.split())
    same = _says(example)
    base = base_url(doc)

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
    attributes: list[tuple[HtmlElement, str]] = []
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
                attributes.append((element, attribute))
    holding = set(texts)
    deepest = [
        element
        for element in texts
        if not any(child in holding for child in element.iterdescendants())
    ]
    # The page's own place first: a product's title is also its breadcrumb's
    # last step and a related strip's link, both earlier in the document, and
    # neither is where a person pointing at the title means.
    repeated = {member for group in _groups(doc) for member in group}

    def aside(element: HtmlElement) -> tuple[bool, bool]:
        climb = [element, *element.iterancestors()]
        return (
            any(chrome(node) or _a_trail(node) for node in climb),
            any(node in repeated for node in climb),
        )

    if own:
        deepest = [element for element in deepest if not any(aside(element))]
        attributes = [(e, a) for e, a in attributes if not any(aside(e))]
    ranked = sorted(range(len(deepest)), key=lambda n: (*aside(deepest[n]), n))
    return [path_of(deepest[n]) for n in ranked] + [
        f"{path_of(element)}@{attribute}" for element, attribute in attributes
    ]


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
    texts: list[tuple[str, HtmlElement]] | None = None
    for f in fields:
        if f.anchor is None:
            value = _value_at(doc, f.path)
            said = "found" if value else "not found"
        else:
            texts = _text_nodes(doc) if texts is None else texts
            value, said = _value_after(texts, f.anchor)
        checks.append(
            Check(
                "field",
                f"{f.name} at {f.path}"
                if f.anchor is None
                else f"{f.name} after {f.anchor.label!r}",
                said,
                value is not None,
            )
        )
        if value is None:
            continue
        if f.label is not None:
            texts = _text_nodes(doc) if texts is None else texts
            moved = _label_moved(f, doc, texts)
            checks.append(
                Check(
                    "field",
                    f"{f.name} right after {f.label!r}, as on the pages learnt",
                    moved or "yes",
                    moved is None,
                )
            )
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
    same = _says(example)
    found: dict[str, None] = {}
    for row in rows:
        for path, value in row.items():
            if same(value):
                found.setdefault(path)
    return list(found)


def _says(example: str) -> Callable[[str | None], bool]:
    """Whether a text says what ``example`` says: the same with its spaces
    collapsed, or the same amount, compared as a number -- ``8`` is ``£8.00``,
    which ``amount`` gives back as ``8.00``.

    The one comparison every example is found by, on the page, in a listing's
    rows and after a label."""
    wanted = " ".join(example.split())
    worth = _worth(wanted)

    def says(text: str | None) -> bool:
        if text is None:
            return False
        said = " ".join(text.split())
        return said == wanted or (worth is not None and _worth(said) == worth)

    return says


def _worth(text: str) -> Decimal | None:
    """``text`` as a number, when ``amount`` reads it as one."""
    read = amount(text)
    return None if read is None else Decimal(read)


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
        shape=(shapes.pop() or None) if shaped and not _is_address(path) else None,
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
            same = [c for c in parent if _steps_to(c, label)]
            if len(same) > 1:
                label += f"[{same.index(node) + 1}]"
        steps.append(label)
        node = parent
    return ">".join(reversed(steps))


def _steps_to(element: HtmlElement, label: str) -> bool:
    """Whether ``element``'s step is ``label``. Its tag is tried first: a step
    begins with its tag, and working out an element's class reads all of
    them, for every sibling of every step of a path."""
    tag = element.tag
    return (
        isinstance(tag, str)
        and (
            label.startswith(tag)
            or (not tag.isalnum() and label.startswith(_written(tag, _IN_A_STEP)))
        )
        and _step_label(element) == label
    )


def _step_label(element: HtmlElement) -> str:
    if element.tag in ("html", "body"):
        # Their classes are state, not structure: scripts swap ``no-js`` for
        # ``js`` and templates stamp the page type on ``<body>``.
        return str(element.tag)
    tag = str(element.tag)
    if not tag.isalnum():
        tag = _written(tag, _IN_A_STEP)
    written = _label(element)
    return f"{tag}.{written}" if written else tag


# What parts a path's steps, a step's number and a field's attribute, and what
# parts a row's kind's classes besides. lxml keeps a tag such as ``<a@b>``,
# ``<p]>`` or ``<x[1]>`` as the page wrote it, and a path through one, written
# as it is, is refused by the reader, or read as another: ``a@b.price`` is
# the attribute ``b.price`` of an ``<a>``. Such a character in a tag is
# written as ``%`` and its code, ``a%40b``; a class holding one -- Tailwind's
# ``@container`` -- has no hand in a path (see ``_label``), nor in a row's kind.
_IN_A_STEP = re.compile(r"[\s\[\]>@]")
_IN_A_KIND = re.compile(r"[\s\[\]>@.]")


def _written(tag: str, reserved: re.Pattern[str]) -> str:
    """``tag`` with each character ``reserved`` matches written as ``%XX``."""
    return reserved.sub(lambda c: f"%{ord(c[0]):02X}", tag)


def _kind_of(element: HtmlElement) -> str:
    """A row's kind as ``kind`` says it, as a listing can write it and read it
    back: its tag written as ``_written`` writes it, and without a class that
    holds a character the kind parts its classes by."""
    tag = element.tag if isinstance(element.tag, str) else "?"
    said = kind(element)[len(tag) + 1 :]
    own = set((element.get("class") or "").split())
    classes = [c for c in said.split(".") if c in own and not _IN_A_KIND.search(c)]
    return ".".join([_written(tag, _IN_A_KIND), *classes])


def _find(
    doc: Document,
    path: str,
    siblings: Sequence[int | None] = (),
    marks: Sequence[str | None] = (),
    member: str = "",
) -> tuple[HtmlElement | None, str]:
    """The element at ``path``, or None and why.

    A step written without ``[n]`` was the only one of its kind when learnt, so
    it must still be the only one: a second listing of the same kind inserted
    before it -- a sponsored strip -- is ambiguous, not the first match. A
    step written with one is held to its mark in ``marks``, the text it began
    with, its rows of ``member`` aside, where known: the second box begins
    "Books" or another box that does is the listing now. Where the mark says
    neither, the step is held to ``siblings``, how many of its kind there were
    at each step, where known: a strip inserted before the second of two
    boxes makes three, and another box the second.
    """
    steps = path.split(">")
    root = doc.tree
    if _step_label(root) != steps[0].split("[")[0]:
        return None, "not found"
    node = root
    marked: list[tuple[str, int, list[HtmlElement], str, int | None]] = []
    for depth, step in enumerate(steps[1:]):
        label, _, ordinal = step.partition("[")
        same = [c for c in node if _steps_to(c, label)]
        if not ordinal and len(same) > 1:
            return None, f"{len(same)} places that match {label}, where there was one"
        learnt = siblings[depth] if depth < len(siblings) else None
        mark = marks[depth] if depth < len(marks) else None
        # Only a digit follows the bracket in a path ``_path`` accepts, or
        # ``path_of`` writes.
        index = int(ordinal.rstrip("]")) - 1 if ordinal else 0
        if ordinal and mark is not None and index < len(same):
            marked.append((label, index, same, mark, learnt))
        elif ordinal and same and learnt is not None and len(same) != learnt:
            return None, _counted(label, len(same), learnt)
        if index >= len(same):
            return None, "not found"
        node = same[index]
    if marked:
        rows = set(_members(node, member)) if member else set()
        for label, index, same, mark, learnt in marked:
            begins = _mark_of(same[index], rows)
            if begins == mark:
                continue
            now = next(
                (n for n, e in enumerate(same) if _mark_of(e, rows) == mark), None
            )
            if now is not None:
                return None, (
                    f"{label}[{index + 1}] begins {begins!r}, and {mark!r} is now "
                    f"{label}[{now + 1}]"
                )
            if learnt is not None and len(same) != learnt:
                return None, _counted(label, len(same), learnt)
    return node, "found"


def _counted(label: str, found: int, learnt: int) -> str:
    matching = "place that matches" if found == 1 else "places that match"
    return f"{found} {matching} {label}, where there were {learnt}"


def _locate(doc: Document, listing: Listing) -> tuple[HtmlElement | None, str]:
    """The element at ``listing``'s container, held to all it learnt of it."""
    return _find(
        doc, listing.container, listing.siblings, listing.marks, listing.member
    )


def _mark_of(element: HtmlElement, rows: set[HtmlElement]) -> str | None:
    """The first text ``element`` holds outside ``rows`` -- a box's heading --
    spaces collapsed, scripts and styles left out; None when it has none."""
    inside = 0
    for event, node in etree.iterwalk(element, events=("start", "end")):
        aside = node is not element and (
            not isinstance(node.tag, str) or node.tag in _NOT_TEXT or node in rows
        )
        if event == "start":
            if aside:
                inside += 1
            elif not inside and (text := " ".join((node.text or "").split())):
                return text
            continue
        if aside:
            inside -= 1
        tail = " ".join((node.tail or "").split())
        if node is not element and not inside and tail:
            return tail
    return None


def _marks(docs: Sequence[Document], path: str, member: str) -> tuple[str | None, ...]:
    """For each numbered step of ``path`` below ``<html>``, the text the
    element there begins with, its rows aside, when it is one text on every
    page that has the path and no other element of its kind there begins with
    it; None elsewhere, and () when no step has one. A heading every box
    shares, "See all", tells none of them apart."""
    seen: list[list[str | None]] = []
    for doc in docs:
        container, _found = _find(doc, path)
        if container is None:
            continue
        rows = set(_members(container, member))
        begun: list[str | None] = []
        node = doc.tree
        for step in path.split(">")[1:]:
            label, _, ordinal = step.partition("[")
            same = [c for c in node if _steps_to(c, label)]
            node = same[int(ordinal.rstrip("]")) - 1 if ordinal else 0]
            mark = _mark_of(node, rows) if ordinal else None
            if mark is not None and any(
                _mark_of(other, rows) == mark for other in same if other is not node
            ):
                mark = None
            begun.append(mark)
        seen.append(begun)
    marks = tuple(
        column[0] if len(set(column)) == 1 else None
        for column in zip(*seen, strict=True)
    )
    return marks if any(m is not None for m in marks) else ()


def _siblings(docs: Sequence[Document], path: str) -> tuple[int | None, ...]:
    """How many elements match each step of ``path`` below ``<html>``, on the
    pages that have it: the number where they agree, None where they do not."""
    seen: list[list[int]] = []
    for doc in docs:
        if _find(doc, path)[0] is None:
            continue
        counts, node = [], doc.tree
        for step in path.split(">")[1:]:
            label, _, ordinal = step.partition("[")
            same = [c for c in node if _steps_to(c, label)]
            counts.append(len(same))
            node = same[int(ordinal.rstrip("]")) - 1 if ordinal else 0]
        seen.append(counts)
    return tuple(
        column[0] if len(set(column)) == 1 else None
        for column in zip(*seen, strict=True)
    )


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
        and (
            child.tag == tag
            or (not child.tag.isalnum() and _written(child.tag, _IN_A_KIND) == tag)
        )
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
    container, found = _locate(doc, listing)
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
    _check_rows(listing.fields, rows, len(members), listing.empty, checks)
    return rows


def _check_rows(
    fields: Sequence[ListingField],
    rows: list[dict[str, str]],
    members: int,
    empty_learnt: float,
    checks: list[Check],
    slots: bool = True,
) -> None:
    """The checks a listing's rows are held to, read from ``members``
    elements: there are some, no more of them empty than were, and each
    column is there, reads and is shaped as learnt, and still varies.

    ``slots`` is False for columns a person named by selector, which
    induction never numbered: ``span.tag2`` is then a class, not a slot.
    """
    # Never zero; a short page of the same template -- the last of a
    # pagination, a small category -- is not a drift.
    checks.append(Check("rows", "at least 1 row", str(len(rows)), bool(rows)))
    if not rows:
        return
    if members >= _SHAPE_EVIDENCE:
        # Skeletons waiting for a script are members with nothing in them: a
        # short page that is not short.
        empty = 1 - len(rows) / members
        allowed = empty_learnt + REQUIRED_MISSING
        checks.append(
            Check(
                "rows",
                f"at most {allowed:.0%} of the listing's members empty",
                f"{members - len(rows)} of {members} empty",
                empty <= allowed,
            )
        )
    paths = {f.path for f in fields}
    for f in fields:
        present = [row[f.name] for row in rows if row.get(f.name)]
        share = len(present) / len(rows)
        learnt = 1 - f.missing
        if slots and _a_later_repeat(f.path, paths):
            # The third tag of a card is a count, not a column: pages differ in
            # how many their rows carry, and none of them has drifted.
            pass
        elif learnt == 1 and not (slots and _a_numbered_slot(f.path, paths)):
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


# -- healing ------------------------------------------------------------------


def _heal_fields(
    old: tuple[PageField, ...], docs: list[Document]
) -> tuple[tuple[PageField, ...], list[Change]]:
    """Each page field where it still is, or where its old values are now.

    A field stays when its place still holds a value that reads as it did;
    otherwise it moves to where the new pages show one of its old values, and
    only among the page's own places: in a related products strip the same
    price is another product's. A field found in neither way is vanished and
    kept out, since a guess would read the wrong value under the old name; one
    two own places claim, reading different values, is ambiguous, for a
    person to decide.
    """
    kept: list[PageField] = []
    changes: list[Change] = []
    texts = (
        [_text_nodes(doc) for doc in docs]
        if any(f.anchor or f.label for f in old)
        else []
    )
    for f in old:
        read = _READERS[f.reads] if f.reads else None
        if f.anchor is not None:
            # Read by its label: kept while the label still points at a value
            # that reads as it did, moved to the label now before one of its
            # old values, and never back to a place its pages contradicted.
            values = [v for nodes in texts if (v := _value_after(nodes, f.anchor)[0])]
            if values and (read is None or all(read(v) for v in values)):
                kept.append(_relearnt(f, f.path, values, f.anchor))
                continue
            again = next(
                (a for sample in f.samples if (a := _anchor_for(docs, sample))), None
            )
            if again is not None:
                anchor, where = again
                found = [v for nodes in texts if (v := _value_after(nodes, anchor)[0])]
                changes.append(Change("moved", f.name, f"after {anchor.label!r}"))
                kept.append(_relearnt(f, where, found, anchor))
                continue
        else:
            values = [v for doc in docs if (v := _value_at(doc, f.path))]
            moved_away = f.label is not None and any(
                _label_moved(f, doc, nodes)
                for doc, nodes in zip(docs, texts, strict=True)
            )
            if (
                values
                and not moved_away
                and (read is None or all(read(v) for v in values))
            ):
                kept.append(_relearnt(f, f.path, values, label=f.label))
                continue
            if moved_away and f.label is not None:
                # The place holds another row's value, and the label every
                # learnt page put before this one says where it went.
                anchor = Anchor(f.label, "after")
                found = [v for nodes in texts if (v := _value_after(nodes, anchor)[0])]
                if found and (read is None or all(read(v) for v in found)):
                    changes.append(Change("moved", f.name, f"after {f.label!r}"))
                    kept.append(_relearnt(f, f.path, found, anchor))
                    continue
        claimed = next(
            (
                places
                for sample in f.samples
                for doc in docs
                if (places := _places(doc, sample, own=True))
            ),
            None,
        )
        if claimed is None:
            changes.append(Change("vanished", f.name, None))
            continue
        moved = claimed[0]
        read_there = [_value_at(doc, moved) for doc in docs]
        if any(
            [_value_at(doc, other) for doc in docs] != read_there
            for other in claimed[1:]
        ):
            changes.append(Change("ambiguous", f.name, moved))
            continue
        found = [v for v in read_there if v]
        changes.append(Change("moved", f.name, moved))
        kept.append(_relearnt(f, moved, found, label=_label_before(docs, moved)))
    return tuple(kept), changes


def _relearnt(
    f: PageField,
    path: str,
    values: list[str],
    anchor: Anchor | None = None,
    label: str | None = None,
) -> PageField:
    """``f`` at ``path``, or after ``anchor``, its samples those of the new
    pages, its reading kept."""
    shapes = {shape(v) for v in values}
    return PageField(
        name=f.name,
        path=path,
        shape=(shapes.pop() or None)
        if f.shape and len(shapes) == 1 and len(values) >= _SHAPE_EVIDENCE
        else None,
        samples=tuple(dict.fromkeys(values))[:_SAMPLES] or f.samples,
        reads=f.reads,
        anchor=anchor,
        label=label,
    )


def _heal_listing(
    old: Listing, new: Listing, docs: list[Document]
) -> tuple[Listing, list[Change]]:
    changes: list[Change] = []
    if old.container != new.container:
        changes.append(Change("container", old.container, new.container))
    if old.member != new.member:
        changes.append(Change("member", old.member, new.member))
    values: dict[str, list[str]] = {f.path: [] for f in new.fields}
    for doc in docs:
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
    undecided: set[str] = set()
    for f in old.fields:
        if f.name not in matched:
            continue
        place = matched[f.name]
        kind_ = "kept" if place == f.path else "moved"
        others = [seen_in(f, path) for path in fresh if path != place]
        evidence = {
            "seen": seen_in(f, place),
            "samples": len({_comparable(f.path, v) for v in f.samples}),
            "runner_up": max(others, default=0),
        }
        # A move is a guess when another new place holds as many of the old
        # values, on as many rows, in the same kind of element, and would read
        # other values: the tie the ranking breaks by page order. The field is
        # left out, for a person. Two places reading the same values -- a
        # film's poster and its title both link to the film -- are no guess.
        if kind_ == "moved" and any(
            path != place
            and seen_in(f, path) == evidence["seen"]
            and fresh[path].missing == fresh[place].missing
            and _element_kind(path) == _element_kind(place)
            and not _read_alike(path, place, values)
            for path in fresh
        ):
            kind_ = "ambiguous"
            undecided.add(place)
            del claimed[place]
        changes.append(Change(kind_, f.name, place, evidence))
    for f in old.fields:
        if f.name not in matched:
            changes.append(Change("vanished", f.name, None))
    for path in fresh:
        if path not in claimed and path not in undecided and not old.chosen:
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
        new.container,
        new.member,
        new.rows,
        fields,
        new.empty,
        chosen=old.chosen,
        siblings=new.siblings,
        marks=new.marks,
    )
    return listing, changes


def _read_alike(one: str, other: str, values: dict[str, list[str]]) -> bool:
    """Whether two places read the same values on the pages given: addresses
    by where they go, their parameters aside, since a poster and a title that
    both link to the film carry different tracking tags."""

    def read(path: str) -> set[str]:
        held = values.get(path, [])
        if _is_address(path):
            return {value.partition("?")[0] for value in held}
        return set(held)

    return read(one) == read(other)


def _element_kind(path: str) -> tuple[str, str]:
    """A field's element tag and attribute: ``a.title@href`` is ``a``, ``href``."""
    step, _, attribute = path.rsplit(">", 1)[-1].partition("@")
    return step.split(".")[0].split("[")[0], attribute


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
