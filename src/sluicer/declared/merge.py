"""Fold the readers' findings into records that remember their source.

Folding happens only across readers: when the same entity is described in
both JSON-LD and microdata, fields from the lower-precedence reader fill
gaps in the higher-precedence one. Within a single reader, two entries with
the same @type are two distinct things and remain separate records.

This slice extracts scalar values only; complex-typed fields (objects and
lists, such as JSON-LD's offers or image) are not carried into records.

A JSON-LD null is an absence, not a value: it is dropped, so it can neither
be recorded as the text "None" nor shadow a real value a later reader has.
A real boolean is a value, and is recorded the way the page declared it,
lowercase "true" or "false", rather than as Python's repr of it."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    """One extracted value and the reader that produced it."""

    value: str
    source: str


@dataclass
class Record:
    """A set of fields describing one thing on the page.

    ``type`` is the first type the page declared for this thing; ``types``
    is every type it declared. JSON-LD allows a list -- Yoast routinely
    emits ``["Person", "Organization"]`` -- and the whole list is what the
    fold matches on.
    """

    type: str | None = None
    types: tuple[str, ...] = ()
    fields: dict[str, Field] = field(default_factory=dict)


def merge(
    jsonld: list[dict],
    microdata: list[dict],
    opengraph: dict,
) -> list[Record]:
    """Merge reader output. Earlier sources win; every field keeps its source.

    Two records fold together when they declare at least one type in common:
    a page saying ``["Product", "Thing"]`` in JSON-LD and ``Thing`` in
    microdata is describing one thing twice. A record that declares no type
    never folds, with anything: "unknown" is not an identity, and two untyped
    things are not one thing. Each untyped record stays on its own.

    When more than one record could receive a gap-filling field, the fold
    targets the first matching record in document order, and OpenGraph, which
    declares no type at all, fills the first record on the page. Document
    order is the only deterministic signal available in this slice: nothing
    here knows which record is the page's primary entity, so on a page whose
    @graph opens with a BreadcrumbList the og:title lands on the breadcrumb.
    That is a known limit of this slice, not a claim about picking the right
    record."""
    records: list[Record] = []

    for item in jsonld:
        records.append(_record_from(item, "jsonld"))

    for item in microdata:
        record = _record_from(item, "microdata")
        target = _fold_target(records, record)
        if target is None:
            records.append(record)
            continue
        for key, value in record.fields.items():
            target.fields.setdefault(key, value)

    if opengraph:
        target = records[0] if records else Record()
        for key, value in opengraph.items():
            target.fields.setdefault(key, Field(value=str(value), source="opengraph"))
        if not records:
            records.append(target)
    return records


def _fold_target(records: list[Record], incoming: Record) -> Record | None:
    """The first record sharing a type with ``incoming``, or None if none does."""
    if not incoming.types:
        return None
    for record in records:
        if set(record.types) & set(incoming.types):
            return record
    return None


def _record_from(item: dict, source: str) -> Record:
    types = _types(item.get("@type"))
    record = Record(type=types[0] if types else None, types=types)
    for key, value in item.items():
        if key.startswith("@"):
            continue
        if isinstance(value, (dict, list)):
            continue
        text = _scalar(value)
        if text is None:
            continue
        record.fields[key] = Field(value=text, source=source)
    return record


def _scalar(value: object) -> str | None:
    """Render one declared scalar as text, or None when it carries nothing.

    A null carries nothing. A boolean carries "true" or "false", spelt the
    way the page declared it and not the way Python repr()s it."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _types(declared: object) -> tuple[str, ...]:
    """Every type declared for one item, in the order the page declared them."""
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        return ()
    return tuple(name.strip() for name in declared if isinstance(name, str) and name.strip())
