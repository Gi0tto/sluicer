"""Extractors a person writes: every field a selector, and every check kept.

A learnt extractor knows where its fields are because pages showed it; a
hand-written one because a person said so, each field a selector in CSS or
XPath (see ``sluicer.selectors``), and a listing's rows one more. It is kept
in the same file, as format 3, replayed by the same ``run_extractor`` and
held to the same checks where they apply. A selector that finds nothing
fails the run. Written from pages, the extractor also learns what the pages
showed of each field -- how many rows carry it, its shape, whether it reads
as an amount or a date, whether it was ever found twice -- and holds every
later page to that, with the words and the thresholds a learnt one uses.

So a selector a redesign broke is a failed run, exit 3, and never rows that
came back empty: the one way a hand-written scraper fails that a learnt
extractor was made not to.

``heal`` does not rewrite what a person wrote. A selector the new pages
still bear out is kept, its profile learnt again from them; one they break
is reported ``broken``, a loss, and kept as written, so the extractor goes on
failing until a person writes the new selector.
"""

from __future__ import annotations

import contextlib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sluicer.document import Document, load
from sluicer.extractor import (
    _COMMON,
    _READERS,
    _SAMPLES,
    _SHAPE_EVIDENCE,
    Change,
    Check,
    Extractor,
    ListingField,
    NothingToLearn,
    Page as Source,
    _check_rows,
    _compiled,
    _fits,
    _learnt_from,
    _learnt_nothing,
    _list,
    _reading,
    _reads,
    _shape,
    _share,
    _text,
    _unique,
    shape,
)
from sluicer.selectors import (
    Page,
    Selected,
    SelectorError,
    _an_address,
    _element_of,
    selector,
)


@dataclass(frozen=True)
class WrittenField:
    """One field a person named by selector, and what the pages it was
    written from showed of it.

    ``selector`` is as written, CSS or XPath; in a listing it is read inside
    each row. The value is its first non-empty one, and ``first`` says it may
    have several: False holds it to one, since a second value where there
    was one -- an old price beside the new -- makes the first the wrong one.
    ``missing`` is the share of learnt rows without it, ``shape`` and
    ``reads`` are learnt as a learnt field's are, and ``samples`` are a few
    of its values. Every one of them is at its strictest when no page taught
    it: required, held to one value, shape and reading unchecked.
    """

    name: str
    selector: str
    shape: str | None = None
    reads: str | None = None
    samples: tuple[str, ...] = ()
    missing: float = 0.0
    first: bool = False


@dataclass(frozen=True)
class Written:
    """The fields of a hand-written extractor, and the rows they are read in.

    ``rows`` is the selector of a listing's rows, each field read inside
    each one, or None when the fields are the page's own. ``empty`` is the
    largest share of a learnt page's rows that held none of the fields.
    """

    fields: tuple[WrittenField, ...]
    rows: str | None = None
    empty: float = 0.0


BY_CHANCE = 0.01
"""How unlikely it must be that no row of a page carries a column a few of
the learnt rows carried before the page fails for it: a sale badge three rows
in ten carry is absent from ten rows 2.8% of the time, and from twenty 0.08%.
A column most rows carried is held to some row on every page, as a learnt
one is."""


def compile_written(
    pages: Sequence[Source],
    select: Mapping[str, str],
    rows: str | None,
    names: Sequence[str] | None,
) -> Extractor:
    """``compile_extractor`` of fields named by selector (see its ``select``)."""
    if not select or any(not name.strip() for name in select):
        raise ValueError("every field needs a name and a selector: name=selector")
    for text in select.values():
        _field_selector(text, rows is not None)
    if rows is not None:
        _rows_selector(rows)
    docs = [load(html, url=url) for html, url in pages]
    fresh = _learnt_nothing(docs, names)
    if docs:
        # What the pages declare, learnt as for any extractor; no listing,
        # since the selectors say where the rows are.
        with contextlib.suppress(NothingToLearn):
            fresh = _compiled(docs, False, names, None)
    written, notes = _learn(
        docs,
        fresh.learnt_from,
        {name: text.strip() for name, text in select.items()},
        None if rows is None else rows.strip(),
    )
    return Extractor(
        learnt_from=fresh.learnt_from,
        summary=fresh.summary,
        types=fresh.types,
        listing=None,
        notes=(*fresh.notes, *notes),
        written=written,
    )


