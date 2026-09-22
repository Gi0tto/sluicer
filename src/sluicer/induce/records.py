"""Turning one repeated shape into the records it describes.

A page that declares nothing has not told us what its fields are called, so we
do not invent names for them. A field is named by where it sits in the shape and
what class it carries, which is exactly as much as the page said, and every one
of them is marked as induced so a caller never mistakes it for a declaration.
"""

from __future__ import annotations

from lxml.html import HtmlElement

from sluicer.declared.merge import Field, Record

# Which attribute carries the address, per tag. Named without an underscore
# because the ranking in ``groups`` asks the same question -- an element that
# points somewhere carries something, whether or not it also carries text --
# and one table is the only way the two can never disagree.
ADDRESS = {"a": "href", "img": "src", "link": "href", "source": "src"}


def address_of(element: HtmlElement) -> str | None:
    """Return the address ``element`` points at, or None when it points nowhere."""
    if not isinstance(element.tag, str):
        return None
    attribute = ADDRESS.get(element.tag)
    if not attribute:
        return None
    value = element.get(attribute)
    return value.strip() if value else None


def _name(element: HtmlElement, position: int) -> str:
    classes = sorted((element.get("class") or "").split())[:1]
    tag = element.tag if isinstance(element.tag, str) else "node"
    return f"{tag}.{classes[0]}" if classes else f"{tag}{position}"


def _value(element: HtmlElement) -> str:
    address = address_of(element)
    if address:
        return address
    return " ".join((element.text_content() or "").split())


def records_from(group: list[HtmlElement]) -> list[Record]:
    """Return one record per member of ``group``."""
    records: list[Record] = []
    for member in group:
        record = Record(type=None)
        for position, part in enumerate(member.iter()):
            if part is member or not isinstance(part.tag, str):
                continue
            value = _value(part)
            if not value:
                continue
            name = _name(part, position)
            record.fields.setdefault(name, Field(value=value, source="induced"))
        if record.fields:
            records.append(record)
    return records
