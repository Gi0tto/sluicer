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
from functools import partial
from typing import Any, TypeAlias

from sluicer.declared.jsonld import Terms
from sluicer.declared.located import (
    Located,
    Place,
    Places,
    Positions,
    Step,
    paid,
    place,
    spell,
)
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
    declared, with every leaf as text. A JSON-LD number is the text the page
    wrote, ``"41.90"`` and never the float ``41.9``, so a price keeps its
    cents; ``Extraction.normalised`` reads the summary's prices as decimals.
    """

    value: JsonValue
    source: str
    where: str | None = None
    """Where on the page the value was declared: an XPath, and for JSON-LD the
    ``<script>`` block's with a JSON pointer after ``#``. None where the
    reader does not say, as for a meta tag, whose name is its place."""


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
    where: str | None = None
    """Where on the page the record was declared, as ``Field.where``."""


def merge(*, places: Places | None = None, **found: Any) -> list[Record]:
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

    Every record and field says where on the page it was declared, when its
    reader knows (``Field.where``); ``places`` pays for those, and without it
    they are free, as for a page the caller trusts.

    Raises:
        ValueError: a name no reader has, which would otherwise be dropped.
    """
    unknown = sorted(set(found) - set(BY_NAME))
    if unknown:
        raise ValueError(f"no reader is called {', '.join(unknown)}")
    records: list[Record] = []
    # Every place in the records is spelt here, from one count of each parent's
    # children: counted by lxml for each place, a listing of four thousand
    # items took each item's four thousand siblings over again.
    positions: Positions = {}

    # A reader folds only into what earlier readers found, and each of those
    # records takes at most one item from it: one product described in two
    # vocabularies is one product, but three products in one vocabulary are
    # three. Folding all three onto the first put a related product's SKU and
    # price on the main one. JSON-LD, first, finds nothing to fold into.
    for reader in READERS:
        if not reader.about_things:
            continue
        candidates = _Candidates(records)
        # JSON-LD's words are named through the context each was written in,
        # every context of the page read once.
        terms = Terms() if reader.name == "jsonld" else None
        for item in found.get(reader.name) or ():
            record = _record_from(item, reader.name, places, positions, terms)
            target = candidates.take(record)
            if target is None:
                records.append(record)
                continue
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
                held = _json(declared, 0)
                if held is None:
                    continue
                target.fields.setdefault(key, Field(value=held, source=source))
        if not records:
            records.append(target)
    return records


class _Candidates:
    """The records one reader may fold into, each taken at most once.

    Indexed by type, so finding the first record that shares a type with an
    item costs what that item's types cost, not a walk over every record: a
    page declaring four thousand products in JSON-LD and again in microdata
    walked them for each of the other four thousand.
    """

    def __init__(self, records: list[Record]) -> None:
        self.records = list(records)
        self.taken = [False] * len(self.records)
        self.by_type: dict[str, list[int]] = {}
        for index, record in enumerate(self.records):
            for name in dict.fromkeys(record.types):
                self.by_type.setdefault(name, []).append(index)
        # Where each type's list is still untaken from: a record once taken
        # stays taken, so the start of a list only ever moves forward.
        self.start: dict[str, int] = dict.fromkeys(self.by_type, 0)

    def take(self, incoming: Record) -> Record | None:
        """The first record in document order sharing a type with ``incoming``,
        now taken, or None if none is left. A record with no type folds into
        nothing: "unknown" is not an identity."""
        first: int | None = None
        for name in incoming.types:
            held = self.by_type.get(name)
            if held is None:
                continue
            at = self.start[name]
            while at < len(held) and self.taken[held[at]]:
                at += 1
            self.start[name] = at
            if at < len(held) and (first is None or held[at] < first):
                first = held[at]
        if first is None:
            return None
        self.taken[first] = True
        return self.records[first]


def _record_from(
    item: dict[str, Any],
    source: str,
    places: Places | None,
    positions: Positions,
    terms: Terms | None = None,
) -> Record:
    """One item as a record. ``terms``, for JSON-LD, names its words through
    their context; of two words naming one property, see ``_named``."""
    if terms is not None and "@context" in item:
        terms = terms.within(item["@context"])
    types = _types(item.get("@type"), terms)
    at = item.at if isinstance(item, Located) else None
    record = Record(
        type=types[0] if types else None,
        types=types,
        source=source,
        where=paid(places, lambda: spell(at, positions)),
    )
    for name, keys in _named(item, terms).items():
        for key in keys:
            normalised = _json(item[key], 0, None if at is None else (at, key), terms)
            if normalised is None:
                continue
            record.fields[name] = Field(
                value=normalised,
                source=source,
                where=paid(places, partial(place, item, at, (key,), positions)),
            )
            break
    return record


