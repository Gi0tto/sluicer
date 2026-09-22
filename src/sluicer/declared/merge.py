"""Fold the readers' findings into records that remember their source."""

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
    """Merge reader output. Earlier sources win; every field keeps its source."""
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
