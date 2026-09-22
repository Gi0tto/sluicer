"""Fold the readers' findings into records that remember their source.

Folding happens only across readers: when the same entity is described in
both JSON-LD and microdata, fields from the lower-precedence reader fill
gaps in the higher-precedence one. Within a single reader, two entries with
the same @type are two distinct things and remain separate records.

Eight readers reach here, and ``merge`` is where their order of precedence
is written down: JSON-LD, microdata, microformats, RDFa, Dublin Core,
OpenGraph, the Twitter card, HTML's own metadata names. It is one rule in one
place, so no pair of vocabularies is left to settle a shared key by whichever
tag the page's author typed first.

A nested value -- JSON-LD's ``offers``, ``author`` or ``recipeIngredient``,
a microdata item inside another -- is carried whole, as JSON: an object is a
``dict`` keeping its ``@type``, a list is a ``list`` in the order declared, and
every leaf is text. It is one field with one source, because one reader
declared it.

An empty or whitespace-only value is not a value, in any reader and at any
depth: it is dropped, so it cannot shadow a real value a later reader has, and
an object or list left with nothing in it is dropped too. A JSON-LD null is an
absence for the same reason, and is never recorded as the text "None".

A real boolean is a value, and is recorded the way the page declared it,
lowercase "true" or "false", rather than as Python's repr of it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from sluicer.declared.types import type_name

# What a field holds: text, or the objects and lists a page nests, down to text.
JsonValue: TypeAlias = "str | list[JsonValue] | dict[str, JsonValue]"

# Deeper than any real page nests; a bound so a hostile one costs a fixed amount.
MAX_DEPTH = 16

# The vocabularies that describe a thing on the page rather than the page
# itself. Named positively on purpose: the gate used to ask which source was
# not OpenGraph, and every document-level vocabulary added after it would have
# switched induction off silently. A reader added here is a reader claiming to
# describe the page's subject; anything unlisted is taken to describe the
# document, which is the safe side -- it lets induction run.
#
# The Twitter card is what that bought: a sixth reader, document-level like
# OpenGraph, wired in without a line changing here. So was the eighth,
# ``html``: ``<meta name="description">`` describes the document, so a page
# carrying nothing else is still induced over, and this set did not have to
# learn a name to keep that true.
#
# ``microformats`` was named here before its reader existed, and the reader
# arrived without this line changing either: the set is the statement of the
# rule, and a rule written down in instalments judges pages by half of itself
# in between. An ``h-entry`` describes a thing, so a page carrying one has
# declared something about its own subject and is not induced over.
ABOUT_A_THING = frozenset({"jsonld", "microdata", "rdfa", "microformats"})


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

    ``type`` is the first type the page declared for this thing; ``types``
    is every type it declared. JSON-LD allows a list -- Yoast routinely
    emits ``["Person", "Organization"]`` -- and the whole list is what the
    fold matches on.
    """

    type: str | None = None
    types: tuple[str, ...] = ()
    fields: dict[str, Field] = field(default_factory=dict)


def merge(
    jsonld: list[dict[str, Any]],
    microdata: list[dict[str, str]],
    microformats: list[dict[str, str]],
    rdfa: list[dict[str, str]],
    dublincore: dict[str, str],
    opengraph: dict[str, str],
    twitter: dict[str, str],
    htmlmeta: dict[str, str],
) -> list[Record]:
    """Merge reader output. Earlier sources win; every field keeps its source.

    The order of precedence is JSON-LD, microdata, microformats, RDFa, Dublin
    Core, OpenGraph, the Twitter card, HTML's own metadata names, and this
    signature is where it is stated: the first field written under a name is
    the one that survives, so a reader named later can only ever fill a gap.
    The first four describe the thing the page is about and name it with a
    type, so they fold by type. The last four describe the document, declare no
    type at all, and fill the first record on the page.

    Every parameter is positional and none has a default. A default would let
    a reader be added and then silently left out of a call site that was never
    updated, which is precisely the failure this signature exists to make
    impossible: widening it is a compile-time argument with every caller.

    ``microformats`` is an empty list unless the caller asked for it, since its
    reader needs an optional extra. It is a parameter like any other all the
    same: what is not declared is an empty finding, and a reader that is off is
    a reader that found nothing.

    Two records fold together when they declare at least one type in common:
    a page saying ``["Product", "Thing"]`` in JSON-LD and ``Thing`` in
    microdata is describing one thing twice. A record that declares no type
    never folds, with anything: "unknown" is not an identity, and two untyped
    things are not one thing. Each untyped record stays on its own.

    When more than one record could receive a gap-filling field, the fold
    targets the first matching record in document order. Document order is
    the only deterministic signal available in this slice: nothing here knows
    which record is the page's primary entity, so on a page whose @graph opens
    with a BreadcrumbList the og:title lands on the breadcrumb. That is a
    known limit of this slice, not a claim about picking the right record."""
    records: list[Record] = []

    for item in jsonld:
        records.append(_record_from(item, "jsonld"))

    # Microdata, microformats and RDFa each name a subject and its fields, so
    # all three fold the same way. The order they are written in here is their
    # precedence.
    #
    # A reader folds only into what earlier readers found, and each of those
    # records takes at most one item from it: the same product described in
    # two vocabularies is one product, but three products in one vocabulary
    # are three, and folding them all onto the first spliced a related
    # product's SKU and price onto the main one.
    for source, items in (
        ("microdata", microdata),
        ("microformats", microformats),
        ("rdfa", rdfa),
    ):
        candidates = list(records)
        for item in items:
            record = _record_from(item, source)
            target = _fold_target(candidates, record)
            if target is None:
                records.append(record)
                continue
            candidates = [record for record in candidates if record is not target]
            for key, value in record.fields.items():
                target.fields.setdefault(key, value)

    # Dublin Core, OpenGraph, the Twitter card and HTML's own metadata names
    # describe the document. None of them declares a type, so none of them can
    # fold by type: each fills the first record on the page, in the order
    # written here. It is what settles ``og:title`` against ``twitter:title``,
    # which strip to the same key and used to be decided by whichever tag the
    # author typed first, and what puts ``<meta name="description">`` behind
    # ``og:description``, which on most pages is the same sentence said with
    # less behind it.
    about_the_document = (
        ("dublincore", dublincore),
        ("opengraph", opengraph),
        ("twitter", twitter),
        ("html", htmlmeta),
    )
    if any(found for _, found in about_the_document):
        target = records[0] if records else Record()
        for source, found in about_the_document:
            # ``declared``, not a second ``value``: the fold above binds
            # ``value`` to a ``Field`` and this loop binds it to the raw text
            # the page declared. One name for two types is how a reader, and a
            # checker, both end up believing the wrong one.
            for key, declared in found.items():
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
    record = Record(type=types[0] if types else None, types=types)
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
    if "@value" in value:
        return _json(value["@value"], depth + 1)
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
    """Render one declared scalar as text, or None when it carries nothing.

    A null carries nothing, and neither does a string that is empty or all
    whitespace. A boolean carries "true" or "false", spelt the way the page
    declared it and not the way Python repr()s it."""
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
