"""Fold the readers' findings into records that remember their source.

Folding happens only across readers: when the same entity is described in
both JSON-LD and microdata, fields from the lower-precedence reader fill
gaps in the higher-precedence one. Within a single reader, two entries with
the same @type are two distinct things and remain separate records.

This slice extracts scalar values only; complex-typed fields (objects and
lists, such as JSON-LD's offers or image) are not carried into records."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    """One extracted value and the reader that produced it."""

    value: str
    source: str


@dataclass
class Record:
    """A set of fields describing one thing on the page."""

    type: str | None = None
    fields: dict[str, Field] = field(default_factory=dict)


def merge(
    jsonld: list[dict],
    microdata: list[dict],
    opengraph: dict,
) -> list[Record]:
    """Merge reader output. Earlier sources win; every field keeps its source.

    When several records share a @type, gap-filling from lower-precedence
    readers targets the first record of that type. This is a deliberate choice
    for the common page shape where one primary entity may be described in
    multiple ways, and secondary mentions (such as breadcrumb schemas) should
    not receive fields intended for the primary one."""
    records: list[Record] = []
    by_type: dict[str | None, Record] = {}

    for item in jsonld:
        record = _record_from(item, "jsonld")
        records.append(record)
        by_type.setdefault(record.type, record)

    for item in microdata:
        record = _record_from(item, "microdata")
        target = by_type.get(record.type)
        if target is None:
            records.append(record)
            by_type.setdefault(record.type, record)
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


def _record_from(item: dict, source: str) -> Record:
    record = Record(type=item.get("@type"))
    for key, value in item.items():
        if key.startswith("@"):
            continue
        if isinstance(value, (dict, list)):
            continue
        record.fields[key] = Field(value=str(value), source=source)
    return record