def _named(value: dict[str, Any], terms: Terms | None) -> dict[str, list[str]]:
    """``value``'s words by the name each gives, keywords left out.

    Two words can name one property -- ``price`` and ``schema:price`` under
    schema.org's context -- and a record holds one value for it. The word
    written as the name itself comes first, wherever it stands: it is the key
    0.7.1 read, and every reader that goes by the key, so the answer does not
    turn on the order a page lists its keys in. The other spellings follow,
    first written first. The first of them with a value gives the property.
    """
    named: dict[str, list[str]] = {}
    for key in value:
        if key.startswith("@"):
            continue
        name = key if terms is None else terms.name(key)
        held = named.get(name)
        if held is None:
            named[name] = [key]
        elif key == name:
            held.insert(0, key)
        else:
            held.append(key)
    return named


def _json(
    value: object, depth: int, at: Place | None = None, terms: Terms | None = None
) -> JsonValue | None:
    """``value`` as a field holds it, or None when it carries nothing.

    A JSON-LD value object is its ``@value``. An object keeps its ``@type`` and
    loses the other keywords, which say how to read it rather than what it
    says, unless it is nothing but an ``@id``: an unresolved reference is all a
    page said, so it is kept as one.

    ``at`` is where ``value`` was declared. An object keeps its place, as a
    ``Located``, so a value read deep inside a field can still say where it
    was; one a reader placed keeps the reader's place. ``terms`` names a
    JSON-LD object's words, in its own context when it declares one; a
    place keeps the word as the page wrote it, and a word named otherwise is
    placed through the object's ``props`` at the key written.
    """
    if depth > MAX_DEPTH:
        return None
    if isinstance(value, list):
        items = [
            normalised
            for n, item in enumerate(value)
            if (normalised := _json(item, depth + 1, _on(at, n), terms)) is not None
        ]
        return items or None
    if not isinstance(value, dict):
        return _scalar(value)
    for keyword in ("@value", "@list", "@set"):
        # A value object is its value; a list or set object is its items.
        if keyword in value:
            return _json(value[keyword], depth + 1, _on(at, keyword), terms)
    node: dict[str, JsonValue]
    if isinstance(value, Located):
        # Its own, since a word renamed below is placed through it.
        node = Located(at=value.at, props=dict(value.props))
    elif at is not None:
        node = Located(at=at)
    else:
        node = {}
    here = node if isinstance(node, Located) else None
    if terms is not None and "@context" in value:
        terms = terms.within(value["@context"])
    out: dict[str, JsonValue] = {}
    for name, keys in _named(value, terms).items():
        for key in keys:
            normalised = _json(value[key], depth + 1, _on(here, key), terms)
            if normalised is None:
                continue
            out[name] = normalised
            if here is not None and key != name:
                # A value is placed at the key the page wrote, not at its name.
                here.props[name] = (here, key)
            break
    if not out:
        identifier = _scalar(value.get("@id"))
        if identifier is None:
            return None
        node["@id"] = identifier
        return node
    types = _types(value.get("@type"), terms)
    if types:
        node["@type"] = types[0] if len(types) == 1 else list(types)
    node.update(out)
    return node


def _on(at: Place | None, step: Step) -> Place | None:
    """One step on from ``at``, or no place when there is none to step from."""
    return None if at is None else (at, step)


def _scalar(value: object) -> str | None:
    """One declared scalar as text, or None for a null or blank value.

    A boolean is "true" or "false", as the page wrote it, not Python's repr."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def _types(declared: object, terms: Terms | None = None) -> tuple[str, ...]:
    """Every type declared for one item, in the order the page declared them,
    each named through ``terms`` when they are given."""
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        return ()
    return tuple(
        found
        for name in declared
        if isinstance(name, str)
        and (found := type_name(name if terms is None else terms.name(name)))
        is not None
    )