def _field_selector(text: str, in_rows: bool) -> None:
    """Refuse a field's selector that cannot be read, or that inside a row
    would read the whole page: ``//a`` is every link, in every row."""
    chosen = selector(text)
    if in_rows and chosen.kind == "xpath" and re.match(r"[(\s]*/", chosen.text):
        raise SelectorError(
            f"{text.strip()!r} reads the whole page, not the row: an XPath "
            "inside a row begins with ., as .//a"
        )


def _rows_selector(text: str) -> None:
    chosen = selector(text)
    if chosen.kind == "css" and chosen.reads != "element":
        raise SelectorError(
            f"{text.strip()!r}: rows are elements, and ::text or ::attr() reads "
            "a text or an attribute"
        )


def _values(found: Sequence[Selected]) -> list[str]:
    """What a field reads of what its selector gave: the values not empty."""
    return [one.value for one in found if one.value]


def _given(found: Sequence[Selected]) -> list[Selected]:
    """``_values``, each with where it was read from."""
    return [one for one in found if one.value]


def _learn(
    docs: list[Document],
    called: Sequence[str],
    select: dict[str, str],
    rows: str | None,
) -> tuple[Written, list[str]]:
    """What ``docs`` show of each field, as the file keeps it.

    Raises:
        NothingToLearn: a selector gives nothing on a page it is written
            from, which names both: a mistake, said while it is being made.
    """
    pages = [Page(doc) for doc in docs]
    if rows is not None:
        return _learn_rows(pages, called, select, rows)
    notes: list[str] = []
    fields = []
    for name, text in select.items():
        values: list[str] = []
        # An address -- an href or a src, read from the attribute -- has no
        # shape or reading worth holding it to, as a learnt one has none.
        address = True
        first = False
        for page, called_as in zip(pages, called, strict=True):
            found = _given(page.select(text))
            if not found:
                raise NothingToLearn(f"{name}={text!r} gives nothing on {called_as}")
            if len(found) > 1 and not first:
                first = True
                notes.append(
                    f"{name}={text!r} gives {len(found)} values on {called_as}; the "
                    "first is read, and a run does not hold it to one"
                )
            values.append(found[0].value)
            address = address and _an_address(found[0])
        shapes = {shape(value) for value in values}
        # A reading from two pages at least, as a label is learnt: one page
        # cannot tell a price from a title that happens to be a number.
        reads = next(
            (
                r
                for r, read in _READERS.items()
                if all(read(v) is not None for v in values)
            ),
            None,
        )
        fields.append(
            WrittenField(
                name=name,
                selector=text,
                shape=(shapes.pop() or None)
                if not address and len(shapes) == 1 and len(values) >= _SHAPE_EVIDENCE
                else None,
                reads=None if address or len(values) < 2 else reads,
                samples=tuple(dict.fromkeys(values))[:_SAMPLES],
                first=first,
            )
        )
    return Written(tuple(fields)), notes


