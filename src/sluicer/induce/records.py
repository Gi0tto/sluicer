"""Turning one repeated shape into the records it describes.

A page that declares nothing has not told us what its fields are called, so we
do not invent names for them. A field is named by where it sits in the shape and
what class it carries, which is exactly as much as the page said, and every one
of them is marked as induced so a caller never mistakes it for a declaration.

Some parts carry two facts rather than one, and both are kept. An anchor is the
clearest case: ``<a href="/p0">Product name 0</a>`` is a name *and* a link, and
returning only the address loses the product's name on the commonest listing
shape on the web. An image is the same, with its alt text and its src. The
convention is that the text takes the slot's own name and the address takes that
name with the attribute appended -- ``a.more`` and ``a.more@href``, ``img.photo``
and ``img.photo@src`` -- so the two are visibly one slot, and a caller reading a
record never has to guess which name belongs to which.
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


# The text of an image is the text its author wrote for the people who cannot
# see it. Every other element's text is the text inside it.
_TEXT_ATTRIBUTE = {"img": "alt"}


def _text(element: HtmlElement) -> str:
    attribute = _TEXT_ATTRIBUTE.get(str(element.tag))
    if attribute:
        return " ".join((element.get(attribute) or "").split())
    return " ".join((element.text_content() or "").split())


def _facts(element: HtmlElement) -> list[tuple[str, str]]:
    """The facts one part carries, each with the suffix its name takes."""
    facts = []
    text = _text(element)
    if text:
        facts.append(("", text))
    address = address_of(element)
    if address:
        facts.append(("@" + str(ADDRESS[str(element.tag)]), address))
    return facts


def records_from(group: list[HtmlElement]) -> list[Record]:
    """Return one record per member of ``group``."""
    records: list[Record] = []
    for member in group:
        record = Record(type=None)
        for position, part in enumerate(member.iter()):
            if part is member or not isinstance(part.tag, str):
                continue
            name = _name(part, position)
            for suffix, value in _facts(part):
                record.fields.setdefault(
                    name + suffix, Field(value=value, source="induced")
                )
        if record.fields:
            records.append(record)
    return records
