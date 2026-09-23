"""Fold the readers' findings into records that remember their source.

Folding happens only across readers: when the same entity is described in
both JSON-LD and microdata, fields from the lower-precedence reader fill gaps
in the higher-precedence one. Within one reader, two entries of the same type
are two things and stay two records.

The order of precedence is written down once, in
``sluicer.declared.readers.READERS``: JSON-LD, microdata, microformats, RDFa,
Dublin Core, OpenGraph, the Twitter card, HTML's own metadata names.

A nested value -- JSON-LD's ``offers``, ``author`` or ``recipeIngredient``, a
microdata item inside another -- is carried whole, as JSON: an object is a
``dict`` keeping its ``@type``, a list keeps the order declared, and every
leaf is text. It is one field with one source, because one reader declared it.

An empty or whitespace-only value is not a value, at any depth, so it cannot
shadow a real value a later reader has; an object or list left with nothing in
it is dropped too. A JSON-LD null is an absence, never the text "None". A
boolean is recorded as the page wrote it, "true" or "false".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from sluicer.declared.readers import BY_NAME, READERS
from sluicer.declared.types import type_name

# What a field holds: text, or the objects and lists a page nests, down to text.
JsonValue: TypeAlias = "str | list[JsonValue] | dict[str, JsonValue]"

# Deeper than any real page nests; a bound so a hostile one costs a fixed amount.
MAX_DEPTH = 16

# The readers that describe a thing on the page, as opposed to the page itself
# (Dublin Core, OpenGraph, the Twitter card, HTML's meta names). Induction runs
# only when none of these produced a field, and the summary answers a record's
# own questions only from these. Read off the registry, so a new reader is
# counted by saying what it describes, once.
ABOUT_A_THING = frozenset(reader.name for reader in READERS if reader.about_things)


@dataclass(frozen=True)
class Field:
    """One extracted value and the reader that produced it.

    ``value`` is text for a scalar, and for a nested value the JSON the page
    declared, with every leaf as text.
    """

    value: JsonValue
    source: str


@dataclass
class Record:
    """A set of fields describing one thing on the page.

    ``type`` is the first type the page declared for this thing; ``types`` is
    every type it declared (Yoast writes ``["Person", "Organization"]``), and
    the whole tuple is what folding matches on.

    ``source`` is the reader that declared the record: ``"induced"`` for a row
    induction found, and None for the one record the document-level
    vocabularies make when nothing else declared a thing. Fields folded in from
    other readers keep their own sources.
    """

    type: str | None = None
    types: tuple[str, ...] = ()
    fields: dict[str, Field] = field(default_factory=dict)
    source: str | None = None


def merge(**found: Any) -> list[Record]:
    """Merge what each reader found. Earlier readers win; every field keeps its source.

    ``found`` maps a reader's name (``jsonld``, ``html``, see ``READERS``) to
    what it read; a reader left out found nothing. The precedence is the
    registry's, never the caller's: the first field written under a name
    survives, so a later reader only fills gaps. The readers about things fold
    by type; the readers about the document declare no type and fill the first
    record on the page.

    Two records fold when they share at least one type (``["Product",
    "Thing"]`` in JSON-LD and ``Thing`` in microdata). A record with no type
    never folds: "unknown" is not an identity. A gap-filling field goes to the
    first matching record in document order, the only deterministic signal
    available; which record is the page's subject is the summary's question,
    not this one's.

    Raises:
        ValueError: a name no reader has, which would otherwise be dropped.
    """
    unknown = sorted(set(found) - set(BY_NAME))
    if unknown:
        raise ValueError(f"no reader is called {', '.join(unknown)}")
    records: list[Record] = []

    # A reader folds only into what earlier readers found, and each of those
    # records takes at most one item from it: one product described in two
    # vocabularies is one product, but three products in one vocabulary are
    # three. Folding all three onto the first put a related product's SKU and
    # price on the main one. JSON-LD, first, finds nothing to fold into.
    for reader in READERS:
        if not reader.about_things:
            continue
        candidates = list(records)
        for item in found.get(reader.name) or ():
            record = _record_from(item, reader.name)
            target = _fold_target(candidates, record)
            if target is None:
                records.append(record)
                continue
            candidates = [record for record in candidates if record is not target]
            for key, value in record.fields.items():
                target.fields.setdefault(key, value)

    # The document-level readers declare no type, so each fills the first
    # record, in the registry's order. That settles og:title against
    # twitter:title, which strip to the same key, and puts <meta
    # name="description"> behind og:description.
    about_the_document = [
        (reader.name, found.get(reader.name) or {})
        for reader in READERS
        if not reader.about_things
    ]
    if any(declared for _, declared in about_the_document):
        target = records[0] if records else Record()
        for source, declared_by_it in about_the_document:
            for key, declared in declared_by_it.items():
                text = _scalar(declared)
                if text is None:
                    continue
                target.fields.setdefault(key, Field(value=text, source=source))
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


def _record_from(item: dict[str, Any], source: str) -> Record:
    types = _types(item.get("@type"))
    record = Record(type=types[0] if types else None, types=types, source=source)
    for key, value in item.items():
        if key.startswith("@"):
            continue
        normalised = _json(value, 0)
        if normalised is None:
            continue
        record.fields[key] = Field(value=normalised, source=source)
    return record


def _json(value: object, depth: int) -> JsonValue | None:
    """``value`` as a field holds it, or None when it carries nothing.

    A JSON-LD value object is its ``@value``. An object keeps its ``@type`` and
    loses the other keywords, which say how to read it rather than what it
    says, unless it is nothing but an ``@id``: an unresolved reference is all a
    page said, so it is kept as one.
    """
    if depth > MAX_DEPTH:
        return None
    if isinstance(value, list):
        items = [
            normalised
            for item in value
            if (normalised := _json(item, depth + 1)) is not None
        ]
        return items or None
    if not isinstance(value, dict):
        return _scalar(value)
    for keyword in ("@value", "@list", "@set"):
        # A value object is its value; a list or set object is its items.
        if keyword in value:
            return _json(value[keyword], depth + 1)
    out: dict[str, JsonValue] = {}
    for key, item in value.items():
        if key.startswith("@"):
            continue
        normalised = _json(item, depth + 1)
        if normalised is not None:
            out[key] = normalised
    if not out:
        identifier = _scalar(value.get("@id"))
        return {"@id": identifier} if identifier is not None else None
    types = _types(value.get("@type"))
    if types:
        return {"@type": types[0] if len(types) == 1 else list(types), **out}
    return out


def _scalar(value: object) -> str | None:
    """One declared scalar as text, or None for a null or blank value.

    A boolean is "true" or "false", as the page wrote it, not Python's repr."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def _types(declared: object) -> tuple[str, ...]:
    """Every type declared for one item, in the order the page declared them."""
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        return ()
    return tuple(
        found
        for name in declared
        if isinstance(name, str) and (found := type_name(name)) is not None
    )