def _learn_rows(
    pages: list[Page], called: Sequence[str], select: dict[str, str], rows: str
) -> tuple[Written, list[str]]:
    """A listing's fields as its rows on ``pages`` show them, profiled as a
    learnt listing's columns are."""
    notes: list[str] = []
    held: list[dict[str, str]] = []
    doubled: Counter[str] = Counter()
    addresses: Counter[str] = Counter()
    empty = 0.0
    for page, called_as in zip(pages, called, strict=True):
        members = page.select(rows)
        elements = [one for one in members if _element_of(one) is not None]
        if len(elements) != len(members):
            raise SelectorError(
                f"{rows!r} selects a text or an attribute on {called_as}: rows "
                "are elements"
            )
        if not elements:
            raise NothingToLearn(f"the rows {rows!r} are nowhere on {called_as}")
        read, twice, links, _broken = _read_rows(elements, select, raising=True)
        doubled.update(twice)
        addresses.update(links)
        kept = [row for row in read if row]
        empty = max(empty, round(1 - len(kept) / len(elements), 4))
        held.extend(kept)
    fields = []
    for name, text in select.items():
        present = [row[name] for row in held if name in row]
        if pages and not present:
            raise NothingToLearn(
                f"{name}={text!r} gives nothing in any row of {rows!r} on the "
                "pages given"
            )
        if doubled[name]:
            notes.append(
                f"{name}={text!r} gives more than one value in {doubled[name]} "
                "rows; the first is read, and a run does not hold it to one"
            )
        address = addresses[name] == len(present)
        shapes = {shape(value) for value in present}
        shaped = len(shapes) == 1 and len(present) >= _SHAPE_EVIDENCE
        fields.append(
            WrittenField(
                name=name,
                selector=text,
                shape=(shapes.pop() or None) if shaped and not address else None,
                reads=None if address else _reads(present),
                samples=tuple(dict.fromkeys(present))[:_SAMPLES],
                missing=round(1 - len(present) / len(held), 4) if held else 0.0,
                first=bool(doubled[name]),
            )
        )
    return Written(tuple(fields), rows, empty), notes


def _read_rows(
    elements: list[Selected], select: Mapping[str, str], raising: bool = False
) -> tuple[list[dict[str, str]], Counter[str], Counter[str], dict[str, str]]:
    """Each row's fields: the first value each selector gives inside it.

    Also how many rows gave a field more than one value, how many gave it an
    address (``_an_address``), and, unless ``raising``, the fields whose
    selector could not be read on this page -- one that selected a comment --
    with why."""
    rows: list[dict[str, str]] = []
    doubled: Counter[str] = Counter()
    addresses: Counter[str] = Counter()
    broken: dict[str, str] = {}
    for element in elements:
        row: dict[str, str] = {}
        for name, text in select.items():
            if name in broken:
                continue
            try:
                found = _given(element.select(text))
            except SelectorError as why:
                if raising:
                    raise
                broken[name] = str(why)
                continue
            if len(found) > 1:
                doubled[name] += 1
            if found:
                row[name] = found[0].value
                addresses[name] += _an_address(found[0])
        rows.append(row)
    return rows, doubled, addresses, broken


# -- replaying ----------------------------------------------------------------


def replay_written(
    written: Written, doc: Document, checks: list[Check]
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """The rows or the page's fields ``written`` reads on ``doc``, each check
    it is held to added to ``checks``."""
    rows, fields, said = _replayed(written, doc)
    checks.extend(check for _owner, check in said)
    return rows, fields


Said = list[tuple[str | None, Check]]
"""Checks, each with the field it is about, or None for the rows'."""


def _replayed(
    written: Written, doc: Document
) -> tuple[list[dict[str, str]], dict[str, str], Said]:
    page = Page(doc)
    said: Said = []
    if written.rows is None:
        fields = {}
        for f in written.fields:
            value = _replay_field(page, f, said)
            if value is not None:
                fields[f.name] = value
        return [], fields, said
    where = f"rows at {written.rows}"
    try:
        members = page.select(written.rows)
    except SelectorError as why:
        # Read on an empty page when written, a selector can still fail on
        # one page -- an XPath that selects a comment there -- and the page
        # fails, as one without the rows does; the rest are still read.
        said.append((None, Check("listing", where, str(why), False)))
        return [], {}, said
    elements = [one for one in members if _element_of(one) is not None]
    if not members or len(elements) != len(members):
        got = (
            "not found"
            if not members
            else f"{len(members) - len(elements)} texts or attributes, not elements"
        )
        said.append((None, Check("listing", where, got, False)))
        return [], {}, said
    said.append((None, Check("listing", where, f"{len(elements)} found", True)))
    read, doubled, _addresses, broken = _read_rows(
        elements, {f.name: f.selector for f in written.fields}
    )
    rows = [row for row in read if row]
    level: list[Check] = []
    # The rows' own checks depend on the rows alone, so each field's are its
    # own: a heal names the field a check failed for, not the listing.
    _check_rows([], rows, len(elements), written.empty, level, slots=False)
    said.extend((None, check) for check in level)
    for f in written.fields if rows else ():
        if f.name in broken:
            said.append(
                (
                    f.name,
                    Check("field", f"{f.name} at {f.selector}", broken[f.name], False),
                )
            )
            continue
        own: list[Check] = []
        column = ListingField(
            name=f.name,
            path=f.selector,
            missing=f.missing,
            shape=f.shape,
            samples=f.samples,
            reads=f.reads,
        )
        _check_rows([column], rows, len(elements), written.empty, own, slots=False)
        said.extend((f.name, check) for check in own[len(level) :])
        seldom = _seldom(f, len(rows))
        if seldom is not None:
            carried = sum(1 for row in rows if f.name in row)
            said.append(
                (
                    f.name,
                    Check(
                        "field",
                        f"{f.name} in some rows",
                        f"in {carried / len(rows):.0%}"
                        if carried
                        else f"in none of {len(rows)} rows, {seldom}",
                        carried > 0,
                    ),
                )
            )
        if not f.first:
            twice = doubled[f.name]
            said.append(
                (
                    f.name,
                    Check(
                        "field",
                        f"{f.name} once in each row",
                        f"{twice} of {len(rows)} rows hold it more than once"
                        if twice
                        else "yes",
                        not twice,
                    ),
                )
            )
    return rows, {}, said


def _seldom(f: WrittenField, rows: int) -> str | None:
    """How unlikely ``rows`` rows none of which carries ``f`` are, when ``f``
    is a column fewer than half the learnt rows carried -- which a learnt
    listing leaves unchecked -- and that is under ``BY_CHANCE``; else None.

    A person named the column, and a selector a redesign broke finds it in no
    row: a sale badge renamed passed every page as a day with no sale."""
    if not 1 - _COMMON < f.missing < 1:
        return None
    chance = f.missing**rows
    if chance >= BY_CHANCE:
        return None
    return f"a {chance:.2%} chance for a field {1 - f.missing:.0%} carried"


def _replay_field(page: Page, f: WrittenField, said: Said) -> str | None:
    """A page field's value, checked as a learnt page field's is."""
    expected = f"{f.name} at {f.selector}"
    try:
        found = _values(page.select(f.selector))
    except SelectorError as why:
        said.append((f.name, Check("field", expected, str(why), False)))
        return None
    if not found:
        said.append((f.name, Check("field", expected, "not found", False)))
        return None
    if len(found) > 1 and not f.first:
        got = f"{len(found)} values, where one was expected"
        said.append((f.name, Check("field", expected, got, False)))
        return None
    said.append((f.name, Check("field", expected, "found", True)))
    value = found[0]
    if f.reads:
        read = _READERS[f.reads]
        said.append(
            (
                f.name,
                Check(
                    "reads",
                    f"{f.name} to read as {'an' if f.reads == 'amount' else 'a'} "
                    f"{f.reads}",
                    repr(value),
                    read(value) is not None,
                ),
            )
        )
    if f.shape:
        said.append(
            (
                f.name,
                Check(
                    "shape",
                    f"{f.name} shaped {f.shape}",
                    f"{value!r} ({shape(value) or 'empty'})",
                    _fits(value, f.shape),
                ),
            )
        )
    return value


# -- healing ------------------------------------------------------------------


def heal_written(
    written: Written, docs: list[Document]
) -> tuple[Written, list[Change]]:
    """``written`` held to the new pages: kept, its profile learnt again from
    them, when every check holds on every one; otherwise kept as written,
    each field a check failed for reported ``broken`` -- or the rows, when
    they are what failed -- since a selector is what a person said, and heal
    cannot say it for them."""
    rows_broken = False
    broken: set[str] = set()
    pooled: list[dict[str, str]] = []
    for doc in docs:
        rows, _fields, said = _replayed(written, doc)
        pooled.extend(rows)
        for owner, check in said:
            if check.ok:
                continue
            if owner is None:
                rows_broken = True
            else:
                broken.add(owner)
    if rows_broken:
        return written, [Change("broken", written.rows, None)]
    # A column too few rows carry to fail any one page, found in no row of
    # all the new pages together.
    broken.update(
        f.name
        for f in written.fields
        if written.rows is not None
        and _seldom(f, len(pooled)) is not None
        and not any(f.name in row for row in pooled)
    )
    changes = [
        Change("broken", f.name, None)
        if f.name in broken
        else Change("kept", f.name, f.selector)
        for f in written.fields
    ]
    if broken:
        return written, changes
    try:
        again, _notes = _learn(
            docs,
            _learnt_from(docs, None),
            {f.name: f.selector for f in written.fields},
            written.rows,
        )
    except NothingToLearn:
        # A column no new row carries, and too few could have for that to
        # say it is gone: kept, as it was learnt.
        return written, changes
    return again, changes


# -- the file -----------------------------------------------------------------


def written_json(written: Written) -> dict[str, Any]:
    """``written`` as the ``select`` of the extractor's file."""
    in_rows = written.rows is not None
    return {
        "rows": written.rows,
        **({"empty": written.empty} if in_rows else {}),
        "fields": [
            {
                "name": f.name,
                "selector": f.selector,
                **({"missing": f.missing} if in_rows else {}),
                "shape": f.shape,
                "reads": f.reads,
                "samples": list(f.samples),
                "first": f.first,
            }
            for f in written.fields
        ],
    }


def written_of(raw: Any) -> Written:
    """The ``select`` of an extractor's file, every value checked.

    A key left out takes its strictest value -- a field required in every
    row, held to one value -- so a file written by hand needs only each
    field's name and selector, and leaving a key out never turns a check off.

    Raises:
        ValueError: a value no check can be true of, or a selector that
            cannot be read, named.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"select holds rows and fields, not {raw!r}")
    rows = raw.get("rows")
    if rows is not None:
        if not isinstance(rows, str) or not rows.strip():
            raise ValueError(f"rows is a selector, or null, not {rows!r}")
        _rows_selector(rows)
    fields = tuple(
        _field_of(f, rows is not None) for f in _list(raw["fields"], "fields")
    )
    if not fields:
        raise ValueError("a hand-written extractor with no field checks nothing")
    _unique(f.name for f in fields)
    return Written(
        fields=fields,
        rows=rows,
        empty=_share(raw.get("empty", 0.0), "empty"),
    )


def _field_of(raw: Any, in_rows: bool) -> WrittenField:
    if not isinstance(raw, dict):
        raise ValueError(f"a field is a name and a selector, not {raw!r}")
    text = _text(raw["selector"])
    _field_selector(text, in_rows)
    first = raw.get("first", False)
    if type(first) is not bool:
        raise ValueError(f"first is true or false, not {first!r}")
    return WrittenField(
        name=_text(raw["name"]),
        selector=text,
        shape=_shape(raw.get("shape")),
        reads=_reading(raw.get("reads")),
        samples=tuple(_text(v) for v in _list(raw.get("samples", []), "samples")),
        missing=_share(raw.get("missing", 0.0), "missing"),
        first=first,
    )
